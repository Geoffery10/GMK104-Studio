#!/usr/bin/env python3
"""Build a self-contained x86_64 AppImage. Run on Ubuntu 22.04 for release builds."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request

import PySide6
from gmk104_app import __version__

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
TOOL_URL = "https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
TOOL_SHA256 = "ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"


def run(args, **kwargs):
    subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def main():
    if sys.platform != "linux" or platform.machine() != "x86_64":
        raise SystemExit("v1.0 AppImage builds support Linux x86_64 only.")
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    arguments = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir",
        "--name", "gmk104-studio", "--distpath", BUILD / "bundle",
        "--workpath", BUILD / "pyinstaller", "--specpath", BUILD,
        "--collect-data", "gmk104_app", "--hidden-import", "PySide6.QtSvg",
        "--copy-metadata", "Pillow", "--copy-metadata", "PySide6",
        "--copy-metadata", "PySide6_Essentials", "--copy-metadata", "shiboken6",
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtWebEngineWidgets",
        "--exclude-module", "PySide6.QtQml", "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PyQt6", "--exclude-module", "PyQt5",
        "--exclude-module", "tkinter",
    ]
    # Explicit binary collection makes PyInstaller resolve Wayland plugin
    # dependencies rather than just copying unscanned plugin files.
    plugins = Path(PySide6.__file__).parent / "Qt/plugins"
    for group in ("platforms", "wayland-decoration-client", "wayland-graphics-integration-client",
                  "wayland-shell-integration", "xcbglintegrations", "egldeviceintegrations"):
        for library in sorted((plugins / group).glob("*.so")):
            arguments.extend(["--add-binary", f"{library}:PySide6/Qt/plugins/{group}"])
    run(arguments + [ROOT / "launch-studio.py"], cwd=ROOT)
    appdir = BUILD / "GMK104-Studio.AppDir"
    if appdir.exists():
        shutil.rmtree(appdir)  # Only this script's generated staging directory.
    (appdir / "usr/lib").mkdir(parents=True)
    shutil.copytree(BUILD / "bundle/gmk104-studio", appdir / "usr/lib/gmk104-studio")
    shutil.copyfile(ROOT / "packaging/AppRun", appdir / "AppRun")
    (appdir / "AppRun").chmod(0o755)
    (appdir / "usr/bin").mkdir()
    (appdir / "usr/bin/gmk104-studio").symlink_to("../../AppRun")
    desktop = "io.github.Geoffery10.GMK104LinuxImageUploader.desktop"
    shutil.copyfile(ROOT / "packaging" / desktop, appdir / desktop)
    shutil.copyfile(ROOT / "gmk104_app/assets/gmk104-studio.svg", appdir / "gmk104-studio.svg")
    (appdir / ".DirIcon").symlink_to("gmk104-studio.svg")
    metadata = appdir / "usr/share/metainfo"
    metadata.mkdir(parents=True)
    shutil.copyfile(ROOT / "packaging/io.github.Geoffery10.GMK104LinuxImageUploader.metainfo.xml",
                    metadata / "io.github.Geoffery10.GMK104LinuxImageUploader.metainfo.xml")
    share = appdir / "usr/share/gmk104-studio"
    share.mkdir(parents=True)
    for filename in ("LICENSE", "SAFETY.md", "THIRD_PARTY_NOTICES.md", "70-gmk104.rules"):
        shutil.copyfile(ROOT / filename, share / filename)
    packages = {}
    for name in ("Pillow", "PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "pyinstaller"):
        distribution = importlib.metadata.distribution(name)
        packages[name] = distribution.version
        # Preserve dependency-provided license/notice files in addition to
        # metadata bundled by PyInstaller.
        for item in distribution.files or ():
            if any(word in str(item).lower() for word in ("license", "copying", "notice")):
                if Path(item).is_absolute() or ".." in Path(item).parts:
                    continue
                source = Path(distribution.locate_file(item))
                if source.is_file():
                    destination = share / "licenses" / name / str(item)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
    manifest = {"application": __version__, "python": sys.version, "packages": packages}
    (share / "build-info.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # The packaged UI must open with no display or keyboard writes.
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               APPIMAGELAUNCHER_DISABLE="1",
               XDG_DATA_HOME=str(BUILD / "smoke-data"), XDG_CACHE_HOME=str(BUILD / "smoke-cache"),
               XDG_CONFIG_HOME=str(BUILD / "smoke-config"))
    run([appdir / "AppRun", "--version"], env=env)
    run([appdir / "AppRun", "--smoke-test", ROOT / "tests/artwork/04-red-blue-500ms.gif"],
        env=env, timeout=30)
    tool = BUILD / "appimagetool-1.9.1-x86_64.AppImage"
    if not tool.exists():
        urllib.request.urlretrieve(TOOL_URL, tool)
    if hashlib.sha256(tool.read_bytes()).hexdigest() != TOOL_SHA256:
        raise SystemExit("appimagetool checksum mismatch; refusing to execute.")
    tool.chmod(0o755)
    output = DIST / f"GMK104-Studio-{__version__}-x86_64.AppImage"
    with tempfile.TemporaryDirectory(prefix="appimagetool-", dir=BUILD) as directory:
        run([tool, "--appimage-extract"], cwd=directory, stdout=subprocess.DEVNULL)
        run([Path(directory) / "squashfs-root/AppRun", "--no-appstream", appdir, output],
            env=dict(os.environ, ARCH="x86_64", VERSION=__version__))
    output.chmod(0o755)
    run([output, "--appimage-extract-and-run", "--version"], env=env, timeout=30)
    run([output, "--appimage-extract-and-run", "--smoke-test", ROOT / "tests/artwork/04-red-blue-500ms.gif"],
        env=env, timeout=60)
    shutil.copyfile(ROOT / "70-gmk104.rules", DIST / "70-gmk104.rules")
    shutil.copyfile(share / "build-info.json", DIST / "build-info.json")
    artifacts = [output, DIST / "70-gmk104.rules", DIST / "build-info.json"]
    (DIST / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in artifacts))
    print(f"Built {output}")


if __name__ == "__main__":
    main()
