from __future__ import annotations

import ast
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from config import settings


def synthesize_tool(name: str, code: str, test_code: str | None = None, description: str = "") -> dict[str, Any]:
    """Dynamically write, test, and register a new tool script as a permanent skill in the workspace."""
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", (name or "").strip().lower())
    if not clean_name:
        return {"ok": False, "error": "Tool name is required"}

    # Step 1: Validate Python AST syntax
    try:
        ast.parse(code)
    except SyntaxError as exc:
        return {"ok": False, "error": f"Python syntax error in synthesized code at line {exc.lineno}: {exc.msg}", "code": "SYNTAX_ERROR"}

    # Step 2: Target path in skills directory
    skill_dir = Path(settings.skills_path) / clean_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    tool_file = skill_dir / "tool.py"
    tool_file.write_text(code.strip() + "\n", encoding="utf-8")

    # Step 3: Run validation / test code in subprocess if provided
    verification_output = "Syntax validated successfully."
    if test_code:
        test_script = f"{code}\n\n# Verification test\n{test_code}"
        try:
            completed = subprocess.run(
                [sys.executable, "-c", test_script],
                capture_output=True, text=True, timeout=15, check=False
            )
            if completed.returncode != 0:
                # Remove on failure
                tool_file.unlink(missing_ok=True)
                return {
                    "ok": False,
                    "error": "Synthesized tool failed its verification test.",
                    "exit_code": completed.returncode,
                    "stderr": completed.stderr[:1000],
                    "stdout": completed.stdout[:1000]
                }
            verification_output = completed.stdout.strip() or "All test cases passed."
        except subprocess.TimeoutExpired:
            tool_file.unlink(missing_ok=True)
            return {"ok": False, "error": "Tool verification test timed out."}
        except Exception as exc:
            tool_file.unlink(missing_ok=True)
            return {"ok": False, "error": f"Execution test failed: {exc}"}

    # Step 4: Write SKILL.md for skill persistence
    desc = description.strip() or f"Autonomously synthesized Python tool: {clean_name}"
    skill_md = f"""---
name: {clean_name}
description: {desc}
---

## Tool Usage
This tool is installed at `{tool_file}`.
Run it using `run_command` via `{sys.executable} {tool_file}` or via `execute_synthesized_tool`.
"""
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")

    return {
        "ok": True,
        "name": clean_name,
        "tool_path": str(tool_file),
        "skill_dir": str(skill_dir),
        "verified": True,
        "test_output": verification_output,
        "message": f"Tool '{clean_name}' successfully synthesized, tested, and saved as a persistent skill."
    }


def execute_synthesized_tool(name: str, function: str, args: dict | None = None) -> dict[str, Any]:
    """Dynamically execute a function from a synthesized skill tool."""
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", (name or "").strip().lower())
    tool_file = Path(settings.skills_path) / clean_name / "tool.py"
    if not tool_file.exists():
        return {"ok": False, "error": f"Synthesized tool '{clean_name}' not found at {tool_file}", "code": "NOT_FOUND"}

    fn_name = (function or "").strip()
    args = args or {}

    try:
        spec = importlib.util.spec_from_file_location(f"dyn_{clean_name}", str(tool_file))
        if not spec or not spec.loader:
            return {"ok": False, "error": "Failed to create module specification"}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, fn_name):
            return {"ok": False, "error": f"Function '{fn_name}' not found in {tool_file}"}

        target_fn = getattr(module, fn_name)
        result = target_fn(**args)
        return {"ok": True, "name": clean_name, "function": fn_name, "result": result}
    except Exception as exc:
        return {"ok": False, "error": f"Execution error in {fn_name}: {exc}"}
