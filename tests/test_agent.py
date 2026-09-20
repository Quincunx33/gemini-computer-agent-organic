import unittest

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


if __name__ == "__main__":
    unittest.main()
