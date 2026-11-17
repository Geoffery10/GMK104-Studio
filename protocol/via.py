"""Independent, narrowly scoped VIA buffer client for the observed GMK104.

No reset, EEPROM erase, bootloader, lighting, macro or firmware commands.
Keymap words and buffer offsets use big-endian byte order.
"""
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import select
import uuid

from .gmk104 import Device, ProtocolError, default_backup_dir

ROWS, COLS, LAYERS = 8, 15, 4
MAP_SIZE = ROWS * COLS * LAYERS * 2
DESCRIPTOR = bytes.fromhex(
    "0660ff0961a1010962150026ff009520750881020963150026ff00952075089102c0"
)
# The observed firmware reports 0x00ff, not a stock QMK protocol version.
PROTOCOL_VERSION = 0x00FF


def discover_devices(root=Path("/sys/class/hidraw"), devroot=Path("/dev")):
    devices = []
    for entry in sorted(root.glob("hidraw*")):
        device = entry / "device"
        try:
            properties = dict(line.split("=", 1) for line in
                              (device / "uevent").read_text().splitlines() if "=" in line)
            if properties.get("HID_ID", "").upper() != "0003:0000320F:00005055":
                continue
            if (device / "report_descriptor").read_bytes() != DESCRIPTOR:
                continue
            if not any((p / "bInterfaceNumber").exists() and
                       (p / "bInterfaceNumber").read_text().strip() == "01"
                       for p in device.resolve().parents):
                continue
            devices.append(Device(devroot / entry.name, device.resolve()))
        except (OSError, ValueError):
            continue
    return devices


