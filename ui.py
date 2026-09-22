from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

from permissions import redact_secrets

_LABELS = {
    "list_skills": "Listing available skills",
    "list_directory": "Listing files and folders",
    "read_file": "File read",
    "write_file": "Writing file",
    "create_file": "Creating file",
    "move_file": "Moving file",
    "delete_file": "Deleting file",
    "self_update": "Updating code safely",
    "run_command": "Running command",
    "verify_python": "Verifying Python code",
    "verify_tool": "Verifying installed tool",
    "verify_project": "Running project verification",
    "preview_diff": "Previewing Git diff",
    "git_checkpoint": "Saving Git checkpoint",
    "platform_info": "Checking system capabilities",
    "open_app": "Opening app or link",
    "list_processes": "Listing running processes",
    "terminate_process": "Terminating process",
    "gui_capabilities": "Checking GUI capabilities",
    "screenshot": "Taking screenshot",
    "ocr": "Reading text from screenshot",
    "mouse_click": "Clicking on screen",
    "type_text": "Typing text",
    "press_key": "Pressing key",
}


class _Theme:
    def __init__(self, enabled: bool | None = None):
        if enabled is None:
            enabled = bool(sys.stdout.isatty()) and os.getenv("NO_COLOR") is None
        self.enabled = enabled
        self.reset = "\033[0m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.bold = "\033[1m" if enabled else ""
        self.blue = "\033[38;5;75m" if enabled else ""
        self.cyan = "\033[38;5;80m" if enabled else ""
        self.green = "\033[38;5;114m" if enabled else ""
        self.yellow = "\033[38;5;221m" if enabled else ""
        self.red = "\033[38;5;210m" if enabled else ""
        self.gray = "\033[38;5;245m" if enabled else ""

    def paint(self, color: str, text: Any) -> str:
        return f"{color}{text}{self.reset}"


def _clean(value: Any, limit: int = 700) -> str:
    return redact_secrets(str(value)).replace("\n", " ").strip()[:limit]


def format_response(value: Any) -> str:
    """Turn model Markdown/JSON-ish output into readable terminal text."""
    text = str(value or "").strip()
    if text.startswith("{"):
        try:
            encoded = json.loads(text)
            if isinstance(encoded, dict) and isinstance(encoded.get("text"), str):
                text = encoded["text"]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    text = text.replace("\\n", "\n").replace("\\\"", '"')
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _width() -> int:
    try:
        return max(56, min(100, os.get_terminal_size().columns))
    except OSError:
        return 72


class EventRenderer:
    """Render compact, professional execution events without third-party UI libraries."""

    def __init__(self, debug: bool = False, color: bool | None = None):
        self.debug = debug
        self.theme = _Theme(color)

    def set_debug(self, enabled: bool) -> None:
        self.debug = bool(enabled)

    def _debug(self, event: str, **fields: Any) -> str:
        payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event}
        payload.update(fields)
        return "[DEBUG] " + json.dumps(payload, ensure_ascii=False, default=str)

    def start(self, name: str, args: dict[str, Any]) -> str:
        if self.debug:
            return self._debug("tool_start", tool=name, args=redact_secrets(json.dumps(args, ensure_ascii=False, default=str)))
        label = _LABELS.get(name, f"Running {name}")
        detail = ""
        if name in {"read_file", "write_file", "create_file", "self_update", "list_directory", "screenshot", "ocr"}:
            detail = f" · {_clean(args.get('path', args.get('target', '.')), 420)}"
        elif name == "run_command":
            detail = f" · {_clean(args.get('command', ''), 420)}"
        return f"  {self.theme.paint(self.theme.blue, '>')} {label}{self.theme.paint(self.theme.gray, detail)}"

    def permission(self, name: str, args: dict[str, Any]) -> str:
        if self.debug:
            return self._debug("permission_required", tool=name, args=redact_secrets(json.dumps(args, ensure_ascii=False, default=str)))
        return f"  {self.theme.paint(self.theme.yellow, '!')} {self.theme.paint(self.theme.yellow, 'Permission required')} - {_LABELS.get(name, name)}"

    def auto(self, name: str) -> str:
        if self.debug:
            return self._debug("auto_execute", tool=name)
        return ""

    def result(self, name: str, result: Any, duration_ms: float) -> str:
        if self.debug:
            return self._debug("tool_result", tool=name, duration_ms=round(duration_ms, 1), result=redact_secrets(json.dumps(result, ensure_ascii=False, default=str))[:2000])
        if isinstance(result, dict) and result.get("error"):
            code = result.get("code", "UNKNOWN")
            return f"  {self.theme.paint(self.theme.red, 'X')} {name} {self.theme.paint(self.theme.gray, f'[{code}]')} - {_clean(result.get('error'))}"
        summary = "Completed"
        if name == "read_file":
            summary = "File read"
        elif name == "list_directory":
            summary = f"{len(result.get('files', [])) if isinstance(result, dict) else 0} entries found"
        elif name == "run_command":
            code = result.get("exit_code") if isinstance(result, dict) else None
            summary = f"Command finished · exit code {code}"
        elif name in {"verify_python", "platform_info", "gui_capabilities"}:
            summary = "Verification complete"
        elapsed = self.theme.paint(self.theme.gray, f"{round(duration_ms)}ms")
        return f"  {self.theme.paint(self.theme.green, 'OK')} {summary} {elapsed}"

    def thinking(self) -> str:
        return self._debug("model_request") if self.debug else f"  {self.theme.paint(self.theme.cyan, '...')} Planning the next safe action..."

    def divider(self, char: str = "-") -> str:
        return self.theme.paint(self.theme.gray, char * _width())
