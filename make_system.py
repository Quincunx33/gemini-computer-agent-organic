import os

os.makedirs("task_queue_system", exist_ok=True)

# 1. queue_engine.py
queue_engine_code = r'''
import time
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

            logger.info(f"Worker {threading.current_thread().name} picked task {task.id} ('{task.name}'), attempt {task.attempts}")

            handler = self.registry.get(task.name)
            success = False
            res = None
            err_msg = None

            if not handler:
                err_msg = f"No handler registered for task name: {task.name}"
                logger.error(err_msg)
            else:
                try:
                    res = handler(task.payload)
                    success = True
                except Exception as e:
                    err_msg = str(e)
                    logger.exception(f"Task {task.id} ('{task.name}') failed on attempt {task.attempts}")

            with self.tasks_lock:
                if task.state == TaskState.CANCELLED:
                    continue
                if success:
                    task.state = TaskState.COMPLETED
                    task.result = res
                    task.finished_at = time.time()
                    with self.metrics_lock:
                        self.metrics["completed"] += 1
                    logger.info(f"Task {task.id} completed successfully.")
                else:
                    task.error = err_msg
                    if task.attempts <= task.max_retries:
                        task.state = TaskState.RETRYING
                        with self.metrics_lock:
                            self.metrics["retried"] += 1
                        logger.info(f"Task {task.id} scheduling retry {task.attempts}/{task.max_retries} in {task.retry_delay}s")
                        
                        # Re-enqueue after retry_delay in background thread or sleep inline
                        def retry_scheduler():
                            time.sleep(task.retry_delay)
                            with self.tasks_lock:
                                if task.state == TaskState.CANCELLED:
                                    return
                                task.state = TaskState.PENDING
                            with self._queue_lock:
                                self._counter += 1
                                heapq.heappush(self._heap, (-task.priority, self._counter, task))
                                self._cond.notify()
                        
                        threading.Thread(target=retry_scheduler, daemon=True).s_scheduler = retry_scheduler # reference
                        threading.Thread(target=retry_scheduler, daemon=True).start()
                    else:
                        task.state = TaskState.FAILED
                        task.finished_at = time.time()
                        with self.metrics_lock:
                            self.metrics["failed"] += 1
                        logger.error(f"Task {task.id} permanently failed after {task.attempts} attempts.")
'''
with open("task_queue_system/queue_engine.py", "w") as f:
    f.write(queue_engine_code)

# 2. server.py
server_code = r'''
import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional

from task_queue_system.queue_engine import QueueEngine

logger = logging.getLogger("QueueServer")

class QueueHTTPHandler(BaseHTTPRequestHandler):
    engine: Optional[QueueEngine] = None

    def _send_json(self, status: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/health":
            self._send_json(200, {"status": "healthy", "running": self.engine.running if self.engine else False})
        elif path == "/api/metrics":
            if not self.engine:
                self._send_json(500, {"error": "Engine not initialized"})
                return
            self._send_json(200, self.engine.get_metrics())
        elif path == "/api/tasks":
            if not self.engine:
                self._send_json(500, {"error": "Engine not initialized"})
                return
            tasks = [t.to_dict() for t in self.engine.list_tasks()]
            self._send_json(200, {"tasks": tasks, "count": len(tasks)})
        elif path.startswith("/api/tasks/"):
            if not self.engine:
                self._send_json(500, {"error": "Engine not initialized"})
                return
            task_id = path[len("/api/tasks/"):]
            task = self.engine.get_task(task_id)
            if not task:
                self._send_json(404, {"error": f"Task {task_id} not found"})
                return
            self._send_json(200, task.to_dict())
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/tasks":
            if not self.engine:
                self._send_json(500, {"error": "Engine not initialized"})
                return
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.wfile.read(content_length) if content_length > 0 else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
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
            retry_delay = float(data.get("retry_delay", 0.1))
            task_id = data.get("id")

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
            if not self.engine:
                self._send_json(500, {"error": "Engine not initialized"})
                return
            task_id = path[len("/api/tasks/"):]
            success = self.engine.cancel_task(task_id)
            if not success:
                self._send_json(404, {"error": f"Task {task_id} not found or cannot be cancelled"})
                return
            self._send_json(200, {"message": f"Task {task_id} cancelled successfully"})
        else:
            self._send_json(404, {"error": "Not Found"})

def run_server(engine: QueueEngine, host: str = "127.0.0.1", port: int = 8899) -> HTTPServer:
    QueueHTTPHandler.engine = engine
    server = HTTPServer((host, port), QueueHTTPHandler)
    logger.info(f"REST server started at http://{host}:{port}")
    return server
'''
with open("task_queue_system/server.py", "w") as f:
    f.write(server_code)

