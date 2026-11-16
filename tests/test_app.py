"""Offline image editing and persistent history regression tests."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from gmk104_app.core import Adjustments, History, external_editor_environment, load_animation, render_frames, save_animation
import gmk104_app.core as core


class BundleTests(unittest.TestCase):
    def test_external_editor_does_not_inherit_bundled_libraries(self):
        with patch.object(core.sys, "frozen", True, create=True), \
                patch.object(core.sys, "_MEIPASS", "/bundle", create=True), \
                patch.dict(core.os.environ, {
                    "LD_LIBRARY_PATH": "/bundle/lib", "LD_LIBRARY_PATH_ORIG": "/system/lib",
                    "QT_PLUGIN_PATH": "/bundle/qt/plugins", "WAYLAND_DISPLAY": "wayland-0",
                }, clear=True):
            environment = external_editor_environment()
            self.assertEqual(environment["LD_LIBRARY_PATH"], "/system/lib")
            self.assertNotIn("QT_PLUGIN_PATH", environment)
            self.assertEqual(environment["WAYLAND_DISPLAY"], "wayland-0")

    def test_no_original_library_path_means_remove_bundled_path(self):
        with patch.object(core.sys, "frozen", True, create=True), \
                patch.dict(core.os.environ, {"LD_LIBRARY_PATH": "/bundle/lib"}, clear=True):
            self.assertNotIn("LD_LIBRARY_PATH", external_editor_environment())


class EditingTests(unittest.TestCase):
    def test_square_gets_black_pillarboxes(self):
        result = render_frames([Image.new("RGBA", (128, 128), "red")], Adjustments())[0]
        self.assertEqual(result.size, (240, 135))
        self.assertEqual(result.getbbox(), (52, 0, 187, 135))

    def test_transparency_always_composites_black(self):
        result = render_frames([Image.new("RGBA", (240, 135), (255, 255, 255, 0))], Adjustments())[0]
        self.assertIsNone(result.getbbox())

    def test_wide_image_is_letterboxed_not_cropped(self):
        result = render_frames([Image.new("RGB", (480, 135), "red")], Adjustments())[0]
        # Pillow rounds 67.5 pixels to 68; one-pixel asymmetric padding is normal.
        self.assertEqual(result.getbbox(), (0, 33, 240, 101))

    def test_flip_moves_marker(self):
        image = Image.new("RGB", (240, 135), "black")
        image.putpixel((0, 0), (255, 0, 0))
        result = render_frames([image], Adjustments(flip_horizontal=True))[0]
        self.assertEqual(result.getpixel((239, 0)), (255, 0, 0))

    def test_brightness_changes_artwork_but_not_black_padding(self):
        result = render_frames([Image.new("RGB", (128, 128), (100, 100, 100))],
                               Adjustments(brightness=1.5))[0]
        self.assertEqual(result.getpixel((120, 67)), (150, 150, 150))
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0))

    def test_rotation_keeps_full_image_in_bounds(self):
        result = render_frames([Image.new("RGB", (240, 135), "red")],
                               Adjustments(rotation=90))[0]
        self.assertEqual(result.size, (240, 135))
        self.assertLess(result.getbbox()[2] - result.getbbox()[0], 240)
        self.assertEqual(result.getpixel((120, 0)), (255, 0, 0))

    def test_roundtrip_preserves_two_frames_and_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.gif"
            save_animation(path, [Image.new("RGB", (240, 135), "red"),
                                  Image.new("RGB", (240, 135), "blue")], 500)
            frames, durations = load_animation(path)
            self.assertEqual(len(frames), 2)
            self.assertEqual(durations, [500, 500])

    def test_identical_frames_are_not_merged_or_retimed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.gif"
            red = Image.new("RGB", (240, 135), "red")
            save_animation(path, [red, red.copy()], 500)
            frames, durations = load_animation(path)
            self.assertEqual(len(frames), 2)
            self.assertEqual(durations, [500, 500])


class HistoryTests(unittest.TestCase):
    def test_recent_uploads_are_copied_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.gif"
            save_animation(source, [Image.new("RGB", (240, 135), "red")], 1000)
            history = History(root / "history", limit=2)
            for index in range(3):
                history.record(source, f"upload {index}", 1000)
            source.unlink()
            loaded = History(root / "history", limit=2).items()
            self.assertEqual([item["name"] for item in loaded], ["upload 2", "upload 1"])
            self.assertTrue(all((root / "history" / item["file"]).exists() for item in loaded))
            self.assertEqual(len(list((root / "history").glob("*.gif"))), 2)

    def test_bad_index_does_not_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.json").write_text("broken")
            self.assertEqual(History(root).items(), [])

    def test_history_rejects_paths_outside_its_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.json").write_text('[{"file":"../private.gif","name":"bad"}]')
            self.assertEqual(History(root).items(), [])


if __name__ == "__main__":
    unittest.main()
