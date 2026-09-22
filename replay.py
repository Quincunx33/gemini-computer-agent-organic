from __future__ import annotations

import json
from pathlib import Path
from task_store import TaskStore


def replay(task_id: str, db_path: Path) -> list[str]:
    saved = TaskStore(db_path).load(task_id)
    if not saved:
        return [f"Task not found: {task_id}"]
    events = []
    for item in saved.get("history", []):
        events.append(json.dumps(item, ensure_ascii=False, default=str))
    return events
