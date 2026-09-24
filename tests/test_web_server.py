import unittest
import threading
import urllib.request
import json
import time
from web_server import GenAgentWebHandler, HTTPServer

class TestWebServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        HTTPServer.allow_reuse_address = True
        cls.server = HTTPServer(("127.0.0.1", 8199), GenAgentWebHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_01_index_html(self):
        req = urllib.request.Request("http://127.0.0.1:8199/")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertEqual(resp.headers.get("Content-Type"), "text/html; charset=utf-8")
            body = resp.read().decode("utf-8")
            self.assertIn("GENAGENT", body)
            self.assertIn("Settings", body)
            self.assertIn("cfg-api-key", body)

    def test_02_api_status(self):
        req = urllib.request.Request("http://127.0.0.1:8199/api/status")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("model", data)
            self.assertIn("platform", data)
            self.assertIn("workspace", data)

    def test_03_api_config_get_and_post(self):
        # 1. GET config
        req_get = urllib.request.Request("http://127.0.0.1:8199/api/config")
        with urllib.request.urlopen(req_get) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("is_configured", data)
            self.assertIn("api_key_masked", data)
            self.assertIn("model", data)

        # 2. POST config
        payload = json.dumps({"model": "gemini-flash-lite-latest", "autonomy_mode": "trusted"}).encode("utf-8")
        req_post = urllib.request.Request("http://127.0.0.1:8199/api/config", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_post) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res["ok"])

    def test_04_api_verify_key(self):
        payload = json.dumps({"model": "gemini-flash-lite-latest"}).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8199/api/verify_key", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res = json.loads(resp.read().decode("utf-8"))
            self.assertIn("ok", res)
            self.assertIn("message", res)

    def test_05_api_files(self):
        req = urllib.request.Request("http://127.0.0.1:8199/api/files")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("files", data)
            self.assertIsInstance(data["files"], list)

    def test_06_api_file_read_write(self):
        payload = json.dumps({"path": "web_test_tmp.txt", "content": "hello web test"}).encode("utf-8")
        req_post = urllib.request.Request("http://127.0.0.1:8199/api/file", data=payload, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_post) as resp:
            self.assertEqual(resp.status, 200)

        req_get = urllib.request.Request("http://127.0.0.1:8199/api/file?path=web_test_tmp.txt")
        with urllib.request.urlopen(req_get) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data["content"], "hello web test")

        import os
        if os.path.exists("web_test_tmp.txt"):
            os.remove("web_test_tmp.txt")

if __name__ == "__main__":
    unittest.main()
