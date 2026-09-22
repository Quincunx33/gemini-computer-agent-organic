from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class RequestQuota:
    def __init__(self, path: Path):
        self.path = Path(path).with_suffix(".quota.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS requests (ts REAL NOT NULL)")

    def allow(self, limit: int, window: int) -> bool:
        now = time.time()
        with sqlite3.connect(self.path) as db:
            db.execute("DELETE FROM requests WHERE ts < ?", (now - window,))
            count = db.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
            if count >= limit:
                return False
            db.execute("INSERT INTO requests(ts) VALUES (?)", (now,))
            return True
