from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from tools.filesystem import safe_path


def analyze_logs(log_text: str | None = None, path: str | None = None, max_lines: int = 50) -> dict[str, Any]:
    """Filter large terminal/server outputs, extract Tracebacks and pinpoint root-cause errors."""
    content = ""
    if path:
        try:
            target = safe_path(path)
            if target.exists():
                content = target.read_text(encoding="utf-8", errors="replace")
            else:
                return {"ok": False, "error": f"Log file not found: {path}", "code": "NOT_FOUND"}
        except Exception as exc:
            return {"ok": False, "error": f"Error reading log file: {exc}"}
    elif log_text:
        content = log_text
    else:
        return {"ok": False, "error": "Either log_text or path must be provided"}

    lines = content.splitlines()
    total_lines = len(lines)

    # Patterns to match error blocks
    error_pattern = re.compile(
        r"(traceback \(most recent call last\)|exception:|error:|fatal:|critical:|failed|errno|\berr\b)",
        re.IGNORECASE
    )

    extracted_blocks = []
    root_cause = "Unknown error"
    error_count = 0
    in_traceback = False
    current_block = []

    for idx, line in enumerate(lines):
        is_err = bool(error_pattern.search(line))
        if "traceback (most recent call last)" in line.lower():
            in_traceback = True
            current_block = [line]
            error_count += 1
            continue

        if in_traceback:
            current_block.append(line)
            # If exception message reached (usually line starts with no indent and contains Error/Exception)
            if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception|Exit|Interrupt):", line.strip()):
                root_cause = line.strip()
                extracted_blocks.append("\n".join(current_block))
                current_block = []
                in_traceback = False
            elif len(current_block) > 25:  # Cap single traceback
                extracted_blocks.append("\n".join(current_block))
                current_block = []
                in_traceback = False
            continue

        if is_err:
            error_count += 1
            start = max(0, idx - 2)
            end = min(total_lines, idx + 3)
            context_chunk = "\n".join(lines[start:end])
            if context_chunk not in extracted_blocks:
                extracted_blocks.append(context_chunk)
            if root_cause == "Unknown error":
                root_cause = line.strip()

    # If no explicit error keyword found but logs requested, return tail
    if not extracted_blocks:
        summary_logs = "\n".join(lines[-min(total_lines, max_lines):])
    else:
        summary_logs = "\n---\n".join(extracted_blocks[:10])

    # Suggest fix based on root cause
    suggested_fix = None
    if "ModuleNotFoundError" in root_cause or "No module named" in root_cause:
        match = re.search(r"No module named ['\"]?([A-Za-z0-9_.-]+)", root_cause)
        if match:
            suggested_fix = f"Install the missing module: install_package(package='{match.group(1)}')"
    elif "FileNotFoundError" in root_cause or "No such file" in root_cause:
        suggested_fix = "Check the file path using list_directory or find_files"
    elif "PermissionError" in root_cause:
        suggested_fix = "Check file permissions or run with appropriate access"

    return {
        "ok": True,
        "total_lines": total_lines,
        "error_count": error_count,
        "root_cause": root_cause,
        "highlighted_logs": summary_logs[:6000],
        "suggested_fix": suggested_fix,
    }
