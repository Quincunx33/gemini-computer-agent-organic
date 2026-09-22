from __future__ import annotations

import subprocess
from pathlib import Path
from datetime import datetime, timezone
from config import settings


def _git(args: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(["git", *args], cwd=str(settings.workspace), capture_output=True, text=True, timeout=20, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def preview_diff(path: str | None = None) -> dict:
    args = ["diff", "--no-ext-diff"]
    if path:
        args += ["--", path]
    code, stdout, stderr = _git(args)
    return {"ok": code == 0, "path": path, "diff": stdout[-30000:], "error": stderr[-2000:] if code else ""}


def git_checkpoint(label: str = "checkpoint") -> dict:
    checkpoint_dir = settings.workspace / ".agent_checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    safe_label = "".join(char if char.isalnum() or char in "-_" else "_" for char in (label or "checkpoint"))[:80]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    status_code, status, status_err = _git(["status", "--short"])
    diff_code, diff, diff_err = _git(["diff", "--no-ext-diff"])
    if status_code != 0:
        return {"ok": False, "code": "NOT_A_GIT_REPOSITORY", "error": status_err[-2000:]}
    target = checkpoint_dir / f"git-{safe_label}-{stamp}.patch"
    target.write_text(diff, encoding="utf-8")
    return {"ok": diff_code == 0, "path": str(target), "status": status[-10000:], "changed": bool(status.strip()), "diff_bytes": len(diff.encode("utf-8"))}
