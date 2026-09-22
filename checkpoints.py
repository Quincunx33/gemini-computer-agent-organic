from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import difflib
import shutil


def checkpoint(path: Path, root: Path) -> Path | None:
    if not path.exists() or not path.is_file():
        return None
    directory = root / ".agent_checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{path.name}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.bak"
    shutil.copy2(path, target)
    return target


def diff_text(before: str, after: str, path: str) -> str:
    return "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile=path, tofile=path))[:20000]
