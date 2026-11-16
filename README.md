<p align="center">
  <img src="gmk104_app/assets/gmk104-studio.svg" width="112" alt="GMK104 Studio icon">
</p>

<h1 align="center">GMK104 Studio</h1>
<p align="center">A native Linux image and GIF uploader for the ZUOYA GMK104.</p>
<p align="center">
  <a href="https://github.com/Geoffery10/GMK104-Linux-Image-Uploader/actions/workflows/ci.yml"><img src="https://github.com/Geoffery10/GMK104-Linux-Image-Uploader/actions/workflows/ci.yml/badge.svg" alt="Tests and AppImage build"></a>
  <a href="https://github.com/Geoffery10/GMK104-Linux-Image-Uploader/releases/latest"><img src="https://img.shields.io/github/v/release/Geoffery10/GMK104-Linux-Image-Uploader" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

No Wine. No vendor driver. A red, black, and off-white Qt interface that works
on Wayland and X11.

> **Use at your own risk.** This is independent, reverse-engineered software,
> not an official manufacturer tool. Geoffery10 and contributors provide it
> without warranty and accept no liability for damaged devices or lost data,
> to the extent permitted by law. Read [device safety](SAFETY.md) before uploading.

## What it does

- Upload images or **one-/two-frame GIFs** to the keyboard's Custom1 screen.
- Render transparency on **black**.
- Fit artwork proportionally: **pillarboxing/letterboxing, never stretching**.
- Preview animation; rotate, flip, adjust brightness, duplicate/remove frames,
  and export prepared GIFs.
- Open an editable copy in your preferred external editor, then reload it.
- Keep the **last 10 successful uploads** locally.
- Read and back up live keyboard settings before each upload. Preserve unknown
  settings and the current clock/date; abort if reading or saving the backup fails.

## Supported in v1.0

| Item | Support |
| --- | --- |
| Keyboard | ZUOYA GMK104, USB `320f:5055`, observed screen interface 3 |
| Connection | Wired USB |
| Screen | 240 × 135, Custom1 |
| Animation | 1–2 frames, one global 500–1000 ms interval |
| Linux desktop | Wayland or X11 |
| Download bundle | x86_64 AppImage; glibc-based Linux, Ubuntu 22.04 or newer baseline |
| Windows / macOS | Not supported; the device backend is Linux-specific |

Longer animations are rejected, not silently truncated. Different firmware
revisions remain untested. This is a focused first release, not a replacement
for every function in the manufacturer's software.

## Quick start: AppImage

1. Download the `.AppImage`, `70-gmk104.rules`, and `SHA256SUMS` from
   [Releases](https://github.com/Geoffery10/GMK104-Linux-Image-Uploader/releases/latest).
2. Check the AppImage against its entry in `SHA256SUMS`:

   ```bash
   sha256sum GMK104-Studio-1.0.0-x86_64.AppImage
   ```

3. Install the keyboard permission rule once:

   ```bash
   sudo install -m 644 70-gmk104.rules /etc/udev/rules.d/70-gmk104.rules
   sudo udevadm control --reload-rules
   ```

4. Unplug/reconnect the keyboard in **wired mode**. Close the Windows tool.
5. Run the AppImage as your regular user:

   ```bash
   chmod +x GMK104-Studio-1.0.0-x86_64.AppImage
   ./GMK104-Studio-1.0.0-x86_64.AppImage
   ```

**Never run the app as root.** The AppImage includes Python/Qt, but cannot
install system USB permissions for you. A local active desktop session is
required by the `uaccess` rule.

Open your image, check the preview and interval, then click **Upload to keyboard**.
That button starts immediately; there is no extra warning dialog.
Keep the keyboard connected until the upload finishes.

### Troubleshooting

- **Keyboard not found:** use wired mode, check `lsusb` for `320f:5055`, and close
  any other keyboard configuration app.
- **Needs permissions:** install the rule above and reconnect. Don't use broad
  `chmod` rules on all HID devices.
- **FUSE error:** try `./GMK104-Studio-1.0.0-x86_64.AppImage --appimage-extract-and-run`,
  or extract with `--appimage-extract` and run `squashfs-root/AppRun`.
- **Qt platform error:** try `QT_QPA_PLATFORM=wayland ./GMK104-Studio-1.0.0-x86_64.AppImage`
  or `QT_QPA_PLATFORM=xcb ...` on an X11 session.
- **Unsupported settings profile/descriptor:** stop and open an issue. Do not
  bypass the identity checks.

## Run from source

Python 3.11+ is required. Use a virtual environment; don't modify system Python.

```bash
git clone https://github.com/Geoffery10/GMK104-Linux-Image-Uploader.git
cd GMK104-Linux-Image-Uploader
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/gmk104-studio
```

The same udev setup above is required. To install a source-checkout application
menu entry:

```bash
.venv/bin/python install-desktop.py
```

Keep the checkout and its virtual environment in place afterward.

## Test artwork

Only our generated test GIFs are included—no personal or game artwork:

| Single red | Single blue | Red / blue animation | Corner markers |
| :---: | :---: | :---: | :---: |
| ![Red test](tests/artwork/01-red.gif) | ![Blue test](tests/artwork/02-blue.gif) | ![Two-frame test](tests/artwork/04-red-blue-500ms.gif) | ![Corner test](tests/artwork/05-corners.gif) |

## Local files and backups

Usually under:

- `~/.local/share/GMK104/GMK104 Studio/uploads/`: last 10 successful GIFs.
- `~/.local/share/GMK104/GMK104 Studio/backups/`: private settings backups;
  these are **not automatically pruned**.
- `~/.cache/GMK104/GMK104 Studio/`: editor working copies.
- `~/.config/GMK104/GMK104 Studio.conf`: editor/preferences.

XDG directory overrides are respected. **Open history folder** shows the actual
location. Backups contain settings and the read transcript, **not firmware or
the previous animation**. No automatic restore is implemented.

## Command line

After installing from source:

```bash
# Read/back up settings only; no configuration or image writes.
.venv/bin/gmk104-upload --read-settings

# Explicit confirmation required before uploading.
.venv/bin/gmk104-upload tests/artwork/04-red-blue-500ms.gif --interval 500 --upload
```

## Development and releases

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
```

All tests are offline; they never upload to a keyboard. Public regression
fixtures are sanitized summaries/settings exchanges, not raw USB captures.

See [contributing](CONTRIBUTING.md), [protocol notes](docs/PROTOCOL.md), and
[AppImage build/release instructions](docs/BUILDING.md).
CI tests pull requests and pushes; version tags build and publish release
AppImages with SHA-256 checksums.

## License

[MIT](LICENSE) for our code and original icon, with no warranty.
Bundled dependencies retain [their own licenses](THIRD_PARTY_NOTICES.md).
The Persona 5-inspired palette includes no game assets. No vendor executable
or proprietary firmware is distributed.
