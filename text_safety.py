"""Helpers for safely displaying text received from operating systems and APIs."""
from __future__ import annotations

from typing import Any


def safe_text(value: Any) -> str:
    """Return text that can always be encoded by a UTF-8 terminal.

    Some macOS/iPadOS APIs and subprocess boundaries can produce lone UTF-16
    surrogate characters. They are valid Python strings but cannot be encoded
    as UTF-8, so replace them with the Unicode replacement character before
    displaying or sending them across a JSON/UTF-8 boundary.
    """
    text = value if isinstance(value, str) else str(value)
    return "".join("�" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)


def safe_value(value: Any) -> Any:
    """Recursively sanitize strings inside a result before printing/serializing."""
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, dict):
        return {safe_value(key): safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [safe_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(safe_value(item) for item in value)
    return value


def configure_terminal() -> None:
    """Make the CLI resilient even when a caller bypasses safe_text()."""
    import sys

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
