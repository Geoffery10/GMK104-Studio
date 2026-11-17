"""Read-first keymap editor. Edits remain local until explicitly applied."""
import os
from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, Qt, QThread, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGraphicsScene, QGraphicsView, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from protocol import via
from .keycodes import ASSIGNABLE, describe, explanation, is_identified, short_name
from .keymap_layout import CONTROL_NAMES, KEYS, KNOB_PRESS

DEFAULT_KEYMAP = Path(__file__).resolve().parent / "assets" / "gmk104-default-keymap.json"

KEY_STYLE = ("QPushButton { padding: 0; font-size: 11px; }"
             "QPushButton:checked { background: #641c28; border: 2px solid #fffaf0; }")


class KeyboardView(QGraphicsView):
    selected = Signal(int, int)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setMinimumHeight(245)
        self.setViewportMargins(8, 8, 8, 8)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.buttons = {}
        for key in KEYS:
            button = QPushButton()
            button.setStyleSheet(KEY_STYLE)
            button.setCheckable(True)
            button.setEnabled(False)
            button.setFixedSize(round(key.width * 52 - 3), round(key.height * 52 - 3))
            button.clicked.connect(lambda checked=False, r=key.row, c=key.col: self.selected.emit(r, c))
            proxy = self.scene().addWidget(button)
            proxy.setGeometry(QRectF(key.x * 52, key.y * 52,
                                    key.width * 52 - 3, key.height * 52 - 3))
            self.buttons[key.row, key.col] = button
        # The display is decorative: the two switches are on its left and the
        # knob's editable press is on its right, matching the physical hardware.
        self.scene().addRect(QRectF(20.25 * 52, 3, 1.5 * 52, 46),
                             QPen(QColor("#68645e")), QBrush(QColor("#0b0b0b")))
        label = self.scene().addText("LCD screen", QFont("Sans Serif", 9))
        label.setDefaultTextColor(QColor("#b8b5ae"))
        label.setPos(20.28 * 52, .25 * 52)
        label.setToolTip("Display preview illustration. Use the Screen tab to edit artwork.")
        self.rotation_label = self.scene().addText("− Vol +", QFont("Sans Serif", 8))
        self.rotation_label.document().setDocumentMargin(0)
        self.rotation_label.setDefaultTextColor(QColor("#b8b5ae"))
        self.rotation_label.setPos(22.05 * 52, 1.0 * 52)
        self.rotation_label.setToolTip(
            "Native knob rotation (from the GMK104 manual):\n"
            "Counter-clockwise: volume down. Clockwise: volume up.\n"
            "Rotation remapping is not verified; no encoder writes are sent.\n"
            "Click the knob above to edit its press mapping separately.")
        self.setSceneRect(0, 0, 23 * 52, 6.25 * 52)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def show_keymap(self, original, edited, layer, selected):
        for (row, col), button in self.buttons.items():
            button.setEnabled(edited is not None)
            style = KEY_STYLE
            if (row, col) == KNOB_PRESS:
                style += "QPushButton { border-radius: 24px; }"
            if edited is None:
                button.setText({(5, 4): "Light", (5, 6): "LCD", KNOB_PRESS: "Press"}.get(
                    (row, col), f"{row},{col}"))
                button.setToolTip(CONTROL_NAMES.get((row, col), f"Matrix {row},{col}"))
                button.setChecked(False)
                button.setStyleSheet(style)
                continue
            offset = via.key_offset(layer, row, col)
            code = int.from_bytes(edited[offset:offset + 2], "big")
            changed = original.data[offset:offset + 2] != edited[offset:offset + 2]
            button.setText(("Press\n" if (row, col) == KNOB_PRESS else "") + short_name(code))
            physical_name = CONTROL_NAMES.get((row, col))
            button.setToolTip((f"{physical_name}\n" if physical_name else "") +
                              f"Layer {layer}, matrix {row},{col}\n{describe(code)} · 0x{code:04X}" +
                              (f"\n{explanation(code)}" if explanation(code) else ""))
            button.setChecked(selected == (row, col))
            button.setStyleSheet(style + ("QPushButton { border: 2px solid #ff3a50; }" if changed else ""))


