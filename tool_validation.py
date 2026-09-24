from __future__ import annotations
from typing import Any

REQUIRED = {
    "read_file": {"path": str}, "write_file": {"path": str, "content": str},
    "patch_file": {"path": str, "search": str, "replace": str},
    "self_update": {"path": str, "content": str}, "create_file": {"path": str, "content": str}, "move_file": {"source": str, "destination": str}, "delete_file": {"path": str}, "verify_python": {"path": str}, "verify_tool": {"requested": str}, "install_and_verify": {"requested": str}, "install_package": {"package": str}, "inspect_code": {"path": str}, "restore_snapshot": {"snapshot_id": str}, "create_skill": {"name": str, "description": str, "instructions": str}, "synthesize_tool": {"name": str, "code": str}, "execute_synthesized_tool": {"name": str, "function": str}, "check_port": {"port": int}, "search_web": {"query": str}, "install_plugin": {"archive": str}, "parallel_analysis": {"tasks": list}, "preview_diff": {"path": str}, "git_checkpoint": {"label": str},
    "ocr": {"path": str}, "inspect_image": {"path": str}, "open_app": {"target": str}, "terminate_process": {"pid": int},
    "type_text": {"text": str}, "press_key": {"key": str},
    "mouse_click": {"x": int, "y": int}, "run_command": {"command": str},
}

def validate_tool_args(name: str, args: Any) -> tuple[bool, str]:
    if not isinstance(args, dict):
        return False, "arguments must be an object"
    for key, expected in REQUIRED.get(name, {}).items():
        if key not in args:
            return False, f"missing required argument: {key}"
        if not isinstance(args[key], expected) or isinstance(args[key], bool):
            return False, f"{key} must be {expected.__name__}"
    if name in {"read_file", "write_file", "patch_file", "self_update", "verify_python", "ocr"} and len(str(args.get("path", ""))) > 4096:
        return False, "path is too long"
    if name in {"write_file", "self_update"} and len(args.get("content", "").encode("utf-8")) > 100 * 1024 * 1024:
        return False, "content is too large"
    if name == "mouse_click" and any(abs(args[key]) > 100_000 for key in ("x", "y")):
        return False, "mouse coordinates are out of range"
    if name == "terminate_process" and args["pid"] <= 0:
        return False, "pid must be positive"
    return True, ""
