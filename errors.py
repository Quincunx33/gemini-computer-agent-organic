"""
Application-wide error handling architecture for GenAgent.
Pure Python standard library (zero external runtime dependencies).
Provides structured classification, root-cause analysis (RCA),
stack trace sanitization, self-healing recovery strategies, and
actionable remediation suggestions.
"""
from __future__ import annotations

import ast
import json
import os
import random
import re
import socket
import sys
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from permissions import redact_secrets


class ErrorCategory:
    SYSTEM = "system"
    SECURITY = "security"
    SYNTAX = "syntax"
    NETWORK = "network"
    TIMEOUT = "timeout"
    EXECUTION = "execution"
    RESOURCE = "resource"
    VALIDATION = "validation"
    RATE_LIMIT = "rate_limit"
    INTERNAL = "internal"


@dataclass
class AgentError(Exception):
    code: str
    message: str
    public_message: str | None = None
    category: str = ErrorCategory.INTERNAL
    suggestion: str = ""
    root_cause: str = ""
    retryable: bool = False
    status: int = 500
    details: dict[str, Any] = field(default_factory=dict)
    error_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        super().__init__(self.message)
        self.message = _clean(self.message)
        self.public_message = _clean(self.public_message or self.message)
        self.suggestion = _clean(self.suggestion)
        self.root_cause = _clean(self.root_cause)
        self.status = max(400, min(599, int(self.status)))

    def to_dict(self, *, include_details: bool = False) -> dict[str, Any]:
        result: dict[str, Any] = {
            "error": {
                "code": self.code,
                "message": self.public_message,
                "category": self.category,
                "error_id": self.error_id,
                "retryable": self.retryable,
                "suggestion": self.suggestion,
                "root_cause": self.root_cause,
                "status": self.status,
            }
        }
        if include_details and self.details:
            result["error"]["details"] = _safe_value(self.details)
        return result

    def diagnostic_summary(self) -> str:
        lines = [
            f"[ERROR: {self.code}] (ID: {self.error_id})",
            f"  Category  : {self.category}",
            f"  Message   : {self.public_message}",
        ]
        if self.root_cause:
            lines.append(f"  Root Cause: {self.root_cause}")
        if self.suggestion:
            lines.append(f"  Suggestion: {self.suggestion}")
        lines.append(f"  Retryable : {'Yes' if self.retryable else 'No'} (HTTP {self.status})")
        return "\n".join(lines)


# Specific typed errors for granular catching
class SecurityViolationError(AgentError):
    def __init__(self, message: str, suggestion: str = "", details: dict | None = None):
        super().__init__(
            code="SECURITY_VIOLATION",
            message=message,
            category=ErrorCategory.SECURITY,
            suggestion=suggestion or "Review command or path safety permissions.",
            retryable=False,
            status=403,
            details=details or {}
        )


class RateLimitExceededError(AgentError):
    def __init__(self, message: str, retry_after: float = 5.0, details: dict | None = None):
        super().__init__(
            code="API_RATE_LIMIT",
            message=message,
            category=ErrorCategory.RATE_LIMIT,
            suggestion=f"Wait {retry_after:.1f}s before retrying, or switch to fallback model.",
            retryable=True,
            status=429,
            details={**(details or {}), "retry_after": retry_after}
        )


class SyntaxCompilationError(AgentError):
    def __init__(self, message: str, filename: str = "", lineno: int = 0, snippet: str = "", details: dict | None = None):
        super().__init__(
            code="SYNTAX_ERROR",
            message=message,
            category=ErrorCategory.SYNTAX,
            suggestion=f"Inspect and fix the syntax around line {lineno} in '{filename or 'code'}'.",
            root_cause=snippet,
            retryable=False,
            status=400,
            details={**(details or {}), "filename": filename, "lineno": lineno}
        )


