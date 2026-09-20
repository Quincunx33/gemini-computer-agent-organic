---
name: gemini-agent-safety
description: Secure operation of the dependency-free Gemini computer agent. Use when executing shell commands, reading or writing workspace files, handling secrets, or reviewing risky automation.
---

# Gemini Agent Safety

## Core workflow

1. Resolve every path through the configured workspace boundary.
2. Classify commands before execution as normal, low-risk, privileged, or destructive.
3. Classify download-to-shell pipelines and direct reads of credential files as destructive.
4. Require exact-command confirmation for privileged and destructive actions; do not silently block them.
5. Redact API keys, tokens, passwords, and secrets before displaying or storing output.
6. Keep file reads/writes within `MAX_FILE_SIZE`; keep command output within `MAX_OUTPUT_CHARS`.

## Review rules

Treat `rm`, disk tools, reboot/shutdown, destructive Git operations, `sudo`, package installation, service changes, permission escalation, credential-file reads, and network-to-shell pipelines as high risk. Ask for explicit approval before running them; never approve a command merely because the model requested it. Show the exact command and its working directory.

Do not disable the workspace boundary to solve a path error. Inspect symlinks and the resolved path first. Never place credentials in prompts, SQLite memory, logs, commits, or generated files.

## Failure handling

If the user declines confirmation, explain the risky class and propose a narrower read-only alternative. Do not retry a declined command with spelling changes or shell indirection.
