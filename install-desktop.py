#!/usr/bin/env python3
"""Install a per-user launcher pointing to this checkout. No sudo needed."""
import os
from pathlib import Path
import shutil
import sys

root = Path(__file__).resolve().parent
data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
apps = data / "applications"
icons = data / "icons/hicolor/scalable/apps"
apps.mkdir(parents=True, exist_ok=True)
icons.mkdir(parents=True, exist_ok=True)
shutil.copyfile(root / "gmk104_app/assets/gmk104-studio.svg", icons / "gmk104-studio.svg")


def quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%") + '"'


entry = apps / "io.local.gmk104-studio.desktop"
entry.write_text(
    "[Desktop Entry]\nType=Application\nName=GMK104 Studio\n"
    "Comment=Native Linux keyboard screen editing and keymapping\n"
    f"Exec={quote(sys.executable)} {quote(root / 'launch-studio.py')} %f\n"
    "Icon=gmk104-studio\nTerminal=false\nCategories=Graphics;2DGraphics;RasterGraphics;\n"
    "MimeType=image/gif;image/png;image/jpeg;image/webp;\n"
    "StartupNotify=true\n"
)
print(f"Installed {entry}\nKeep the source folder at {root}.")
