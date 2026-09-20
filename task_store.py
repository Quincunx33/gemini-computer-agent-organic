from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any


class TaskStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS agent_tasks (
                task_id TEXT PRIMARY KEY, task TEXT NOT NULL, status TEXT NOT NULL,
                step INTEGER NOT NULL DEFAULT 0, history TEXT NOT NULL DEFAULT '[]',
                updated_at REAL NOT NULL)""")

    def create(self, task: str) -> str:
        task_id = uuid.uuid4().hex
        self.save(task_id, task, "running", 0, [])
        return task_id

    def save(self, task_id: str, task: str, status: str, step: int, history: list) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("""INSERT INTO agent_tasks(task_id, task, status, step, history, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET status=excluded.status, step=excluded.step,
                history=excluded.history, updated_at=excluded.updated_at""",
                (task_id, task, status, step, json.dumps(history, ensure_ascii=False), time.time()))

    def load(self, task_id: str) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT task_id, task, status, step, history FROM agent_tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            return None
        return {"task_id": row[0], "task": row[1], "status": row[2], "step": row[3], "history": json.loads(row[4])}

    def latest(self) -> dict[str, Any] | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT task_id FROM agent_tasks ORDER BY updated_at DESC LIMIT 1").fetchone()
        return self.load(row[0]) if row else None
