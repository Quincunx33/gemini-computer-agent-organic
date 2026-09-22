from dataclasses import dataclass
import os
from pathlib import Path


def _load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    path = path or Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int, *, minimum: int = 1, maximum: int = 10_000_000) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    gemini_fallback_models: tuple[str, ...] = tuple(m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-flash-lite-latest").split(",") if m.strip())
    workspace: Path = Path(os.getenv("AGENT_WORKSPACE", str(Path.cwd()))).expanduser().resolve()
    max_agent_steps: int = _int_env("MAX_AGENT_STEPS", 50, maximum=1000)
    command_timeout: int = _int_env("COMMAND_TIMEOUT", 120, maximum=3600)
    max_retries: int = _int_env("MAX_RETRIES", 3, maximum=10)
    api_retries: int = _int_env("API_RETRIES", 3, maximum=10)
    max_file_size: int = _int_env("MAX_FILE_SIZE", 2 * 1024 * 1024, maximum=100 * 1024 * 1024)
    max_output_chars: int = _int_env("MAX_OUTPUT_CHARS", 20000, maximum=1_000_000)
    max_api_response_bytes: int = _int_env("MAX_API_RESPONSE_BYTES", 4 * 1024 * 1024, maximum=50 * 1024 * 1024)
    max_prompt_chars: int = _int_env("MAX_PROMPT_CHARS", 16000, maximum=200_000)
    max_history_chars: int = _int_env("MAX_HISTORY_CHARS", 12000, maximum=200_000)
    max_memory_chars: int = _int_env("MAX_MEMORY_CHARS", 3000, maximum=50_000)
    max_tool_result_chars: int = _int_env("MAX_TOOL_RESULT_CHARS", 5000, maximum=100_000)
    response_cache_enabled: bool = _bool_env("RESPONSE_CACHE_ENABLED", True)
    response_cache_ttl: int = _int_env("RESPONSE_CACHE_TTL", 300, maximum=86_400)
    response_cache_size: int = _int_env("RESPONSE_CACHE_SIZE", 128, maximum=10_000)
    task_tool_filtering: bool = _bool_env("TASK_TOOL_FILTERING", True)
    fast_model: str = os.getenv("GEMINI_FAST_MODEL", "gemini-flash-lite-latest")
    log_rotate_hours: float = _float_env("LOG_ROTATE_HOURS", 24.0, minimum=1.0, maximum=24 * 30)
    log_retention: int = _int_env("LOG_RETENTION", 7, maximum=365)
    mobile_rate_limit: int = _int_env("MOBILE_RATE_LIMIT", 30, maximum=100_000)
    mobile_rate_window: int = _int_env("MOBILE_RATE_WINDOW", 60, maximum=86_400)
    mobile_max_body: int = _int_env("MOBILE_MAX_BODY", 64 * 1024, maximum=10 * 1024 * 1024)
    require_confirmation: bool = _bool_env("REQUIRE_CONFIRMATION", True)
    db_path: Path = Path(os.getenv("AGENT_DB", str(Path.home() / ".gemini_computer_agent.sqlite3"))).expanduser()
    audit_log_path: Path = Path(os.getenv("AGENT_AUDIT_LOG", str(Path.home() / ".gemini_computer_agent_audit.jsonl"))).expanduser()


settings = Settings()

__all__ = ["Settings", "settings"]
