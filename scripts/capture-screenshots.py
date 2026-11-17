#!/usr/bin/env python3
"""Capture README screenshots of the actual UI, offline and without USB access."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from gmk104_app.core import History, save_animation
from gmk104_app.keymap import DEFAULT_KEYMAP
from gmk104_app.ui import STYLE, Window
from protocol import gmk104, via


def demo_artwork():
    """Original geometric artwork; no personal, vendor or game assets."""
    frames = []
    try:
        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 27)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 10)
    except OSError:
        title_font = small_font = ImageFont.load_default()
    for shift in (0, 7):
        image = Image.new("RGB", (240, 135), "#111111")
        draw = ImageDraw.Draw(image)
        for x in range(-60 + shift, 300, 28):
            draw.line((x, 0, x - 80, 135), fill="#252525", width=8)
        draw.rectangle((12, 12, 227, 122), outline="#ed1935", width=2)
        draw.rectangle((12, 12, 227, 31), fill="#ed1935")
        draw.text((23, 16), "SCREEN + KEYMAP", font=small_font, fill="white")
        draw.text((22, 44), "GMK104", font=title_font, fill="#fffaf0")
        draw.text((24, 82), "STUDIO / LINUX NATIVE", font=small_font, fill="#fffaf0")
        draw.rectangle((24, 107, 24 + 105 + shift, 110), fill="#ed1935")
        frames.append(image)
    return frames


def capture():
    output = ROOT / "docs" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    with tempfile.TemporaryDirectory(prefix="gmk104-screenshots-") as directory:
        root = Path(directory)
        # Guard both discovery AND transports: this helper must never open a
        # keyboard, even if autoload behavior changes in a future UI revision.
        with patch.object(gmk104, "discover_devices", return_value=[]), \
                patch.object(via, "discover_devices", return_value=[]), \
                patch.object(gmk104, "HidrawTransport", side_effect=AssertionError("USB access forbidden")), \
                patch.object(via, "HidrawTransport", side_effect=AssertionError("USB access forbidden")):
            window = Window(History(root / "uploads"), root / "cache",
                            QSettings(str(root / "preferences.ini"), QSettings.Format.IniFormat))
            try:
                window.resize(1280, 940)
                window.device_timer.stop()
                window.timer.stop()
                window.connection.setText("○ Offline documentation preview")
                window.connection.setStyleSheet("color: #b8b5ae;")
                artwork = root / "Studio demo.gif"
                save_animation(artwork, demo_artwork(), 500)
                window.load(artwork)
                window.timer.stop()
                window.status.setText("Offline demo artwork. No screen upload performed.")
                window.show()
                for _ in range(4):
                    app.processEvents()
                if not window.grab().save(str(output / "screen.png")):
                    raise OSError("Could not save Screen screenshot")

                panel = window.keymap
                window.tabs.setCurrentWidget(panel)
                panel.original = via.load_backup(DEFAULT_KEYMAP)
                panel.edited = bytearray(panel.original.data)
                panel.select_key(3, 0)  # Caps Lock: demonstrate one local edit.
                panel.search.setText("F13")
                panel.codes.setCurrentRow(0)
                panel.assign()
                panel.status.setText("Offline demo: bundled defaults with one staged example edit. Nothing sent to a keyboard.")
                for _ in range(4):
                    app.processEvents()
                if not window.grab().save(str(output / "keymap.png")):
                    raise OSError("Could not save Keymap screenshot")
            finally:
                # Avoid a discard-confirmation dialog for the local demo edit.
                window.keymap.original = window.keymap.edited = None
                window.close()
                window.deleteLater()
                app.processEvents()
    print(f"Saved {output / 'screen.png'} and {output / 'keymap.png'}; no keyboard accessed.")


if __name__ == "__main__":
    capture()