class KeymapWorker(QThread):
    succeeded = Signal(object, str)
    failed = Signal(str)

    def __init__(self, device, directory, original=None, desired=None):
        super().__init__()
        self.device, self.directory = device, directory
        self.original, self.desired = original, desired

    def run(self):
        try:
            with via.HidrawTransport(self.device) as transport:
                if self.desired is None:
                    result = via.read_keymap(transport)
                    via.ensure_baseline(result, self.directory, self.device)
                    path = via.backup_keymap(result, self.directory, self.device)
                else:
                    path = via.apply_keymap(transport, self.original, self.desired,
                                            self.directory, self.device)
                    result = self.desired
            self.succeeded.emit(result, str(path))
        except Exception as error:
            self.failed.emit(str(error))


class KeymapContent(QWidget):
    def heightForWidth(self, width):
        # Wrapped labels need their full height, but expandable lists may use
        # less than their preferred height before the entire page must scroll.
        layout = self.layout()
        return layout.minimumHeightForWidth(width) if layout is not None else -1


class KeymapPanel(QWidget):
    busy_changed = Signal()

    def __init__(self, directory, external_busy=lambda: False):
        super().__init__()
        self.directory = Path(directory)
        self.external_busy = external_busy
        self.original = self.edited = self.device = None
        self.worker = None
        self.selected = None
        self.active = False
        self._attempted_device = None
        self._automatic = False
        page = QVBoxLayout(self)
        page.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Reserve the gutter even when no scrolling is needed. Restoring a
        # shorter status message must not change the preview's available width.
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setEnabled(False)
        scrollbar.rangeChanged.connect(lambda minimum, maximum: scrollbar.setEnabled(maximum > minimum))
        page.addWidget(self.scroll_area)
        content = KeymapContent()
        self.scroll_area.setWidget(content)
        outer = QVBoxLayout(content)
        self.content_layout = outer
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self.read_button = QPushButton("Reload keyboard")
        self.read_button.setToolTip("Re-read current mappings and save a backup. Never writes key mappings.")
        self.read_button.clicked.connect(self.read)
        actions.addWidget(self.read_button)
        actions.addWidget(QLabel("Layer"))
        self.layer = QComboBox()
        self.layer.addItems(["0 · Base", "1 · Fn", "2", "3"])
        self.layer.currentIndexChanged.connect(self.refresh)
        actions.addWidget(self.layer)
        actions.addStretch()
        self.restore_button = QPushButton("Load backup…")
        self.restore_button.clicked.connect(self.restore)
        actions.addWidget(self.restore_button)
        self.defaults_button = QPushButton("Restore defaults")
        self.defaults_button.setToolTip("Stage the bundled keymap captured on 17 November 2026. Not manufacturer-certified factory defaults.")
        self.defaults_button.clicked.connect(self.restore_defaults)
        actions.addWidget(self.defaults_button)
        self.discard_button = QPushButton("Discard edits")
        self.discard_button.clicked.connect(self.discard)
        actions.addWidget(self.discard_button)
        self.apply_button = QPushButton("Review and apply…")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply)
        actions.addWidget(self.apply_button)
        outer.addLayout(actions)
        self.keyboard = KeyboardView()
        self.keyboard.selected.connect(self.select_key)
        outer.addWidget(self.keyboard)
        self.knob_info = QLabel("Knob: click to edit its press. Turning adjusts volume in firmware; rotation remapping is not yet verified.")
        self.knob_info.setWordWrap(True)
        outer.addWidget(self.knob_info)
        self.layer_info = QLabel()
        self.layer_info.setWordWrap(True)
        outer.addWidget(self.layer_info)
        lower = QHBoxLayout()
        lower.setSpacing(16)
        picker = QVBoxLayout()
        picker.setSpacing(10)
        self.selection = QLabel("Open this tab to load current keys, then select a key above.")
        picker.addWidget(self.selection)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search keys (e.g. Ctrl, F12, Numpad, MO)…")
        self.search.textChanged.connect(self.filter_codes)
        picker.addWidget(self.search)
        self.codes = QListWidget()
        self.codes.itemDoubleClicked.connect(self.assign)
        picker.addWidget(self.codes)
        self.assign_button = QPushButton("Assign selected keycode")
        self.assign_button.clicked.connect(self.assign)
        picker.addWidget(self.assign_button)
        lower.addLayout(picker, 1)
        changes = QVBoxLayout()
        changes.setSpacing(10)
        changes.addWidget(QLabel("Staged changes · all layers · nothing written yet"))
        self.changes = QListWidget()
        changes.addWidget(self.changes)
        lower.addLayout(changes, 1)
        outer.addLayout(lower, 2)
        self.status = QLabel("Keymapping · wired mode only. Current keys load automatically; no automatic keymap writes.\n"
                             "Unknown codes are preserved. Macros, knob rotation remapping and lighting settings are not supported.")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.baseline_info = QLabel("Restore defaults: bundled keymap captured on 17 November 2026, not certified factory defaults.")
        self.baseline_info.setWordWrap(True)
        outer.addWidget(self.baseline_info)
        self.filter_codes()
        self.refresh()
        self.scroll_viewport = self.scroll_area.viewport()
        self.scroll_viewport.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched is self.scroll_viewport and event.type() == QEvent.Type.Resize:
            self.resize_preview()
        return super().eventFilter(watched, event)

    def resize_preview(self):
        # Status/error messages and layer notes can wrap to different heights.
        # Keep them from resizing (and therefore zooming) the keyboard. Only
        # resizing the panel changes its preview allocation; the editor below
        # absorbs the remaining layout space. At smaller window sizes the page
        # scrolls rather than squeezing controls into the preview.
        scene = self.keyboard.sceneRect()
        margins = self.content_layout.contentsMargins()
        viewport_margins = self.keyboard.viewportMargins()
        border = 2 * self.keyboard.frameWidth() + 4
        horizontal_padding = border + viewport_margins.left() + viewport_margins.right()
        vertical_padding = border + viewport_margins.top() + viewport_margins.bottom()
        viewport = self.scroll_viewport
        width = viewport.width() - margins.left() - margins.right()
        height = viewport.height() - margins.top() - margins.bottom()
        fitted_height = round(max(0, width - horizontal_padding) * scene.height() / scene.width()) + vertical_padding
        self.keyboard.setFixedHeight(max(245, min(fitted_height, round(height * .46))))

    def busy(self):
        return self.worker is not None

    def dirty(self):
        return self.original is not None and self.original.data != self.edited

    def confirm_discard(self):
        return not self.dirty() or QMessageBox.question(
            self, "Discard keymap edits?", "Discard the staged keymap edits? Nothing has been written.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def filter_codes(self):
        query = self.search.text().casefold().strip()
        self.codes.clear()
        for code, name in ASSIGNABLE.items():
            text = f"{name} · 0x{code:04X}"
            if query in text.casefold():
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, code)
                self.codes.addItem(item)

    def refresh(self, *args):
        active = self.original is not None
        idle = not self.busy() and not self.external_busy()
        self.read_button.setEnabled(idle)
        self.layer.setEnabled(active and idle)
        self.restore_button.setEnabled(active and idle)
        self.defaults_button.setEnabled(active and idle)
        self.discard_button.setEnabled(self.dirty() and idle)
        self.apply_button.setEnabled(self.dirty() and idle)
        self.assign_button.setEnabled(active and idle and self.selected is not None)
        self.keyboard.setEnabled(active and idle)
        self.keyboard.show_keymap(self.original, self.edited, self.layer.currentIndex(), self.selected)
        unresolved = {}
        if active:
            for key in KEYS:
                offset = via.key_offset(self.layer.currentIndex(), key.row, key.col)
                code = int.from_bytes(self.edited[offset:offset + 2], "big")
                if not is_identified(code):
                    unresolved[code] = unresolved.get(code, 0) + 1
        if unresolved:
            count = sum(unresolved.values())
            values = ", ".join(f"0x{code:04X}" for code in sorted(unresolved))
            self.layer_info.setText(f"{count} keys on this layer have unresolved firmware codes ({values}). "
                                    "Preserved as-is. Named vendor/extended codes are interpretations; hover for details.")
        else:
            self.layer_info.setText("Named vendor/extended codes follow documented conventions; hover for interpretation notes."
                                    if active else "")
        self.changes.clear()
        if active:
            for offset in range(0, via.MAP_SIZE, 2):
                if self.original.data[offset:offset + 2] != self.edited[offset:offset + 2]:
                    index = offset // 2
                    layer, cell = divmod(index, via.ROWS * via.COLS)
                    row, col = divmod(cell, via.COLS)
                    before = int.from_bytes(self.original.data[offset:offset + 2], "big")
                    after = int.from_bytes(self.edited[offset:offset + 2], "big")
                    control = CONTROL_NAMES.get((row, col))
                    self.changes.addItem(f"L{layer} [{row},{col}]  " + (f"{control}: " if control else "") +
                                         f"{describe(before)} → {describe(after)}")
        self.selection.setToolTip("")
        if active and self.selected is not None:
            row, col = self.selected
            offset = via.key_offset(self.layer.currentIndex(), row, col)
            code = int.from_bytes(self.edited[offset:offset + 2], "big")
            control = CONTROL_NAMES.get((row, col))
            self.selection.setText((f"{control} · " if control else "") + f"Matrix {row},{col} · {describe(code)}")
            self.selection.setToolTip(explanation(code))
        elif active:
            self.selection.setText("Select a key above, then choose its new assignment.")
        else:
            self.selection.setText("Waiting for current keyboard mappings…")

    def set_active(self, active):
        self.active = active
        if active:
            if not self.dirty():
                self._attempted_device = None
            self.autoload()

    def autoload(self):
        """Load on tab entry/reconnect, never overwriting staged edits or retrying errors."""
        if not self.active or self.busy() or self.external_busy() or self.dirty():
            return
        devices = via.discover_devices()
        if len(devices) != 1 or not os.access(devices[0].path, os.R_OK | os.W_OK):
            self._attempted_device = None
            self.original = self.edited = self.device = None
            self.selected = None
            self.status.setText("Waiting for one accessible wired GMK104. Current keys will load when it connects.")
            self.refresh()
            return
        device = devices[0]
        if device == self._attempted_device:
            return
        self.device = self._attempted_device = device
        self.start_worker(automatic=True)

    def select_key(self, row, col):
        self.selected = row, col
        self.refresh()

    def assign(self, *args):
        if self.original is None or self.selected is None or self.busy() or self.external_busy():
            return
        item = self.codes.currentItem()
        if item is None:
            return
        code = item.data(Qt.ItemDataRole.UserRole)
        if code not in ASSIGNABLE:
            return
        offset = via.key_offset(self.layer.currentIndex(), *self.selected)
        self.edited[offset:offset + 2] = code.to_bytes(2, "big")
        self.refresh()

    def discard(self):
        if not self.busy() and self.confirm_discard():
            self.edited = bytearray(self.original.data)
            self.refresh()

    def read(self):
        if self.busy() or self.external_busy() or not self.confirm_discard():
            return
        devices = via.discover_devices()
        if len(devices) != 1 or not os.access(devices[0].path, os.R_OK | os.W_OK):
            self.status.setText("Need exactly one accessible wired GMK104 VIA interface. Check USB mode and udev permissions.")
            return
        self.device = devices[0]
        self._attempted_device = self.device
        self.start_worker()

    def start_worker(self, desired=None, automatic=False):
        self._automatic = automatic
        self.worker = KeymapWorker(self.device, self.directory, self.original, desired)
        self.worker.succeeded.connect(self.success)
        self.worker.failed.connect(self.failure)
        self.worker.finished.connect(self.finished)
        self.status.setText("Reading and saving a private backup…" if desired is None else
                            "Checking for external changes, backing up, applying, and verifying… Do not unplug.")
        self.worker.start()
        self.busy_changed.emit()
        self.refresh()

    def success(self, snapshot, path):
        applied = self.worker.desired is not None
        self.original = snapshot
        self.edited = bytearray(snapshot.data)
        self.status.setText(("Applied and fully verified." if applied else "Read complete. No keymap writes sent.") +
                            f" Backup: {path}")
        self.baseline_info.setText("Restore defaults uses the bundled keymap captured on 17 November 2026. "
                                  f"Extra first-read recovery backup: {via.baseline_path(self.directory)}")
        self.refresh()

    def failure(self, message):
        self.original = self.edited = None
        self.selected = None
        self.status.setText(f"Stopped without retry. Read again before editing. {message}")
        if not self._automatic:
            QMessageBox.warning(self, "Keymap operation stopped", message +
                                "\n\nNo automatic retry or restore. If a write was interrupted, the keymap may be partially changed.")
        self.refresh()

    def finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        self.busy_changed.emit()
        self.refresh()

    def apply(self):
        if not self.dirty() or self.busy() or self.external_busy():
            return
        devices = via.discover_devices()
        if devices != [self.device]:
            self.status.setText("VIA device changed or is ambiguous. Read the keyboard again.")
            return
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Apply keymap changes?")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(f"Write {self.changes.count()} changed key mappings?")
        dialog.setInformativeText("Changes persist on the keyboard. A full backup is saved first.\n"
                                  "Keep a usable Fn/layer key. Changing it can make other layers inaccessible.\n"
                                  "Close VIA and other configuration tools. Do not unplug during the write.\n"
                                  "Expand Details to review every change.")
        dialog.setDetailedText("\n".join(self.changes.item(i).text() for i in range(self.changes.count())))
        dialog.setStandardButtons(QMessageBox.StandardButton.Apply | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if dialog.exec() == QMessageBox.StandardButton.Apply:
            self.start_worker(via.Snapshot(bytes(self.edited)))

    def restore(self):
        if self.original is None or self.busy() or self.external_busy() or not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Load GMK104 Studio keymap backup",
                                              str(self.directory), "Keymap backup (*.json)")
        if path:
            try:
                snapshot = via.load_backup(path)
                self.edited = bytearray(snapshot.data)
                self.status.setText("Backup staged locally. Review all changes, then Apply to restore. Nothing written yet.")
                self.refresh()
            except (OSError, ValueError, KeyError, TypeError) as error:
                QMessageBox.warning(self, "Invalid keymap backup", str(error))

    def restore_defaults(self):
        if self.original is None or self.busy() or self.external_busy() or not self.confirm_discard():
            return
        try:
            snapshot = via.load_backup(DEFAULT_KEYMAP)
            self.edited = bytearray(snapshot.data)
            self.status.setText("Bundled defaults staged locally (captured keymap, not certified factory defaults). "
                                 "Review and apply to restore. Nothing written yet.")
            self.refresh()
            if not self.dirty():
                self.status.setText("Keyboard already matches the bundled defaults. No changes needed.")
        except (OSError, ValueError, KeyError, TypeError) as error:
            QMessageBox.warning(self, "Cannot load bundled defaults", str(error))
