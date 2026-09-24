from __future__ import annotations

TOOLS = [
    {"name": "list_skills", "description": "List installed skill packs and their descriptions.", "parameters": {"type": "object", "properties": {}}},
    {"name": "find_alternatives", "description": "Check whether a capability exists and find installed or standard-library alternatives without installing anything.", "parameters": {"type": "object", "properties": {"requested": {"type": "string"}}, "required": ["requested"]}},
    {"name": "verify_tool", "description": "Verify an installed CLI tool and report its version.", "parameters": {"type": "object", "properties": {"requested": {"type": "string"}}, "required": ["requested"]}},
    {"name": "install_and_verify", "description": "Install a known allowlisted tool, then verify it; returns a fallback on failure.", "parameters": {"type": "object", "properties": {"requested": {"type": "string"}}, "required": ["requested"]}},
    {"name": "install_package", "description": "Autonomously install a Python package or system CLI tool via pip, apt, brew, or pkg.", "parameters": {"type": "object", "properties": {"package": {"type": "string"}, "manager": {"type": "string"}}, "required": ["package"]}},
    {"name": "inspect_code", "description": "Inspect Python code structure (classes, functions, lines) or extract exact source code of a specific class or function using AST without dumping entire files.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "symbol": {"type": "string"}}, "required": ["path"]}},
    {"name": "create_snapshot", "description": "Create a reversible workspace snapshot before making changes to code.", "parameters": {"type": "object", "properties": {"label": {"type": "string"}}}},
    {"name": "restore_snapshot", "description": "Restore workspace files from a previously saved snapshot.", "parameters": {"type": "object", "properties": {"snapshot_id": {"type": "string"}}, "required": ["snapshot_id"]}},
    {"name": "create_skill", "description": "Save a new reusable workflow or tool technique as a persistent skill pack.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "description": {"type": "string"}, "instructions": {"type": "string"}}, "required": ["name", "description", "instructions"]}},
    {"name": "synthesize_tool", "description": "Dynamically write, test, and register a new Python tool as a permanent skill in the workspace.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "code": {"type": "string"}, "test_code": {"type": "string"}, "description": {"type": "string"}}, "required": ["name", "code"]}},
    {"name": "execute_synthesized_tool", "description": "Dynamically execute a function from an autonomously synthesized skill tool.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "function": {"type": "string"}, "args": {"type": "object"}}, "required": ["name", "function"]}},
    {"name": "analyze_logs", "description": "Smart log analyzer: filter large terminal/server outputs, extract Tracebacks, and pinpoint root-cause errors.", "parameters": {"type": "object", "properties": {"log_text": {"type": "string"}, "path": {"type": "string"}, "max_lines": {"type": "integer"}}}},
    {"name": "check_port", "description": "Check if a local/remote TCP port or HTTP web server is active, responding, and healthy.", "parameters": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer"}, "timeout": {"type": "number"}}, "required": ["port"]}},
    {"name": "check_process_resources", "description": "Inspect running processes for high CPU/RAM usage, hang/zombie status, and resource spikes.", "parameters": {"type": "object", "properties": {"pid": {"type": "integer"}}}},
    {"name": "preview_impact", "description": "Dry-run safety simulation: preview diffs and affected files before executing risky or destructive operations.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "tool": {"type": "string"}, "args": {"type": "object"}}}},
    {"name": "search_web", "description": "Search public web results and return source URLs for an unavailable tool or fact.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}},
    {"name": "install_plugin", "description": "Validate and install a plugin zip into the workspace without executing plugin code.", "parameters": {"type": "object", "properties": {"archive": {"type": "string"}}, "required": ["archive"]}},
    {"name": "parallel_analysis", "description": "Run up to four bounded read-only sub-agent analyses in parallel.", "parameters": {"type": "object", "properties": {"tasks": {"type": "array", "items": {"type": "string"}}, "max_workers": {"type": "integer"}}, "required": ["tasks"]}},
    {"name": "verify_project", "description": "Run the project's standard unittest suite and return evidence for recovery or completion.", "parameters": {"type": "object", "properties": {}}},
    {"name": "preview_diff", "description": "Show the current Git diff without changing files.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "git_checkpoint", "description": "Save a reversible Git diff checkpoint artifact before a change.", "parameters": {"type": "object", "properties": {"label": {"type": "string"}}}},
    {"name": "run_command", "description": "Run a workspace shell command; risky commands require confirmation.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "cwd": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read a workspace text file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write a workspace file after inspection.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "patch_file", "description": "Replace an exact snippet or section in a file without rewriting the entire file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "search": {"type": "string"}, "replace": {"type": "string"}, "count": {"type": "integer"}}, "required": ["path", "search", "replace"]}},
    {"name": "create_file", "description": "Create a new workspace file without overwriting an existing file.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "move_file", "description": "Move a workspace file without overwriting an existing destination.", "parameters": {"type": "object", "properties": {"source": {"type": "string"}, "destination": {"type": "string"}}, "required": ["source", "destination"]}},
    {"name": "delete_file", "description": "Delete a workspace file only after explicit user approval.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "self_update", "description": "Atomically update a source file with backup and Python rollback.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "list_directory", "description": "List workspace files.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "verify_python", "description": "Compile a Python file and report syntax errors.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "platform_info", "description": "Report host and control capabilities.", "parameters": {"type": "object", "properties": {}}},
    {"name": "open_app", "description": "Open a URL, file, or app via the host launcher.", "parameters": {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]}},
    {"name": "list_processes", "description": "List running processes.", "parameters": {"type": "object", "properties": {}}},
    {"name": "terminate_process", "description": "Terminate a process after confirmation.", "parameters": {"type": "object", "properties": {"pid": {"type": "integer"}}, "required": ["pid"]}},
    {"name": "gui_capabilities", "description": "Report GUI and OCR availability.", "parameters": {"type": "object", "properties": {}}},
    {"name": "screenshot", "description": "Capture the desktop to a workspace image.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
    {"name": "ocr", "description": "Extract text from a workspace screenshot.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "inspect_image", "description": "Visually inspect and understand an image or screenshot without external OCR dependencies.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "prompt": {"type": "string"}}, "required": ["path"]}},
    {"name": "mouse_click", "description": "Click desktop coordinates after confirmation.", "parameters": {"type": "object", "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}, "clicks": {"type": "integer"}}, "required": ["x", "y"]}},
    {"name": "type_text", "description": "Type into the active window after confirmation.", "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "press_key", "description": "Press a keyboard key after confirmation.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}},
]


CORE_PRIMITIVE_NAMES = {"run_command", "read_file", "write_file", "patch_file", "inspect_image"}


def tools_for_task(task: str, enabled: bool = False, platform_info=None) -> list[dict]:
    """Provide minimal universal core primitives to the AI for complete autonomous decision-making."""
    from config import settings
    if platform_info is None:
        from platform_support import detect
        platform_info = detect()
    from platform_support import supported_tool_names
    supported = supported_tool_names(platform_info)

    if getattr(settings, "pure_primitives_only", True):
        # Pure autonomous mode: Only universal core primitives!
        # The AI decides how to use terminal/python/files freely without bloated hardcoded tools.
        return [tool for tool in TOOLS if tool["name"] in CORE_PRIMITIVE_NAMES and tool["name"] in supported]

    return [tool for tool in TOOLS if tool["name"] in supported]
