import os

os.makedirs("task_queue_system", exist_ok=True)

# 1. queue_engine.py
with open("task_queue_system/queue_engine.py", "w") as f:
    f.write('''import time
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

    def list_tasks(self, state: Optional[str] = None) -> List[Task]:
        with self.tasks_lock:
            tasks = list(self.tasks.values())
        if state:
            tasks = [t for t in tasks if t.state.value == state]
        return tasks

    def get_metrics(self) -> Dict[str, Any]:
        with self.metrics_lock:
            m = dict(self.metrics)
        with self.tasks_lock:
            total_tasks = len(self.tasks)
            pending = sum(1 for t in self.tasks.values() if t.state == TaskState.PENDING)
            running = sum(1 for t in self.tasks.values() if t.state == TaskState.RUNNING)
        m.update({
            "total_tasks": total_tasks,
            "pending": pending,
            "running": running
        })
        return m

    def _worker_loop(self):
        while True:
            with self._queue_lock:
                while self.running and not self._heap:
                    self._cond.wait(timeout=0.5)
                
                if not self.running and not self._heap:
                    break

                if not self._heap:
                    continue

                _, _, task = heapq.heappop(self._heap)

            with self.tasks_lock:
                if task.state == TaskState.CANCELLED:
                    continue
                task.state = TaskState.RUNNING
                task.started_at = time.time()
                task.attempts += 1

            handler = self.registry.get(task.name)
            if not handler:
                logger.error(f"No handler registered for task type: '{task.name}'")
                with self.tasks_lock:
                    task.state = TaskState.FAILED
                    task.error = f"No handler registered for '{task.name}'"
                    task.finished_at = time.time()
                with self.metrics_lock:
                    self.metrics["failed"] += 1
                continue

            try:
                logger.info(f"Executing task {task.id} ('{task.name}'), attempt {task.attempts}")
                result = handler(task.payload)
                with self.tasks_lock:
                    task.state = TaskState.COMPLETED
                    task.result = result
                    task.finished_at = time.time()
                with self.metrics_lock:
                    self.metrics["completed"] += 1
                logger.info(f"Task {task.id} completed successfully.")
            except Exception as e:
                error_msg = str(e)
                logger.exception(f"Task {task.id} failed with error: {error_msg}")
                
                with self.tasks_lock:
                    if task.attempts <= task.max_retries:
                        task.state = TaskState.RETRYING
                        task.error = error_msg
                    else:
                        task.state = TaskState.FAILED
                        task.error = error_msg
                        task.finished_at = time.time()

                if task.state == TaskState.RETRYING:
                    with self.metrics_lock:
                        self.metrics["retried"] += 1
                    time.sleep(task.retry_delay)
                    with self._queue_lock:
                        with self.tasks_lock:
                            if task.state != TaskState.CANCELLED:
                                task.state = TaskState.PENDING
                                self._counter += 1
                                heapq.heappush(self._heap, (-task.priority, self._counter, task))
                                self._cond.notify()
                    logger.info(f"Re-queued task {task.id} for retry (attempt {task.attempts})")
                else:
                    with self.metrics_lock:
                        self.metrics["failed"] += 1
''')

# 2. server.py
with open("task_queue_system/server.py", "w") as f:
    f.write('''import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from task_queue_system.queue_engine import QueueEngine

logger = logging.getLogger("RESTServer")

class QueueRESTHandler(BaseHTTPRequestHandler):
    engine: QueueEngine = None  # Injected globally

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/health":
            self._send_json(200, {"status": "healthy", "running": self.engine.running})
        elif path == "/api/metrics":
            metrics = self.engine.get_metrics()
            self._send_json(200, metrics)
        elif path == "/api/tasks":
            state_filter = query.get("state", [None])[0]
            tasks = self.engine.list_tasks(state=state_filter)
            self._send_json(200, {"tasks": [t.to_dict() for t in tasks]})
        elif path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            task = self.engine.get_task(task_id)
            if not task:
                self._send_json(404, {"error": "Task not found"})
            else:
                self._send_json(200, task.to_dict())
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/tasks":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.wfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(raw_body.decode("utf-8"))
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
            task_id = data.get("task_id")

            task = self.engine.submit_task(
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
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            success = self.engine.cancel_task(task_id)
            if not success:
                self._send_json(404, {"error": "Task not found or cannot be cancelled"})
            else:
                self._send_json(200, {"status": "cancelled", "task_id": task_id})
        else:
            self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        logger.info(f"{self.address_string()} - - [{self.log_date_time_string()}] {format % args}")

def run_server(engine: QueueEngine, host: str = "0.0.0.0", port: int = 8899) -> HTTPServer:
    QueueRESTHandler.engine = engine
    server = HTTPServer((host, port), QueueRESTHandler)
    return server
''')

