from __future__ import annotations

import os
import platform
import shutil
import importlib.util
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PlatformInfo:
    system: str
    release: str
    machine: str
    is_termux: bool
    is_ios_shell: bool
    has_display: bool
    gui_backend: str


def detect() -> PlatformInfo:
    system = platform.system().lower()
    is_termux = bool(os.getenv("TERMUX_VERSION") or os.getenv("PREFIX", "").endswith("com.termux/files/usr"))
    is_ios_shell = system == "darwin" and bool(os.getenv("A_SHELL") or os.getenv("IOS_SHELL"))
    if system == "windows":
        backend = "windows-native"
    elif system == "darwin":
        backend = "macos-accessibility"
    elif system == "linux" and os.getenv("WAYLAND_DISPLAY"):
        backend = "wayland-limited"
    elif system == "linux" and os.getenv("DISPLAY"):
        backend = "x11"
    elif is_termux:
        backend = "termux-shell"
    else:
        backend = "headless"
    return PlatformInfo(system, platform.release(), platform.machine(), is_termux,
                        is_ios_shell, bool(os.getenv("DISPLAY") or os.getenv("WAYLAND_DISPLAY")), backend)


def capabilities() -> dict:
    info = detect()
    has_gui_driver = importlib.util.find_spec("pyautogui") is not None
    return {
        "platform": asdict(info),
        "terminal": True,
        "files": True,
        "processes": True,
        "app_launch": info.system in {"windows", "darwin", "linux"},
        "gui_input": has_gui_driver and info.gui_backend in {"x11", "windows-native", "macos-accessibility"},
        "gui_driver": "pyautogui" if has_gui_driver else None,
        "screen_capture": bool(shutil.which("screencapture") or shutil.which("gnome-screenshot") or shutil.which("import")),
        "ios_note": "Use Shortcuts or a-Shell actions; iOS does not expose arbitrary system GUI control." if info.is_ios_shell else None,
    }
