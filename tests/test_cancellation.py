import tempfile
import unittest
from pathlib import Path

from agent_loop import AgentLoop
from memory import Memory
from task_store import TaskStore


class CancelClient:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, tools, history, cancel_event=None):
        self.calls += 1
        if cancel_event is not None:
            cancel_event.set()
        return {"type": "text", "text": "should not complete", "tool_calls": []}


class CancellationTests(unittest.TestCase):
    def test_cancelled_model_request_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.sqlite3")
            loop = AgentLoop(
                CancelClient(), output=lambda _value: None, store=store,
                memory=Memory(Path(directory) / "memory.sqlite3"), debug=False,
            )
            result = loop.run("inspect status")
            self.assertIn("cancelled", result.lower())
            saved = store.load(loop.last_task_id)
            self.assertEqual(saved["status"], "cancelled")

    def test_cancel_method_stops_before_model_call(self):
        client = CancelClient()
        loop = AgentLoop(client, output=lambda _value: None)
        loop.cancel()
        result = loop.run("inspect status")
        self.assertIn("cancelled", result.lower())
        self.assertEqual(client.calls, 0)


if __name__ == "__main__":
    unittest.main()
