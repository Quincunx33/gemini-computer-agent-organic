from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def _parse(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def bootstrap_env(api_key: str | None = None) -> dict[str, Any]:
    """Create .env with safe defaults; never invent or print a secret."""
    template = EXAMPLE.read_text(encoding="utf-8") if EXAMPLE.exists() else ""
    current = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    values = _parse(current.splitlines())
    if api_key is not None:
        values["GEMINI_API_KEY"] = api_key.strip()
    rendered: list[str] = []
    seen: set[str] = set()
    for line in template.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key:
            value = values.get(key, line.split("=", 1)[1])
            rendered.append(f"{key}={value}")
            seen.add(key)
        else:
            rendered.append(line)
    for key, value in values.items():
        if key not in seen and key != "GEMINI_API_KEY":
            rendered.append(f"{key}={value}")
    if "GEMINI_API_KEY" not in seen:
        rendered.insert(1, f"GEMINI_API_KEY={values.get('GEMINI_API_KEY', '')}")
    ENV.write_text("\n".join(rendered).rstrip() + "\n", encoding="utf-8")
    try:
        ENV.chmod(0o600)
    except OSError:
        pass
    return doctor_env()


def doctor_env() -> dict[str, Any]:
    values = _parse(ENV.read_text(encoding="utf-8").splitlines()) if ENV.exists() else {}
    providers = {"gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY", "xai": "XAI_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}
    configured = [name for name, key in providers.items() if values.get(key)]
    missing = [] if configured else ["one LLM API key (GEMINI_API_KEY/OPENAI_API_KEY/XAI_API_KEY/DEEPSEEK_API_KEY)"]
    return {"env_file": str(ENV), "exists": ENV.exists(), "missing_required": missing, "ready": not missing, "primary_provider": values.get("LLM_PROVIDER", "gemini"), "configured_providers": configured, "configured_keys": sorted(key for key in values if not key.endswith("_API_KEY")), "api_key_present": bool(configured)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap or diagnose genagent .env")
    parser.add_argument("--bootstrap", action="store_true", help="create/update .env with safe defaults")
    parser.add_argument("--doctor", action="store_true", help="report missing configuration without secrets")
    args = parser.parse_args()
    if args.bootstrap:
        print(bootstrap_env())
    else:
        print(doctor_env())


if __name__ == "__main__":
    main()
