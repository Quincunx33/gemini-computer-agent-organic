import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from tools.filesystem import patch_file

class PatchFileTests(unittest.TestCase):
    def test_patch_file_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "sample.py"
            target.write_text("x = 10\ny = 20\n", encoding="utf-8")
            with patch("tools.filesystem.settings", SimpleNamespace(workspace=root, host_mode=False, max_file_size=1024*1024, denied_paths="", allowed_paths="")):
                res = patch_file(str(target), "y = 20", "y = 42")
                self.assertTrue(res["ok"])
                self.assertEqual(target.read_text(encoding="utf-8"), "x = 10\ny = 42\n")

    def test_patch_file_not_found(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "sample.py"
            target.write_text("x = 10\n", encoding="utf-8")
            with patch("tools.filesystem.settings", SimpleNamespace(workspace=root, host_mode=False, max_file_size=1024*1024, denied_paths="", allowed_paths="")):
                res = patch_file(str(target), "non_existent = 1", "replacement")
                self.assertFalse(res["ok"])
                self.assertIn("not found", res["error"])

if __name__ == "__main__":
    unittest.main()
