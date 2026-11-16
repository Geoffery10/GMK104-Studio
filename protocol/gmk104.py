#!/usr/bin/env python3
"""Experimental native GMK104 uploader. Offline by default; Custom1 only."""
import argparse
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import sys
import time
import uuid

from PIL import Image, ImageOps, ImageSequence

WIDTH, HEIGHT = 240, 135
PIXEL_BYTES = WIDTH * HEIGHT * 2
BLOCK_SIZE = 65536
# Exact descriptor of the observed vendor interface, not a keyboard interface.
SCREEN_DESCRIPTOR = bytes.fromhex(
    "061cff0992a101850419002aff00150026ff007508953f9100"
    "19002aff00750895078100c0"
)


class ProtocolError(RuntimeError):
    pass


def report(command, length=0, offset=0, payload=b""):
    if not (0 <= command <= 255 and 0 <= length <= 56
            and 0 <= offset < 2**24 and len(payload) == length):
        raise ValueError("Invalid command, length, offset, or payload")
    result = bytearray(64)
    result[0] = 4
    result[3] = command
    result[4] = length
    result[5:8] = offset.to_bytes(3, "little")
    result[8:8 + length] = payload
    result[1:3] = sum(result[3:]).to_bytes(2, "little")
    return bytes(result)


def fit_frame(image):
    rgba = ImageOps.contain(image.convert("RGBA"), (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    result = Image.new("RGB", (WIDTH, HEIGHT), "black")
    result.paste(rgba, ((WIDTH - rgba.width) // 2, (HEIGHT - rgba.height) // 2), rgba)
    return result


def rgb565(image):
    result = bytearray()
    for r, g, b in zip(*[iter(image.convert("RGB").tobytes())] * 3):
        result.extend((((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)).to_bytes(2, "big"))
    return bytes(result)


def load_frames(path):
    frames, durations = [], []
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) > 2:
            raise ValueError("Prototype supports only 1 or 2 frames (tested range)")
        for frame in ImageSequence.Iterator(image):
            frames.append(rgb565(fit_frame(frame)))
            durations.append(frame.info.get("duration", 1000))
    return frames, durations


def frame_blob(frames):
    if not 1 <= len(frames) <= 2 or any(len(p) != PIXEL_BYTES for p in frames):
        raise ValueError("Expected 1 or 2 frames, each containing 64,800 bytes")
    return b"".join(p + bytes(BLOCK_SIZE - PIXEL_BYTES) for p in frames) + bytes(BLOCK_SIZE)


def settings_report(template, count, interval):
    if (len(template) != 64 or template[0] != 4 or template[3:5] != b"\x06\x30"
            or count not in (1, 2) or not 500 <= interval <= 1000):
        raise ValueError("Invalid settings template, frame count, or interval (500–1000 ms)")
    result = bytearray(template)
    result[42] = count
    result[51:53] = interval.to_bytes(2, "little")
    result[1:3] = sum(result[3:]).to_bytes(2, "little")
    return bytes(result)


def load_capture_reports(path):
    result = []
    for packet in json.loads(Path(path).read_text()):
        layers = packet["_source"]["layers"]
        usb = layers["usb"]
        if usb["usb.endpoint_address"] != "0x05" or usb["usb.urb_type"] != "'S'":
            continue
        if (layers["frame"]["frame.encap_type"] != "115"
                or usb.get("usb.bus_id") is None):
            raise ValueError("Unsupported capture format")
        raw = bytes.fromhex(layers["frame_raw"][0])
        data = raw[64:64 + int(usb["usb.data_len"])]
        if (len(data) != 64 or data[0] != 4
                or int.from_bytes(data[1:3], "little") != sum(data[3:])):
            raise ValueError("Capture contains an invalid report/checksum")
        result.append(data)
    return result


def capture_settings(reports):
    matches = [r for r in reports if r[3:5] == b"\x06\x30"]
    if len(matches) != 1:
        raise ValueError("Expected exactly one settings report in capture")
    return matches[0]


def upload_reports(frames, template, interval):
    blob = frame_blob(frames)
    settings = settings_report(template, len(frames), interval)
    yield report(1)
    yield settings
    yield report(2)
    yield report(0x23)
    yield report(1)
    for offset in range(0, len(blob), 56):
        payload = blob[offset:offset + 56]
        yield report(0x21, len(payload), offset, payload)
    yield report(2)


def send_reports(transport, reports, progress=None):
    for index, packet in enumerate(reports):
        if transport.write(packet) != len(packet):
            raise ProtocolError("Short write; stopped without retry")
        reply = transport.read()
        if reply != packet[:8]:
            raise ProtocolError(f"Unexpected acknowledgment at report {index}; stopped without retry")
        if progress:
            progress(index + 1)


@dataclass(frozen=True)
class SettingsSnapshot:
    payload: bytes
    exchanges: tuple
    captured_at: str

    @property
    def report(self):
        return report(6, 48, 0, self.payload)


def read_current_settings(transport):
    """Only the observed command-05 reads; no begin/write/erase commands."""
    exchanges = []

    def read_chunk(offset, length):
        # Unlike writes, a read's length field describes requested bytes.
        request = report(5, length, offset, bytes(length))
        if transport.write(request) != 64:
            raise ProtocolError("Short settings-read request; no retry")
        reply = transport.read()
        # Read replies echo only ID/checksum/command, then carry up to 4
        # bytes of data at offset 4. They are NOT normal header-echo ACKs.
        if len(reply) != 8 or reply[:4] != request[:4]:
            raise ProtocolError("Invalid settings-read reply; refusing to upload")
        exchanges.append((request, reply))
        return reply[4:4 + length]

    selector = read_chunk(0, 1)[0]
    if selector != 0:
        raise ProtocolError(f"Unsupported settings profile {selector}; no configuration written")
    payload = b"".join(read_chunk(offset, 4) for offset in range(0, 48, 4))
    if payload[0] != selector or payload == bytes(48):
        raise ProtocolError("Inconsistent or empty settings record; refusing to upload")
    return SettingsSnapshot(payload, tuple(exchanges), datetime.now(timezone.utc).isoformat())


def default_backup_dir():
    data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    return data / "GMK104" / "GMK104 Studio" / "backups"


def backup_settings(snapshot, directory, device):
    """Persist a private, exclusive raw backup before configuration writes."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"settings-{timestamp}-{uuid.uuid4().hex[:8]}.json"
    data = {
        "schema_version": 1,
        "captured_at": snapshot.captured_at,
        "device": {"vid": "320f", "pid": "5055", "interface": 3,
                   "hidraw": str(device.path), "sysfs": str(device.sysfs)},
        "settings_hex": snapshot.payload.hex(),
        "write_report_hex": snapshot.report.hex(),
        "exchanges": [{"request": request.hex(), "reply": reply.hex()}
                      for request, reply in snapshot.exchanges],
        "note": "Settings only, not a backup of animation or firmware. No automatic restore.",
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return path


def upload_with_backup(transport, frames, interval, directory, device, progress=None):
    # Reject invalid artwork/timing before even sending read requests.
    frame_blob(frames)
    if not 500 <= interval <= 1000:
        raise ValueError("Interval must be 500–1000 ms")
    snapshot = read_current_settings(transport)
    reports = list(upload_reports(frames, snapshot.report, interval))
    path = backup_settings(snapshot, directory, device)
    send_reports(transport, reports, progress)
    return path


@dataclass(frozen=True)
class Device:
    path: Path
    sysfs: Path


def discover_devices(root=Path("/sys/class/hidraw"), devroot=Path("/dev")):
    result = []
    for entry in sorted(root.glob("hidraw*")):
        device = entry / "device"
        try:
            properties = dict(line.split("=", 1) for line in (device / "uevent").read_text().splitlines() if "=" in line)
            if properties.get("HID_ID", "").upper() != "0003:0000320F:00005055":
                continue
            if (device / "report_descriptor").read_bytes() != SCREEN_DESCRIPTOR:
                continue
            # Require the observed USB interface number as well as the descriptor.
            ancestors = device.resolve().parents
            if not any((p / "bInterfaceNumber").exists()
                       and (p / "bInterfaceNumber").read_text().strip() == "03" for p in ancestors):
                continue
            result.append(Device(devroot / entry.name, device.resolve()))
        except (OSError, ValueError):
            continue
    return result


class HidrawTransport(AbstractContextManager):
    def __init__(self, device, timeout=3.0):
        self.device, self.timeout, self.fd = device, timeout, None

    def __enter__(self):
        # Recheck identity immediately before opening; never select a device by name alone.
        matches = discover_devices()
        if self.device not in matches:
            raise ProtocolError("Device identity changed; refusing to open")
        self.fd = os.open(self.device.path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        return self

    def write(self, packet):
        if not select.select([], [self.fd], [], self.timeout)[1]:
            raise TimeoutError("USB write timeout; no retry")
        return os.write(self.fd, packet)

    def read(self):
        if not select.select([self.fd], [], [], self.timeout)[0]:
            raise TimeoutError("USB acknowledgment timeout; no retry")
        return os.read(self.fd, 64)

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, nargs="?")
    parser.add_argument("--settings-from", type=Path, help="Offline generation only: known-working Custom1 capture JSON")
    parser.add_argument("--interval", type=int, help="Global interval, 500–1000 ms; otherwise use equal GIF durations")
    parser.add_argument("--output", type=Path, help="Write offline 64-byte reports to a NEW binary file")
    parser.add_argument("--upload", action="store_true", help="EXPERIMENTAL: offer a confirmed live upload")
    parser.add_argument("--read-settings", action="store_true", help="Read and back up current settings only; no configuration writes")
    parser.add_argument("--backup-dir", type=Path, default=default_backup_dir(),
                        help="Directory for mandatory pre-upload settings backups")
    args = parser.parse_args(argv)
    if args.read_settings:
        if args.upload or args.image or args.output or args.settings_from or args.interval is not None:
            parser.error("--read-settings cannot be combined with image/upload/offline options")
        devices = discover_devices()
        if len(devices) != 1:
            raise ProtocolError(f"Expected exactly one screen interface; found {len(devices)}")
        with HidrawTransport(devices[0]) as transport:
            snapshot = read_current_settings(transport)
        path = backup_settings(snapshot, args.backup_dir, devices[0])
        print(f"Read 48 current settings bytes via 13 observed read requests.\nBackup: {path}")
        print("No configuration, image, or clock writes were sent.")
        return 0
    if args.image is None:
        parser.error("Provide an image, or use --read-settings")
    if args.upload and (args.settings_from or args.output):
        parser.error("Live uploads read settings from the device; --settings-from/--output are offline-only")
    frames, durations = load_frames(args.image)
    if args.interval is None and len(set(durations)) != 1:
        parser.error("Keyboard uses one global interval; specify --interval for unequal frame durations")
    interval = args.interval if args.interval is not None else durations[0]
    if not 500 <= interval <= 1000:
        parser.error("Interval must be 500–1000 ms")
    blob = frame_blob(frames)
    total = (len(blob) + 55) // 56 + 6
    reports = None
    if not args.upload:
        if args.settings_from is None:
            parser.error("Offline generation requires --settings-from")
        template = capture_settings(load_capture_reports(args.settings_from))
        reports = list(upload_reports(frames, template, interval))
    print(f"Custom1: {len(frames)} frame(s), {WIDTH}x{HEIGHT}, {interval} ms")
    print(f"{total} upload reports; {len(blob):,} image-stream bytes")
    print("Experimental: zero padding/extra black block passed the two-frame 500-ms hardware test.")
    if args.upload:
        print("Live settings will be read and backed up first. Only frame count and interval are changed.")
    else:
        print("Offline plan uses captured settings/time; it is not used for live uploads.")
    if args.output:
        with args.output.open("xb") as stream:
            stream.write(b"".join(reports))
        print(f"Offline reports saved to {args.output}")
    if not args.upload:
        print("OFFLINE ONLY: no device was opened or written.")
        return 0
    devices = discover_devices()
    if len(devices) != 1:
        raise ProtocolError(f"Expected exactly one matching screen interface; found {len(devices)}")
    print(f"Target: {devices[0].path}. This replaces Custom1 using current device settings.")
    print("Close Image Custom Tool before continuing. Keep the keyboard connected.")
    if not sys.stdin.isatty() or input("Type UPLOAD GMK104 to authorize this experimental write: ") != "UPLOAD GMK104":
        raise ProtocolError("Upload not authorized; no device opened")
    start = time.monotonic()
    def progress(n):
        if n % 100 == 0 or n == total:
            print(f"\rAcknowledged {n}/{total} reports", end="", flush=True)
    with HidrawTransport(devices[0]) as transport:
        path = upload_with_backup(transport, frames, interval, args.backup_dir, devices[0], progress)
    print(f"\nTransfer acknowledged in {time.monotonic() - start:.1f}s.\nSettings backup: {path}\nCheck the physical screen.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, ProtocolError, KeyboardInterrupt) as error:
        print(f"\nStopped: {error}. No automatic retry or recovery commands sent.", file=sys.stderr)
        sys.exit(1)
