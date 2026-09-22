from __future__ import annotations

import shutil
import subprocess
from typing import Any

from config import settings
from permissions import Risk, confirm
from platform_support import capabilities, detect, tool_support
from tools.filesystem import safe_path

try:
    import pyautogui  # type: ignore
except ImportError:
    pyautogui = None


def gui_capabilities() -> dict[str, Any]:
    report = capabilities()
    report["pyautogui_installed"] = pyautogui is not None
    report["ocr_engine"] = shutil.which("tesseract")
    return report


def _need_gui() -> None:
    info = detect()
    supported, reason = tool_support("screenshot", info)
    if not supported:
        raise RuntimeError(f"GUI action unavailable on {info.profile}: {reason}")
    if pyautogui is None:
        raise RuntimeError("GUI driver unavailable: install pyautogui on a trusted desktop")


def screenshot(path: str = "screen.png") -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("screenshot", info)
    if not supported:
        return {"ok": False, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    _need_gui()
    target = safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pyautogui.screenshot(str(target))
    return {"ok": True, "path": str(target)}


def ocr(path: str) -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("ocr", info)
    if not supported:
        return {"ok": False, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    target = safe_path(path)
    if not shutil.which("tesseract"):
        return {"ok": False, "error": "OCR unavailable: tesseract is not installed"}
    try:
        result = subprocess.run(["tesseract", str(target), "stdout"], capture_output=True, text=True, encoding="utf-8", errors="replace",
                                timeout=settings.command_timeout, check=False)
        return {"ok": result.returncode == 0, "text": result.stdout[-settings.max_output_chars:], "error": result.stderr[-2000:]}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}


def mouse_click(x: int, y: int, clicks: int = 1, approved: bool = False) -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("mouse_click", info)
    if not supported:
        return {"ok": False, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    _need_gui()
    action = f"click mouse at ({x}, {y}) {clicks} time(s)"
    if not approved and not confirm(Risk.PRIVILEGED, action, settings.require_confirmation):
        return {"ok": False, "error": "Mouse action not approved"}
    pyautogui.click(x=x, y=y, clicks=clicks)
    return {"ok": True, "action": action}


def type_text(text: str, approved: bool = False) -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("type_text", info)
    if not supported:
        return {"ok": False, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    _need_gui()
    if len(text) > 2000:
        return {"ok": False, "error": "Text exceeds 2000 characters"}
    action = f"type {len(text)} characters into the active window"
    if not approved and not confirm(Risk.PRIVILEGED, action, settings.require_confirmation):
        return {"ok": False, "error": "Keyboard action not approved"}
    pyautogui.write(text)
    return {"ok": True, "action": action}


def press_key(key: str, approved: bool = False) -> dict[str, Any]:
    info = detect()
    supported, reason = tool_support("press_key", info)
    if not supported:
        return {"ok": False, "error": reason, "code": "UNSUPPORTED_PLATFORM", "platform": info.profile}
    _need_gui()
    action = f"press key {key}"
    if not approved and not confirm(Risk.PRIVILEGED, action, settings.require_confirmation):
        return {"ok": False, "error": "Keyboard action not approved"}
    pyautogui.press(key)
    return {"ok": True, "action": action}
