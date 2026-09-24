#!/usr/bin/env bash
# GenAgent One-Click Multi-Device Web Server Runner
# Works on Linux, macOS, Android (Termux), iOS (iSH, a-Shell)

cd "$(dirname "$0")" || exit 1

echo "========================================================"
echo "    Starting GenAgent Multi-Device Web Server...       "
echo "========================================================"

if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
else
    echo "Error: Python 3 was not found on this device."
    exit 1
fi

PORT="${1:-8080}"
exec $PYTHON_CMD web_server.py --port "$PORT"
