import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from text_safety import configure_terminal, safe_text, safe_value
from tools.terminal import run_command


class TextSafetyTests(unittest.TestCase):
    def test_safe_text_replaces_lone_surrogates(self):
        value = safe_text("device\ud83d\udca9")
        self.assertNotIn("\ud83d", value)
        self.assertNotIn("\udca9", value)
        value.encode("utf-8")

    def test_safe_value_sanitizes_nested_results(self):
        value = safe_value({"stdout": "bad\ud800", "items": ["ok\udfff"]})
        self.assertEqual(value, {"stdout": "bad", "items": ["ok"]})

    def test_terminal_command_output_is_utf8_safe(self):
        result = run_command("printf '\\377'", approved=True)
        self.assertEqual(result["exit_code"], 0)
        result["stdout"].encode("utf-8")

    def test_terminal_configuration_does_not_raise(self):
        stream = io.StringIO()
        with redirect_stdout(stream), redirect_stderr(stream):
            configure_terminal()
            print("safe")
        self.assertEqual(stream.getvalue(), "safe\n")


if __name__ == "__main__":
    unittest.main()
