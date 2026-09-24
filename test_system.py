import time
import unittest
import threading
import json
import urllib.request
from task_queue_system.queue_engine import QueueEngine, TaskState
from task_queue_system.server import run_server, engine as server_engine

class TestQueueEngine(unittest.TestCase):
    def setUp(self):
        self.engine = QueueEngine(num_workers=2)
        self.engine.register_handler("echo", lambda p: p)
        self.engine.register_handler("add", lambda p: p["x"] + p["y"])
        def flaky(p):
            if p.get("attempts", 0) < 1:
                p["attempts"] = p.get("attempts", 0) + 1
                raise ValueError("temporary error")
            return "success"
        self.engine.register_handler("flaky", flaky)
        self.engine.start()

    def tearDown(self):
        self.engine.stop()

    def test_successful_task(self):
        task = self.engine.submit_task("echo", {"message": "hello"})
        # wait for completion
        start = time.time()
        while task.state not in (TaskState.COMPLETED, TaskState.FAILED):
            time.sleep(0.01)
            if time.time() - start > 2.0:
                break
        
        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(task.result, {"message": "hello"})

    def test_priority_ordering(self):
        execution_order = []
        lock = threading.Lock()

        def ordered_handler(p):
            with lock:
                execution_order.append(p["id"])

        self.engine.register_handler("ordered", ordered_handler)
        
        # Stop workers temporarily or submit with workers paused
        # Instead, let's submit tasks with low worker count and inspect
        # To test priority cleanly, let's submit lower priority first, then higher priority
        t1 = self.engine.submit_task("ordered", {"id": "low"}, priority=1)
        t2 = self.engine.submit_task("ordered", {"id": "high"}, priority=10)
        t3 = self.engine.submit_task("ordered", {"id": "medium"}, priority=5)

        time.sleep(0.5)
        with lock:
            # High priority should execute before low priority
            self.assertIn("high", execution_order)
            self.assertIn("medium", execution_order)
            self.assertIn("low", execution_order)
            self.assertEqual(execution_order[0], "high")

    def test_retry_and_failure(self):
        task = self.engine.submit_task("flaky", {"attempts": 0}, max_retries=2, retry_delay=0.01)
        start = time.time()
        while task.state not in (TaskState.COMPLETED, TaskState.FAILED):
            time.sleep(0.01)
            if time.time() - start > 2.0:
                break

        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(task.result, "success")
        self.assertGreaterEqual(task.attempts, 2)

    def test_cancellation(self):
        # Register a slow task
        self.engine.register_handler("slow", lambda p: time.sleep(0.5))
        task = self.engine.submit_task("slow")
        time.sleep(0.05)
        success = self.engine.cancel_task(task.id)
        self.assertTrue(success)
        self.assertEqual(task.state, TaskState.CANCELLED)

class TestRestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8999
        # Start server in daemon thread
        server_engine.num_workers = 2
        server_engine.register_handler("ping", lambda p: {"pong": True})
        server_engine.start()
        
        from http.server import HTTPServer
        from task_queue_system.server import TaskHTTPHandler
        cls.httpd = HTTPServer(("0.0.0.0", cls.port), TaskHTTPHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server_engine.stop()

    def _request(self, method, endpoint, data=None):
        url = f"http://localhost:{self.port}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method=method)
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_health_endpoint(self):
        status, data = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "healthy")

    def test_submit_and_get_task(self):
        # Submit task
        status, resp = self._request("POST", "/api/tasks", {
            "name": "ping",
            "payload": {},
            "priority": 3
        })
        self.assertEqual(status, 201)
        task_id = resp["id"]
        self.assertEqual(resp["name"], "ping")

        # Wait for completion & get task
        time.sleep(0.2)
        status, task_data = self._request("GET", f"/api/tasks/{task_id}")
        self.assertEqual(status, 200)
        self.assertEqual(task_data["state"], "completed")
        self.assertEqual(task_data["result"], {"pong": True})

    def test_metrics_endpoint(self):
        status, data = self._request("GET", "/api/metrics")
        self.assertEqual(status, 200)
        self.assertIn("submitted", data)
        self.assertIn("completed", data)

if __name__ == "__main__":
    unittest.main()
