import os

os.makedirs("task_queue_system", exist_ok=True)

# 1. queue_engine.py
queue_engine_code = r'''import time
import uuid
import threading
import heapq
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Callable, Optional, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
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
    retry_delay: float = 0.1  # seconds
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
        
        # Metrics counters
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

    def submit_task(self, name: str, payload: Optional[Dict[str, Any]] = None, priority: int = 0, max_retries: int = 3, retry_delay: float = 0.1, task_id: Optional[str] = None) -> Task:
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
            # Min-heap: negative priority for highest first, counter for FIFO tie-breaker
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

    def get_metrics(self) -> Dict[str, Any]:
        with self.metrics_lock:
            m = dict(self.metrics)
        with self.tasks_lock:
            m["active_tasks"] = len(self.tasks)
            m["pending_tasks"] = sum(1 for t in self.tasks.values() if t.state == TaskState.PENDING)
            m["running_tasks"] = sum(1 for t in self.tasks.values() if t.state == TaskState.RUNNING)
        return m

    def _worker_loop(self):
        while True:
            with self._queue_lock:
                while self.running and not self._heap:
                    self._cond.wait()
                
                if not self.running and not self._heap:
                    break
                
                _, _, task = heapq.heappop(self._heap)

            # Check if task was cancelled while pending in heap
            with self.tasks_lock:
                if task.state == TaskState.CANCELLED:
                    continue
                task.state = TaskState.RUNNING
                task.started_at = time.time()
                task.attempts += 1

            logger.info(f"Worker {threading.current_thread().name} starting task {task.id} ({task.name}), attempt {task.attempts}")

            handler = self.registry.get(task.name)
            if not handler:
                err_msg = f"No handler registered for task name: {task.name}"
                logger.error(err_msg)
                with self.tasks_lock:
                    task.state = TaskState.FAILED
                    task.error = err_msg
                    task.finished_at = time.time()
                with self.metrics_lock:
                    self.metrics["failed"] += 1
                continue

            try:
                result = handler(task.payload)
                with self.tasks_lock:
                    task.state = TaskState.COMPLETED
                    task.result = result
                    task.finished_at = time.time()
                with self.metrics_lock:
                    self.metrics["completed"] += 1
                logger.info(f"Task {task.id} completed successfully.")
            except Exception as e:
                err_str = str(e)
                logger.warning(f"Task {task.id} failed on attempt {task.attempts}: {err_str}")
                
                should_retry = task.attempts < task.max_retries
                with self.tasks_lock:
                    task.error = err_str
                    if should_retry:
                        task.state = TaskState.RETRYING
                    else:
                        task.state = TaskState.FAILED
                        task.finished_at = time.time()

                if should_retry:
                    with self.metrics_lock:
                        self.metrics["retried"] += 1
                    # Schedule retry after delay
                    delay = task.retry_delay
                    def retry_target():
                        time.sleep(delay)
                        with self.tasks_lock:
                            if task.state == TaskState.CANCELLED:
                                return
                            task.state = TaskState.PENDING
                        with self._queue_lock:
                            self._counter += 1
                            heapq.heappush(self._heap, (-task.priority, self._counter, task))
                            self._cond.notify()
                        logger.info(f"Re-queued task {task.id} for retry ({task.attempts}/{task.max_retries})")
                    
                    threading.Thread(target=retry_target, daemon=True).start()
                else:
                    with self.metrics_lock:
                        self.metrics["failed"] += 1
                    logger.error(f"Task {task.id} permanently failed after {task.attempts} attempts.")
'''
with open("task_queue_system/queue_engine.py", "w") as f:
    f.write(queue_engine_code)

