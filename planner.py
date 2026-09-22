from __future__ import annotations

TOOLS=[
    {"name":"run_command","description":"Run a workspace shell command; risky commands require confirmation.","parameters":{"type":"object","properties":{"command":{"type":"string"},"cwd":{"type":"string"}},"required":["command"]}},
    {"name":"read_file","description":"Read a workspace text file.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
    {"name":"write_file","description":"Write a workspace file after inspection.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
    {"name":"self_update","description":"Atomically update a source file with backup and Python rollback.","parameters":{"type":"object","properties":{"path":{"type":"string"},"content":{"type":"string"}},"required":["path","content"]}},
    {"name":"list_directory","description":"List workspace files.","parameters":{"type":"object","properties":{"path":{"type":"string"}}}},
    {"name":"verify_python","description":"Compile a Python file and report syntax errors.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
    {"name":"platform_info","description":"Report host and control capabilities.","parameters":{"type":"object","properties":{}}},
    {"name":"open_app","description":"Open a URL, file, or app via the host launcher.","parameters":{"type":"object","properties":{"target":{"type":"string"}},"required":["target"]}},
    {"name":"list_processes","description":"List running processes.","parameters":{"type":"object","properties":{}}},
    {"name":"terminate_process","description":"Terminate a process after confirmation.","parameters":{"type":"object","properties":{"pid":{"type":"integer"}},"required":["pid"]}},
    {"name":"gui_capabilities","description":"Report GUI and OCR availability.","parameters":{"type":"object","properties":{}}},
    {"name":"screenshot","description":"Capture the desktop to a workspace image.","parameters":{"type":"object","properties":{"path":{"type":"string"}}}},
    {"name":"ocr","description":"Extract text from a workspace screenshot.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}},
    {"name":"mouse_click","description":"Click desktop coordinates after confirmation.","parameters":{"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"},"clicks":{"type":"integer"}},"required":["x","y"]}},
    {"name":"type_text","description":"Type into the active window after confirmation.","parameters":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}},
    {"name":"press_key","description":"Press a keyboard key after confirmation.","parameters":{"type":"object","properties":{"key":{"type":"string"}},"required":["key"]}},
]


_READ_TOOLS = {"list_directory", "read_file", "platform_info", "gui_capabilities", "list_processes", "verify_python"}
_WRITE_TOOLS = {"write_file", "self_update", "run_command", "read_file", "list_directory", "verify_python"}
_GUI_TOOLS = {"platform_info", "gui_capabilities", "screenshot", "ocr", "mouse_click", "type_text", "press_key"}
_PROCESS_TOOLS = {"platform_info", "list_processes", "terminate_process", "open_app", "run_command"}


def tools_for_task(task: str, enabled: bool = True, platform_info=None) -> list[dict]:
    """Return the smallest safe schema set suggested by task intent.

    Ambiguous tasks deliberately receive the full schema; filtering is an
    optimization, never a capability or permission bypass.
    """
    if platform_info is None:
        from platform_support import detect
        platform_info = detect()
    from platform_support import supported_tool_names
    supported = supported_tool_names(platform_info)
    if not enabled:
        return [tool for tool in TOOLS if tool["name"] in supported]
    text = (task or "").lower()
    write_words = ("write", "edit", "change", "modify", "update", "fix", "implement", "create", "delete", "remove", "install")
    gui_words = ("gui", "screen", "screenshot", "click", "mouse", "keyboard", "type", "desktop", "ocr")
    process_words = ("process", "application", "app", "open", "terminate", "kill", "pid")
    test_words = ("test", "run", "command", "compile", "build", "shell", "execute")
    if any(word in text for word in write_words):
        names = _WRITE_TOOLS
    elif any(word in text for word in gui_words):
        names = _GUI_TOOLS | {"read_file", "list_directory"}
    elif any(word in text for word in process_words):
        names = _PROCESS_TOOLS
    elif any(word in text for word in test_words):
        names = _WRITE_TOOLS | {"platform_info"}
    elif any(word in text for word in ("inspect", "read", "list", "status", "check", "find", "what")):
        names = _READ_TOOLS
    else:
        return [tool for tool in TOOLS if tool["name"] in supported]
    return [tool for tool in TOOLS if tool["name"] in names and tool["name"] in supported]
