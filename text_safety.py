from __future__ import annotations
from typing import Any

def safe_text(value: Any) -> str:
    text = value if isinstance(value, str) else str(value)
    return "".join("" if 0xD800 <= ord(char) <= 0xDFFF else char for char in text)

def safe_value(value: Any) -> Any:
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
    import sys
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")
