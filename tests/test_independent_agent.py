import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from git_tools import preview_diff
from plugin_manager import PluginError, PluginManager
from tools.project_verify import verify_project


class IndependentAgentTests(unittest.TestCase):
    def test_project_verifier_reports_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests" / "test_ok.py").write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\n", encoding="utf-8")
            with patch("tools.project_verify.settings", SimpleNamespace(workspace=root, command_timeout=30, max_output_chars=2000)):
                result = verify_project()
        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "PASS")

    def test_diff_preview_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("git_tools.settings", SimpleNamespace(workspace=Path(directory))):
                result = preview_diff()
        self.assertFalse(result["ok"])

    def test_plugin_cannot_request_auto_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("plugin.json", json.dumps({"name": "unsafe", "version": "1", "auto_execute": True}))
            with self.assertRaises(PluginError):
                PluginManager(root / "plugins").install_zip(str(archive))


if __name__ == "__main__":
    unittest.main()
