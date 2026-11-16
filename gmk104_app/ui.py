import os
import argparse
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

from PIL import Image
from PySide6.QtCore import QLockFile, QSettings, QSize, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QSlider, QSpinBox, QSplitter,
    QVBoxLayout, QWidget,
)

from protocol import gmk104 as protocol
from .core import Adjustments, History, external_editor_environment, load_animation, render_frames, save_animation
from . import __version__

STYLE = """
QWidget { background: #111111; color: #f6f2e9; font-size: 13px; }
QMainWindow { background: #111111; }
QFrame#card { background: #1b1b1b; border: 1px solid #494949; border-left: 4px solid #ed1935; border-radius: 2px; }
QLabel { background: transparent; }
QLabel#title { font-size: 30px; font-weight: 900; font-style: italic; color: #fffaf0; }
QLabel#muted { color: #b8b5ae; }
QLabel#eyebrow { color: #ff3a50; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
QPushButton { background: #242424; border: 1px solid #68645e; border-radius: 2px; padding: 9px 14px; font-weight: 600; }
QPushButton:hover { background: #393939; border-color: #fffaf0; }
QPushButton:disabled { color: #747474; background: #1c1c1c; border-color: #343434; }
QPushButton#primary { background: #ed1935; color: #ffffff; font-weight: 800; border: 1px solid #ff566b; }
QPushButton#primary:hover { background: #ff304a; border-color: #ffffff; }
QPushButton#primary:disabled { background: #54232a; color: #b38d92; border-color: #54232a; }
QListWidget { background: #171717; border: 1px solid #454545; border-radius: 2px; padding: 5px; outline: none; }
QListWidget::item { padding: 9px; border-bottom: 1px solid #323232; }
QListWidget::item:selected { background: #b8142c; color: #fff; }
QComboBox, QSpinBox { background: #242424; border: 1px solid #68645e; border-radius: 2px; padding: 7px; }
QComboBox QAbstractItemView { background: #242424; selection-background-color: #b8142c; }
QSlider::groove:horizontal { background: #494949; height: 5px; }
QSlider::handle:horizontal { background: #fffaf0; border: 2px solid #ed1935; width: 12px; margin: -5px 0; }
QProgressBar { border: 1px solid #68645e; border-radius: 2px; background: #202020; text-align: center; min-height: 22px; }
QProgressBar::chunk { background: #bc1730; }
QToolTip { background: #242424; color: #fff; border: 1px solid #ed1935; }
QSplitter::handle { background: #494949; width: 1px; }
"""


