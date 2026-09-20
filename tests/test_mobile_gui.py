import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from mobile_server import CommandHandler
from tools.gui_control import gui_capabilities
from http.server import ThreadingHTTPServer


class MobileGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CommandHandler)
        cls.server.agent_token = "test-token"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_capabilities_are_public(self):
        with urlopen(self.base + "/capabilities", timeout=3) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["ok"])
        self.assertIn("platform", payload["capabilities"])

    def test_command_requires_bearer_token(self):
        request = Request(self.base + "/command", data=b'{"task":"status"}',
                          headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(HTTPError) as context:
            urlopen(request, timeout=3)
        self.assertEqual(context.exception.code, 401)

    def test_gui_report_is_structured(self):
        report = gui_capabilities()
        self.assertIn("pyautogui_installed", report)
        self.assertIn("ocr_engine", report)


if __name__ == "__main__":
    unittest.main()
