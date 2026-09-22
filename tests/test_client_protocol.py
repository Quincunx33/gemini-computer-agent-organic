import json
import unittest
from unittest.mock import patch

from gemini_client import GeminiClient
from agent_loop import AgentLoop


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class ProtocolTests(unittest.TestCase):
    def test_json_text_tool_call_is_normalized(self):
        payload = {
            "candidates": [{
                "content": {"parts": [{"text": json.dumps({
                    "type": "tool_call",
                    "text": "",
                    "tool_calls": [{"name": "platform_info", "args": {}}],
                })}]}
            }]
        }
        with patch("gemini_client.urlopen", return_value=FakeResponse(payload)):
            result = GeminiClient(api_key="test-key", model="test-model").generate("inspect", [])
        self.assertEqual(result["type"], "tool_call")
        self.assertEqual(result["tool_calls"][0]["name"], "platform_info")

    def test_loop_continues_after_tool_call(self):
        class SequenceClient:
            def __init__(self):
                self.responses = [
                    {"type": "tool_call", "text": "", "tool_calls": [{"name": "platform_info", "args": {}}]},
                    {"type": "text", "text": "summary complete", "tool_calls": []},
                ]

            def generate(self, *_args, **_kwargs):
                return self.responses.pop(0)

        result = AgentLoop(SequenceClient(), output=lambda _value: None).run("inspect")
        self.assertEqual(result, "summary complete")

    def test_final_text_response_is_cached(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "cached answer"}]}}]}
        client = GeminiClient(api_key="test-key", model="test-model")
        with patch("gemini_client.urlopen", return_value=FakeResponse(payload)) as request:
            first = client.generate("same", [])
            second = client.generate("same", [])
        self.assertEqual(first, second)
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
