"""Dependency compatibility policy and binding-level UI regression; no USB."""
import os
from pathlib import Path
import subprocess
import sys
import tomllib
import unittest


class DependencyTests(unittest.TestCase):
    def test_python_311_excludes_known_broken_pyside_bindings(self):
        root = Path(__file__).resolve().parents[1]
        metadata = tomllib.loads((root / "pyproject.toml").read_text())
        requirements = metadata["project"]["dependencies"]
        self.assertIn("PySide6>=6.8,<6.12; python_version < '3.12'", requirements)
        self.assertIn("PySide6>=6.8,<7; python_version >= '3.12'", requirements)

    def test_repeated_ui_calls_exit_without_singleton_refcount_crash(self):
        # A subprocess is essential: the bad wheels can pass assertions but
        # abort at interpreter finalization. No project transport is involved.
        code = """
from PySide6.QtWidgets import QApplication, QPushButton
app = QApplication([])
button = QPushButton("Binding regression")
button.show()
app.processEvents()
for index in range(20000):
    button.setEnabled(bool(index % 2))
    button.repaint()
button.close()
app.processEvents()
"""
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
