# Building and releasing

## Local development

Use Linux x86_64 and Python 3.11+. The release builder uses Ubuntu 22.04 and
Python 3.12, providing a conservative glibc baseline. Building on a newer
distribution can raise the resulting bundle's minimum system requirements.

On Python 3.11, dependency metadata temporarily selects PySide6 below 6.12:
6.12.0 has an upstream singleton-refcount crash on that interpreter
(PYSIDE-3474). Python 3.12+ retains the normal `<7` range. Revisit the bound only
after corrected wheels pass the subprocess UI regression and full suite on 3.11.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[build]"
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/build-appimage.py
```

The script freezes Python/Pillow/PySide6 with PyInstaller, explicitly includes
Wayland and X11 plugins, assembles an AppDir with notices and the udev rule,
runs packaged version/GUI smoke tests, verifies the pinned appimagetool download,
and builds `dist/GMK104-Studio-2.0.0-x86_64.AppImage`.
It also writes `SHA256SUMS`, `70-gmk104.rules`, and `build-info.json`.

The build needs internet access for Python dependencies, appimagetool, and
AppImage runtime downloads. It does not need a keyboard or privileged USB access.
Building isn't bit-for-bit reproducible: dependency constraints and the upstream
AppImage runtime can change. Exact Python versions are recorded per release.

Required system libraries include Mesa/OpenGL/EGL, fontconfig, xkbcommon,
Wayland, and XCB. `.github/workflows/ci.yml` lists Ubuntu package dependencies.
Fontconfig and FreeType are intentionally taken from the host desktop, avoiding
an old bundled parser reading a newer system font configuration.
FUSE is not needed for the build: appimagetool is extracted before execution.

## CI/CD

Every pull request and main-branch push:

1. Runs all offline tests on Python 3.11 and 3.12.
2. Validates package version and desktop metadata.
3. Builds the x86_64 AppImage.
4. Starts the packaged GUI offscreen without uploading.
5. Uploads the AppImage, rule, manifest, and checksums as a workflow artifact.

A version tag (`v2.0` for application version `2.0.0`) runs the same checks and
then creates a GitHub Release with those files. Publishing has `contents: write`
only in its release job; ordinary tests/builds have read-only repository access.

## Release checklist

1. Update `pyproject.toml`, `gmk104_app/__init__.py`, AppStream metadata,
   `CHANGELOG.md`, and `docs/releases/<tag>.md`.
2. Run tests and review safety/known limits. Never add raw USB captures or
   personal/vendor artwork to a release.
3. Push and wait for main-branch CI to succeed.
4. Smoke-test the main-branch AppImage on the target desktop. Hardware testing
   is manual and opt-in; CI cannot establish USB device safety.
5. Create/push the release tag:

   ```bash
    git tag -a v2.0 -m "GMK104 Studio v2.0"
    git push origin v2.0
   ```

6. Check that the release workflow succeeded and the downloaded files match
   `SHA256SUMS`.

No signing key is configured. Checksums detect corruption, not publisher
identity independently of GitHub. GitHub-generated source archives are provided
alongside the binary. Qt and other bundled components retain their own licenses.