class HidrawTransport(AbstractContextManager):
    def __init__(self, device, timeout=3.0):
        self.device, self.timeout, self.fd = device, timeout, None

    def __enter__(self):
        if self.device not in discover_devices():
            raise ProtocolError("VIA device identity changed; refusing to open")
        self.fd = os.open(self.device.path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        return self

    def exchange(self, packet):
        if len(packet) != 32 or packet[0] not in (1, 0x11, 0x12, 0x13):
            raise ValueError("Only protocol, layer-count and keymap-buffer commands allowed")
        if packet[0] in (0x12, 0x13):
            offset, size = int.from_bytes(packet[1:3], "big"), packet[3]
            if not 1 <= size <= 28 or offset + size > MAP_SIZE:
                raise ValueError("Keymap buffer request outside supported bounds")
            if packet[0] == 0x13 and (size != 2 or offset % 2):
                raise ValueError("Only aligned two-byte keymap writes allowed")
        if not select.select([], [self.fd], [], self.timeout)[1]:
            raise TimeoutError("VIA write timeout; no retry")
        # hidraw requires a leading zero report ID for this unnumbered interface.
        if os.write(self.fd, b"\0" + packet) != 33:
            raise ProtocolError("Short VIA write; stopped without retry")
        if not select.select([self.fd], [], [], self.timeout)[0]:
            raise TimeoutError("VIA reply timeout; no retry")
        reply = os.read(self.fd, 32)
        if len(reply) != 32 or reply[0] != packet[0]:
            raise ProtocolError("Unexpected VIA reply; stopped without retry")
        return reply

    def __exit__(self, *args):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def request(transport, command, data=b""):
    if len(data) > 31:
        raise ValueError("VIA payload too large")
    packet = (bytes([command]) + data).ljust(32, b"\0")
    reply = transport.exchange(packet)
    if len(reply) != 32 or reply[0] != command:
        raise ProtocolError("Unexpected VIA response; no retry")
    return reply


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    version: int = PROTOCOL_VERSION

    def __post_init__(self):
        if not isinstance(self.data, bytes) or len(self.data) != MAP_SIZE:
            raise ValueError("Expected four complete 8 × 15 keymap layers")
        if self.version != PROTOCOL_VERSION:
            raise ValueError("Unsupported GMK104 VIA firmware")

    def keycode(self, layer, row, col):
        offset = key_offset(layer, row, col)
        return int.from_bytes(self.data[offset:offset + 2], "big")


def key_offset(layer, row, col):
    if not (0 <= layer < LAYERS and 0 <= row < ROWS and 0 <= col < COLS):
        raise ValueError("Key outside the supported matrix")
    return ((layer * ROWS + row) * COLS + col) * 2


def read_keymap(transport):
    version = int.from_bytes(request(transport, 1)[1:3], "big")
    if version != PROTOCOL_VERSION:
        raise ProtocolError(f"Unsupported VIA version 0x{version:04X}; no writes allowed")
    if request(transport, 0x11)[1] != LAYERS:
        raise ProtocolError("Unsupported layer count; no writes allowed")
    result = bytearray()
    for offset in range(0, MAP_SIZE, 28):
        size = min(28, MAP_SIZE - offset)
        header = offset.to_bytes(2, "big") + bytes([size])
        reply = request(transport, 0x12, header)
        if reply[1:4] != header:
            raise ProtocolError("Mismatched keymap-buffer reply; no retry")
        result.extend(reply[4:4 + size])
    return Snapshot(bytes(result), version)


def backup_keymap(snapshot, directory, device):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = datetime.now(timezone.utc)
    path = directory / f"keymap-{now.strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex[:8]}.json"
    record = {
        "format": "gmk104-studio-keymap", "schema_version": 1,
        "captured_at": now.isoformat(), "vid": "320f", "pid": "5055",
        "interface": 1, "matrix": [LAYERS, ROWS, COLS],
        "protocol_version": snapshot.version, "hidraw": str(device.path),
        "sysfs": str(device.sysfs), "keymap_hex": snapshot.data.hex(),
        "sha256": hashlib.sha256(snapshot.data).hexdigest(),
        "note": "Keymap only; not firmware, macros, lighting or screen settings.",
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return path


def load_backup(path):
    with Path(path).open() as stream:
        content = stream.read(16385)
    if len(content) > 16384:
        raise ValueError("Keymap backup is too large")
    record = json.loads(content)
    if (not isinstance(record, dict)
            or record.get("format") != "gmk104-studio-keymap" or record.get("schema_version") != 1
            or record.get("vid") != "320f" or record.get("pid") != "5055"
            or record.get("interface") != 1 or record.get("matrix") != [LAYERS, ROWS, COLS]):
        raise ValueError("Not a supported GMK104 Studio keymap backup")
    data = bytes.fromhex(record["keymap_hex"])
    if hashlib.sha256(data).hexdigest() != record.get("sha256"):
        raise ValueError("Backup checksum mismatch")
    return Snapshot(data, record["protocol_version"])


def baseline_path(directory):
    return Path(directory) / "baseline" / "keymap.json"


def ensure_baseline(snapshot, directory, device):
    """Atomically preserve the first observed map, never replacing an existing one.

    This is a local fallback, NOT a claim that the firmware is factory-default.
    A corrupt baseline blocks further operations rather than being overwritten.
    """
    path = baseline_path(directory)
    if not path.exists():
        # Publish a fully flushed file with an exclusive hard link. A crash
        # cannot leave a partially written baseline at the well-known path.
        temporary = backup_keymap(snapshot, path.parent, device)
        try:
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass  # Another reader won; validate and preserve its baseline.
        finally:
            temporary.unlink()
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    load_backup(path)
    return path


def _write_word(transport, offset, word):
    if offset % 2 or not 0 <= offset <= MAP_SIZE - 2 or len(word) != 2:
        raise ValueError("Only aligned, in-range two-byte keymap writes allowed")
    payload = offset.to_bytes(2, "big") + b"\x02" + word
    reply = request(transport, 0x13, payload)
    if reply[1:4] != payload[:3]:
        raise ProtocolError("Invalid keymap-write acknowledgment; no retry")


def apply_keymap(transport, original, desired, directory, device):
    """Check for external edits, back up, write changed words once, verify all.

    Failure may leave a partial keymap. Never retry or automatically roll back.
    """
    if not isinstance(original, Snapshot) or not isinstance(desired, Snapshot):
        raise ValueError("Apply requires complete validated keymap snapshots")
    current = read_keymap(transport)
    if current != original:
        raise ProtocolError("Keyboard changed since Read. Read again before applying.")
    ensure_baseline(current, directory, device)
    path = backup_keymap(current, directory, device)
    try:
        for offset in range(0, MAP_SIZE, 2):
            if current.data[offset:offset + 2] != desired.data[offset:offset + 2]:
                _write_word(transport, offset, desired.data[offset:offset + 2])
        if read_keymap(transport) != desired:
            raise ProtocolError("Full keymap verification failed")
    except Exception as error:
        raise ProtocolError(f"{error}. Keymap may be partially changed. Backup: {path}") from error
    return path


def confirm_unchanged_write(transport, directory, device):
    """Explicit hardware test: one unchanged word at base-layer A, then full read."""
    before = read_keymap(transport)
    path = backup_keymap(before, directory, device)
    offset = key_offset(0, 3, 1)
    _write_word(transport, offset, before.data[offset:offset + 2])
    if read_keymap(transport) != before:
        raise ProtocolError(f"Unchanged-write verification failed. Stop. Backup: {path}")
    return path
