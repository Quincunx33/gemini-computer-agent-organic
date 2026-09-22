import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from plugin_manager import PluginManager
from tools.fallbacks import install_and_verify
from web_search import search_web
from subagents import run_parallel


class ExtensionsTests(unittest.TestCase):
    def test_plugin_requires_manifest_and_does_not_execute(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "plugin.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("plugin.json", json.dumps({"name": "demo", "version": "1.0"}))
                bundle.writestr("run.py", "raise RuntimeError('must not execute')")
            result = PluginManager(root / "plugins").install_zip(str(archive))
            self.assertTrue(result["ok"])
            self.assertFalse(result["executed"])
            self.assertTrue((root / "plugins" / "demo" / "run.py").exists())

    def test_web_search_extracts_sources(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, *_args): return b'<a href="https://example.com">Example result</a>'
        with patch("web_search.urlopen", return_value=Response()):
            result = search_web("safe query")
        self.assertTrue(result["ok"])
        self.assertEqual(result["results"][0]["url"], "https://example.com")

    def test_auto_install_is_opt_in(self):
        with patch("tools.fallbacks.settings", SimpleNamespace(auto_install=False)):
            result = install_and_verify("ffmpeg")
        self.assertFalse(result["ok"])
        self.assertFalse(result["install_attempted"])

    def test_existing_tool_is_not_reinstalled(self):
        with patch("tools.fallbacks.verify_tool", return_value={"ok": True, "version": "v1"}):
            result = install_and_verify("node")
        self.assertTrue(result["ok"])
        self.assertFalse(result["install_attempted"])

    def test_empty_parallel_task_list_is_safe(self):
        self.assertFalse(run_parallel([])["ok"])


if __name__ == "__main__":
    unittest.main()
