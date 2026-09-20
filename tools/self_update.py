from __future__ import annotations

import os
import py_compile
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from config import settings
from tools.filesystem import safe_path


def self_update(path: str, content: str) -> dict[str, Any]:
    """Atomically update a workspace file and roll back Python syntax failures."""
    target = safe_path(path)
    if len(content.encode("utf-8")) > settings.max_file_size:
        return {"ok": False, "error": "Content exceeds MAX_FILE_SIZE"}
    backup_dir = settings.workspace / ".agent_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    backup = backup_dir / f"{target.name}.{int(time.time() * 1000)}.bak"
    if existed:
        shutil.copy2(target, backup)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as stream:
            stream.write(content)
            temporary = Path(stream.name)
        os.replace(temporary, target)
        if target.suffix == ".py":
            try:
                py_compile.compile(str(target), doraise=True)
            except py_compile.PyCompileError as exc:
                if existed:
                    shutil.copy2(backup, target)
                else:
                    target.unlink(missing_ok=True)
                return {"ok": False, "rolled_back": True, "error": str(exc), "backup": str(backup) if existed else None}
        return {"ok": True, "path": str(target), "backup": str(backup) if existed else None, "verified": target.suffix != ".py" or True}
    finally:
        if "temporary" in locals():
            temporary.unlink(missing_ok=True)
