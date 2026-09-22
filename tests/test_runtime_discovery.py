import unittest
from unittest.mock import patch

from tools.fallbacks import find_alternatives, verify_tool
from planner import tools_for_task


class RuntimeDiscoveryTests(unittest.TestCase):
    def test_missing_tool_has_stable_fallback_contract(self):
        with patch("tools.fallbacks.shutil.which", return_value=None):
            result = find_alternatives("rg")
        self.assertIn("alternatives", result)
        self.assertIn("install_attempted", result)
        self.assertFalse(result["install_attempted"])
        self.assertIn("package_candidates", result)

    def test_existing_tool_reports_version(self):
        with patch("tools.fallbacks.shutil.which", return_value="/usr/bin/node"), patch("tools.fallbacks.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = "v22.1.0\n"
            run.return_value.stderr = ""
            result = verify_tool("node")
        self.assertTrue(result["ok"])
        self.assertEqual(result["version"], "v22.1.0")

    def test_lifecycle_tools_are_exposed_for_file_task(self):
        names = {tool["name"] for tool in tools_for_task("create, move, run, and delete a test file")}
        self.assertTrue({"create_file", "move_file", "delete_file", "run_command"}.issubset(names))


if __name__ == "__main__":
    unittest.main()