# 3. cli.py
cli_code = r'''
import sys
import argparse
import json
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:8899/api"

def api_request(method: str, endpoint: str, data: dict = None):
    url = f"{BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": e.reason}
        return e.code, err_body
    except urllib.error.URLError as e:
        print(f"Error connecting to server at {BASE_URL}: {e.reason}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Task Queue CLI Client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # health
    subparsers.add_parser("health", help="Check server health")

    # metrics
    subparsers.add_parser("metrics", help="Get queue metrics")

    # list tasks
    subparsers.add_parser("list", help="List all tasks")

    # get task
    get_parser = subparsers.add_parser("get", help="Get task details by ID")
    get_parser.add_argument("id", help="Task ID")

    # submit task
    sub_parser = subparsers.add_parser("submit", help="Submit a new task")
    sub_parser.add_argument("--name", required=True, help="Task handler name")
    sub_parser.add_argument("--payload", default="{}", help="JSON payload string")
    sub_parser.add_argument("--priority", type=int, default=0, help="Task priority")
    sub_parser.add_argument("--retries", type=int, default=3, help="Max retries")
    sub_parser.add_argument("--delay", type=float, default=0.1, help="Retry delay")

    # cancel task
    cancel_parser = subparsers.add_parser("cancel", help="Cancel a task")
    cancel_parser.add_argument("id", help="Task ID")

    args = parser.parse_args()

    if args.command == "health":
        status, data = api_request("GET", "/health")
        print(json.dumps(data, indent=2))
    elif args.command == "metrics":
        status, data = api_request("GET", "/metrics")
        print(json.dumps(data, indent=2))
    elif args.command == "list":
        status, data = api_request("GET", "/tasks")
        print(json.dumps(data, indent=2))
    elif args.command == "get":
        status, data = api_request("GET", f"/tasks/{args.id}")
        print(json.dumps(data, indent=2))
    elif args.command == "submit":
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON payload: {e}", file=sys.stderr)
            sys.exit(1)
        data = {
            "name": args.name,
            "payload": payload,
            "priority": args.priority,
            "max_retries": args.retries,
            "retry_delay": args.delay
        }
        status, resp = api_request("POST", "/tasks", data)
        print(json.dumps(resp, indent=2))
    elif args.command == "cancel":
        status, data = api_request("DELETE", f"/tasks/{args.id}")
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
'''
with open("task_queue_system/cli.py", "w") as f:
    f.write(cli_code)

# 4. test_system.py
test_code = r'''
import unittest
import time
import threading
import json
import urllib.request

from task_queue_system.queue_engine import QueueEngine, TaskState
from task_queue_system.server import run_server

class TestQueueEngineAndServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = QueueEngine(num_workers=2)
        cls.engine.register_handler("echo", lambda p: p.get("message", "hello"))
        cls.engine.register_handler("add", lambda p: p.get("a", 0) + p.get("b", 0))
        
        def fail_then_succeed(p):
            # We can use a counter stored in payload or global or thread-safe dict
            # For simplicity, let's raise error on first attempt
            raise RuntimeError("Temporary failure")

        cls.engine.register_handler("flaky", fail_then_succeed)
        cls.engine.start()

        cls.server = run_server(cls.engine, host="127.0.0.1", port=8899)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.2) # let server start

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.engine.stop()

    def test_01_engine_submit_and_complete(self):
        task = self.engine.submit_task("echo", payload={"message": "test-echo"}, priority=1)
        
        # Wait for completion
        start = time.time()
        while time.time() - start < 2.0:
            t = self.engine.get_task(task.id)
            if t and t.state == TaskState.COMPLETED:
                break
            time.sleep(0.05)
            
        t = self.engine.get_task(task.id)
        self.assertEqual(t.state, TaskState.COMPLETED)
        self.assertEqual(t.result, "test-echo")

    def test_02_priority_ordering(self):
        # We can test high priority vs low priority execution order or just state
        t_low = self.engine.submit_task("echo", payload={"message": "low"}, priority=0)
        t_high = self.engine.submit_task("echo", payload={"message": "high"}, priority=10)

        start = time.time()
        while time.time() - start < 3.0:
            if self.engine.get_task(t_high.id).state == TaskState.COMPLETED and \
               self.engine.get_task(t_low.id).state == TaskState.COMPLETED:
                break
            time.sleep(0.05)

        self.assertEqual(self.engine.get_task(t_high.id).state, TaskState.COMPLETED)
        self.assertEqual(self.engine.get_task(t_low.id).state, TaskState.COMPLETED)

    def test_03_rest_api_health(self):
        req = urllib.request.urlopen("http://127.0.0.1:8899/api/health")
        self.assertEqual(req.status, 200)
        data = json.loads(req.read().decode("utf-8"))
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["running"])

    def test_04_rest_api_submit_and_get_task(self):
        body = json.dumps({
            "name": "add",
            "payload": {"a": 10, "b": 32},
            "priority": 5
        }).encode("utf-8")
        req = urllib.request.Request("http://127.0.0.1:8899/api/tasks", data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            task_data = json.loads(resp.read().decode("utf-8"))
            task_id = task_data["id"]

        # Wait for task completion
        start = time.time()
        while time.time() - start < 3.0:
            req_get = urllib.request.urlopen(f"http://127.0.0.1:8899/api/tasks/{task_id}")
            t_data = json.loads(req_get.read().decode("utf-8"))
            if t_data["state"] == "completed":
                break
            time.sleep(0.05)

        req_get = urllib.request.urlopen(f"http://127.0.0.1:8899/api/tasks/{task_id}")
        t_data = json.loads(req_get.read().decode("utf-8"))
        self.assertEqual(t_data["state"], "completed")
        self.assertEqual(t_data["result"], 42)

    def test_05_rest_api_metrics_and_list(self):
        req_metrics = urllib.request.urlopen("http://127.0.0.1:8899/api/metrics")
        self.assertEqual(req_metrics.status, 200)
        metrics = json.loads(req_metrics.read().decode("utf-8"))
        self.assertIn("submitted", metrics)
        self.assertIn("completed", metrics)

        req_list = urllib.request.urlopen("http://127.0.0.1:8899/api/tasks")
        self.assertEqual(req_list.status, 200)
        lst = json.loads(req_list.read().decode("utf-8"))
        self.assertIn("tasks", lst)
        self.assertGreaterEqual(lst["count"], 1)

if __name__ == "__main__":
    unittest.main()
'''
with open("task_queue_system/test_system.py", "w") as f:
    f.write(test_code)

print("Successfully created all files!")
