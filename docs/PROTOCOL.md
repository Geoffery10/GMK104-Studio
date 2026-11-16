# Observed GMK104 screen protocol

These are observations, not an official or complete manufacturer specification.
See [SAFETY.md](../SAFETY.md). Do not apply this protocol to other devices.

## Device and transport

- USB VID/PID `320f:5055`, interface 3.
- HID usage page `ff1c`, usage `92`, report ID `04`.
- Interrupt OUT endpoint `05`, 64-byte output reports.
- Interrupt IN endpoint `83`, 8-byte input reports.
- Exact descriptor matching is required by the Linux backend.

## Host report

| Offset | Length | Meaning |
| --- | --- | --- |
| 0 | 1 | Report ID `04` |
| 1 | 2 | Little-endian sum of bytes 3–63 |
| 3 | 1 | Command |
| 4 | 1 | Command-specific length |
| 5 | 3 | Command-specific offset |
| 8 | 0–56 | Write payload |

For ordinary writes, the reply must exactly equal the first eight request bytes.
No retries occur after bad replies, short writes, or timeouts.

## Current settings readback

Startup traffic confirmed:

1. Command `05`, requested length 1, offset 0 → settings selector 0.
2. Twelve `05` reads, length 4, offsets 0, 4, …, 44 → 48 settings bytes.

Read requests carry zero-filled payload bytes; their length specifies requested
data, not supplied data. Replies echo request bytes 0–3 and return up to four data
bytes at offsets 4–7. They are **not** write acknowledgments. Their echoed checksum
does not verify returned data; do not interpret it as a payload checksum.

Only observed selector 0 is implemented. The original software has generic code
suggesting other records/offsets, but these are not validated on this keyboard.
Unsupported selectors abort rather than guessing.

The returned 48 bytes become the payload of command `06`, length 48, offset 0.
Before uploading, the current record and exact read transcript are saved to an
exclusive, private (0600), timestamped JSON file. File and directory are flushed
before configuration writes start. Backup failure aborts the upload.

In that reconstructed 64-byte report:

- Byte 42: animation frame count.
- Bytes 51–52: little-endian global frame interval in milliseconds.
- Bytes 43–49: clock/calendar-related data, copied from the fresh read.

Only count, interval, and checksum change. No PC-clock synchronization is
requested. The write still rewrites the freshly read RTC bytes, so this is
preservation, not proof of a firmware operation that never touches the clock.
There is no fallback to a captured settings template for live uploads.

## Upload sequence

Following readback/backup:

1. `01`
2. `06` with modified live settings
3. `02`
4. `23`
5. `01`
6. Repeated `21` reports containing image-stream chunks
7. `02`

Exact meanings of `01`, `02`, and `23` are not fully established; only this
observed sequence is used. No firmware commands are implemented.

## Image stream

- 240 × 135, row-major, left-to-right/top-to-bottom.
- Big-endian RGB565; red `f800`, green `07e0`, blue `001f`, white `ffff`.
- Each frame occupies a 65,536-byte block: 64,800 image bytes plus 736 padding.
- The observed tool sends an additional black block after the visible frames.
- Command `21`: length up to 56 in byte 4; 24-bit little-endian byte offset in
  bytes 5–7; data begins at byte 8.

The Windows tool transmitted unexpected JSON fragments in its padding. These
were not reproduced; native zero-filled padding plus the extra black block
was hardware-tested successfully.

One-frame transfers: 131,072 data bytes, 2,341 data reports, 2,347 upload reports.
Two-frame transfers: 196,608 data bytes, 3,511 data reports, 3,517 upload reports.
Readback adds 13 separate requests before those upload reports.

## Evidence and validation

Controlled single-red, single-blue, two-frame 1000/500-ms, and corner-marker
uploads established encoding, timing, frame stride, and exact raster ordering.
The corner image matched the source RGB565 bytes exactly. Native readback,
backup creation, and visible two-frame playback through the complete
read-backup-upload path were confirmed on hardware.

`tests/fixtures/uploads.json` contains sanitized command prefixes, counts,
lengths, and per-frame SHA-256 hashes from the controlled captures.
`tests/fixtures/readback.json` contains only settings read/write exchanges.
Raw keyboard-input captures, device paths, accidental buffer tails, personal
artwork, and vendor binaries are deliberately excluded.

## Unknowns

Other firmware, selectors, Custom modes, more than two frames, wider interval
ranges, interrupted-transfer recovery, firmware operations, and reading back
the current animation have not been validated. Settings backups alone do not
provide a guaranteed device-recovery mechanism.
