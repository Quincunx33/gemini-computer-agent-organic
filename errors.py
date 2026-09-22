"""Application-wide error contract for safe, observable failure handling.

This module intentionally uses only the Python standard library. Internal
exceptions are converted to stable, non-secret public errors at boundaries.
"""
from __future__ import annotations

import json
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any

from permissions import redact_secrets


@dataclass
class AgentError(Exception):
    """A controlled error that is safe to cross an application boundary."""

    code: str
    message: str
    public_message: str | None = None
    retryable: bool = False
    status: int = 500
    details: dict[str, Any] = field(default_factory=dict)
    error_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
        self.message = _clean(self.message)
        self.public_message = _clean(self.public_message or self.message)
        self.status = max(400, min(599, int(self.status)))

    def to_dict(self, *, include_details: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.public_message,
                "error_id": self.error_id,
                "retryable": self.retryable,
            }
        }
        if include_details and self.details:
            result["error"]["details"] = _safe_value(self.details)
        return result


def _clean(value: Any) -> str:
    return redact_secrets(str(value)).replace("\x00", "\\0")[:2000]


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(v) for v in value]
    if isinstance(value, str):
        return _clean(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _clean(value)


def normalize_exception(exc: BaseException, *, operation: str = "operation") -> AgentError:
    """Map arbitrary exceptions to stable categories without exposing secrets."""
    if isinstance(exc, AgentError):
        return exc

    name = type(exc).__name__
    message = _clean(str(exc) or name)
    lower = message.lower()
    if isinstance(exc, (TimeoutError,)) or "timed out" in lower or "timeout" in lower:
        return AgentError("TIMEOUT", f"{operation} timed out", "The operation timed out. Please retry.", True, 504, {"exception": name})
    if isinstance(exc, (ConnectionError, OSError)) and any(x in lower for x in ("connection", "network", "dns", "name or service", "refused", "unreachable")):
        return AgentError("NETWORK_ERROR", f"{operation} network failure: {message}", "A network error interrupted the operation. Please retry.", True, 503, {"exception": name})
    if isinstance(exc, PermissionError):
        return AgentError("PERMISSION_DENIED", f"{operation} permission denied", "Permission was denied for this operation.", False, 403, {"exception": name})
    if isinstance(exc, (ValueError, TypeError, json.JSONDecodeError)):
        return AgentError("INVALID_RESPONSE", f"{operation} returned invalid data: {message}", "The operation returned an invalid response.", False, 502, {"exception": name})
    if isinstance(exc, FileNotFoundError):
        return AgentError("NOT_FOUND", f"{operation} resource not found", "The requested resource was not found.", False, 404, {"exception": name})
    return AgentError("INTERNAL_ERROR", f"{operation} failed: {message}", "The agent could not complete the operation.", False, 500, {"exception": name})


def error_payload(exc: BaseException, *, operation: str = "operation", include_details: bool = False) -> dict[str, Any]:
    return normalize_exception(exc, operation=operation).to_dict(include_details=include_details)


def error_text(exc: BaseException, *, operation: str = "operation") -> str:
    err = normalize_exception(exc, operation=operation)
    return f"{err.public_message} (error_id={err.error_id})"


def traceback_text(exc: BaseException) -> str:
    """Return a bounded diagnostic for logs; never use this for user responses."""
    return _clean("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))[:8000]


__all__ = ["AgentError", "normalize_exception", "error_payload", "error_text", "traceback_text"]


def _json_default(value: Any) -> str:
    return _clean(value)


# Keep this helper private but testable through the public boundary behavior.
def safe_json(value: Any) -> str:
    return json.dumps(_safe_value(value), ensure_ascii=False, default=_json_default)


__all__.append("safe_json")
