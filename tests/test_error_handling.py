import json
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from errors import AgentError, normalize_exception
from gemini_client import GeminiClient
from config import settings
from planner import tools_for_task
from agent_loop import AgentLoop
from memory import Memory
from task_store import TaskStore


class ErrorHandlingTests(unittest.TestCase):
    def test_network_error_is_retryable_and_public_message_is_safe(self):
        error = normalize_exception(URLError("API key=super-secret connection refused"), operation="API request")
        self.assertEqual(error.code, "NETWORK_ERROR")
        self.assertTrue(error.retryable)
        self.assertNotIn("super-secret", error.public_message)

    def test_http_auth_error_does_not_retry_or_leak_key(self):
        response = BytesIO(b'{"error":{"message":"bad key"}}')
        failure = HTTPError("https://example.test", 401, "Unauthorized", {}, response)
        with patch("gemini_client.urlopen", side_effect=failure):
            result = GeminiClient(api_key="super-secret", model="test-model").generate("hello", [])
        self.assertEqual(result["type"], "error")
        self.assertEqual(result["error"]["code"], "API_AUTH_ERROR")
        self.assertNotIn("super-secret", json.dumps(result))

    def test_missing_api_key_is_structured(self):
        result = GeminiClient(api_key="", model="test-model").generate("hello", [])
        self.assertEqual(result["type"], "error")
        self.assertEqual(result["error"]["code"], "NOT_CONFIGURED")

    def test_error_payload_has_correlation_id(self):
        error = AgentError("TEST", "internal secret=hidden", "safe message")
        self.assertEqual(error.to_dict()["error"]["message"], "safe message")
        self.assertTrue(error.to_dict()["error"]["error_id"])

    def test_history_is_bounded_to_newest_context(self):
        history = [{"role": "tool", "content": {"result": "x" * settings.max_tool_result_chars}} for _ in range(20)]
        contents = GeminiClient._history_contents(history)
        serialized_size = sum(len(item["parts"][0]["text"]) for item in contents)
        self.assertLessEqual(serialized_size, settings.max_history_chars)
        self.assertLessEqual(len(contents), settings.max_history_chars // settings.max_tool_result_chars + 1)

    def test_read_task_gets_small_tool_schema(self):
        tools = tools_for_task("read and inspect the project")
        names = {tool["name"] for tool in tools}
        self.assertIn("read_file", names)
        self.assertNotIn("type_text", names)
        self.assertLess(len(tools), 16)

    def test_simple_task_routes_fast_model_first(self):
        client = GeminiClient(api_key="test-key", model="primary-model")
        client.set_task_route("show project status")
        self.assertEqual(client.models[0], settings.fast_model)

    def test_repeated_tool_result_is_deduplicated(self):
        class SequenceClient:
            def __init__(self):
                self.responses = [
                    {"type": "tool_call", "text": "", "tool_calls": [{"name": "platform_info", "args": {}}]},
                    {"type": "tool_call", "text": "", "tool_calls": [{"name": "platform_info", "args": {}}]},
                    {"type": "text", "text": "done", "tool_calls": []},
                ]

            def generate(self, *_args, **_kwargs):
                return self.responses.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            store = TaskStore(Path(directory) / "tasks.sqlite3")
            loop = AgentLoop(SequenceClient(), output=lambda _value: None, store=store, memory=Memory(Path(directory) / "memory.sqlite3"))
            self.assertEqual(loop.run("inspect status"), "done")
            saved = store.load(loop.last_task_id)
            self.assertTrue(any(item.get("content", {}).get("result", {}).get("deduplicated") for item in saved["history"] if item.get("role") == "tool"))


if __name__ == "__main__":
    unittest.main()
