from __future__ import annotations

import difflib
import os
import re
import shlex
from pathlib import Path
from typing import Any
from config import settings
from tools.filesystem import safe_path


def preview_impact(command: str | None = None, tool: str | None = None, args: dict | None = None) -> dict[str, Any]:
    """Dry-run safety simulation: preview diffs and affected files before executing risky operations."""
    args = args or {}
    affected_files = []
    diff_preview = ""
    risk_level = "low"
    warning = ""

    # Case 1: Terminal shell command simulation
    if command:
        cmd = command.strip()
        first = cmd.split()[0].lower() if cmd.split() else ""
        if first in {"rm", "del", "unlink", "rmdir"} or "git reset" in cmd or "git clean" in cmd:
            risk_level = "high"
            warning = "Destructive file deletion or Git working tree wipe detected."
            # Find targeted paths in command
            tokens = shlex.split(cmd)[1:]
            for tok in tokens:
                if not tok.startswith("-"):
                    try:
                        p = safe_path(tok)
                        if p.exists():
                            size = p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.glob("**/*") if f.is_file())
                            affected_files.append({"path": str(p), "exists": True, "is_dir": p.is_dir(), "size_bytes": size})
                    except Exception:
                        pass
        elif "chmod -r" in cmd.lower() or "chown -r" in cmd.lower():
            risk_level = "medium"
            warning = "Recursive permission alteration."
        elif "git checkout" in cmd or "git restore" in cmd:
            risk_level = "medium"
            warning = "Potential overwrite of uncommitted local changes."
        else:
            risk_level = "low"
            warning = "Standard non-destructive command execution."

    # Case 2: Tool action simulation (write_file, patch_file, delete_file)
    target_tool = tool or args.get("tool")
    if target_tool:
        path_str = args.get("path", "")
        if path_str:
            try:
                target = safe_path(path_str)
                exists = target.exists()
                old_content = target.read_text(encoding="utf-8", errors="replace") if exists else ""

                if target_tool in {"write_file", "create_file"}:
                    new_content = args.get("content", "")
                    diff = list(difflib.unified_diff(
                        old_content.splitlines(keepends=True),
                        new_content.splitlines(keepends=True),
                        fromfile=f"a/{path_str}" if exists else "/dev/null",
                        tofile=f"b/{path_str}",
                        n=3
                    ))
                    diff_preview = "".join(diff)
                    risk_level = "medium" if exists else "low"
                    affected_files.append({"path": str(target), "exists": exists, "bytes_before": len(old_content), "bytes_after": len(new_content)})
                    warning = "Existing file will be overwritten." if exists else "New file will be created."

                elif target_tool == "patch_file":
                    search = args.get("search", "")
                    replace = args.get("replace", "")
                    count = args.get("count", 1)
                    if search not in old_content:
                        diff_preview = "Search snippet not found in target file."
                        risk_level = "low"
                        warning = "Patch search snippet not matched."
                    else:
                        new_content = old_content.replace(search, replace, count)
                        diff = list(difflib.unified_diff(
                            old_content.splitlines(keepends=True),
                            new_content.splitlines(keepends=True),
                            fromfile=f"a/{path_str}",
                            tofile=f"b/{path_str}",
                            n=3
                        ))
                        diff_preview = "".join(diff)
                        risk_level = "low"
                        affected_files.append({"path": str(target), "exists": True, "replacements": min(count, old_content.count(search))})

                elif target_tool == "delete_file":
                    risk_level = "high"
                    warning = "Permanent file deletion."
                    affected_files.append({"path": str(target), "exists": exists, "size_bytes": target.stat().st_size if exists else 0})

            except Exception as exc:
                warning = f"Preview evaluation error: {exc}"

    return {
        "ok": True,
        "safe_to_proceed": risk_level != "high",
        "risk_level": risk_level,
        "affected_files": affected_files,
        "diff_preview": diff_preview[:4000],
        "warning": warning or "No high-risk operations detected."
    }
