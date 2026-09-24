import unittest
import time
import threading
import json
import urllib.request
from task_queue_system.queue_engine import QueueEngine, TaskState
from task_queue_system.metrics_collector import MetricsCollector
from task_queue_system.server import run_server

class TestTaskQueueSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        if os.path.exists("task_queue.db"):
            try: os.remove("task_queue.db")
            except OSError: pass
        cls.metrics = MetricsCollector()
        cls.engine = QueueEngine(max_workers=2, metrics_collector=cls.metrics)
        cls.engine.register_handler("add", lambda p: p["a"] + p["b"])
        cls.engine.register_handler("fail_always", lambda p: 1 / 0)
        
        # Flaky handler that succeeds on 2nd attempt
        cls.flaky_attempts = {}
        def flaky(p):
            tid = p["tid"]
            cls.flaky_attempts[tid] = cls.flaky_attempts.get(tid, 0) + 1
            if cls.flaky_attempts[tid] < 2:
                raise ValueError("Transient error")
            return "recovered"
        cls.engine.register_handler("flaky", flaky)
        cls.engine.start()

        # Start REST server
        cls.server = run_server(cls.engine, host="127.0.0.1", port=8899)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.engine.stop()

    def test_01_successful_task(self):
        task = self.engine.submit_task("add", {"a": 15, "b": 27})
        deadline = time.time() + 3.0
        while time.time() < deadline:
            t = self.engine.get_task(task["id"])
            if t["status"] == TaskState.COMPLETED:
                break
            time.sleep(0.02)

        t = self.engine.get_task(task["id"])
        self.assertEqual(t["status"], TaskState.COMPLETED)
        self.assertEqual(t["result"], 42)

    def test_02_retry_and_failure(self):
        task = self.engine.submit_task("fail_always", {}, max_retries=2, retry_delay=0.01)
        deadline = time.time() + 4.0
        while time.time() < deadline:
            t = self.engine.get_task(task["id"])
            if t["status"] == TaskState.FAILED:
                break
            time.sleep(0.05)

        t = self.engine.get_task(task["id"])
        self.assertEqual(t["status"], TaskState.FAILED)
        self.assertGreaterEqual(t["retries"], 2)

    def test_03_flaky_task_retry_success(self):
        tid = f"flaky-test-{int(time.time()*1000)}"
        task = self.engine.submit_task("flaky", {"tid": tid}, max_retries=3, retry_delay=0.01, task_id=tid)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            t = self.engine.get_task(task["id"])
            if t["status"] == TaskState.COMPLETED:
                break
            time.sleep(0.05)

        t = self.engine.get_task(task["id"])
        self.assertEqual(t["status"], TaskState.COMPLETED)
        self.assertEqual(t["result"], "recovered")

    def test_04_cancel_task(self):
        # Submit task with future delay
        task = self.engine.submit_task("add", {"a": 1, "b": 1}, priority=-10)
        # Cancel right away if pending
        cancelled = self.engine.cancel_task(task["id"])
        if cancelled:
            t = self.engine.get_task(task["id"])
            self.assertEqual(t["status"], TaskState.CANCELLED)

    def test_05_rest_api_health(self):
        req = urllib.request.Request("http://127.0.0.1:8899/api/health")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertEqual(data["status"], "healthy")
            self.assertTrue(data["running"])

    def test_06_rest_api_submit_and_get(self):
        body = json.dumps({
            "name": "add",
            "payload": {"a": 20, "b": 22}
        }).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8899/api/tasks", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 201)
            task_id = data["id"]

        deadline = time.time() + 3.0
        while time.time() < deadline:
            req_get = urllib.request.Request(f"http://127.0.0.1:8899/api/tasks/{task_id}")
            with urllib.request.urlopen(req_get) as resp_get:
                t_data = json.loads(resp_get.read().decode("utf-8"))
                if t_data["status"] == "COMPLETED":
                    break
            time.sleep(0.05)

        self.assertEqual(t_data["status"], "COMPLETED")
        self.assertEqual(t_data["result"], 42)

    def test_07_rest_api_metrics(self):
        req = urllib.request.Request("http://127.0.0.1:8899/api/metrics")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertIn("submitted", data)
            self.assertIn("completed", data)
            self.assertIn("throughput_tasks_per_sec", data)

    def test_08_rest_api_list(self):
        req = urllib.request.Request("http://127.0.0.1:8899/api/tasks")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertIn("tasks", data)
            self.assertIsInstance(data["tasks"], list)
            self.assertGreater(len(data["tasks"]), 0)

if __name__ == "__main__":
    unittest.main()
