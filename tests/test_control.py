import unittest

from platform_support import capabilities
from tools.control import list_processes


class ControlTests(unittest.TestCase):
    def test_capability_report(self):
        report = capabilities()
        self.assertIn("platform", report)
        self.assertIn("terminal", report)
        self.assertTrue(report["terminal"])

    def test_list_processes(self):
        result = list_processes()
        self.assertIn("exit_code", result)
        self.assertIsNotNone(result["stdout"] if result["exit_code"] == 0 else result.get("error"))


if __name__ == "__main__":
    unittest.main()