def qimage(image):
    rgb = image.convert("RGB")
    return QImage(rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()


class Preview(QWidget):
    def __init__(self):
        super().__init__()
        self.image = None
        self.setMinimumSize(420, 250)
        self.setSizePolicy(self.sizePolicy().Policy.Expanding, self.sizePolicy().Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0b0b0b"))
        width = min(self.width() - 48, (self.height() - 48) * 16 / 9)
        height = width * 9 / 16
        x, y = (self.width() - width) / 2, (self.height() - height) / 2
        from PySide6.QtCore import QRectF
        rect = QRectF(x, y, width, height)
        painter.fillRect(rect, Qt.GlobalColor.black)
        if self.image is not None:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(rect, self.image)
        else:
            painter.setPen(QColor("#b8b5ae"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                             "Drop a GIF or image here\n\n240 × 135  /  black canvas  /  no stretching")
        painter.setPen(QColor("#ed1935"))
        painter.drawRect(rect)


class UploadWorker(QThread):
    progress = Signal(int, int)
    succeeded = Signal(str)
    failed = Signal(str)
    stage = Signal(str)

    def __init__(self, frames, interval, device, backup_dir=None):
        super().__init__()
        self.frames, self.interval, self.device = frames, interval, device
        self.backup_dir = backup_dir if backup_dir is not None else protocol.default_backup_dir()

    def run(self):
        try:
            self.stage.emit("Reading current keyboard settings and saving a backup…")
            total = ((len(self.frames) + 1) * protocol.BLOCK_SIZE + 55) // 56 + 6 if self.frames else 0
            def update(count):
                if count % 25 == 0 or count == total:
                    self.progress.emit(count, total)
            with protocol.HidrawTransport(self.device) as transport:
                if self.frames is None:
                    snapshot = protocol.read_current_settings(transport)
                    path = protocol.backup_settings(snapshot, self.backup_dir, self.device)
                else:
                    path = protocol.upload_with_backup(
                        transport, [protocol.rgb565(frame) for frame in self.frames],
                        self.interval, self.backup_dir, self.device, update)
            self.succeeded.emit(str(path))
        except Exception as error:
            self.failed.emit(str(error))


class Window(QMainWindow):
    def __init__(self, history, cache, settings):
        super().__init__()
        self.history, self.cache, self.settings = history, cache, settings
        self.frames, self.rendered = [], []
        self.source = None
        self.display_name = ""
        self.editor_file = None
        self.worker = None
        self.pending_file = None
        self.device = None
        self.frame_index = 0
        self.setWindowTitle(f"GMK104 Studio {__version__}")
        self.resize(1180, 850)
        self.setMinimumSize(980, 720)
        self.setAcceptDrops(True)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(15)
        heading = QHBoxLayout()
        titles = QVBoxLayout()
        eyebrow = QLabel("TAKE OVER YOUR SCREEN  /  LINUX NATIVE")
        eyebrow.setObjectName("eyebrow")
        titles.addWidget(eyebrow)
        title = QLabel("GMK104 / STUDIO")
        title.setObjectName("title")
        titles.addWidget(title)
        heading.addLayout(titles)
        heading.addStretch()
        self.connection = QLabel("Checking keyboard…")
        heading.addWidget(self.connection)
        self.refresh_button = self.button("Refresh device", self.check_device)
        heading.addWidget(self.refresh_button)
        outer.addLayout(heading)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)
        sidebar = QWidget()
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(0, 0, 14, 0)
        side.addWidget(self.button("＋ Open GIF or image", self.open_file, primary=True))
        side.addWidget(self.muted("RECENT SUCCESSFUL UPLOADS"))
        self.recents = QListWidget()
        self.recents.setIconSize(QSize(96, 54))
        self.recents.itemActivated.connect(self.open_recent)
        side.addWidget(self.recents, 1)
        side.addWidget(self.muted("Last 10 uploads, stored locally.\nDouble-click to reopen. Originals stay untouched."))
        side.addWidget(self.button("Open history folder", self.open_history_folder))
        self.backup_button = self.button("Back up keyboard settings", self.backup_only)
        self.backup_button.setToolTip("Read and save current settings. No image, clock, or configuration writes.")
        side.addWidget(self.backup_button)
        splitter.addWidget(sidebar)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        self.info = self.muted("Open artwork to begin • GIF, PNG, JPEG, WebP")
        body.addWidget(self.info)
        self.preview = Preview()
        body.addWidget(self.preview, 1)
        playback = QHBoxLayout()
        self.play_button = self.button("Pause preview", self.toggle_play)
        playback.addWidget(self.play_button)
        self.frame_select = QComboBox()
        self.frame_select.currentIndexChanged.connect(self.select_frame)
        playback.addWidget(self.frame_select)
        playback.addStretch()
        playback.addWidget(QLabel("Frame interval"))
        self.interval = QSpinBox()
        self.interval.setRange(500, 1000)
        self.interval.setSingleStep(10)
        self.interval.setSuffix(" ms")
        self.interval.setValue(1000)
        self.interval.editingFinished.connect(self.normalize_interval)
        self.interval.valueChanged.connect(self.interval_changed)
        playback.addWidget(self.interval)
        body.addLayout(playback)
        card = QFrame()
        card.setObjectName("card")
        controls = QVBoxLayout(card)
        controls.setContentsMargins(14, 12, 14, 12)
        transforms = QHBoxLayout()
        transforms.addWidget(QLabel("Rotate"))
        self.rotation = QComboBox()
        self.rotation.addItems(["0°", "90°", "180°", "270°"])
        self.rotation.currentIndexChanged.connect(self.render)
        transforms.addWidget(self.rotation)
        self.flip_h = QCheckBox("Flip horizontal")
        self.flip_v = QCheckBox("Flip vertical")
        for control in (self.flip_h, self.flip_v):
            control.toggled.connect(self.render)
            transforms.addWidget(control)
        transforms.addStretch()
        transforms.addWidget(self.button("Reset edits", self.reset_edits))
        controls.addLayout(transforms)
        brightness = QHBoxLayout()
        brightness.addWidget(QLabel("Brightness"))
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(25, 200)
        self.brightness.setValue(100)
        self.brightness.valueChanged.connect(self.render)
        brightness.addWidget(self.brightness)
        self.brightness_label = QLabel("100%")
        brightness.addWidget(self.brightness_label)
        controls.addLayout(brightness)
        actions = QHBoxLayout()
        self.duplicate_button = self.button("Duplicate frame", self.duplicate_frame)
        self.remove_button = self.button("Remove frame", self.remove_frame)
        actions.addWidget(self.duplicate_button)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        self.editor_button = self.button("Open in editor…", self.open_editor)
        self.reload_button = self.button("Reload editor copy", self.reload_editor)
        actions.addWidget(self.editor_button)
        actions.addWidget(self.reload_button)
        controls.addLayout(actions)
        body.addWidget(card)
        body.addWidget(self.muted("Black transparency • Proportional fit + black padding • Custom1 • 1–2 frames"))
        bottom = QHBoxLayout()
        self.export_button = self.button("Export prepared GIF…", self.export)
        bottom.addWidget(self.export_button)
        self.editor_settings_button = self.button("Choose editor…", self.choose_editor)
        bottom.addWidget(self.editor_settings_button)
        bottom.addStretch()
        self.upload_button = self.button("Upload to keyboard", self.upload, primary=True)
        bottom.addWidget(self.upload_button)
        body.addLayout(bottom)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        body.addWidget(self.progress)
        self.status = QLabel("Ready. Upload reads and backs up current settings first.")
        self.status.setWordWrap(True)
        body.addWidget(self.status)
        splitter.addWidget(content)
        splitter.setSizes([270, 860])
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.timer.start(self.interval.value())
        self.device_timer = QTimer(self)
        self.device_timer.timeout.connect(self.check_device)
        self.device_timer.start(10000)
        open_action = QAction("Open", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        self.addAction(open_action)
        self.populate_history()
        self.check_device()
        self.update_enabled()

    def button(self, text, callback, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        return button

    def muted(self, text):
        label = QLabel(text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        return label

    def busy(self):
        return self.worker is not None and self.worker.isRunning()

    def error(self, message):
        QMessageBox.warning(self, "GMK104 Studio", str(message))

    def update_enabled(self):
        ready = bool(self.frames) and not self.busy()
        for widget in (self.export_button, self.editor_button, self.play_button, self.frame_select,
                       self.rotation, self.flip_h, self.flip_v, self.brightness, self.interval):
            widget.setEnabled(ready)
        self.upload_button.setEnabled(ready and self.device is not None)
        self.backup_button.setEnabled(not self.busy() and self.device is not None)
        self.duplicate_button.setEnabled(ready and len(self.frames) == 1)
        self.remove_button.setEnabled(ready and len(self.frames) == 2)
        self.reload_button.setEnabled(not self.busy() and self.editor_file is not None)
        self.refresh_button.setEnabled(not self.busy())

    def check_device(self):
        if self.busy():
            return
        devices = protocol.discover_devices()
        self.device = devices[0] if len(devices) == 1 else None
        if self.device:
            writable = os.access(self.device.path, os.R_OK | os.W_OK)
            self.connection.setText("● GMK104 connected" if writable else "● GMK104 needs permissions")
            self.connection.setStyleSheet("color: #a7d7b0;" if writable else "color: #efc17c;")
            if not writable:
                self.device = None
        else:
            self.connection.setText("○ Keyboard not found" if not devices else "Multiple keyboards found")
            self.connection.setStyleSheet("color: #b8b5ae;")
        self.update_enabled()

    def open_file(self):
        if self.busy():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open artwork", self.settings.value("last_folder", ""),
                                             "Images (*.gif *.png *.jpg *.jpeg *.webp *.bmp)")
        if path:
            self.load(path)

    def load(self, path):
        if self.busy():
            return
        try:
            frames, durations = load_animation(path)
            self.frames, self.source = frames, Path(path)
            self.display_name = self.source.name
            self.editor_file = None
            self.settings.setValue("last_folder", str(self.source.parent))
            self.frame_index = 0
            self.reset_edits()
            duration = max(500, min(1000, round(durations[0] / 10) * 10))
            self.interval.setValue(duration)
            self.render()
            warning = (" Timing normalized: keyboard uses one 500–1000 ms interval."
                       if len(set(durations)) > 1 or any(d != duration for d in durations) else "")
            self.status.setText("Loaded. Edits apply to all frames; original file is never changed." + warning)
        except Exception as error:
            self.error(error)

    def reset_edits(self):
        self.rotation.setCurrentIndex(0)
        self.flip_h.setChecked(False)
        self.flip_v.setChecked(False)
        self.brightness.setValue(100)
        self.render()

    def render(self, *args):
        self.brightness_label.setText(f"{self.brightness.value()}%")
        if not self.frames:
            return
        self.rendered = render_frames(self.frames, Adjustments(
            rotation=self.rotation.currentIndex() * 90,
            flip_horizontal=self.flip_h.isChecked(), flip_vertical=self.flip_v.isChecked(),
            brightness=self.brightness.value() / 100))
        self.frame_index = min(self.frame_index, len(self.rendered) - 1)
        self.frame_select.blockSignals(True)
        self.frame_select.clear()
        self.frame_select.addItems([f"Frame {i + 1}" for i in range(len(self.frames))])
        self.frame_select.setCurrentIndex(self.frame_index)
        self.frame_select.blockSignals(False)
        self.info.setText(f"{self.display_name}  •  {len(self.frames)} frame(s)  •  "
                          f"source {self.frames[0].width} × {self.frames[0].height} → 240 × 135")
        self.show_frame()
        self.update_enabled()

    def show_frame(self):
        if self.rendered:
            self.preview.image = qimage(self.rendered[self.frame_index])
            self.preview.update()

    def select_frame(self, index):
        if 0 <= index < len(self.rendered):
            self.frame_index = index
            self.timer.stop()
            self.play_button.setText("Play preview")
            self.show_frame()

    def toggle_play(self):
        if self.timer.isActive():
            self.timer.stop()
            self.play_button.setText("Play preview")
        else:
            self.timer.start(self.interval.value())
            self.play_button.setText("Pause preview")

    def advance(self):
        if self.rendered:
            self.frame_index = (self.frame_index + 1) % len(self.rendered)
            self.frame_select.blockSignals(True)
            self.frame_select.setCurrentIndex(self.frame_index)
            self.frame_select.blockSignals(False)
            self.show_frame()

    def interval_changed(self, value):
        self.timer.setInterval(value)

    def normalize_interval(self):
        self.interval.setValue(round(self.interval.value() / 10) * 10)

    def duplicate_frame(self):
        if len(self.frames) == 1 and not self.busy():
            self.frames.append(self.frames[0].copy())
            self.render()

    def remove_frame(self):
        if len(self.frames) == 2 and not self.busy():
            self.frames.pop(self.frame_index)
            self.frame_index = 0
            self.render()

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export prepared artwork",
                                             str(self.source.with_name(self.source.stem + "-keyboard.gif")), "GIF (*.gif)")
        if path:
            try:
                self.normalize_interval()
                save_animation(path, self.rendered, self.interval.value())
                self.status.setText(f"Exported {path}")
            except Exception as error:
                self.error(error)

    def choose_editor(self):
        command, ok = QInputDialog.getText(
            self, "External image editor",
            "Editor executable and optional arguments (no shell).\nExamples: krita, gimp, /usr/bin/pinta\n"
            "An editable GIF copy will be appended to this command.",
            text=self.settings.value("editor", "krita"))
        if ok and command.strip():
            try:
                parts = shlex.split(command)
                if not parts or not shutil.which(parts[0]):
                    raise ValueError("Editor executable not found. Enter an installed editor.")
                self.settings.setValue("editor", command)
                return True
            except ValueError as error:
                self.error(error)
        return False

    def open_editor(self):
        if not self.settings.value("editor") and not self.choose_editor():
            return
        try:
            self.normalize_interval()
            path = self.cache / f"editor-{uuid.uuid4().hex}.gif"
            save_animation(path, self.rendered, self.interval.value())
            command = shlex.split(self.settings.value("editor"))
            if not command or not shutil.which(command[0]):
                raise ValueError("Editor not found. Use Choose editor to change it.")
            subprocess.Popen(command + [str(path)], start_new_session=True,
                             env=external_editor_environment())
            self.editor_file = path
            self.status.setText("Editing a separate GIF copy. Save it in your editor, then click Reload editor copy.")
            self.update_enabled()
        except Exception as error:
            self.error(error)

    def reload_editor(self):
        path = self.editor_file
        name = self.display_name
        if path:
            self.load(path)
            self.editor_file = path
            self.display_name = name
            self.render()
            self.update_enabled()

    def populate_history(self):
        self.recents.clear()
        for item in self.history.items():
            path = self.history.root / item["file"]
            entry = QListWidgetItem(f"{item['name']}\n{item.get('interval', '?')} ms")
            entry.setData(Qt.ItemDataRole.UserRole, str(path))
            entry.setData(Qt.ItemDataRole.UserRole + 1, item["name"])
            entry.setToolTip(f"Uploaded {item.get('uploaded', '')}\n{path}")
            try:
                with Image.open(path) as image:
                    entry.setIcon(QIcon(QPixmap.fromImage(qimage(image))))
            except OSError:
                pass
            self.recents.addItem(entry)

    def open_recent(self, item):
        self.load(item.data(Qt.ItemDataRole.UserRole))
        if not self.busy():
            self.display_name = item.data(Qt.ItemDataRole.UserRole + 1)
            self.render()

    def open_history_folder(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.history.root)))

    def upload(self):
        self.check_device()
        if not self.rendered or self.device is None or self.busy():
            return
        try:
            self.normalize_interval()
            self.pending_file = self.cache / f"upload-{uuid.uuid4().hex}.gif"
            self.pending_name = self.display_name
            self.pending_interval = self.interval.value()
            save_animation(self.pending_file, self.rendered, self.pending_interval)
            # Upload exactly the same quantized GIF which will enter history.
            frames, _ = load_animation(self.pending_file)
            self.worker = UploadWorker([frame.convert("RGB") for frame in frames],
                                       self.pending_interval, self.device, self.history.root.parent / "backups")
            self.worker.progress.connect(self.upload_progress)
            self.worker.succeeded.connect(self.upload_success)
            self.worker.failed.connect(self.upload_failed)
            self.worker.stage.connect(self.status.setText)
            self.worker.finished.connect(self.upload_finished)
            self.progress.setValue(0)
            self.status.setText("Uploading… keep the keyboard connected.")
            self.worker.start()
            self.update_enabled()
        except Exception as error:
            self.error(error)

    def upload_progress(self, count, total):
        self.progress.setValue(round(count / total * 100))
        self.status.setText(f"Uploading • {count:,} / {total:,} reports acknowledged")

    def backup_only(self):
        self.check_device()
        if self.device is None or self.busy():
            return
        self.pending_file = None
        self.worker = UploadWorker(None, 0, self.device, self.history.root.parent / "backups")
        self.worker.stage.connect(self.status.setText)
        self.worker.succeeded.connect(self.upload_success)
        self.worker.failed.connect(self.upload_failed)
        self.worker.finished.connect(self.upload_finished)
        self.progress.setValue(0)
        self.worker.start()
        self.update_enabled()

    def upload_success(self, backup_path=""):
        self.progress.setValue(100)
        if self.pending_file is None:
            self.status.setText(f"Settings read and backed up: {backup_path}. No configuration writes sent.")
            return
        try:
            self.history.record(self.pending_file, self.pending_name, self.pending_interval)
            self.populate_history()
            self.status.setText(f"Upload acknowledged and saved to recent uploads. Settings backup: {backup_path}")
        except OSError as error:
            self.status.setText(f"Upload succeeded, but history could not be saved: {error}")

    def upload_failed(self, message):
        self.status.setText(f"Operation stopped: {message}. No automatic retry was sent.")
        self.error("Operation stopped without retry.\n\n" + message +
                   "\n\nIf needed, restore artwork using the known-working Windows tool.")

    def upload_finished(self):
        if self.pending_file is not None:
            self.pending_file.unlink(missing_ok=True)
            self.pending_file = None
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        self.check_device()

    def dragEnterEvent(self, event):
        if not self.busy() and event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.load(event.mimeData().urls()[0].toLocalFile())

    def closeEvent(self, event):
        if self.busy():
            self.error("Wait for the upload to finish before closing.")
            event.ignore()
        else:
            event.accept()


def main():
    parser = argparse.ArgumentParser(description="GMK104 Studio: native Linux keyboard artwork uploader")
    parser.add_argument("image", nargs="?", help="Optional image or GIF to open")
    parser.add_argument("--version", action="version", version=f"GMK104 Studio {__version__}")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setOrganizationName("GMK104")
    app.setApplicationName("GMK104 Studio")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "assets/gmk104-studio.svg")))
    data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))
    cache = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation))
    data.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data / "studio.lock"))
    if not lock.tryLock(0):
        QMessageBox.information(None, "GMK104 Studio", "Another instance is already running.")
        return 1
    window = Window(History(data / "uploads"), cache, QSettings())
    window.show()
    if args.image:
        window.load(args.image)
    if args.smoke_test:
        print(f"GMK104 Studio {__version__}: GUI smoke test ({app.platformName()}); no uploads.", flush=True)
        QTimer.singleShot(300, app.quit)
    return app.exec()
