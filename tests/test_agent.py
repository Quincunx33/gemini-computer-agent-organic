import unittest
from unittest.mock import patch

from agent_loop import AgentLoop


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate(self, *args, **kwargs):
        self.calls += 1
        return {"type": "text", "text": "done", "tool_calls": []}


class AgentTests(unittest.TestCase):
    def test_loop(self):
        self.assertEqual(AgentLoop(FakeClient(), output=lambda _value: None).run("hello"), "done")

    def test_read_file_result_is_redacted_before_model_context(self):
        loop = AgentLoop(FakeClient(), output=lambda _value: None)
        with patch("agent_loop.read_file", return_value="GEMINI_API_KEY=super-secret\nvisible=value"):
            result = loop.execute("read_file", {"path": "config.txt"})
        self.assertNotIn("super-secret", result["content"])
        self.assertIn("[REDACTED]", result["content"])

    def test_terminate_process_does_not_double_prompt(self):
        loop = AgentLoop(FakeClient(), output=lambda _value: None)
        with patch("builtins.input", return_value="y") as prompt, patch("agent_loop.terminate_process", return_value={"ok": True}) as terminate:
            loop.execute("terminate_process", {"pid": 1234})
        prompt.assert_called_once()
        terminate.assert_called_once_with(1234, approved=True)


if __name__ == "__main__":
    unittest.main()
