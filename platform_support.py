from __future__ import annotations

import importlib.util
import os
import platform
import shutil
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PlatformInfo:
    system: str
    release: str
    machine: str
    profile: str
    shell_family: str
    is_termux: bool
    is_ios_shell: bool
    has_display: bool
    gui_backend: str


_ALL_TOOLS = {"run_command", "read_file", "write_file", "create_file", "move_file", "delete_file", "self_update", "list_directory", "verify_python", "verify_tool", "find_alternatives", "install_and_verify", "search_web", "install_plugin", "parallel_analysis", "verify_project", "preview_diff", "git_checkpoint", "platform_info", "open_app", "list_processes", "terminate_process", "gui_capabilities", "screenshot", "ocr", "mouse_click", "type_text", "press_key"}
_GUI_ACTION_TOOLS = {"screenshot", "ocr", "mouse_click", "type_text", "press_key"}


def detect() -> PlatformInfo:
    system = platform.system().lower()
    prefix = os.getenv("PREFIX", "")
    is_termux = bool(os.getenv("TERMUX_VERSION") or prefix.endswith("com.termux/files/usr"))
    is_ios_shell = bool(os.getenv("A_SHELL") or os.getenv("IOS_SHELL")) or system in {"ios", "ipados"}
    has_display = bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY"))
    if is_ios_shell:
        profile, shell_family, backend = "ios_shell", "ios-shell", "ios-shell"
    elif is_termux:
        profile, shell_family, backend = "termux", "posix-shell", "termux-shell"
    elif system == "windows":
        profile, shell_family, backend = "windows", "windows-shell", "windows-native"
    elif system == "linux":
        profile, shell_family = "linux", "posix-shell"
        backend = "wayland-limited" if os.getenv("WAYLAND_DISPLAY") else "x11" if os.getenv("DISPLAY") else "headless"
    elif system == "darwin":
        profile, shell_family, backend = "macos", "posix-shell", "macos-accessibility"
    else:
        profile, shell_family, backend = "unknown", "unknown-shell", "headless"
    return PlatformInfo(system, platform.release(), platform.machine(), profile, shell_family, is_termux, is_ios_shell, has_display, backend)


def supported_tool_names(info: PlatformInfo | None = None) -> set[str]:
    info = info or detect()
    supported = set(_ALL_TOOLS)
    if info.profile == "ios_shell":
        supported -= {"open_app", "list_processes", "terminate_process", *_GUI_ACTION_TOOLS}
    elif info.profile == "termux":
        supported -= {"open_app", *_GUI_ACTION_TOOLS}
    elif info.profile in {"windows", "linux", "macos"}:
        if not info.has_display:
            supported -= _GUI_ACTION_TOOLS
    else:
        supported -= {"open_app", "list_processes", "terminate_process", *_GUI_ACTION_TOOLS}
    return supported


def tool_support(tool: str, info: PlatformInfo | None = None) -> tuple[bool, str]:
    info = info or detect()
    if tool in supported_tool_names(info):
        return True, "supported"
    reasons = {
        "ios_shell": "iOS shell does not expose desktop app/process/GUI control",
        "termux": "Termux is a mobile POSIX shell without desktop launcher/GUI control",
        "unknown": "platform capabilities are unknown",
    }
    return False, reasons.get(info.profile, f"tool '{tool}' is unavailable on {info.profile}")


def command_environment(info: PlatformInfo | None = None) -> dict[str, Any]:
    info = info or detect()
    return {
        "profile": info.profile,
        "shell_family": info.shell_family,
        "shell_guidance": {
            "windows-shell": "Use Windows cmd.exe or PowerShell syntax; do not send bash, sh, sed, grep, or Linux paths.",
            "posix-shell": "Use POSIX shell syntax only when the command exists on this host; Termux has a reduced/mobile command set.",
            "ios-shell": "Use a-Shell/iOS shell commands only; do not assume Linux packages, ps, GUI, or desktop paths.",
            "unknown-shell": "Ask for clarification or inspect capabilities before using platform-specific commands.",
        }.get(info.shell_family, "Inspect platform capabilities before using platform-specific commands."),
    }


def capabilities() -> dict[str, Any]:
    info = detect()
    has_gui_driver = importlib.util.find_spec("pyautogui") is not None
    supported = supported_tool_names(info)
    screenshot_tools = [name for name in ("screencapture", "gnome-screenshot", "import") if shutil.which(name)]
    if not info.has_display and info.profile not in {"windows"}:
        screenshot_tools = []
    return {
        "platform": asdict(info),
        "command_environment": command_environment(info),
        "supported_tools": sorted(supported),
        "unsupported_tools": sorted(_ALL_TOOLS - supported),
        "terminal": True,
        "files": True,
        "processes": "list_processes" in supported,
        "app_launch": "open_app" in supported,
        "gui_input": has_gui_driver and _GUI_ACTION_TOOLS.issubset(supported) and info.gui_backend in {"x11", "windows-native", "macos-accessibility"},
        "gui_driver": "pyautogui" if has_gui_driver else None,
        "screen_capture": bool(screenshot_tools),
        "screenshot_tools": screenshot_tools,
        "ios_note": "Use Shortcuts or a-Shell actions; iOS does not expose arbitrary system GUI or desktop process control." if info.is_ios_shell else None,
    }


__all__ = ["PlatformInfo", "detect", "capabilities", "supported_tool_names", "tool_support", "command_environment"]