class ExecutionTimeoutError(AgentError):
    def __init__(self, message: str, timeout_seconds: float = 0.0, details: dict | None = None):
        super().__init__(
            code="TIMEOUT",
            message=message,
            category=ErrorCategory.TIMEOUT,
            suggestion=f"Increase command timeout or optimize execution (exceeded {timeout_seconds}s).",
            retryable=True,
            status=504,
            details={**(details or {}), "timeout_seconds": timeout_seconds}
        )


class TracebackInspector:
    """Standard library stack trace extraction and security sanitizer."""

    @staticmethod
    def sanitize_frame_summary(tb: traceback.TracebackException) -> list[dict[str, Any]]:
        frames = []
        for frame in tb.stack:
            frames.append({
                "filename": os.path.basename(frame.filename),
                "lineno": frame.lineno,
                "name": frame.name,
                "line": redact_secrets(frame.line or "").strip()[:200]
            })
        return frames

    @staticmethod
    def compact_summary(exc: BaseException) -> str:
        tb = traceback.TracebackException.from_exception(exc)
        sanitized = TracebackInspector.sanitize_frame_summary(tb)
        relevant = [f for f in sanitized if not f["filename"].startswith("<") and "python" not in f["filename"]]
        target = relevant[-1] if relevant else (sanitized[-1] if sanitized else None)
        if target:
            return f"at {target['filename']}:{target['lineno']} in {target['name']}() -> {target['line']}"
        return f"{type(exc).__name__}: {redact_secrets(str(exc))[:200]}"


class ASTErrorAnalyzer:
    """Uses Python standard library AST to analyze syntax and structural defects."""

    @staticmethod
    def analyze_source(code: str, filename: str = "<string>") -> Optional[dict[str, Any]]:
        try:
            ast.parse(code, filename=filename)
            return None  # Syntax is clean
        except SyntaxError as exc:
            lineno = exc.lineno or 1
            offset = exc.offset or 1
            text = (exc.text or "").rstrip()
            caret = " " * max(0, offset - 1) + "^" if offset > 0 else ""
            visual = f"{text}\n{caret}" if text and caret else text
            return {
                "error_type": type(exc).__name__,
                "filename": os.path.basename(filename),
                "lineno": lineno,
                "offset": offset,
                "msg": exc.msg,
                "visual_snippet": visual,
                "suggestion": f"Inspect line {lineno} in '{os.path.basename(filename)}': check for unclosed quotes, brackets, or missing colons."
            }


class RetryPolicy:
    """Standard library exponential backoff with full jitter."""

    @staticmethod
    def compute_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0, factor: float = 2.0) -> float:
        attempt = max(0, int(attempt))
        computed = base_delay * (factor ** attempt)
        capped = min(max_delay, computed)
        jittered = capped * (0.5 + 0.5 * random.random())
        return round(jittered, 3)

    @staticmethod
    def is_retryable(exc: BaseException) -> bool:
        if isinstance(exc, AgentError):
            return exc.retryable
        err = normalize_exception(exc)
        return err.retryable


class AutoRecoveryHandler:
    """Autonomous self-healing engine to detect root causes and execute recovery strategies."""

    _consecutive_errors: int = 0
    _last_error_time: float = 0.0

    @classmethod
    def record_error(cls, exc: BaseException) -> dict[str, Any]:
        now = time.time()
        if now - cls._last_error_time > 60.0:
            cls._consecutive_errors = 0
        cls._consecutive_errors += 1
        cls._last_error_time = now

        err = normalize_exception(exc)
        actionable_plan = {
            "should_halt": cls._consecutive_errors >= 5,
            "consecutive_count": cls._consecutive_errors,
            "category": err.category,
            "remedy": err.suggestion,
        }

        # Autonomous directory self-healing
        if isinstance(exc, FileNotFoundError):
            missing_path = getattr(exc, "filename", "") or ""
            if missing_path and os.sep in missing_path:
                parent_dir = os.path.dirname(missing_path)
                if parent_dir and not os.path.exists(parent_dir):
                    actionable_plan["auto_action"] = f"mkdir -p {parent_dir}"

        return actionable_plan

    @classmethod
    def reset(cls) -> None:
        cls._consecutive_errors = 0
        cls._last_error_time = 0.0


