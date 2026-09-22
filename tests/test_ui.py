import json
import unittest

from ui import EventRenderer


class EventRendererTests(unittest.TestCase):
    def test_friendly_file_event_hides_secrets(self):
        event = EventRenderer().start("read_file", {"path": "/tmp/.env", "token": "secret-value"})
        self.assertIn("File read", event)
        self.assertNotIn("secret-value", event)

    def test_debug_event_is_structured_and_redacted(self):
        event = EventRenderer(debug=True).result(
            "run_command", {"error": "token=secret-value", "code": "FAILED"}, 12.5
        )
        payload = json.loads(event.removeprefix("[DEBUG] "))
        self.assertEqual(payload["event"], "tool_result")
        self.assertEqual(payload["duration_ms"], 12.5)
        self.assertNotIn("secret-value", event)


if __name__ == "__main__":
    unittest.main()
