import os

os.makedirs("task_queue_system", exist_ok=True)

# 1. queue_engine.py
queue_engine_code = '''import time
import uuid
import threading
import heapq
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Callable, Optional, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("QueueEngine")

class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"

@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "default_task"
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher number = higher priority
    max_retries: int = 3
    retry_delay: float = 0.05  # seconds
    state: TaskState = TaskState.PENDING
    attempts: int = 0
    result: Any = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "payload": self.payload,
            "priority": self.priority,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "state": self.state.value,
            "attempts": self.attempts,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at
        }

class QueueEngine:
    def __init__(self, num_workers: int = 4):
        self.num_workers = num_workers
        self.tasks: Dict[str, Task] = {}
        self.tasks_lock = threading.Lock()
        
        self._heap: List[Tuple[int, int, Task]] = []
        self._counter = 0
        self._queue_lock = threading.Lock()
        self._cond = threading.Condition(self._queue_lock)
        
        self.registry: Dict[str, Callable[[Dict[str, Any]], Any]] = {}
        self.running = False
        self.workers: List[threading.Thread] = []
        
        self.metrics = {
            "submitted": 0,
            "completed": 0,
            "failed": 0,
            "retried": 0,
            "cancelled": 0
        }
        self.metrics_lock = threading.Lock()

    def register_handler(self, name: str, func: Callable[[Dict[str, Any]], Any]):
        self.registry[name] = func
        logger.info(f"Registered task handler: {name}")

    def start(self):
        with self._queue_lock:
            if self.running:
                return
            self.running = True
        
        self.workers = []
        for i in range(self.num_workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"Worker-{i}")
            t.start()
            self.workers.append(t)
        logger.info(f"QueueEngine started with {self.num_workers} workers.")

    def stop(self, timeout: float = 5.0):
        with self._queue_lock:
            if not self.running:
                return
            self.running = False
            self._cond.notify_all()

        for t in self.workers:
            t.join(timeout=timeout)
        logger.info("QueueEngine stopped.")

    def submit_task(self, name: str, payload: Optional[Dict[str, Any]] = None, priority: int = 0, max_retries: int = 3, retry_delay: float = 0.05, task_id: Optional[str] = None) -> Task:
        task = Task(
            id=task_id or str(uuid.uuid4()),
            name=name,
            payload=payload or {},
            priority=priority,
            max_retries=max_retries,
            retry_delay=retry_delay,
            state=TaskState.PENDING
        )

        with self.tasks_lock:
            self.tasks[task.id] = task

        with self.metrics_lock:
            self.metrics["submitted"] += 1

        with self._queue_lock:
            self._counter += 1
            heapq.heappush(self._heap, (-task.priority, self._counter, task))
            self._cond.notify()

        logger.info(f"Submitted task {task.id} ('{task.name}') with priority {priority}")
        return task

    def cancel_task(self, task_id: str) -> bool:
        with self.tasks_lock:
            task = self.tasks.get(task_id)
            if not task:
                return False
            if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                return False
            task.state = TaskState.CANCELLED
            task.finished_at = time.time()

        with self.metrics_lock:
            self.metrics["cancelled"] += 1
        logger.info(f"Cancelled task {task_id}")
        return True

    def get_task(self, task_id: str) -> Optional[Task]:
        with self.tasks_lock:
            return self.tasks.get(task_id)

    def list_tasks(self) -> List[Task]:
        with self.tasks_lock:
            return list(self.tasks.values())

    def get_metrics(self) -> Dict[str, int]:
        with self.metrics_lock:
            m = dict(self.metrics)
        with self._queue_lock:
            m["queue_size"] = len(self._heap)
        with self.tasks_lock:
            m["total_tracked"] = len(self.tasks)
        return m

    def _worker_loop(self):
        while True:
            with self._queue_lock:
                while self.running and not self._heap:
                    self._cond.wait()
                
                if not self.running and not self._heap:
                    break

                _, _, task = heapq.heappop(self._heap)

            # Check if task was cancelled while pending in queue
            with self.tasks_lock:
                if task.state == TaskState.CANCELLED:
                    continue

            self._execute_task(task)

    def _execute_task(self, task: Task):
        handler = self.registry.get(task.name)
        if not handler:
            with self.tasks_lock:
                task.state = TaskState.FAILED
                task.error = f"No handler registered for task name '{task.name}'"
                task.finished_at = time.time()
            with self.metrics_lock:
                self.metrics["failed"] += 1
            logger.error(task.error)
            return

        while True:
            with self.tasks_lock:
                if task.state == TaskState.CANCELLED:
                    return
                task.state = TaskState.RUNNING
                task.attempts += 1
                task.started_at = time.time()

            logger.info(f"Executing task {task.id} ('{task.name}'), attempt {task.attempts}/{task.max_retries + 1}")
            try:
                result = handler(task.payload)
                with self.tasks_lock:
                    task.state = TaskState.COMPLETED
                    task.result = result
                    task.finished_at = time.time()
                with self.metrics_lock:
                    self.metrics["completed"] += 1
                logger.info(f"Task {task.id} ('{task.name}') completed successfully.")
                return
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Task {task.id} ('{task.name}') failed on attempt {task.attempts}: {error_msg}")
                
                with self.tasks_lock:
                    task.error = error_msg

                if task.attempts <= task.max_retries:
                    with self.tasks_lock:
                        task.state = TaskState.RETRYING
                    with self.metrics_lock:
                        self.metrics["retried"] += 1
                    
                    time.sleep(task.retry_delay)
                    
                    # Check if cancelled during retry wait
                    with self.tasks_lock:
                        if task.state == TaskState.CANCELLED:
                            return
                    continue
                else:
                    with self.tasks_lock:
                        task.state = TaskState.FAILED
                        task.finished_at = time.time()
                    with self.metrics_lock:
                        self.metrics["failed"] += 1
                    logger.error(f"Task {task.id} ('{task.name}') permanently failed after {task.attempts} attempts.")
                    return
'''