def install_global_error_handler(log_func: Optional[Callable[[str], None]] = None) -> None:
    """Install clean unhandled exception hook across the application."""
    def excepthook(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        err = normalize_exception(exc_value, operation="application execution")
        clean_tb = redact_secrets("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        summary = err.diagnostic_summary()

        out = f"\n[UNHANDLED EXCEPTION INTERCEPTED]\n{summary}\n\nSanitized Traceback:\n{clean_tb}"
        if log_func:
            log_func(out)
        else:
            print(out, file=sys.stderr)

    sys.excepthook = excepthook


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = redact_secrets(text)
    return text.replace("\x00", "\\0")[:4000]


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
    """
    Intelligently inspect and normalize any Python exception into an actionable AgentError
    with root cause diagnosis and remedy suggestions.
    """
    if isinstance(exc, AgentError):
        return exc

    name = type(exc).__name__
    raw_message = str(exc).strip() or name
    message = _clean(raw_message)
    lower = message.lower()
    compact_frame = TracebackInspector.compact_summary(exc)

    # 1. Syntax, Indentation, and Compilation Errors
    if isinstance(exc, (SyntaxError, IndentationError, TabError)):
        fn = getattr(exc, "filename", "") or "script.py"
        lineno = getattr(exc, "lineno", 0) or 0
        offset = getattr(exc, "offset", 0) or 0
        text = (getattr(exc, "text", "") or "").rstrip()
        caret = " " * (max(0, offset - 1)) + "^" if offset > 0 else ""
        snippet = f"{text}\n{caret}" if text and caret else text
        return AgentError(
            code="SYNTAX_ERROR",
            message=f"{operation} syntax error at line {lineno} of {os.path.basename(fn)}: {exc.msg}",
            public_message=f"Syntax error on line {lineno}: {exc.msg}",
            category=ErrorCategory.SYNTAX,
            suggestion=f"Inspect and fix the syntax around line {lineno} in '{os.path.basename(fn)}'.",
            root_cause=snippet or f"{name}: {exc.msg}",
            retryable=False,
            status=400,
            details={"filename": fn, "lineno": lineno, "offset": offset, "code_snippet": snippet}
        )

    # 2. Timeouts (Process, Network, Threading)
    if isinstance(exc, TimeoutError) or "timed out" in lower or "timeout" in lower:
        timeout_val = getattr(exc, "timeout", None)
        return AgentError(
            code="TIMEOUT",
            message=f"{operation} timed out: {message}",
            public_message=f"The {operation} timed out while waiting for completion.",
            category=ErrorCategory.TIMEOUT,
            suggestion="Increase the timeout limit or break the task into smaller sub-steps.",
            root_cause=f"Operation exceeded time limit (timeout={timeout_val}s)" if timeout_val else "Timeout deadline exceeded",
            retryable=True,
            status=504,
            details={"exception": name, "timeout": timeout_val, "trace": compact_frame}
        )

    # 3. HTTP and API Errors (urllib.error.HTTPError)
    if hasattr(exc, "code") and isinstance(getattr(exc, "code"), int):
        http_code = getattr(exc, "code")
        if http_code == 429:
            return AgentError(
                code="API_RATE_LIMIT",
                message=f"{operation} rate limit reached (HTTP 429): {message}",
                public_message="AI API rate limit reached (too many requests). Please wait a moment before trying again.",
                category=ErrorCategory.RATE_LIMIT,
                suggestion="Back off request frequency or configure fallback model.",
                root_cause="HTTP 429 Too Many Requests from API endpoint",
                retryable=True,
                status=429,
                details={"http_code": 429, "exception": name}
            )
        if http_code in (401, 403):
            return AgentError(
                code="AUTHENTICATION_FAILED",
                message=f"{operation} access denied (HTTP {http_code}): {message}",
                public_message="API authentication failed or permission was denied.",
                category=ErrorCategory.SECURITY,
                suggestion="Verify that your API key or token is valid and active in config.",
                root_cause=f"HTTP {http_code} Unauthorized / Forbidden",
                retryable=False,
                status=http_code,
                details={"http_code": http_code, "exception": name}
            )
        if http_code == 404:
            return AgentError(
                code="ENDPOINT_NOT_FOUND",
                message=f"{operation} resource or model not found (HTTP 404): {message}",
                public_message="The requested remote resource or model was not found.",
                category=ErrorCategory.SYSTEM,
                suggestion="Check the model name or API endpoint URL in settings.",
                root_cause="HTTP 404 Not Found",
                retryable=False,
                status=404,
                details={"http_code": 404, "exception": name}
            )
        if http_code in (500, 502, 503, 504):
            return AgentError(
                code="REMOTE_SERVICE_ERROR",
                message=f"{operation} remote service error (HTTP {http_code}): {message}",
                public_message=f"The remote service is temporarily unavailable (HTTP {http_code}).",
                category=ErrorCategory.NETWORK,
                suggestion="The upstream server encountered an error. A retry will be attempted.",
                root_cause=f"HTTP {http_code} Upstream Server Error",
                retryable=True,
                status=http_code,
                details={"http_code": http_code, "exception": name}
            )

    # 4. Network and Socket Failures
    if isinstance(exc, (ConnectionError, OSError)) and any(x in lower for x in ("connection", "network", "dns", "name or service", "refused", "unreachable", "reset by peer", "broken pipe")):
        return AgentError(
            code="NETWORK_ERROR",
            message=f"{operation} network failure: {message}",
            public_message="A network communication error interrupted the operation.",
            category=ErrorCategory.NETWORK,
            suggestion="Verify internet connection and check if the remote host is reachable.",
            root_cause=f"Network transport failure ({name}): {message}",
            retryable=True,
            status=503,
            details={"exception": name, "trace": compact_frame}
        )

    # 5. File System & Path Errors
    if isinstance(exc, FileNotFoundError):
        missing_fn = getattr(exc, "filename", "") or ""
        return AgentError(
            code="NOT_FOUND",
            message=f"{operation} resource not found: {missing_fn or message}",
            public_message=f"The file or path '{os.path.basename(missing_fn) if missing_fn else 'target'}' was not found.",
            category=ErrorCategory.SYSTEM,
            suggestion="Check the path spelling, use 'list_directory' to inspect files, or create the file first.",
            root_cause=f"FileNotFoundError on '{missing_fn}'" if missing_fn else "Target file or directory does not exist",
            retryable=False,
            status=404,
            details={"filename": missing_fn, "exception": name}
        )

    if isinstance(exc, (IsADirectoryError, NotADirectoryError)):
        return AgentError(
            code="INVALID_PATH_TYPE",
            message=f"{operation} path type mismatch: {message}",
            public_message=f"Path type conflict: {message}",
            category=ErrorCategory.SYSTEM,
            suggestion="Ensure you are specifying a file path where a file is expected, or directory where directory is expected.",
            root_cause=f"{name}: {message}",
            retryable=False,
            status=400,
            details={"exception": name}
        )

    # 6. Permissions and Security
    if isinstance(exc, PermissionError):
        return AgentError(
            code="PERMISSION_DENIED",
            message=f"{operation} permission denied: {message}",
            public_message="Permission was denied for this operation.",
            category=ErrorCategory.SECURITY,
            suggestion="Check file permissions with 'ls -l' or verify process execution rights.",
            root_cause=f"PermissionError: {message}",
            retryable=False,
            status=403,
            details={"exception": name, "trace": compact_frame}
        )

    # 7. SQLite Database Errors
    if "sqlite" in name.lower() or "sqlite3" in type(exc).__module__:
        if "no such table" in lower:
            table_match = re.search(r"no such table:\s*([^\s]+)", lower)
            table_name = table_match.group(1) if table_match else "unknown"
            return AgentError(
                code="DATABASE_SCHEMA_ERROR",
                message=f"{operation} database error: {message}",
                public_message=f"Database table '{table_name}' does not exist.",
                category=ErrorCategory.SYSTEM,
                suggestion=f"Run the database schema initialization script to create table '{table_name}'.",
                root_cause=f"Missing database table: {table_name}",
                retryable=False,
                status=500,
                details={"exception": name, "table": table_name}
            )
        if "unique constraint" in lower:
            return AgentError(
                code="DATABASE_CONSTRAINT_ERROR",
                message=f"{operation} database constraint violation: {message}",
                public_message="Database unique constraint violation.",
                category=ErrorCategory.SYSTEM,
                suggestion="Use INSERT OR REPLACE / ON CONFLICT, or generate a distinct primary key.",
                root_cause="UNIQUE constraint failed",
                retryable=False,
                status=409,
                details={"exception": name}
            )
        if "database is locked" in lower:
            return AgentError(
                code="DATABASE_LOCKED",
                message=f"{operation} database is locked: {message}",
                public_message="SQLite database is currently locked by another transaction.",
                category=ErrorCategory.SYSTEM,
                suggestion="Ensure transactions are promptly committed or closed; increase sqlite3 timeout.",
                root_cause="Database concurrency lock contention",
                retryable=True,
                status=503,
                details={"exception": name}
            )

    # 8. Memory & Recursion Exhaustion
    if isinstance(exc, (MemoryError, RecursionError)):
        return AgentError(
            code="RESOURCE_EXHAUSTED",
            message=f"{operation} resource exhausted: {message}",
            public_message=f"System resource limit reached ({name}).",
            category=ErrorCategory.RESOURCE,
            suggestion="Check for unbounded loops, recursive function calls, or excessive in-memory allocations.",
            root_cause=f"Stack/Memory exhaustion: {name}",
            retryable=False,
            status=500,
            details={"exception": name}
        )

    # 9. JSON and Parsing Validation
    if isinstance(exc, (json.JSONDecodeError, ValueError, TypeError)):
        return AgentError(
            code="INVALID_RESPONSE",
            message=f"{operation} invalid data format: {message}",
            public_message="The operation produced or received invalid/malformed data.",
            category=ErrorCategory.VALIDATION,
            suggestion="Validate JSON payload formatting, data types, and required fields.",
            root_cause=f"Data parsing error ({name}): {message}",
            retryable=False,
            status=400,
            details={"exception": name, "trace": compact_frame}
        )

    # 10. Default General Internal Error
    return AgentError(
        code="INTERNAL_ERROR",
        message=f"{operation} failed: {message}",
        public_message=f"An unexpected error occurred during {operation}.",
        category=ErrorCategory.INTERNAL,
        suggestion="Inspect the application logs or traceback details for diagnosis.",
        root_cause=f"{name}: {message}",
        retryable=False,
        status=500,
        details={"exception": name, "trace": compact_frame}
    )


def error_payload(exc: BaseException, *, operation: str = "operation", include_details: bool = False) -> dict[str, Any]:
    return normalize_exception(exc, operation=operation).to_dict(include_details=include_details)


def error_text(exc: BaseException, *, operation: str = "operation") -> str:
    err = normalize_exception(exc, operation=operation)
    return f"{err.public_message} (error_id={err.error_id})"


def traceback_text(exc: BaseException) -> str:
    return _clean("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))[:8000]


def _json_default(value: Any) -> str:
    return _clean(value)


def safe_json(value: Any) -> str:
    return json.dumps(_safe_value(value), ensure_ascii=False, default=_json_default)
