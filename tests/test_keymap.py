"""Headless keymap UI tests; real USB access is never used."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEventLoop, QSettings, QTimer

from gmk104_app.core import History
from gmk104_app.keycodes import ASSIGNABLE, describe, explanation, is_identified, short_name
from gmk104_app.keymap import DEFAULT_KEYMAP, KeymapPanel, KeymapWorker
from gmk104_app.keymap_layout import KEYS, KNOB_PRESS
from gmk104_app.ui import STYLE, Window
from protocol import via
from protocol.gmk104 import Device


class KeymapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.panel = KeymapPanel(self.temp.name)
        self.device = Device(Path("/unused"), Path("/unused/sysfs"))
        self.snapshot = via.Snapshot(b"\x7f\x7f" * (via.MAP_SIZE // 2))

    def tearDown(self):
        self.panel.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def load_snapshot(self):
        self.panel.original = self.snapshot
        self.panel.edited = bytearray(self.snapshot.data)
        self.panel.device = self.device
        self.panel.refresh()

    def stage_a(self):
        self.load_snapshot()
        self.panel.select_key(3, 1)
        self.panel.search.setText("A ·")
        self.panel.codes.setCurrentRow(0)
        self.panel.assign()

    def test_construct_and_edit_never_open_usb(self):
        with patch.object(via, "HidrawTransport") as transport:
            self.assertFalse(self.panel.apply_button.isEnabled())
            self.stage_a()
            self.assertTrue(self.panel.dirty())
            self.assertEqual(self.panel.changes.count(), 1)
            offset = via.key_offset(0, 3, 1)
            self.assertEqual(self.panel.edited[offset:offset + 2], b"\0\x04")
            # Every unknown firmware word except the selected key is preserved.
            self.assertEqual(self.panel.edited[:offset], self.snapshot.data[:offset])
            self.assertEqual(self.panel.edited[offset + 2:], self.snapshot.data[offset + 2:])
            transport.assert_not_called()

    def test_layer_edit_uses_correct_buffer_offset(self):
        self.stage_a()
        self.panel.layer.setCurrentIndex(3)
        self.panel.assign()
        self.assertEqual(self.panel.changes.count(), 2)
        self.assertEqual(self.panel.edited[via.key_offset(3, 3, 1):][:2], b"\0\x04")

    def test_cancel_apply_never_starts_worker(self):
        self.stage_a()
        with patch.object(via, "discover_devices", return_value=[self.device]), \
                patch("gmk104_app.keymap.QMessageBox") as dialog, \
                patch.object(self.panel, "start_worker") as start:
            dialog.StandardButton = QMessageBox.StandardButton
            dialog.return_value.exec.return_value = QMessageBox.StandardButton.Cancel
            self.panel.apply()
            start.assert_not_called()

    def test_confirmed_apply_passes_staged_snapshot(self):
        self.stage_a()
        with patch.object(via, "discover_devices", return_value=[self.device]), \
                patch("gmk104_app.keymap.QMessageBox") as dialog, \
                patch.object(self.panel, "start_worker") as start:
            dialog.StandardButton = QMessageBox.StandardButton
            dialog.return_value.exec.return_value = QMessageBox.StandardButton.Apply
            self.panel.apply()
            self.assertEqual(start.call_args.args[0].data, bytes(self.panel.edited))

    def test_changed_device_prevents_apply(self):
        self.stage_a()
        with patch.object(via, "discover_devices", return_value=[]), \
                patch.object(self.panel, "start_worker") as start:
            self.panel.apply()
            start.assert_not_called()

    def test_external_operation_blocks_all_keymap_actions(self):
        self.stage_a()
        before = bytes(self.panel.edited)
        self.panel.external_busy = lambda: True
        self.panel.refresh()
        self.assertFalse(self.panel.read_button.isEnabled())
        self.assertFalse(self.panel.apply_button.isEnabled())
        with patch.object(self.panel, "start_worker") as start:
            self.panel.apply()
            self.panel.read()
            self.panel.assign()
            start.assert_not_called()
        self.assertEqual(bytes(self.panel.edited), before)

    def test_failure_invalidates_snapshot_and_requires_new_read(self):
        self.stage_a()
        with patch.object(QMessageBox, "warning"):
            self.panel.failure("timeout")
        self.assertIsNone(self.panel.original)
        self.assertFalse(self.panel.apply_button.isEnabled())
        self.assertFalse(self.panel.assign_button.isEnabled())

    def test_restore_stages_backup_without_usb(self):
        self.load_snapshot()
        desired = via.Snapshot(b"\0\x04" * (via.MAP_SIZE // 2))
        path = via.backup_keymap(desired, self.temp.name, self.device)
        with patch("gmk104_app.keymap.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                patch.object(via, "HidrawTransport") as transport:
            self.panel.restore()
            self.assertEqual(bytes(self.panel.edited), desired.data)
            self.assertEqual(self.panel.original, self.snapshot)
            transport.assert_not_called()

    def test_discard_confirmed_resets_staged_changes(self):
        self.stage_a()
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.panel.discard()
        self.assertFalse(self.panel.dirty())
        self.assertEqual(self.panel.changes.count(), 0)

    def test_worker_read_backs_up_without_apply(self):
        worker = KeymapWorker(self.device, self.temp.name)
        snapshots, errors = [], []
        worker.succeeded.connect(lambda snapshot, path: snapshots.append(snapshot))
        worker.failed.connect(errors.append)
        with patch.object(via, "HidrawTransport"), \
                patch.object(via, "read_keymap", return_value=self.snapshot), \
                patch.object(via, "ensure_baseline"), \
                patch.object(via, "backup_keymap", return_value=Path("/unused/backup")), \
                patch.object(via, "apply_keymap") as apply:
            worker.run()
            apply.assert_not_called()
        self.assertEqual(snapshots, [self.snapshot])
        self.assertEqual(errors, [])

    def test_worker_failure_does_not_retry(self):
        worker = KeymapWorker(self.device, self.temp.name)
        errors = []
        worker.failed.connect(errors.append)
        with patch.object(via, "HidrawTransport") as transport:
            transport.return_value.__enter__.side_effect = OSError("access denied")
            worker.run()
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(errors, ["access denied"])

    def test_layout_has_unique_in_range_keys_and_corrected_esc(self):
        cells = [(key.row, key.col) for key in KEYS]
        self.assertEqual(len(cells), len(set(cells)))
        self.assertEqual(len(cells), 107)
        self.assertEqual(cells[0], (0, 0))
        self.assertEqual(cells.count((7, 13)), 1)
        self.assertEqual(cells.count(KNOB_PRESS), 1)
        for key in KEYS:
            via.key_offset(0, key.row, key.col)
            self.assertLessEqual(key.x + key.width, 23)
            self.assertLessEqual(key.y + key.height, 6.25)

    def test_picker_does_not_offer_bootloader_or_unknown_codes(self):
        self.assertNotIn(0x7C00, ASSIGNABLE)
        self.assertNotIn(0x5C00, ASSIGNABLE)
        self.assertNotIn(0x7F7F, ASSIGNABLE)
        self.assertIn("preserved", describe(0x7F7F))

    def test_auxiliary_controls_and_knob_show_identified_functions(self):
        defaults = via.load_backup(DEFAULT_KEYMAP)
        self.panel.original = defaults
        self.panel.edited = bytearray(defaults.data)
        self.panel.refresh()
        buttons = self.panel.keyboard.buttons
        self.assertEqual(buttons[5, 4].text(), "Light")
        self.assertEqual(buttons[5, 6].text(), "LCD")
        self.assertEqual(buttons[KNOB_PRESS].text(), "Press\nMute")
        self.assertIn("0x7820", buttons[5, 4].toolTip())
        self.assertIn("0x7F09", buttons[5, 6].toolTip())
        self.assertIn("Knob press", buttons[KNOB_PRESS].toolTip())
        self.assertIn("Counter-clockwise", self.panel.keyboard.rotation_label.toolTip())
        self.assertIn("not verified", self.panel.keyboard.rotation_label.toolTip())

    def test_knob_press_edits_selected_layer_only_without_usb(self):
        self.load_snapshot()
        before = bytes(self.panel.edited)
        self.panel.layer.setCurrentIndex(3)
        with patch.object(via, "HidrawTransport") as transport:
            self.panel.keyboard.buttons[KNOB_PRESS].click()
            self.assertEqual(self.panel.selected, KNOB_PRESS)
            self.panel.search.setText("A ·")
            self.panel.codes.setCurrentRow(0)
            self.panel.assign()
            transport.assert_not_called()
        offset = via.key_offset(3, *KNOB_PRESS)
        self.assertEqual(self.panel.edited[offset:offset + 2], b"\0\x04")
        self.assertEqual(self.panel.edited[:offset], before[:offset])
        self.assertEqual(self.panel.edited[offset + 2:], before[offset + 2:])
        self.assertEqual(self.panel.changes.count(), 1)
        self.assertIn("Knob press", self.panel.changes.item(0).text())
        self.assertEqual(self.panel.keyboard.buttons[KNOB_PRESS].text(), "Press\nA")

    def test_control_labels_follow_remaps_instead_of_hardcoding_default_functions(self):
        self.load_snapshot()
        self.panel.select_key(5, 4)
        self.panel.search.setText("A ·")
        self.panel.codes.setCurrentRow(0)
        self.panel.assign()
        self.assertEqual(self.panel.keyboard.buttons[5, 4].text(), "A")
        self.assertIn("Backlight button", self.panel.keyboard.buttons[5, 4].toolTip())
        self.assertIn("Backlight button", self.panel.selection.text())

    def test_identified_controls_are_available_to_restore_assignments(self):
        for code, label in ((0x7820, "Backlight toggle"), (0x7F09, "LCD toggle"),
                            (0x00A8, "Mute"), (0x00A9, "Volume up"), (0x00AA, "Volume down")):
            self.assertEqual(ASSIGNABLE[code], label)
            self.assertEqual(describe(code), label)
        self.assertEqual(short_name(0x7820), "Light")
        self.assertEqual(short_name(0x7F09), "LCD")

    def test_fn_labels_resolve_known_families_but_preserve_unresolved_values(self):
        defaults = via.load_backup(DEFAULT_KEYMAP)
        self.panel.original = defaults
        self.panel.edited = bytearray(defaults.data)
        self.panel.layer.setCurrentIndex(1)
        self.panel.refresh()
        buttons = self.panel.keyboard.buttons
        self.assertEqual(buttons[0, 6].text(), "Prev")
        self.assertEqual(buttons[0, 7].text(), "Play")
        self.assertEqual(buttons[2, 1].text(), "BT 1")
        self.assertEqual(buttons[7, 8].text(), "Bri +")
        self.assertEqual(buttons[3, 13].text(), "LCD mode")
        self.assertEqual(buttons[5, 10].text(), "MO(1)*")
        self.assertEqual(buttons[0, 0].text(), "0xFFFF")
        self.assertIn("do not assume", buttons[0, 0].toolTip())
        self.assertIn("identification only", buttons[2, 1].toolTip())
        self.assertIn("6 keys", self.panel.layer_info.text())
        self.assertIn("0xFFFF", self.panel.layer_info.text())
        self.assertFalse(self.panel.dirty())
        self.assertEqual(bytes(self.panel.edited), defaults.data)

    def test_new_interpretations_are_display_only_and_not_offered_as_assignments(self):
        for code in (0x00AB, 0x00AC, 0x00AE, 0x00B1, 0x00B2, 0x00B4, 0x00B5,
                     0x5221, 0x7821, 0x7823, 0x782A, 0x7F00, 0x7F01, 0x7F0C, 0x5F88):
            self.assertTrue(is_identified(code))
            self.assertNotIn(code, ASSIGNABLE)
            self.assertNotEqual(explanation(code), "")
        for code in (0xFFFF, 0x7F7F):
            self.assertFalse(is_identified(code))
            self.assertNotIn(code, ASSIGNABLE)
        self.assertNotEqual(short_name(0x5101), short_name(0x5221))

    def test_only_ffff_remains_unresolved_in_captured_default_map(self):
        data = via.load_backup(DEFAULT_KEYMAP).data
        unresolved = {int.from_bytes(data[i:i + 2], "big") for i in range(0, len(data), 2)
                      if not is_identified(int.from_bytes(data[i:i + 2], "big"))}
        self.assertEqual(unresolved, {0xFFFF})

    def test_review_button_has_no_accidental_qt_mnemonic(self):
        self.assertEqual(self.panel.apply_button.text(), "Review and apply…")
        self.assertNotIn("&", self.panel.apply_button.text())
        self.assertNotIn("experimental", self.panel.status.text().lower())

    def test_restore_defaults_does_not_resize_or_rescale_keyboard_preview(self):
        root = Path(self.temp.name)
        with patch("gmk104_app.ui.protocol.discover_devices", return_value=[]), \
                patch.object(via, "discover_devices", return_value=[]):
            window = Window(History(root / "history"), root,
                            QSettings(str(root / "prefs.ini"), QSettings.Format.IniFormat))
            window.setStyleSheet(STYLE)
            window.tabs.setCurrentWidget(window.keymap)
        try:
            panel = window.keymap
            defaults = via.load_backup(DEFAULT_KEYMAP)
            window.resize(1180, 780)
            window.show()
            for changed in (False, True):
                with self.subTest(changed_mapping=changed):
                    data = bytearray(defaults.data)
                    if changed:
                        offset = via.key_offset(0, 3, 1)
                        data[offset:offset + 2] = b"\0\x05"
                    panel.original = via.Snapshot(bytes(data))
                    panel.edited = bytearray(data)
                    panel.status.setText("Read complete.\nNo keymap writes sent.\nBackup: saved-keymap.json")
                    panel.refresh()
                    for _ in range(4):
                        self.app.processEvents()
                    size = panel.keyboard.viewport().size()
                    scale = panel.keyboard.transform().m11()
                    panel.restore_defaults()
                    for _ in range(4):
                        self.app.processEvents()
                    self.assertEqual(panel.keyboard.viewport().size(), size)
                    self.assertAlmostEqual(panel.keyboard.transform().m11(), scale)
            previous_width = panel.keyboard.viewport().width()
            previous_scale = panel.keyboard.transform().m11()
            window.resize(1280, 900)
            for _ in range(4):
                self.app.processEvents()
            self.assertGreater(panel.keyboard.viewport().width(), previous_width)
            self.assertGreater(panel.keyboard.transform().m11(), previous_scale)
        finally:
            window.keymap.original = window.keymap.edited = None
            window.close()
            window.deleteLater()

    def test_padded_keymap_scrolls_instead_of_overlapping_at_compact_sizes(self):
        root = Path(self.temp.name)
        with patch("gmk104_app.ui.protocol.discover_devices", return_value=[]), \
                patch.object(via, "discover_devices", return_value=[]):
            window = Window(History(root / "history"), root,
                            QSettings(str(root / "prefs.ini"), QSettings.Format.IniFormat))
            window.setStyleSheet(STYLE)
            window.tabs.setCurrentWidget(window.keymap)
            panel = window.keymap
            panel.original = via.load_backup(DEFAULT_KEYMAP)
            panel.edited = bytearray(panel.original.data)
            panel.refresh()
            try:
                window.show()
                for width, height in ((1280, 940), (1180, 850), (980, 720)):
                    with self.subTest(width=width, height=height):
                        window.resize(width, height)
                        for _ in range(4):
                            self.app.processEvents()
                        self.assertGreaterEqual(panel.knob_info.y(), panel.keyboard.geometry().bottom() + 12)
                        self.assertGreaterEqual(panel.layer_info.y(), panel.knob_info.geometry().bottom() + 12)
                        self.assertGreaterEqual(panel.status.y(), panel.assign_button.geometry().bottom() + 12)
                self.assertGreater(panel.scroll_area.verticalScrollBar().maximum(), 0)
                self.assertTrue(panel.scroll_area.verticalScrollBar().isEnabled())
            finally:
                window.close()
                window.deleteLater()

    def test_keymap_padding_does_not_pad_individual_keycaps(self):
        margins = self.panel.content_layout.contentsMargins()
        self.assertEqual((margins.left(), margins.top(), margins.right(), margins.bottom()), (16, 16, 16, 16))
        self.assertEqual(self.panel.content_layout.spacing(), 12)
        viewport_margins = self.panel.keyboard.viewportMargins()
        self.assertEqual((viewport_margins.left(), viewport_margins.top(),
                          viewport_margins.right(), viewport_margins.bottom()), (8, 8, 8, 8))
        for button in self.panel.keyboard.buttons.values():
            self.assertIn("padding: 0", button.styleSheet())
            self.assertEqual(button.minimumSize(), button.maximumSize())

    def test_unverified_mouse_codes_are_not_offered(self):
        for code in (0x00CD, 0x00D1, 0x00F0, 0x00F4):
            self.assertNotIn(code, ASSIGNABLE)

    def test_keymap_worker_blocks_screen_operations(self):
        root = Path(self.temp.name)
        with patch("gmk104_app.ui.protocol.discover_devices", return_value=[]):
            window = Window(History(root / "history"), root,
                            QSettings(str(root / "prefs.ini"), QSettings.Format.IniFormat))
        try:
            self.assertEqual(window.tabs.tabText(window.tabs.indexOf(window.keymap)), "Keymap")
            window.device = self.device
            window.keymap.worker = object()  # An in-flight keymap operation.
            window.update_enabled()
            self.assertTrue(window.busy())
            self.assertFalse(window.upload_button.isEnabled())
            self.assertFalse(window.backup_button.isEnabled())
            self.assertFalse(window.keymap.read_button.isEnabled())
            with patch("gmk104_app.ui.UploadWorker") as worker:
                window.backup_only()
                worker.assert_not_called()
        finally:
            window.keymap.worker = None
            window.close()
            window.deleteLater()

    def test_tab_entry_autoloads_and_polling_does_not_repeat_reads(self):
        with patch.object(via, "discover_devices", return_value=[self.device]), \
                patch("gmk104_app.keymap.os.access", return_value=True), \
                patch.object(self.panel, "start_worker") as start:
            self.panel.set_active(True)
            self.panel.autoload()
            start.assert_called_once_with(automatic=True)
            self.panel.set_active(False)
            self.panel.autoload()
            start.assert_called_once()
            self.panel.set_active(True)
            self.assertEqual(start.call_count, 2)

    def test_autoload_never_discards_staged_edits(self):
        self.stage_a()
        before = bytes(self.panel.edited)
        with patch.object(via, "discover_devices") as discover, \
                patch.object(self.panel, "start_worker") as start, \
                patch.object(QMessageBox, "question") as question:
            self.panel.set_active(True)
            self.panel.autoload()
            discover.assert_not_called()
            start.assert_not_called()
            question.assert_not_called()
        self.assertEqual(bytes(self.panel.edited), before)

    def test_autoload_waits_for_idle_then_loads(self):
        self.panel.external_busy = lambda: True
        with patch.object(via, "discover_devices", return_value=[self.device]), \
                patch("gmk104_app.keymap.os.access", return_value=True), \
                patch.object(self.panel, "start_worker") as start:
            self.panel.set_active(True)
            start.assert_not_called()
            self.panel.external_busy = lambda: False
            self.panel.autoload()
            start.assert_called_once_with(automatic=True)

    def test_autoload_waits_for_connection_and_reloads_after_reconnect(self):
        with patch.object(via, "discover_devices", return_value=[]) as discover, \
                patch("gmk104_app.keymap.os.access", return_value=True), \
                patch.object(self.panel, "start_worker") as start:
            self.panel.set_active(True)
            start.assert_not_called()
            discover.return_value = [self.device]
            self.panel.autoload()
            start.assert_called_once_with(automatic=True)
            self.load_snapshot()
            discover.return_value = []
            self.panel.autoload()
            self.assertIsNone(self.panel.original)
            discover.return_value = [self.device]
            self.panel.autoload()
            self.assertEqual(start.call_count, 2)

    def test_autoload_error_is_inline_without_polling_retries(self):
        self.panel.active = True
        self.panel._automatic = True
        self.panel._attempted_device = self.device
        with patch.object(QMessageBox, "warning") as warning, \
                patch.object(via, "discover_devices", return_value=[self.device]), \
                patch("gmk104_app.keymap.os.access", return_value=True), \
                patch.object(self.panel, "start_worker") as start:
            self.panel.failure("simulated read error")
            self.panel.autoload()
            warning.assert_not_called()
            start.assert_not_called()
        self.assertIn("simulated read error", self.panel.status.text())

    def test_restore_defaults_only_stages_bundled_keys_and_preserves_local_baseline(self):
        path = via.ensure_baseline(self.snapshot, self.temp.name, self.device)
        defaults = via.load_backup(DEFAULT_KEYMAP)
        current = via.Snapshot(b"\0\x04" * (via.MAP_SIZE // 2))
        self.panel.original = current
        self.panel.edited = bytearray(current.data)
        self.panel.refresh()
        self.assertTrue(self.panel.defaults_button.isEnabled())
        with patch.object(via, "HidrawTransport") as transport:
            self.panel.restore_defaults()
            transport.assert_not_called()
        self.assertEqual(self.panel.original, current)
        self.assertEqual(bytes(self.panel.edited), defaults.data)
        self.assertTrue(self.panel.dirty())
        self.assertEqual(via.load_backup(path), self.snapshot)

    def test_bundled_defaults_work_without_local_baseline(self):
        self.load_snapshot()
        self.assertFalse(via.baseline_path(self.temp.name).exists())
        with patch.object(via, "HidrawTransport") as transport:
            self.panel.restore_defaults()
            transport.assert_not_called()
        self.assertEqual(bytes(self.panel.edited), via.load_backup(DEFAULT_KEYMAP).data)
        self.assertFalse(via.baseline_path(self.temp.name).exists())

    def test_corrupt_bundled_defaults_are_not_silently_replaced(self):
        self.load_snapshot()
        path = Path(self.temp.name) / "bad-defaults.json"
        path.write_text("{}")
        with patch("gmk104_app.keymap.DEFAULT_KEYMAP", path), \
                patch.object(QMessageBox, "warning") as warning:
            self.panel.restore_defaults()
            warning.assert_called_once()
        self.assertEqual(bytes(self.panel.edited), self.snapshot.data)
        self.assertFalse(self.panel.dirty())

    def test_restore_defaults_can_cancel_discarding_edits(self):
        self.stage_a()
        before = bytes(self.panel.edited)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No), \
                patch.object(via, "load_backup") as load:
            self.panel.restore_defaults()
            load.assert_not_called()
        self.assertEqual(bytes(self.panel.edited), before)

    def test_bundled_defaults_include_all_layers_and_no_machine_identity(self):
        snapshot = via.load_backup(DEFAULT_KEYMAP)
        self.assertEqual(len(snapshot.data), 960)
        self.assertEqual(snapshot.keycode(0, 0, 0), 0x29)
        self.assertEqual(snapshot.keycode(0, 3, 1), 0x04)
        self.assertEqual(snapshot.keycode(0, 5, 11), 0x5101)
        self.assertEqual(snapshot.keycode(0, 7, 13), 0x58)
        self.assertEqual(snapshot.keycode(0, 5, 6), 0x7F09)
        record = json.loads(DEFAULT_KEYMAP.read_text())
        self.assertNotIn("hidraw", record)
        self.assertNotIn("sysfs", record)

    def test_window_opens_keymap_with_automatic_load(self):
        root = Path(self.temp.name)
        with patch("gmk104_app.ui.protocol.discover_devices", return_value=[]):
            window = Window(History(root / "history"), root,
                            QSettings(str(root / "prefs.ini"), QSettings.Format.IniFormat))
        try:
            with patch.object(via, "discover_devices", return_value=[self.device]), \
                    patch("gmk104_app.keymap.os.access", return_value=True), \
                    patch.object(window.keymap, "start_worker") as start:
                window.tabs.setCurrentWidget(window.keymap)
                start.assert_called_once_with(automatic=True)
        finally:
            window.close()
            window.deleteLater()

    def test_automatic_worker_loads_keys_and_persists_baseline_end_to_end(self):
        loop = QEventLoop()
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        self.panel.busy_changed.connect(lambda: loop.quit() if not self.panel.busy() else None)
        with patch.object(via, "discover_devices", return_value=[self.device]), \
                patch("gmk104_app.keymap.os.access", return_value=True), \
                patch.object(via, "HidrawTransport"), \
                patch.object(via, "read_keymap", return_value=self.snapshot), \
                patch.object(via, "apply_keymap") as apply:
            self.panel.set_active(True)
            worker = self.panel.worker
            timeout.start(5000)
            loop.exec()
            timeout.stop()
            worker.wait()
            self.app.processEvents()
            apply.assert_not_called()
        self.assertFalse(self.panel.busy())
        self.assertEqual(self.panel.original, self.snapshot)
        self.assertFalse(self.panel.dirty())
        self.assertTrue(self.panel.defaults_button.isEnabled())
        self.assertEqual(via.load_backup(via.baseline_path(self.temp.name)), self.snapshot)


if __name__ == "__main__":
    unittest.main()
