from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from config import settings


def verify_project() -> dict[str, Any]:
    root = settings.workspace
    tests = root / "tests"
    if not tests.is_dir():
        return {"ok": False, "code": "NO_TESTS", "workspace": str(root), "message": "No tests directory found."}
    command = ["python3", "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]
    try:
        completed = subprocess.run(command, cwd=str(root), capture_output=True, text=True, timeout=settings.command_timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "TIMEOUT", "command": command}
    output = ((completed.stdout or "") + (completed.stderr or ""))[-settings.max_output_chars:]
    return {"ok": completed.returncode == 0, "code": "PASS" if completed.returncode == 0 else "TEST_FAILURE", "command": command, "exit_code": completed.returncode, "output": output}
