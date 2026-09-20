import tempfile
import unittest
from pathlib import Path

from agent_loop import AgentLoop
from memory import Memory
from task_store import TaskStore


class OrganicAgentTests(unittest.TestCase):
    def test_memory_retrieves_relevant_context_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            memory = Memory(Path(directory) / "memory.sqlite3")
            memory.save("preference", {"workspace": "demo", "API_KEY": "hidden"})
            memory.save("unrelated", "weather")
            context = memory.context("workspace demo")
            self.assertIn("preference", context)
            self.assertIn("[REDACTED]", context)
            self.assertNotIn("hidden", context)

    def test_repeated_tool_call_gets_a_recovery_observation(self):
        class RepeatingClient:
            def __init__(self):
                self.calls = 0

            def generate(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls <= 3:
                    return {"type": "tool_call", "text": "", "tool_calls": [
                        {"name": "platform_info", "args": {}}
                    ]}
                return {"type": "text", "text": "I recovered and finished.", "tool_calls": []}

        outputs = []
        with tempfile.TemporaryDirectory() as directory:
            loop = AgentLoop(
                RepeatingClient(),
                output=outputs.append,
                store=TaskStore(Path(directory) / "tasks.sqlite3"),
                memory=Memory(Path(directory) / "memory.sqlite3"),
            )
            self.assertEqual(loop.run("inspect the platform"), "I recovered and finished.")
        self.assertTrue(any("repeatedly" in str(item) for item in outputs))


if __name__ == "__main__":
    unittest.main()
