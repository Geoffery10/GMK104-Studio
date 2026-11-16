#!/usr/bin/env python3
"""Generate minimal public regression evidence; never copy raw capture payload tails."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("capture_directory", type=Path)
parser.add_argument("output_directory", type=Path)
args = parser.parse_args()
args.output_directory.mkdir(parents=True, exist_ok=True)


def exchanges(path):
    pending, result = None, []
    for record in json.loads(path.read_text()):
        layers = record["_source"]["layers"]
        usb = layers["usb"]
        data = bytes.fromhex(layers["frame_raw"][0])[64:64 + int(usb["usb.data_len"])]
        if usb["usb.endpoint_address"] == "0x05" and usb["usb.urb_type"] == "'S'":
            pending = data
        if usb["usb.endpoint_address"] == "0x83" and usb["usb.urb_type"] == "'C'" and pending and data:
            result.append((pending, data))
            pending = None
    return result


def find(label):
    return next(p for p in args.capture_directory.glob(label + "-*.json")
                if not p.name.endswith(".metadata.json"))


uploads = []
for label in ("01-red", "02-blue", "03-red-blue-1000ms", "04-red-blue-500ms", "05-corners"):
    source = find(label)
    pairs = exchanges(source)
    reports = [request for request, reply in pairs]
    assert all(len(request) == 64 and reply == request[:8] for request, reply in pairs)
    assert all(int.from_bytes(r[1:3], "little") == sum(r[3:]) for r in reports)
    chunks = [r for r in reports if r[3] == 33]
    assert all(int.from_bytes(r[5:8], "little") == index * 56 for index, r in enumerate(chunks))
    blob = b"".join(r[8:8 + r[4]] for r in chunks)
    count = reports[1][42]
    uploads.append({
        "name": label, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "report_count": len(reports), "prefix": [r.hex() for r in reports[:5]],
        "suffix": reports[-1].hex(), "interval": int.from_bytes(reports[1][51:53], "little"),
        "stream_bytes": len(blob), "last_chunk_length": chunks[-1][4],
        "frame_sha256": [hashlib.sha256(blob[index * 65536:index * 65536 + 64800]).hexdigest()
                         for index in range(count)],
    })
(args.output_directory / "uploads.json").write_text(json.dumps(uploads, indent=2) + "\n")
source = find("06-startup")
# Only settings reads and the following settings write; exclude input reports,
# descriptors, device IDs, packet timestamps, and all image/buffer data.
pairs = [(a, b) for a, b in exchanges(source) if a[3] in (5, 6)]
readback = {
    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "exchanges": [{"request": a.hex(), "reply": b.hex()} for a, b in pairs],
}
(args.output_directory / "readback.json").write_text(json.dumps(readback, indent=2) + "\n")
print("Saved sanitized upload summaries and settings-only exchanges.")
