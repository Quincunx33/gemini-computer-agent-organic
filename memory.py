from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from permissions import redact_secrets

_TOKEN_RE = re.compile(r"[\w'-]{2,}", re.UNICODE)

_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "up", "about", "into", "over", "after", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "can", "could", "shall", "should", "will", "would", "may",
    "might", "must", "it", "its", "that", "this", "these", "those", "then", "there", "when", "where",
    "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no",
    "nor", "not", "only", "own", "same", "so", "than", "too", "very", "file", "run", "script", "code",
    "output", "print", "task", "create", "make", "check", "inspect", "koro", "ekta", "naam", "jar"
}


class Memory:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or settings.db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=30.0)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS memories(" 
            "id INTEGER PRIMARY KEY, kind TEXT, content TEXT, created_at TEXT)"
        )
        self.db.commit()

    def save(self, kind: str, content: Any) -> None:
        safe_content = redact_secrets(json.dumps(content, ensure_ascii=False))
        with self.lock:
            self.db.execute(
                "INSERT INTO memories(kind,content,created_at) VALUES(?,?,?)",
                (kind, safe_content, datetime.now(timezone.utc).isoformat()),
            )
        self.db.commit()

    def recent(self, limit: int = 10) -> list[tuple]:
        with self.lock:
            return self.db.execute(
                "SELECT kind,content,created_at FROM memories ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 100)),),
            ).fetchall()

    def relevant(self, query: str, limit: int = 3) -> list[tuple]:
        query_tokens = set(_TOKEN_RE.findall(query.lower())) - _STOP_WORDS
        if not query_tokens:
            return []
        with self.lock:
            rows = self.db.execute(
                "SELECT kind,content,created_at FROM memories ORDER BY id DESC LIMIT 200"
            ).fetchall()
        ranked: list[tuple[int, int, tuple]] = []
        for index, row in enumerate(rows):
            content_tokens = set(_TOKEN_RE.findall(f"{row[0]} {row[1]}".lower())) - _STOP_WORDS
            score = len(query_tokens & content_tokens)
            if score >= 2:
                ranked.append((score, -index, row))
        ranked.sort(reverse=True)
        return [row for _, _, row in ranked[: max(1, min(limit, 20))]]

    def context(self, query: str, limit: int = 3) -> str:
        rows = self.relevant(query, limit)
        if not rows:
            return ""
        lines = []
        for kind, content, created_at in rows:
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    task_title = data.get("task", "")[:60]
                    summary = data.get("summary", "")[:120].replace("\n", " ").strip()
                    lines.append(f"- [{kind}] {task_title}: {summary}")
                    continue
            except Exception:
                pass
            clean_snippet = content[:150].replace("\n", " ").strip()
            lines.append(f"- [{kind}] {clean_snippet}")
        return "\n".join(lines)

    def clear(self) -> None:
        with self.lock:
            self.db.execute("DELETE FROM memories")
        self.db.commit()

    def close(self) -> None:
        self.db.close()


__all__ = ["Memory"]
