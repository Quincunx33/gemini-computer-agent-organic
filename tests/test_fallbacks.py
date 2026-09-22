import unittest
from unittest.mock import patch

from tools.fallbacks import find_alternatives
from tools.terminal import run_command


class FallbackTests(unittest.TestCase):
    def test_missing_tool_gets_alternatives_without_install(self):
        with patch("tools.fallbacks.shutil.which", return_value=None):
            result = find_alternatives("rg")
        self.assertTrue(result["ok"])
        self.assertFalse(result["installed"])
        self.assertFalse(result["install_attempted"])
        self.assertTrue(result["alternatives"])

    def test_existing_tool_is_preferred(self):
        with patch("tools.fallbacks.shutil.which", return_value="/usr/bin/tool"):
            result = find_alternatives("custom-tool")
        self.assertTrue(result["alternatives"][0]["preferred"])

    def test_command_not_found_contains_ai_options(self):
        with patch("tools.terminal.safe_path", return_value="."), patch("tools.terminal.find_alternatives", return_value={"alternatives": [{"name": "grep"}]}):
            result = run_command("definitely_missing_genagent_command", approved=True)
        self.assertEqual(result["error"]["code"], "COMMAND_NOT_FOUND")
        self.assertEqual(result["error"]["alternatives"]["alternatives"][0]["name"], "grep")


if __name__ == "__main__":
    unittest.main()
