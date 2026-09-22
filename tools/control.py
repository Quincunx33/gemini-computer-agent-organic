from __future__ import annotations

import os
import platform
import signal
import subprocess
from typing import Any

from config import settings
from permissions import Risk, confirm
from platform_support import capabilities, detect, tool_support


def platform_info() -> dict[str, Any]:
    return capabilities()


def open_app(target: str) -> dict[str, Any]:
    """Open a URL or application using the host OS launcher."""
    info = detect()
    supported, reason = tool_support("open_app", info)
    if not supported:
        return {"ok": False, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    system = info.system
    if system == "windows":
        command = ["cmd", "/c", "start", "", target]
    elif system == "darwin":
        command = ["open", target]
    elif system == "linux":
        command = ["xdg-open", target]
    else:
        return {"ok": False, "error": f"Unsupported host platform: {system}"}
    try:
        subprocess.Popen(command, cwd=settings.workspace, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "target": target, "platform": system}
    except OSError as exc:
        return {"ok": False, "error": str(exc), "target": target}


def list_processes() -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("list_processes", info)
    if not supported:
        return {"exit_code": None, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    system = info.system
    command = ["tasklist"] if system == "windows" else ["ps", "-eo", "pid,comm,args"]
    try:
        result = subprocess.run(command, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=settings.command_timeout)
        return {"exit_code": result.returncode, "stdout": result.stdout[-settings.max_output_chars:], "stderr": result.stderr[-settings.max_output_chars:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": None, "error": str(exc)}


def terminate_process(pid: int, approved: bool = False) -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("terminate_process", info)
    if not supported:
        return {"ok": False, "pid": pid, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    if not approved and not confirm(Risk.DESTRUCTIVE, f"terminate process {pid}", settings.require_confirmation):
        return {"ok": False, "error": "Process termination not approved", "pid": pid}
    try:
        os.kill(int(pid), signal.SIGTERM)
        return {"ok": True, "pid": int(pid), "signal": "SIGTERM"}
    except (OSError, ValueError) as exc:
        return {"ok": False, "pid": pid, "error": str(exc)}
