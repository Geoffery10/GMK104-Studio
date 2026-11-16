# Third-party components

GMK104 Studio's own source code and icon are MIT-licensed. Bundled components
retain their own licenses; the AppImage is not entirely MIT-licensed.

- **Python**: Python Software Foundation License. https://www.python.org/psf/license/
- **Pillow**: HPND/PIL-style license. https://pillow.readthedocs.io/en/stable/about.html
- **PySide6, Shiboken, and Qt**: LGPLv3/GPL/commercial licensing, including
  third-party Qt components under their respective terms.
  https://doc.qt.io/qtforpython-6/licenses.html
  https://doc.qt.io/qt-6/licensing.html
- **PyInstaller bootloader**: GPL with the bootloader exception permitting
  redistribution of generated executables. https://pyinstaller.org/en/stable/license.html
- **AppImage runtime**: see https://github.com/AppImage/type2-runtime

The build includes dependency-provided license and notice files, metadata, and
exact Python package versions under `usr/share/gmk104-studio/` in the extracted
AppImage. Additional licenses may also reside with the libraries themselves.
The version manifest is separately attached to each release.

Qt is dynamically linked, not statically linked into this application. You can
extract the AppImage with `--appimage-extract`, inspect or replace bundled shared
libraries with ABI-compatible builds, and run the extracted `AppRun`. No license
term in this project restricts reverse engineering for debugging modifications
to LGPL components.

Corresponding upstream source for Qt/PySide/Shiboken is available through:

- https://download.qt.io/archive/qt/
- https://download.qt.io/official_releases/QtForPython/
- https://code.qt.io/cgit/pyside/pyside-setup.git/

Use the versions in the release's `build-info.json` to select matching sources.
Please report missing license material or unavailable corresponding source.

The Persona 5-inspired color palette uses no game artwork, trademarks as logos,
or other game assets. No vendor executable, proprietary firmware, personal
artwork, or raw USB keyboard-input captures are distributed.
