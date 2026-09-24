import sqlite3
import threading
import time
import uuid
import json
import logging
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Callable, Any, List, Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("QueueEngine")

class TaskState:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"

class QueueEngine:
    """
    Priority-based SQLite persistent task queue with worker thread pool,
    task states, and exponential backoff retry logic.
    """
    def __init__(self, db_path: str = "task_queue.db", max_workers: int = 4, metrics_collector = None):
        self.db_path = db_path
        self.max_workers = max_workers
        self.metrics_collector = metrics_collector
        self._lock = threading.Lock()
        self.handlers: Dict[str, Callable] = {}
        self.executor: Optional[ThreadPoolExecutor] = None
        self._running = False
        self._worker_thread = None

        self._init_db()

    @property
    def running(self) -> bool:
        return self._running

    def _get_connection(self):
        if self.db_path.startswith("file:"):
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False, uri=True)
        else:
            conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        priority INTEGER DEFAULT 0,
                        payload TEXT,
                        status TEXT NOT NULL,
                        result TEXT,
                        error TEXT,
                        retries INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 3,
                        retry_delay REAL DEFAULT 0.05,
                        next_run_at REAL DEFAULT 0.0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    )
                """)
                conn.commit()
            finally:
                conn.close()

    def register_handler(self, name: str, func: Callable):
        with self._lock:
            self.handlers[name] = func
            logger.info(f"Registered task handler for: {name}")

    def submit_task(self, name: str, payload: Any = None, priority: int = 0, max_retries: int = 3, retry_delay: float = 0.05, task_id: Optional[str] = None) -> dict:
        t_id = task_id or str(uuid.uuid4())
        now = time.time()
        payload_str = json.dumps(payload) if payload is not None else None

        with self._lock:
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    INSERT INTO tasks (id, name, priority, payload, status, retries, max_retries, retry_delay, next_run_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                    """,
                    (t_id, name, priority, payload_str, TaskState.PENDING, max_retries, retry_delay, now, now, now)
                )
                conn.commit()
                logger.info(f"Submitted task {t_id} ({name}) with priority {priority}")
            finally:
                conn.close()
        return self.get_task(t_id)

    def get_task(self, task_id: str) -> Optional[dict]:
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            task = dict(row)
            if task["payload"]:
                try:
                    task["payload"] = json.loads(task["payload"])
                except Exception:
                    pass
            if task["result"]:
                try:
                    task["result"] = json.loads(task["result"])
                except Exception:
                    pass
            # Compatibility helpers
            task["state"] = task["status"].lower()
            task["attempts"] = task["retries"] + 1
            return task
        finally:
            conn.close()

    def list_tasks(self, status: Optional[str] = None) -> List[dict]:
        conn = self._get_connection()
        try:
            if status:
                cursor = conn.execute("SELECT * FROM tasks WHERE UPPER(status) = ? ORDER BY priority DESC, created_at ASC", (status.upper(),))
            else:
                cursor = conn.execute("SELECT * FROM tasks ORDER BY priority DESC, created_at ASC")
            
            tasks = []
            for row in cursor.fetchall():
                t = dict(row)
                if t["payload"]:
                    try:
                        t["payload"] = json.loads(t["payload"])
                    except Exception:
                        pass
                if t["result"]:
                    try:
                        t["result"] = json.loads(t["result"])
                    except Exception:
                        pass
                t["state"] = t["status"].lower()
                t["attempts"] = t["retries"] + 1
                tasks.append(t)
            return tasks
        finally:
            conn.close()

    def cancel_task(self, task_id: str) -> bool:
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
                row = cursor.fetchone()
                if not row:
                    return False
                status = row["status"]
                if status in (TaskState.PENDING, TaskState.RETRYING):
                    conn.execute(
                        "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
                        (TaskState.CANCELLED, time.time(), task_id)
                    )
                    conn.commit()
                    logger.info(f"Cancelled task {task_id}")
                    return True
                return False
            finally:
                conn.close()

    def get_metrics(self) -> dict:
        base = {}
        if self.metrics_collector:
            base = self.metrics_collector.get_metrics()

        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT status, count(*) as cnt FROM tasks GROUP BY status")
            counts = {row["status"]: row["cnt"] for row in cursor.fetchall()}
            cursor_tot = conn.execute("SELECT count(*) as total FROM tasks")
            total = cursor_tot.fetchone()["total"]

            base["submitted"] = total
            base["completed"] = counts.get(TaskState.COMPLETED, 0)
            base["failed"] = counts.get(TaskState.FAILED, 0)
            base["pending"] = counts.get(TaskState.PENDING, 0)
            base["running"] = counts.get(TaskState.RUNNING, 0)
            base["retrying"] = counts.get(TaskState.RETRYING, 0)
            base["cancelled"] = counts.get(TaskState.CANCELLED, 0)
            base["active_workers"] = self.max_workers if self._running else 0
            return base
        finally:
            conn.close()

    def start(self):
        with self._lock:
            if self._running:
                return
            self._running = True
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="QueueWorker")
            self._worker_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
            self._worker_thread.start()
            logger.info("QueueEngine started dispatch loop and worker pool.")

    def stop(self, wait: bool = True):
        with self._lock:
            if not self._running:
                return
            self._running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=2.0)
        
        if self.executor:
            self.executor.shutdown(wait=wait)
            logger.info("QueueEngine stopped.")

    def _dispatch_loop(self):
        while self._running:
            try:
                now = time.time()
                conn = self._get_connection()
                try:
                    cursor = conn.execute(
                        """
                        SELECT * FROM tasks 
                        WHERE (status = ? OR (status = ? AND next_run_at <= ?))
                        ORDER BY priority DESC, created_at ASC
                        LIMIT 1
                        """,
                        (TaskState.PENDING, TaskState.RETRYING, now)
                    )
                    row = cursor.fetchone()
                    if not row:
                        time.sleep(0.05)
                        continue
                    
                    task_dict = dict(row)
                    task_id = task_dict["id"]

                    cursor2 = conn.execute(
                        """
                        UPDATE tasks SET status = ?, updated_at = ? 
                        WHERE id = ? AND status IN (?, ?)
                        """,
                        (TaskState.RUNNING, time.time(), task_id, TaskState.PENDING, TaskState.RETRYING)
                    )
                    conn.commit()
                    if cursor2.rowcount == 0:
                        continue

                    self.executor.submit(self._execute_task, task_id)

                finally:
                    conn.close()

            except Exception as e:
                logger.error(f"Error in dispatch loop: {e}", exc_info=True)
                time.sleep(0.1)

    def _execute_task(self, task_id: str):
        task = self.get_task(task_id)
        if not task:
            return

        name = task["name"]
        payload = task["payload"]
        handler = self.handlers.get(name)

        if not handler:
            err_msg = f"No handler registered for task name: {name}"
            logger.error(err_msg)
            self._fail_task(task_id, err_msg)
            return

        start_time = time.time()
        try:
            logger.info(f"Executing task {task_id} ({name})")
            
            # Smart handler invocation
            sig = inspect.signature(handler)
            if len(sig.parameters) == 0:
                result = handler()
            elif isinstance(payload, dict):
                try:
                    result = handler(payload)
                except TypeError:
                    result = handler(**payload)
            elif isinstance(payload, list):
                result = handler(*payload)
            else:
                result = handler(payload)

            duration = time.time() - start_time
            self._complete_task(task_id, result, duration)

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Task {task_id} ({name}) failed with exception: {e}")
            self._handle_task_failure(task, str(e))

    def _complete_task(self, task_id: str, result: Any, duration: float):
        now = time.time()
        res_str = json.dumps(result) if result is not None else None
        conn = self._get_connection()
        try:
            conn.execute(
                """
                UPDATE tasks SET status = ?, result = ?, updated_at = ? WHERE id = ?
                """,
                (TaskState.COMPLETED, res_str, now, task_id)
            )
            conn.commit()
            logger.info(f"Task {task_id} completed successfully in {duration:.4f}s")
            if self.metrics_collector:
                self.metrics_collector.record_success(duration)
        finally:
            conn.close()

    def _fail_task(self, task_id: str, error: str):
        now = time.time()
        conn = self._get_connection()
        try:
            conn.execute(
                """
                UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?
                """,
                (TaskState.FAILED, error, now, task_id)
            )
            conn.commit()
            if self.metrics_collector:
                self.metrics_collector.record_failure()
        finally:
            conn.close()

    def _handle_task_failure(self, task: dict, error: str):
        task_id = task["id"]
        retries = task["retries"] + 1
        max_retries = task["max_retries"]

        if retries <= max_retries:
            base_delay = task.get("retry_delay", 0.05)
            backoff_delay = base_delay * (2 ** (retries - 1))
            next_run = time.time() + backoff_delay
            
            conn = self._get_connection()
            try:
                conn.execute(
                    """
                    UPDATE tasks SET status = ?, retries = ?, error = ?, next_run_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (TaskState.RETRYING, retries, error, next_run, time.time(), task_id)
                )
                conn.commit()
                logger.warning(f"Task {task_id} scheduled for retry #{retries} in {backoff_delay:.2f}s")
                if self.metrics_collector:
                    self.metrics_collector.record_retry()
            finally:
                conn.close()
        else:
            logger.error(f"Task {task_id} exceeded max retries ({max_retries}). Marked as FAILED.")
            self._fail_task(task_id, f"Exceeded max retries ({max_retries}). Last error: {error}")
