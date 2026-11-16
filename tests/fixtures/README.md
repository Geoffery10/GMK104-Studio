# Sanitized protocol regression evidence

`uploads.json` summarizes five controlled uploads: solid red, solid blue,
red/blue at 1000 ms, red/blue at 500 ms, and four colored corner markers.
It retains:

- Source-capture SHA-256 for provenance (raw captures are not distributed).
- The five setup reports and final report, counts, lengths, and timing.
- SHA-256 hashes of the exact visible RGB565 frames.

It deliberately omits image-packet buffer tails, keyboard input, USB descriptors,
system paths, and packet timestamps.

`readback.json` retains only the settings-read requests/replies and the subsequent
settings write from startup. Its clock bytes are historical test data and are
**never a live-upload fallback**.

These fixtures are protocol observations for offline tests, not firmware,
manufacturer software, or a complete packet capture. Fixtures and the generated
artwork are distributed under this project's MIT license.
