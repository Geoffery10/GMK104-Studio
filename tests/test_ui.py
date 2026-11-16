"""Headless UI tests; never access a real keyboard."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from gmk104_app.core import History, save_animation
from gmk104_app.ui import UploadWorker, Window
from protocol import gmk104


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.discover = patch.object(gmk104, "discover_devices", return_value=[])
        self.discover.start()
        self.window = Window(History(self.root / "history"), self.root,
                             QSettings(str(self.root / "prefs.ini"), QSettings.Format.IniFormat))
        self.source = self.root / "artwork.gif"
        save_animation(self.source, [Image.new("RGB", (240, 135), "red")], 500)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        self.discover.stop()
        self.temp.cleanup()

    def test_open_and_duplicate_remove_frame_without_usb_write(self):
        with patch.object(gmk104.os, "open") as open_device:
            self.window.load(self.source)
            self.assertEqual(len(self.window.frames), 1)
            self.window.duplicate_frame()
            self.assertEqual(len(self.window.frames), 2)
            self.window.remove_frame()
            self.assertEqual(len(self.window.frames), 1)
            open_device.assert_not_called()

    def test_no_device_disables_upload(self):
        self.window.load(self.source)
        self.assertFalse(self.window.upload_button.isEnabled())

    def test_upload_starts_without_a_confirmation_dialog(self):
        self.window.load(self.source)
        device = gmk104.Device(Path("/unused"), Path("/unused"))
        with patch.object(gmk104, "discover_devices", return_value=[device]), \
                patch("gmk104_app.ui.os.access", return_value=True), \
                patch.object(QMessageBox, "question") as question, \
                patch("gmk104_app.ui.UploadWorker") as worker, \
                patch.object(gmk104, "HidrawTransport") as transport:
            worker.return_value.isRunning.return_value = False
            self.window.upload()
            question.assert_not_called()
            worker.return_value.start.assert_called_once()
            self.assertEqual(worker.call_args.args[3], self.window.history.root.parent / "backups")
            transport.assert_not_called()
            self.assertEqual(self.window.history.items(), [])

    def test_success_records_prepared_copy(self):
        self.window.pending_file = self.source
        self.window.pending_name = "Artwork"
        self.window.pending_interval = 500
        self.window.upload_success()
        self.assertEqual(self.window.history.items()[0]["name"], "Artwork")
        self.assertEqual(self.window.recents.count(), 1)

    def test_failure_does_not_record_history(self):
        with patch.object(self.window, "error"):
            self.window.upload_failed("simulated timeout")
        self.assertEqual(self.window.history.items(), [])
        self.assertIn("No automatic retry", self.window.status.text())

    def test_backup_only_success_does_not_add_gif_to_history(self):
        self.window.upload_success("/example/settings.json")
        self.assertEqual(self.window.history.items(), [])
        self.assertIn("No configuration writes", self.window.status.text())

    def test_worker_reports_error_without_history_or_retry(self):
        worker = UploadWorker([Image.new("RGB", (240, 135), "red")], 500,
                              gmk104.Device(Path("/unused"), Path("/unused")))
        errors, successes = [], []
        worker.failed.connect(errors.append)
        worker.succeeded.connect(lambda path: successes.append(path))
        with patch.object(gmk104, "HidrawTransport") as transport:
            transport.return_value.__enter__.side_effect = OSError("simulated failure")
            worker.run()
            self.assertEqual(transport.call_count, 1)
        self.assertEqual(successes, [])
        self.assertEqual(errors, ["simulated failure"])

    def test_editor_receives_a_copy_without_shell(self):
        self.window.load(self.source)
        original = self.source.read_bytes()
        self.window.settings.setValue("editor", "fake-editor --new-window")
        with patch("gmk104_app.ui.shutil.which", return_value="/usr/bin/fake-editor"), \
                patch("gmk104_app.ui.subprocess.Popen") as launch:
            self.window.open_editor()
        args, kwargs = launch.call_args
        self.assertEqual(args[0][:2], ["fake-editor", "--new-window"])
        self.assertNotEqual(Path(args[0][-1]), self.source)
        self.assertTrue(Path(args[0][-1]).exists())
        self.assertNotIn("shell", kwargs)
        self.assertEqual(self.source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
