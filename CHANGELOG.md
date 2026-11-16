# Changelog

## v1.0 — 2026-11-15

First public release of GMK104 Studio.

- Native Linux HID uploads without Wine, with strict identity checks.
- Live settings readback and mandatory private settings backups.
- Hardware-tested one-/two-frame uploads, RGB565, 240x135, Custom1.
- Wayland/X11 Qt GUI with red/black/off-white styling and original icon.
- Black transparency, proportional fit, animation preview, basic editing/export.
- External-editor copies and history of the last 10 successful uploads.
- Offline protocol, readback, image, history, and GUI tests.
- x86_64 AppImage packaging, checksums, and GitHub Actions release automation.

Known limits: 1–2 frames, one 500–1000 ms interval, observed settings selector 0,
Linux only. See [SAFETY.md](SAFETY.md).
