import unittest

from tools.terminal import run_command


class ToolTests(unittest.TestCase):
    def test_command(self):
        result = run_command("printf hello", approved=True)
        self.assertEqual(result["exit_code"], 0)
        self.assertEqual(result["stdout"], "hello")

    def test_timeout(self):
        result = run_command("sleep 1", timeout=0.05, approved=True)
        self.assertTrue(result["timed_out"])


if __name__ == "__main__":
    unittest.main()
