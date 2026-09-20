# Gemini Computer Agent

A modular, local-first Python terminal agent that uses the Google Gemini REST API to plan and execute controlled computer actions. It follows **Observe → Plan → Act → Observe → Verify** and never hides commands or silently escalates privileges.

## Features

The current implementation includes Gemini REST integration, bounded agent loop, terminal execution with timeout and structured results, workspace-confined filesystem operations, risk classification and confirmation for privileged/destructive commands, SQLite memory, a standard-library terminal UI, optional Playwright browser helpers, optional PyAutoGUI GUI helpers, process and Git helpers, audit-friendly logs, and unit tests. The core application has **no third-party runtime dependency**.

Security hardening includes workspace-safe command cwd resolution, confirmation-required download-to-shell and credential-file reads, secret redaction, configurable file/output limits, bounded Gemini API retries, and a `verify_python` tool. Reusable agent instructions are included in `skills/` as `SKILL.md` files for safety, verification, and tool extension workflows.

Cross-platform control now includes `platform_info`, `open_app`, `list_processes`, and confirmation-protected `terminate_process`. Linux, macOS, Windows, and Termux are detected at runtime. GUI capability is reported rather than assumed: desktop input requires the host OS accessibility/display permissions, while iOS remains a limited shell/Shortcuts target and cannot expose arbitrary system GUI control.

## Organic agent behavior

The core loop is designed to behave like a grounded collaborator rather than a fixed command script. Each task is handled through an adaptive **observe → plan → act → verify** cycle. The agent receives relevant local memories as optional hints, chooses the smallest useful next action, preserves structured observations between steps, detects repeated tool calls, and asks the model to recover instead of looping blindly. Completed tasks are stored as redacted summaries so later requests can preserve continuity without storing common credentials or tokens.

“Organic” does not mean unrestricted autonomy: the workspace boundary, bounded step count, command timeouts, explicit confirmation for privileged/destructive actions, and audit-friendly redaction remain active. The agent does not expose hidden chain-of-thought; it reports concise reasons, concrete actions, verification results, and blockers.

## Installation

```bash
git clone <repo>
cd gemini-computer-agent
python3 -m venv .venv
source .venv/bin/activate
# requirements.txt is intentionally empty of third-party packages
python -m unittest discover -s tests -p 'test_*.py'
python setup.py
python agent.py
```

Browser and GUI helpers remain optional adapters. They require Playwright or PyAutoGUI only if those specific helpers are used; the core agent does not import them at startup.

## Desktop GUI and OCR

Run `python mobile_server.py --host 127.0.0.1 --port 8765` to start a token-protected local command bridge. `tools/gui_control.py` provides `screenshot`, `ocr`, `mouse_click`, `type_text`, and `press_key`. Install `pyautogui` only on a trusted desktop when mouse/keyboard control is needed; install the native `tesseract` executable when OCR is needed. The agent reports both capabilities instead of pretending they are available.

## Mobile command client

The bridge prints a one-time bearer token. Keep it private. From another trusted device or Termux shell, use:

```bash
python mobile_client.py http://HOST:8765 --token TOKEN --capabilities
python mobile_client.py http://HOST:8765 --token TOKEN "Open the browser and inspect the project tests"
```

Keep the server bound to `127.0.0.1` unless a trusted LAN is required. If exposing it on a LAN, use `--host 0.0.0.0`, a long random token, firewall rules, and a private network. This is not an internet-facing service and does not bypass iOS sandbox restrictions.

## Production-hardening controls

The mobile bridge now enforces a per-client rate limit, a maximum request body, bearer-token authentication, JSONL audit logging with secret redaction, and HTTPS for every non-loopback bind. Create or obtain a certificate and private key, then run `python mobile_server.py --host 0.0.0.0 --certfile server.crt --keyfile server.key --token LONG_RANDOM_TOKEN`. The server refuses non-loopback HTTP. Review `AGENT_AUDIT_LOG`, `MOBILE_RATE_LIMIT`, `MOBILE_RATE_WINDOW`, and `MOBILE_MAX_BODY` before deployment.

## Configuration

Run `python setup.py` once. It requests the API key with hidden terminal input and writes it to the local `.env` file with restrictive permissions; the key is never embedded in Python source, committed to Git, or stored in SQLite memory. The setup wizard configures this model order:

1. `gemini-3.6-flash` — current API-supported primary model, live-tested in this project.
2. `gemini-flash-lite-latest` — fast fallback for lightweight planning and recovery.
3. `gemini-3.6-flash` — compatibility fallback for the current model endpoint.

The client automatically tries the next configured model if a model request fails. You can override `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS` in `.env`. `AGENT_WORKSPACE`, `MAX_AGENT_STEPS`, `MAX_RETRIES`, `COMMAND_TIMEOUT`, `REQUIRE_CONFIRMATION`, and `AGENT_DB` are also configurable. The workspace restriction prevents accidental writes outside the project unless a caller explicitly opts out at the tool layer.

The client also normalizes JSON-encoded tool calls when a model returns a function call as plain text instead of a native function-call part, allowing the bounded agent loop to continue. Temporary Gemini `503 Service Unavailable` responses are retried and then reported cleanly without hiding the failure.

The `self_update` tool lets the agent modify workspace source code after the user requests a fix. It writes atomically, keeps a timestamped copy under `.agent_backups/`, compiles Python files, and automatically restores the previous version when syntax validation fails. The agent should then run the test suite and report the change; self-update does not bypass the workspace boundary.

## Commands

`/help`, `/status`, `/tools`, `/model`, `/workspace`, `/permissions`, `/memory`, `/clear-memory`, `/tasks`, `/resume TASK_ID`, and `/exit` are available. Tasks are journaled in SQLite with their status, step, and conversation history. Normal input is treated as an agent task, for example: “Inspect this project, open the browser, list processes, and explain the first test failure.”

## Safety model

Normal and low-risk commands may run automatically. Privileged and destructive commands display the exact command and require the user to type `yes`. The agent has bounded steps and command timeouts, rejects unsafe filesystem paths, does not bypass OS authentication, does not store credentials, and does not implement CAPTCHA bypass, credential theft, stealth scraping, or unauthorized access. Review the command before approving it.

## Architecture

`agent.py` provides the UI; `agent_loop.py` coordinates bounded reasoning and tool calls; `gemini_client.py` isolates the Gemini REST API; `planner.py` defines structured tool schemas; `permissions.py` classifies risk; `tools/` contains execution adapters; `memory.py` persists non-secret task summaries; `state.py` tracks task history; and `tests/` contains isolated unit tests.

## Development and tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

Gemini calls should be mocked in tests. Do not run destructive tests against a real filesystem. Add new tools with typed, validated arguments, explicit safety behavior, structured results, and verification steps.

## Troubleshooting

If Gemini is unavailable, confirm `.env` is present, the key is valid, and the selected model is available to your account. If a task is stopped at the step limit, split it into smaller tasks. If a file is rejected, set `AGENT_WORKSPACE` to the intended project root rather than disabling the safety boundary.
