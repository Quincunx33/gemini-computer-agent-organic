import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional
try:
    from task_queue_system.queue_engine import QueueEngine, TaskState
    from task_queue_system.metrics_collector import MetricsCollector
except ModuleNotFoundError:
    from queue_engine import QueueEngine, TaskState
    from metrics_collector import MetricsCollector

collector = MetricsCollector()
engine = QueueEngine(max_workers=4, metrics_collector=collector)

# Register default standard handlers
engine.register_handler("echo", lambda p: p)
engine.register_handler("add", lambda p: p.get("a", 0) + p.get("b", 0))

class TaskHTTPHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @property
    def current_engine(self) -> QueueEngine:
        return getattr(self.server, "engine", engine)

    def do_GET(self):
        eng = self.current_engine
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._send_json(200, {"status": "healthy", "running": eng.running})
        elif path == "/api/metrics":
            self._send_json(200, eng.get_metrics())
        elif path == "/api/tasks":
            tasks = eng.list_tasks()
            self._send_json(200, {"tasks": tasks})
        elif path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            task = eng.get_task(task_id)
            if not task:
                self._send_json(404, {"error": "Task not found"})
            else:
                self._send_json(200, task)
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_POST(self):
        eng = self.current_engine
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

            task = eng.submit_task(
                name=name,
                payload=payload,
                priority=priority,
                max_retries=max_retries,
                retry_delay=retry_delay,
                task_id=task_id
            )
            self._send_json(201, task)
        else:
            self._send_json(404, {"error": "Not Found"})

    def do_DELETE(self):
        eng = self.current_engine
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        if path.startswith("/api/tasks/"):
            task_id = path[len("/api/tasks/"):]
            success = eng.cancel_task(task_id)
            if not success:
                self._send_json(400, {"error": "Unable to cancel task (not found or already finished)"})
            else:
                self._send_json(200, {"status": "cancelled", "id": task_id})
        else:
            self._send_json(404, {"error": "Not Found"})

    def log_message(self, format, *args):
        # Silence HTTP server logs during automated test runs
        pass

def create_server(eng: Optional[QueueEngine] = None, host: str = "127.0.0.1", port: int = 8899) -> HTTPServer:
    HTTPServer.allow_reuse_address = True
    srv = HTTPServer((host, port), TaskHTTPHandler)
    srv.engine = eng or engine
    return srv

def run_server(eng: Optional[QueueEngine] = None, host: str = "127.0.0.1", port: int = 8899):
    active_eng = eng or engine
    if not active_eng.running:
        active_eng.start()
    server = create_server(active_eng, host, port)
    return server

if __name__ == "__main__":
    s = run_server(port=8899)
    print("REST Server running on http://127.0.0.1:8899")
    try:
        s.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        s.server_close()
        engine.stop()
        print("REST Server stopped.")