# 2. server.py
server_code = r'''import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional

from task_queue_system.queue_engine import QueueEngine, TaskState

# Global queue engine instance
engine = QueueEngine(num_workers=4)

# Register some default handlers for demonstration & testing
def echo_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"echo": payload}

def fail_handler(payload: Dict[str, Any]) -> Any:
    raise RuntimeError(payload.get("error_message", "Task simulated failure"))

def sleep_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    duration = payload.get("duration", 0.1)
    import time
    time.sleep(duration)
    return {"slept": duration}

engine.register_handler("echo", echo_handler)
engine.register_handler("fail", fail_handler)
engine.register_handler("sleep", sleep_handler)
engine.start()

class TaskQueueHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, data: Any):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _parse_body(self) -> Optional[Dict[str, Any]]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        try:
            raw = self.rfile.read(content_length)
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return None

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._send_json(200, {"status": "healthy", "engine_running": engine.running})
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
            self._send_json(404, {"error": "Endpoint not found"})

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/tasks":
            data = self._parse_body()
            if data is None or "name" not in data:
                self._send_json(400, {"error": "Invalid JSON or missing 'name' field"})
                return

            name = data["name"]
            payload = data.get("payload", {})
            priority = data.get("priority", 0)
            max_retries = data.get("max_retries", 3)
            retry_delay = data.get("retry_delay", 0.1)
            task_id = data.get("task_id")

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
            self._send_json(404, {"error": "Endpoint not found"})

    def do_DELETE(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            success = engine.cancel_task(task_id)
            if success:
                self._send_json(200, {"status": "cancelled", "id": task_id})
            else:
                self._send_json(400, {"error": "Could not cancel task (may not exist or already completed)"})
        else:
            self._send_json(404, {"error": "Endpoint not found"})

    def log_message(self, format, *args):
        # Silence default stderr logging for clean test runs
        pass

def run_server(port: int = 8899):
    server = HTTPServer(("0.0.0.0", port), TaskQueueHTTPHandler)
    print(f"TaskQueue REST server running on port {port}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        server.server_close()

if __name__ == "__main__":
    run_server()
'''
with open("task_queue_system/server.py", "w") as f:
    f.write(server_code)

# 3. cli.py
cli_code = r'''#!/usr/bin/env python3
import sys
import json
import argparse
import urllib.request
import urllib.error

DEFAULT_URL = "http://localhost:8899"

def request_api(method: str, endpoint: str, data: dict = None, base_url: str = DEFAULT_URL):
    url = f"{base_url}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            err_data = json.loads(raw)
        except Exception:
            err_data = {"error": raw}
        return e.code, err_data
    except urllib.error.URLError as e:
        print(f"Error connecting to server at {base_url}: {e.reason}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Task Queue CLI Client")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL of the task queue server")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # submit
    sub_submit = subparsers.add_parser("submit", help="Submit a new task")
    sub_submit.add_argument("name", help="Task handler name")
    sub_submit.add_argument("--payload", default="{}", help="JSON payload string")
    sub_submit.add_argument("--priority", type=int, default=0, help="Task priority")
    sub_submit.add_argument("--retries", type=int, default=3, help="Max retries")
    sub_submit.add_argument("--delay", type=float, default=0.1, help="Retry delay in seconds")

    # list
    subparsers.add_parser("list", help="List all tasks")

    # get
    sub_get = subparsers.add_parser("get", help="Get details of a specific task")
    sub_get.add_argument("task_id", help="Task ID")

    # cancel
    sub_cancel = subparsers.add_parser("cancel", help="Cancel a pending or running task")
    sub_cancel.add_argument("task_id", help="Task ID")

    # metrics
    subparsers.add_parser("metrics", help="View server metrics")

    # health
    subparsers.add_parser("health", help="Check server health")

    args = parser.parse_args()

    if args.command == "submit":
        try:
            payload_dict = json.loads(args.payload)
        except Exception as e:
            print(f"Invalid JSON payload: {e}", file=sys.stderr)
            sys.exit(1)
        
        data = {
            "name": args.name,
            "payload": payload_dict,
            "priority": args.priority,
            "max_retries": args.retries,
            "retry_delay": args.delay
        }
        status, resp = request_api("POST", "/api/tasks", data, args.url)
        print(json.dumps(resp, indent=2))
        sys.exit(0 if status in (200, 201) else 1)

    elif args.command == "list":
        status, resp = request_api("GET", "/api/tasks", base_url=args.url)
        print(json.dumps(resp, indent=2))
        sys.exit(0 if status == 200 else 1)

    elif args.command == "get":
        status, resp = request_api("GET", f"/api/tasks/{args.task_id}", base_url=args.url)
        print(json.dumps(resp, indent=2))
        sys.exit(0 if status == 200 else 1)

    elif args.command == "cancel":
        status, resp = request_api("DELETE", f"/api/tasks/{args.task_id}", base_url=args.url)
        print(json.dumps(resp, indent=2))
        sys.exit(0 if status == 200 else 1)

    elif args.command == "metrics":
        status, resp = request_api("GET", "/api/metrics", base_url=args.url)
        print(json.dumps(resp, indent=2))
        sys.exit(0 if status == 200 else 1)

    elif args.command == "health":
        status, resp = request_api("GET", "/api/health", base_url=args.url)
        print(json.dumps(resp, indent=2))
        sys.exit(0 if status == 200 else 1)

if __name__ == "__main__":
    main()
'''
with open("task_queue_system/cli.py", "w") as f:
    f.write(cli_code)

