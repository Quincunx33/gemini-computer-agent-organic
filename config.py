from dataclasses import dataclass
import os
from pathlib import Path


def _load_dotenv(path: Path | None = None) -> None:
    """Load simple KEY=VALUE entries without requiring python-dotenv."""
    path = path or Path(__file__).resolve().parent / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    gemini_fallback_models: tuple[str, ...] = tuple(
        m.strip() for m in os.getenv(
            "GEMINI_FALLBACK_MODELS",
            "gemini-3.6-flash,gemini-flash-lite-latest",
        ).split(",") if m.strip()
    )
    workspace: Path = Path(os.getenv("AGENT_WORKSPACE", str(Path.cwd()))).expanduser().resolve()
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "50"))
    command_timeout: int = int(os.getenv("COMMAND_TIMEOUT", "120"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    api_retries: int = int(os.getenv("API_RETRIES", "3"))
    max_file_size: int = int(os.getenv("MAX_FILE_SIZE", str(2 * 1024 * 1024)))
    max_output_chars: int = int(os.getenv("MAX_OUTPUT_CHARS", "20000"))
    mobile_rate_limit: int = int(os.getenv("MOBILE_RATE_LIMIT", "30"))
    mobile_rate_window: int = int(os.getenv("MOBILE_RATE_WINDOW", "60"))
    mobile_max_body: int = int(os.getenv("MOBILE_MAX_BODY", str(64 * 1024)))
    require_confirmation: bool = os.getenv("REQUIRE_CONFIRMATION", "true").lower() in {"1", "true", "yes", "on"}
    db_path: Path = Path(os.getenv("AGENT_DB", str(Path.home() / ".gemini_computer_agent.sqlite3"))).expanduser()
    audit_log_path: Path = Path(os.getenv("AGENT_AUDIT_LOG", str(Path.home() / ".gemini_computer_agent_audit.jsonl"))).expanduser()


settings = Settings()

__all__ = ["Settings", "settings"]
