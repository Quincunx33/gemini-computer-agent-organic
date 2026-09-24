#!/usr/bin/env bash
# Start the dependency-free GenAgent control panel.
set -e
cd "$(dirname "$0")"
PYTHON_CMD="${PYTHON_CMD:-python3}"
command -v "$PYTHON_CMD" >/dev/null 2>&1 || { echo "Python 3 is required." >&2; exit 1; }
exec "$PYTHON_CMD" web_server.py --host "${HOST:-0.0.0.0}" --port "${1:-8080}"
