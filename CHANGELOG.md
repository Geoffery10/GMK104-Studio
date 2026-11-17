# Changelog

## v2.0 — 2026-11-17

- Screen and Keymap tabs; four layers and a physical keyboard view.
- Original basic-key catalogue, search, local staged edits and all-layer diff.
- Explicit Apply confirmation, external-change detection, mandatory full private
  backups, changed-word-only writes and full read-back verification.
- Stage/restore checked GMK104 Studio keymap backups; preserve unknown keycodes.
- Automatically load current keys on tab entry/reconnect without discarding edits.
- Keep the first saved keymap as a permanent baseline, with review-before-apply
  restoration; it is not claimed to be factory defaults.
- Bundle a complete keymap JSON captured from two matching current-device reads;
  Restore defaults stages this fixed snapshot, independent of local backups.
- Name the backlight/LCD switches and mute/volume keycodes; add the missing
  editable knob press at matrix `5,7` with a physical display/knob illustration.
  Rotation is shown as native volume control, with remapping still unverified.
- Fix the Review and apply button's accidental Qt mnemonic and simplify the tab
  name to Keymap. Identify existing Fn-layer code families with interpretation
  notes and unresolved-code counts; retain `0xFFFF` as unknown, never normalize it.
- Keep the keyboard preview size stable when Restore defaults changes status text;
  preview scaling now follows window resizing rather than message height.
- Present GMK104 Studio as a screen editor and keymapper across the README,
  launchers and package descriptions. Document the full keymapping workflow and
  limitations, with reproducible offline screenshots of both tabs.
- Add consistent tab/content insets, control spacing, padded search fields and
  lists, and keyboard-canvas breathing room. Compact Keymap windows scroll
  without overlapping the preview; refresh README screenshots.
- Remove horizontal scrolling from recent uploads, elide long names with full
  tooltips, and inset the Screen editor's filename, playback and export rows.
- Strict VIA interface/descriptor/version checks; no reset or firmware commands.
- One unchanged-word hardware write verified against all 960 keymap bytes;
  the keyboard owner also reports successful changed keymap writes.
  Restoration and power-cycle persistence remain unverified.

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
