#!/usr/bin/env python3
"""Complete first-run setup for genagent; secrets stay only in local .env."""
from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path

from env_manager import ENV, bootstrap_env, doctor_env

ROOT = Path(__file__).resolve().parent
MODELS = {
    "1": "gemini-3.6-flash",
    "2": "gemini-flash-lite-latest",
}
PROVIDER_MODELS = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL", "gemini-3.6-flash"),
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL", "gpt-6-astra"),
    "xai": ("XAI_API_KEY", "XAI_MODEL", "grok-4.7"),
    "deepseek": ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL", "deepseek-flash"),
}
PROVIDER_FALLBACKS = {
    "gemini": ("GEMINI_FALLBACK_MODELS", "gemini-flash-lite-latest"),
    "openai": ("OPENAI_FALLBACK_MODELS", "gpt-5.6-terra"),
    "xai": ("XAI_FALLBACK_MODELS", "grok-4.6"),
    "deepseek": ("DEEPSEEK_FALLBACK_MODELS", "deepseek-v4-pro"),
}


def ask(prompt: str, default: str = "") -> str:
    value = input(f"{prompt}" + (f" [{default}]" if default else "") + ": ").strip()
    return value or default


def ask_bool(prompt: str, default: bool) -> str:
    suffix = "Y/n" if default else "y/N"
    value = input(f"{prompt} [{suffix}]: ").strip().lower()
    if not value:
        return "true" if default else "false"
    return "true" if value in {"y", "yes", "1", "true", "on"} else "false"


def update_env(values: dict[str, str]) -> None:
    existing = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    lines: list[str] = []
    seen: set[str] = set()
    for line in existing.splitlines():
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in values:
            lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            lines.append(line)
    for key, value in values.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    ENV.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        ENV.chmod(0o600)
    except OSError:
        pass


def run_interactive() -> None:
    print("Genagent complete setup")
    print("Safe defaults will be written to .env. API key input is hidden and never printed.")
    bootstrap_env()
    current = doctor_env()
    keys: dict[str, str] = {}
    for provider, (key_name, _model_name, _default_model) in PROVIDER_MODELS.items():
        value = getpass(f"{provider} API key (press Enter to skip): ").strip()
        if value:
            keys[key_name] = value
    provider = ask("Primary provider: gemini, openai, xai, deepseek", "gemini").lower()
    if provider not in PROVIDER_MODELS:
        provider = "gemini"
    fallback = ask("Fallback providers, comma-separated", "openai,xai,deepseek")
    model = ask(f"{provider} model", PROVIDER_MODELS[provider][2])
    fallback_model = ask(f"{provider} fallback model", PROVIDER_FALLBACKS[provider][1])
    autonomy = ask("Autonomy mode: safe, supervised, trusted", "supervised").lower()
    if autonomy not in {"safe", "supervised", "trusted"}:
        autonomy = "supervised"
    workspace = ask("Workspace directory", str(ROOT))
    values = {
        "LLM_PROVIDER": provider,
        "LLM_FALLBACK_PROVIDERS": fallback,
        "AGENT_WORKSPACE": workspace,
        "AUTONOMY_MODE": autonomy,
        "REQUIRE_CONFIRMATION": ask_bool("Require confirmation for protected actions", True),
        "AUTO_INSTALL": ask_bool("Allow known-package automatic install chain", False),
        "WEB_SEARCH_ENABLED": ask_bool("Enable public web-search fallback", True),
        "PLUGIN_ENABLED": ask_bool("Enable validated plugin zip installation", True),
        "MAX_PARALLEL_AGENTS": ask("Maximum read-only parallel agents", "3"),
        "AGENT_HOST_MODE": ask_bool("Allow host-wide paths outside workspace", False),
        "SKILLS_ENABLED": ask_bool("Enable runtime skill packs", True),
    }
    values[PROVIDER_MODELS[provider][1]] = model
    values[PROVIDER_FALLBACKS[provider][0]] = fallback_model
    values.update(keys)
    update_env(values)
    result = doctor_env()
    print("\nSaved .env with mode:", autonomy)
    print("API key:", "configured" if result["api_key_present"] else "missing (add it later with: python setup.py)")
    print("Workspace:", workspace)
    print("Automatic install:", values["AUTO_INSTALL"])
    print("Setup complete. Restart the agent for configuration changes to take effect.")


def run_non_interactive() -> None:
    bootstrap_env()
    update_env({
        "AUTONOMY_MODE": "supervised",
        "REQUIRE_CONFIRMATION": "true",
        "AUTO_INSTALL": "false",
        "WEB_SEARCH_ENABLED": "true",
        "PLUGIN_ENABLED": "true",
        "MAX_PARALLEL_AGENTS": "3",
    })
    print(doctor_env())


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure all genagent settings")
    parser.add_argument("--non-interactive", action="store_true", help="write safe defaults without prompting for secrets")
    parser.add_argument("--doctor", action="store_true", help="show configuration status without secrets")
    args = parser.parse_args()
    if args.doctor:
        print(doctor_env())
    elif args.non_interactive:
        run_non_interactive()
    else:
        run_interactive()


if __name__ == "__main__":
    main()