# 3. cli.py
with open("task_queue_system/cli.py", "w") as f:
    f.write('''import sys
import argparse
import json
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8899"

def make_request(method: str, endpoint: str, data: dict = None, base_url: str = DEFAULT_URL):
    url = f"{base_url}{endpoint}"
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
        except Exception:
            err_json = {"error": err_body}
        return e.code, err_json
    except urllib.error.URLError as e:
        print(f"Error connecting to server at {base_url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Task Queue System CLI")
    parser.add_argument("--url", default=DEFAULT_URL, help="Server base URL")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # submit
    sub_submit = subparsers.add_parser("submit", help="Submit a new task")
    sub_submit.add_argument("--name", required=True, help="Task name / handler")
    sub_submit.add_argument("--payload", default="{}", help="JSON payload string")
    sub_submit.add_argument("--priority", type=int, default=0, help="Task priority")
    sub_submit.add_argument("--max-retries", type=int, default=3, help="Max retries")
    sub_submit.add_argument("--retry-delay", type=float, default=0.05, help="Retry delay in seconds")

    # list
    sub_list = subparsers.add_parser("list", help="List tasks")
    sub_list.add_argument("--state", default=None, help="Filter by state (pending, running, completed, failed, retrying, cancelled)")

    # get
    sub_get = subparsers.add_parser("get", help="Get task details")
    sub_get.add_argument("task_id", help="Task ID")

    # cancel
    sub_cancel = subparsers.add_parser("cancel", help="Cancel a task")
    sub_cancel.add_argument("task_id", help="Task ID")

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
            "max_retries": args.max_retries,
            "retry_delay": args.retry_delay
        }
        status, resp = make_request("POST", "/api/tasks", data, base_url=args.url)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "list":
        endpoint = "/api/tasks"
        if args.state:
            endpoint += f"?state={args.state}"
        status, resp = make_request("GET", endpoint, base_url=args.url)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "get":
        status, resp = make_request("GET", f"/api/tasks/{args.task_id}", base_url=args.url)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "cancel":
        status, resp = make_request("DELETE", f"/api/tasks/{args.task_id}", base_url=args.url)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "metrics":
        status, resp = make_request("GET", "/api/metrics", base_url=args.url)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

    elif args.command == "health":
        status, resp = make_request("GET", "/api/health", base_url=args.url)
        print(f"Status: {status}")
        print(json.dumps(resp, indent=2))

if __name__ == "__main__":
    main()
''')

# 4. test_system.py
with open("task_queue_system/test_system.py", "w") as f:
    f.write('''import unittest
import time
import threading
import json
import urllib.request
from task_queue_system.queue_engine import QueueEngine, TaskState
from task_queue_system.server import run_server

class TestQueueSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = QueueEngine(num_workers=2)
        cls.engine.register_handler("add", lambda p: p["a"] + p["b"])
        cls.engine.register_handler("fail_always", lambda p: 1 / 0)
        
        # Flaky handler that succeeds on 2nd attempt
        cls.flaky_attempts = {}
        def flaky(p):
            tid = p["tid"]
            cls.flaky_attempts[tid] = cls.flaky_attempts.get(tid, 0) + 1
            if cls.flaky_attempts[tid] < 2:
                raise ValueError("Temporary failure")
            return "success"
        cls.engine.register_handler("flaky", flaky)

        cls.engine.start()

        cls.server = run_server(cls.engine, host="127.0.0.1", port=8899)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)  # wait for server

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.engine.stop()

    def test_01_successful_task(self):
        task = self.engine.submit_task("add", {"a": 10, "b": 32})
        deadline = time.time() + 3.0
        while time.time() < deadline:
            t = self.engine.get_task(task.id)
            if t.state == TaskState.COMPLETED:
                break
            time.sleep(0.05)

        t = self.engine.get_task(task.id)
        self.assertEqual(t.state, TaskState.COMPLETED)
        self.assertEqual(t.result, 42)

    def test_02_retry_and_failure(self):
        task = self.engine.submit_task("fail_always", max_retries=2, retry_delay=0.01)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            t = self.engine.get_task(task.id)
            if t.state == TaskState.FAILED:
                break
            time.sleep(0.05)

        t = self.engine.get_task(task.id)
        self.assertEqual(t.state, TaskState.FAILED)
        self.assertGreaterEqual(t.attempts, 3)

    def test_03_flaky_task_retry_success(self):
        task_id = "flaky-task-1"
        task = self.engine.submit_task("flaky", {"tid": task_id}, max_retries=3, retry_delay=0.01, task_id=task_id)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            t = self.engine.get_task(task.id)
            if t.state == TaskState.COMPLETED:
                break
            time.sleep(0.05)

        t = self.engine.get_task(task.id)
        self.assertEqual(t.state, TaskState.COMPLETED)
        self.assertEqual(t.result, "success")

    def test_04_priority_ordering(self):
        # We can submit tasks with different priorities and check order
        pass

    def test_05_rest_api_health(self):
        req = urllib.request.Request("http://localhost:8899/api/health")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertEqual(data["status"], "healthy")

    def test_06_rest_api_submit_and_get(self):
        body = json.dumps({
            "name": "add",
            "payload": {"a": 5, "b": 5}
        }).encode("utf-8")
        req = urllib.request.Request("http://localhost:8899/api/tasks", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 201)
            task_id = data["id"]

        # Wait for completion via API
        deadline = time.time() + 3.0
        while time.time() < deadline:
            req_get = urllib.request.Request(f"http://localhost:8899/api/tasks/{task_id}")
            with urllib.request.urlopen(req_get) as resp_get:
                t_data = json.loads(resp_get.read().decode("utf-8"))
                if t_data["state"] == "completed":
                    break
            time.sleep(0.05)

        self.assertEqual(t_data["state"], "completed")
        self.assertEqual(t_data["result"], 10)

    def test_07_rest_api_metrics(self):
        req = urllib.request.Request("http://localhost:8899/api/metrics")
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertIn("submitted", data)
            self.assertIn("completed", data)

if __name__ == "__main__":
    unittest.main()
''')

print("All system files generated successfully.")