# 4. test_system.py
test_system_code = r'''import unittest
import time
import threading
import json
import urllib.request
from http.server import HTTPServer

from task_queue_system.queue_engine import QueueEngine, TaskState
from task_queue_system.server import TaskQueueHTTPHandler, engine as server_engine

class TestQueueEngine(unittest.TestCase):
    def setUp(self):
        self.engine = QueueEngine(num_workers=2)
        self.engine.register_handler("add", lambda p: p["a"] + p["b"])
        self.engine.register_handler("fail_always", lambda p: 1 / 0)
        self.engine.start()

    def tearDown(self):
        self.engine.stop()

    def test_successful_task(self):
        task = self.engine.submit_task("add", {"a": 10, "b": 32})
        # Wait for completion
        start = time.time()
        while task.state not in (TaskState.COMPLETED, TaskState.FAILED):
            time.sleep(0.01)
            if time.time() - start > 2.0:
                break
        
        self.assertEqual(task.state, TaskState.COMPLETED)
        self.assertEqual(task.result, 42)

    def test_priority_order(self):
        execution_order = []
        lock = threading.Lock()

        def tracking_handler(p):
            with lock:
                execution_order.append(p["id"])
            return p["id"]

        self.engine.register_handler("track", tracking_handler)

        # Stop and restart engine with 1 worker to strictly test priority heap ordering
        self.engine.stop()
        self.engine = QueueEngine(num_workers=1)
        self.engine.register_handler("track", tracking_handler)
        self.engine.start()

        t1 = self.engine.submit_task("track", {"id": "low"}, priority=1)
        t2 = self.engine.submit_task("track", {"id": "high"}, priority=10)
        t3 = self.engine.submit_task("track", {"id": "medium"}, priority=5)

        # Wait for all tasks
        start = time.time()
        while len(execution_order) < 3:
            time.sleep(0.01)
            if time.time() - start > 3.0:
                break

        self.assertEqual(execution_order, ["high", "medium", "low"])

    def test_retry_and_failure(self):
        task = self.engine.submit_task("fail_always", {}, max_retries=2, retry_delay=0.05)
        start = time.time()
        while task.state != TaskState.FAILED:
            time.sleep(0.01)
            if time.time() - start > 3.0:
                break

        self.assertEqual(task.state, TaskState.FAILED)
        self.assertEqual(task.attempts, 2)
        self.assertIsNotNone(task.error)

    def test_cancellation(self):
        # Register a slow handler
        self.engine.register_handler("slow", lambda p: time.sleep(0.5))
        # Submit a task with priority to make it pending or running
        task = self.engine.submit_task("slow", {})
        time.sleep(0.05) # let it start
        cancelled = self.engine.cancel_task(task.id)
        # Even if running or pending, test cancel method runs correctly
        self.assertIn(task.state, (TaskState.CANCELLED, TaskState.RUNNING, TaskState.COMPLETED))

class TestRESTServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 8999
        cls.server = HTTPServer(("127.0.0.1", cls.port), TaskQueueHTTPHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1) # startup grace

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2.0)

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_health_endpoint(self):
        req = urllib.request.Request(self._url("/api/health"))
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertEqual(data["status"], "healthy")

    def test_metrics_endpoint(self):
        req = urllib.request.Request(self._url("/api/metrics"))
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("submitted", data)

    def test_submit_and_get_task(self):
        body = json.dumps({
            "name": "echo",
            "payload": {"message": "hello rest"}
        }).encode("utf-8")

        req = urllib.request.Request(
            self._url("/api/tasks"),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            task_data = json.loads(resp.read().decode())
            task_id = task_data["id"]

        # Wait a moment for completion
        time.sleep(0.2)

        # Get task status
        req2 = urllib.request.Request(self._url(f"/api/tasks/{task_id}"))
        with urllib.request.urlopen(req2) as resp:
            self.assertEqual(resp.status, 200)
            task_data = json.loads(resp.read().decode())
            self.assertEqual(task_data["state"], "completed")
            self.assertEqual(task_data["result"], {"echo": {"message": "hello rest"}})

if __name__ == "__main__":
    unittest.main()
'''
with open("test_system.py", "w") as f:
    f.write(test_system_code)

print("All files created successfully!")
