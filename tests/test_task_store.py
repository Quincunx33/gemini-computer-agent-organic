import tempfile
import unittest
from pathlib import Path

from agent_loop import AgentLoop
from task_store import TaskStore


class SequenceClient:
    def __init__(self):
        self.responses = [
            {"type": "tool_call", "text": "", "tool_calls": [{"name": "platform_info", "args": {}}]},
            {"type": "text", "text": "task complete", "tool_calls": []},
        ]

    def generate(self, *_args, **_kwargs):
        return self.responses.pop(0)


class TaskStoreTests(unittest.TestCase):
    def test_task_is_persisted_and_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.sqlite3")
            loop = AgentLoop(SequenceClient(), output=lambda _value: None, store=store)
            result = loop.run("inspect platform")
            saved = store.load(loop.last_task_id)
            self.assertEqual(result, "task complete")
            self.assertEqual(saved["status"], "completed")
            self.assertGreaterEqual(saved["step"], 2)

    def test_missing_resume_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            loop = AgentLoop(SequenceClient(), output=lambda _value: None, store=TaskStore(Path(directory) / "tasks.sqlite3"))
            self.assertIn("Task not found", loop.resume("missing"))


if __name__ == "__main__":
    unittest.main()
