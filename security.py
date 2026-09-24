from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from config import settings
from permissions import redact_secrets


class RateLimiter:
    def __init__(self, limit: int = 30, window_seconds: int = 60):
        self.limit = max(1, limit)
        self.window_seconds = max(1, window_seconds)
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            events = self._events[key]
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True


class AuditLogger:
    def __init__(self, path: Path, rotate_hours: float | None = None, retention: int | None = None):
        self.path = Path(path).expanduser()
        self.rotate_seconds = max(3600.0, float(rotate_hours if rotate_hours is not None else settings.log_rotate_hours) * 3600)
        self.retention = max(1, int(retention if retention is not None else settings.log_retention))
        self._lock = threading.Lock()

    def _archive_pattern(self) -> str:
        return f"{self.path.name}.20*"

    def _prune(self) -> None:
        archives = sorted(self.path.parent.glob(self._archive_pattern()), key=lambda item: item.stat().st_mtime, reverse=True)
        for stale in archives[self.retention:]:
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                continue

    def _rotate_if_due(self, now: float) -> None:
        try:
            age = now - self.path.stat().st_mtime
        except FileNotFoundError:
            return
        except OSError:
            return
        if age < self.rotate_seconds:
            return

        timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now))
        archive = self.path.with_name(f"{self.path.name}.{timestamp}")
        suffix = 1
        while archive.exists():
            archive = self.path.with_name(f"{self.path.name}.{timestamp}.{suffix}")
            suffix += 1
        try:
            self.path.replace(archive)
        except FileNotFoundError:
            return
        except OSError:
            return
        self._prune()

    def reset(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                now = time.time()
                old_mtime = self.path.stat().st_mtime
                try:
                    os.utime(self.path, (old_mtime - self.rotate_seconds - 1, old_mtime - self.rotate_seconds - 1))
                except OSError:
                    pass
                self._rotate_if_due(now)

    def write(self, event: str, **fields: Any) -> None:
        record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": redact_secrets(str(event))[:200]}
        for key, value in fields.items():
            text = redact_secrets(str(value)) if isinstance(value, str) else value
            record[str(key)] = text
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._rotate_if_due(time.time())
            try:
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(line)
                    stream.flush()
            except OSError:
                raise