with open("task_queue_system/queue_engine.py", "w") as f:
    f.write(queue_engine_code)

# 2. server.py
server_code = '''import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
from task_queue_system.queue_engine import QueueEngine, TaskState

# Global engine instance for server
engine = QueueEngine(num_workers=4)
# Register a sample default handler
engine.register_handler("echo", lambda payload: payload)
engine.register_handler("add", lambda p: p.get("a", 0) + p.get("b", 0))
engine.register_handler("fail_then_succeed", lambda p: _fail_then_succeed(p))

_attempt_tracker = {}
def _fail_then_succeed(payload):
    task_id = payload.get("task_id", "default")
    count = _attempt_tracker.get(task_id, 0) + 1
    _attempt_tracker[task_id] = count
    if count < 2:
        raise ValueError("Simulated transient failure")
    return {"success": True, "attempts": count}

class TaskHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._send_json(200, {"status": "healthy", "running": engine.running})
        elif path == "/api/metrics":
            self._send_json(200, engine.get_metrics())
        elif path == "/api/tasks":
            tasks = [t.to_dict() for t in engine.list_tasks()]
            self._send_json(200, {"tasks": tasks})
        elif path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            task = engine.get_task(task_id)
            if not task:
                self._send_json(404, {"error": "Task not found"})
            else:
                self._send_json(200, task.to_dict())
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/tasks":
            content_length = int(self.headers.get("Content-Length", 0))
            body_data = self.rfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(body_data.decode("utf-8"))
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Invalid JSON"})
                return

            name = data.get("name")
            if not name:
                self._send_json(400, {"error": "Missing task 'name'"})
                return

            payload = data.get("payload", {})
            priority = int(data.get("priority", 0))
            max_retries = int(data.get("max_retries", 3))
            retry_delay = float(data.get("retry_delay", 0.05))
            task_id = data.get("id")

            # Inject task_id into payload for handlers if helpful
            if isinstance(payload, dict) and "task_id" not in payload and task_id:
                payload["task_id"] = task_id

            task = engine.submit_task(
                name=name,
                payload=payload,
                priority=priority,
                max_retries=max_retries,
                retry_delay=retry_delay,
                task_id=task_id
            )
            self._send_json(201, task.to_dict())
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        if path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            success = engine.cancel_task(task_id)
            if not success:
                self._send_json(400, {"error": "Unable to cancel task (not found or already finished)"})
            else:
                self._send_json(200, {"status": "cancelled", "id": task_id})
        else:
            self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # Silence default HTTP server logging to keep test output clean
        pass

def run_server(port: int = 8899):
    engine.start()
    server = HTTPServer(("0.0.0.0", port), TaskHTTPHandler)
    print(f"REST Server started on port {port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.stop()
        print("REST Server stopped.")

if __name__ == "__main__":
    run_server()
'''

