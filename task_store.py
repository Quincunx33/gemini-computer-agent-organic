from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class TaskStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS agent_tasks (
                task_id TEXT PRIMARY KEY, task TEXT NOT NULL, status TEXT NOT NULL,
                step INTEGER NOT NULL DEFAULT 0, history TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL)""")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def create(self, task: str) -> str:
        if not isinstance(task, str) or not task.strip():
            raise ValueError("task must be a non-empty string")
        task_id = uuid.uuid4().hex
        self.save(task_id, task, "running", 0, [])
        return task_id

    def save(self, task_id: str, task: str, status: str, step: int, history: list) -> None:
        if not task_id or not isinstance(task, str):
            raise ValueError("invalid task record")
        if status not in {"running", "completed", "failed", "paused", "cancelled"}:
            raise ValueError(f"invalid task status: {status}")
        encoded = json.dumps(history if isinstance(history, list) else [], ensure_ascii=False, default=str)
        with self._connect() as db:
            db.execute("""INSERT INTO agent_tasks(task_id, task, status, step, history, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET task=excluded.task, status=excluded.status,
                step=excluded.step, history=excluded.history, updated_at=excluded.updated_at""",
                (task_id, task, status, max(0, int(step)), encoded, time.time()))

    def load(self, task_id: str) -> dict[str, Any] | None:
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
            return None
        with self._connect() as db:
            row = db.execute("SELECT task_id, task, status, step, history FROM agent_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        try:
            history = json.loads(row[4])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"task history is corrupt for {task_id}") from exc
        if not isinstance(history, list):
            raise ValueError(f"task history is invalid for {task_id}")
        return {"task_id": row[0], "task": row[1], "status": row[2], "step": row[3], "history": history}

    def latest(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT task_id FROM agent_tasks ORDER BY updated_at DESC LIMIT 1").fetchone()
        return self.load(row[0]) if row else None
