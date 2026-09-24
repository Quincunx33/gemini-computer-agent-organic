import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools.self_update import self_update

class SelfUpdateTests(unittest.TestCase):
    def test_valid_update_creates_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sample.py"
            target.write_text("value = 1\n", encoding="utf-8")
            config = SimpleNamespace(workspace=root, max_file_size=1024 * 1024, host_mode=False, denied_paths="", allowed_paths="")
            with patch("tools.self_update.settings", config), patch("tools.filesystem.settings", config):
                result = self_update("sample.py", "value = 2\n")
            self.assertTrue(result["ok"])
            self.assertEqual(target.read_text(encoding="utf-8"), "value = 2\n")
            self.assertTrue(Path(result["backup"]).exists())

    def test_invalid_python_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "sample.py"
            target.write_text("value = 1\n", encoding="utf-8")
            config = SimpleNamespace(workspace=root, max_file_size=1024 * 1024, host_mode=False, denied_paths="", allowed_paths="")
            with patch("tools.self_update.settings", config), patch("tools.filesystem.settings", config):
                result = self_update("sample.py", "value =\n")
            self.assertFalse(result["ok"])
            self.assertTrue(result["rolled_back"])
            self.assertEqual(target.read_text(encoding="utf-8"), "value = 1\n")

if __name__ == "__main__":
    unittest.main()
