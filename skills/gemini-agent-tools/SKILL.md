---
name: gemini-agent-tools
description: Extend or use the Gemini computer agent's tool layer. Use when adding terminal, filesystem, Git, verification, browser, or other action tools.
---

# Gemini Agent Tools

## Tool contract

Every tool must have a stable name, concise description, JSON-compatible argument schema, explicit safety behavior, structured return data, and a verification path. Keep tool execution in `agent_loop.py` and keep implementation adapters under `tools/`.

## Adding a tool

1. Implement a small function in `tools/<name>.py`.
2. Validate paths and argument sizes before performing side effects.
3. Add the function declaration to `planner.py`.
4. Route the name in `AgentLoop.execute`.
5. Return a dictionary with predictable keys; include `error` instead of leaking a traceback to the model.
6. Add a `unittest` test using temporary workspace data or a fake client.
7. Run the complete verification workflow.

## Existing core tools

- `run_command`: bounded shell execution with risk confirmation and redacted output.
- `read_file` / `write_file` / `list_directory`: workspace-confined file operations.
- `verify_python`: syntax compilation without external packages.
- `self_update`: atomic source update with backup and Python syntax rollback.
- `platform_info`: report the actual host and available capabilities.
- `open_app`: use the host launcher to open a URL, file, or application.
- `list_processes` / `terminate_process`: inspect or confirmation-protect process control.

Treat GUI support as capability-based. Do not promise arbitrary iOS control; use Shortcuts or a-Shell there. On desktop platforms, require the user's display/accessibility permissions before adding mouse or keyboard automation.

Do not add a tool that bypasses confirmation, reads secrets by default, writes outside the workspace, or silently changes permissions.
For self-updates, inspect the current file first, keep the generated backup, run syntax checks and tests, and report or restore any failure.
