from __future__ import annotations

from pathlib import Path
from config import settings


def _paths(name: str, config=settings) -> list[Path]:
    raw = getattr(config, name, "")
    return [Path(item).expanduser().resolve() for item in raw.split(":") if item.strip()]


def check_path(path: Path, config=settings) -> None:
    denied = _paths("denied_paths", config)
    if any(path == item or item in path.parents for item in denied):
        raise PermissionError(f"Path is protected by AGENT_DENIED_PATHS: {path}")
    allowed = _paths("allowed_paths", config)
    if getattr(config, "host_mode", False) and allowed and not any(path == item or item in path.parents for item in allowed):
        raise PermissionError(f"Path is outside AGENT_ALLOWED_PATHS: {path}")


def is_sensitive(path: Path) -> bool:
    names = {".env", ".ssh", ".gnupg", ".aws", "credentials", "secrets", "id_rsa", "id_ed25519"}
    return any(part in names or part.endswith(".pem") for part in (path.name, *path.parts))
