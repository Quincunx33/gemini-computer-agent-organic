import unittest

from openai_compatible import OpenAICompatibleClient


class ProviderTests(unittest.TestCase):
    def test_openai_compatible_tool_call_parsing(self):
        result = OpenAICompatibleClient.parse_response({
            "choices": [{"message": {"content": "", "tool_calls": [{"function": {"name": "read_file", "arguments": "{\"path\": \"README.md\"}"}}]}}]
        })
        self.assertEqual(result["type"], "tool_call")
        self.assertEqual(result["tool_calls"][0]["name"], "read_file")
        self.assertEqual(result["tool_calls"][0]["args"]["path"], "README.md")

    def test_text_response_contract_matches_agent_loop(self):
        result = OpenAICompatibleClient.parse_response({"choices": [{"message": {"content": "hello"}}]})
        self.assertEqual(result, {"type": "text", "text": "hello", "tool_calls": []})

    def test_each_compatible_provider_has_primary_and_fallback_model(self):
        for provider, expected in {
            "openai": "gpt-5.6-terra",
            "xai": "grok-4.6",
            "deepseek": "deepseek-v4-pro",
        }.items():
            client = OpenAICompatibleClient(provider, api_key="test")
            self.assertGreaterEqual(len(client.models), 2)
            self.assertEqual(client.models[1], expected)


if __name__ == "__main__":
    unittest.main()