with open("task_queue_system/server.py", "w") as f:
    f.write(server_code)

# 3. cli.py
cli_code = '''import argparse
import json
import urllib.request
import urllib.error
import sys

DEFAULT_URL = "http://localhost:8899"

def api_request(method: str, endpoint: str, data: dict = None, port: int = 8899):
    url = f"http://localhost:{port}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            resp_body = resp.read().decode("utf-8")
            return resp.status, json.loads(resp_body) if resp_body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            err_json = json.loads(err_body)
        except:
            err_json = {"error": err_body}
        return e.code, err_json
    except urllib.error.URLError as e:
        print(f"Error connecting to server at {url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Task Queue System CLI Client")
    parser.add_argument("--port", type=int, default=8899, help="Server port (default: 8899)")
    
    subparsers = parser.add_subparsers(dest="command", required=True)

    # submit
    sub_submit = subparsers.add_parser("submit", help="Submit a new task")
    sub_submit.add_argument("--name", required=True, help="Task handler name")
    sub_submit.add_argument("--payload", default="{}", help="JSON payload string")
    sub_submit.add_argument("--priority", type=int, default=0, help="Priority (integer)")
    sub_submit.add_argument("--retries", type=int, default=3, help="Max retries")
    sub_submit.add_argument("--delay", type=float, default=0.05, help="Retry delay in seconds")

    # list
    subparsers.add_parser("list", help="List all tasks")

    # get
    sub_get = subparsers.add_parser("get", help="Get task details by ID")
    sub_get.add_argument("id", help="Task ID")

    # cancel
    sub_cancel = subparsers.add_parser("cancel", help="Cancel a pending or running task")
    sub_cancel.add_argument("id", help="Task ID")

    # metrics
    subparsers.add_parser("metrics", help="View queue metrics")

    # health
    subparsers.add_parser("health", help="Check server health")

    args = parser.parse_args()

    if args.command == "submit":
        try:
            payload_dict = json.loads(args.payload)
        except json.JSONDecodeError:
            print("Error: --payload must be valid JSON", file=sys.stderr)
            sys.exit(1)

        data = {
            "name": args.name,
            "payload": payload_dict,
            "priority": args.priority,
            "max_retries": args.retries,
            "retry_delay": args.delay
        }
        status, resp = api_request("POST", "/api/tasks", data, port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "list":
        status, resp = api_request("GET", "/api/tasks", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "get":
        status, resp = api_request("GET", f"/api/tasks/{args.id}", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "cancel":
        status, resp = api_request("DELETE", f"/api/tasks/{args.id}", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "metrics":
        status, resp = api_request("GET", "/api/metrics", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "health":
        status, resp = api_request("GET", "/api/health", port=args.port)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
'''

with open("task_queue_system/cli.py", "w") as f:
    f.write(cli_code)

# 4. test_system.py
test_code = '''import time
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
'''

with open("test_system.py", "w") as f:
    f.write(test_code)

print("All files successfully written via script!")
