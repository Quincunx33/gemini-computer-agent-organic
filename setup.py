#!/usr/bin/env python3
"""Interactive first-run setup; stores secrets only in the local .env file."""
from getpass import getpass
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
MODELS = {
    "1": "gemini-3.6-flash",
    "2": "gemini-flash-lite-latest",
    "3": "gemini-3.6-flash",
}

def main() -> None:
    print("Gemini Computer Agent setup")
    print("API key is written to .env (never to Python source or SQLite memory).")
    key = getpass("Gemini API key (hidden input): ").strip()
    if not key:
        raise SystemExit("No API key entered.")
    print("\nChoose the primary model:")
    print("1) gemini-3.6-flash       (current API-supported model)")
    print("2) gemini-flash-lite-latest (fast fallback)")
    print("3) gemini-3.6-flash       (same current model)")
    choice = input("Selection [1]: ").strip() or "1"
    primary = MODELS.get(choice, MODELS["1"])
    fallback = [m for m in MODELS.values() if m != primary]
    existing = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    values = {
        "GEMINI_API_KEY": key,
        "GEMINI_MODEL": primary,
        "GEMINI_FALLBACK_MODELS": ",".join(fallback),
    }
    lines = []
    seen = set()
    for line in existing.splitlines():
        name = line.split("=", 1)[0].strip() if "=" in line else ""
        if name in values:
            lines.append(f"{name}={values[name]}")
            seen.add(name)
        elif line.strip() != "":
            lines.append(line)
    for name, value in values.items():
        if name not in seen:
            lines.append(f"{name}={value}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        ENV.chmod(0o600)
    except OSError:
        pass
    print(f"Saved .env with primary model: {primary}")
    print(f"Fallback order: {', '.join(fallback)}")

if __name__ == "__main__":
    main()
