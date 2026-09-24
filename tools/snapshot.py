from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any
from config import settings

_SNAPSHOT_DIR = Path.home() / ".genagent_snapshots"


def create_snapshot(label: str = "") -> dict[str, Any]:
    """Create a workspace snapshot before making code changes."""
    try:
        _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        sanitized_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in (label or "checkpoint"))[:30]
        snap_id = f"snap_{int(time.time())}_{sanitized_label}"
        snap_path = _SNAPSHOT_DIR / snap_id
        snap_path.mkdir(parents=True, exist_ok=True)

        manifest: dict[str, Any] = {"id": snap_id, "label": label, "timestamp": time.time(), "files": {}}
        workspace = Path(settings.workspace).expanduser().resolve()
        for p in workspace.rglob("*.py"):
            if any(part.startswith(".") or part in {"__pycache__", "venv", ".venv"} for part in p.parts):
                continue
            try:
                rel = p.relative_to(workspace)
                dest = snap_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dest)
                manifest["files"][str(rel)] = str(dest)
            except (OSError, ValueError):
                continue

        (snap_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"ok": True, "snapshot_id": snap_id, "label": label, "saved_files": len(manifest["files"])}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def restore_snapshot(snapshot_id: str) -> dict[str, Any]:
    """Restore workspace files from a previously saved snapshot."""
    snap_path = _SNAPSHOT_DIR / str(snapshot_id).strip()
    manifest_file = snap_path / "manifest.json"
    if not manifest_file.exists():
        return {"ok": False, "error": f"Snapshot '{snapshot_id}' not found", "code": "NOT_FOUND"}

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        workspace = Path(settings.workspace).expanduser().resolve()
        restored = 0
        for rel_str, backup_str in manifest.get("files", {}).items():
            dest = workspace / rel_str
            src = Path(backup_str)
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored += 1
        return {"ok": True, "snapshot_id": snapshot_id, "restored_files": restored}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
