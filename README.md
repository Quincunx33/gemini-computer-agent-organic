<div align="center">

# genagent

### A grounded, local-first computer agent powered by Google Gemini

**Observe → Plan → Act → Verify**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Tests](https://img.shields.io/badge/tests-73%20passing-22C55E?style=for-the-badge)](tests/)
[![Security](https://img.shields.io/badge/safety-bounded%20%26%20audited-F59E0B?style=for-the-badge)](#safety-first)

*A transparent terminal agent that can inspect a workspace, choose controlled tools, recover from failures, and verify its work without silently escalating privileges.*

</div>

<br />

<p align="center">
  <img src="docs/architecture.png" alt="genagent architecture diagram" width="100%" />
</p>

## Why genagent?

Most automation scripts follow a fixed sequence. **genagent** instead maintains a bounded feedback loop: it observes the current state, asks Gemini to select the smallest useful next action, executes that action through a typed tool, and verifies the result. When a command fails or a tool call repeats without progress, the agent records the observation and asks the model to recover rather than blindly retrying.

The agent is designed for local development and system tasks where the user should be able to see what is happening. Commands, permissions, workspace boundaries, timeouts, audit records, and verification are explicit parts of the system—not hidden implementation details.

## Highlights

- **Gemini-powered planning** through the official REST API, with model fallback and structured tool-call normalization.
- **Bounded autonomy** with configurable step limits, command timeouts, API retries, cancellation, and repeated-call detection.
- **Safety-first execution** with risk classification, exact-command confirmation for privileged or destructive actions, path validation, and secret redaction.
- **Workspace-aware tools** for terminal commands, filesystem operations, Python verification, processes, Git, browser adapters, and optional desktop GUI control.
- **Persistent continuity** through redacted SQLite task summaries and resumable task state.
- **Verification after change** through syntax checks, atomic self-updates, backups, and rollback when a Python update is invalid.
- **Cross-platform capability reporting** for Linux, macOS, Windows, Termux, and restricted mobile environments.
- **Runtime skill packs** for browser, coding, research, and DevOps work, selected from the task and injected as bounded guidance.
- **Opt-in host mode** for operating outside the project workspace while retaining secret redaction, path resolution, and protected-action confirmation.
- **Human-friendly activity events** in Bengali for file reads, commands, verification, permissions, and results, plus a developer debug stream with structured timestamps, arguments, result summaries, error IDs, and duration.
- **API-friendly request control** with process-wide pacing, rolling request quotas, `Retry-After` support, exponential backoff with jitter, and cancellation-aware waits so retries do not burst Gemini.
- **Cooperative task cancellation** through `Ctrl+C` during a running task and `/cancel` between tasks; cancellation is persisted and can be resumed by task ID.
- **Platform-aware execution** with explicit Linux, Windows, Termux, and iOS-shell profiles, shell-family guidance, capability-based tool schemas, and hard guards against incompatible GUI, process, app, and shell commands.
- **Standard-library core** with no required third-party runtime dependency.
- **Enterprise-grade failure handling** with stable error codes, correlation IDs, safe public messages, structured logs, bounded retries, response-size limits, and graceful recovery across model, network, tool, SQLite, and mobile API boundaries.

## Quick start

### 1. Clone and create an environment

```bash
git clone https://github.com/Quincunx33/genagent.git
cd genagent
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate the environment with `.venv\\Scripts\\Activate.ps1`.

### 2. Configure the complete agent

```bash
python3 setup.py
```

The setup wizard configures Gemini, OpenAI/ChatGPT, xAI/Grok, and DeepSeek API keys, provider priority, **two models per provider (primary plus same-provider fallback)**, workspace, autonomy mode, confirmation policy, automatic-install policy, web search, plugins, parallel-agent limit, host mode, and skill loading. The API keys use hidden input, are written only to the local `.env`, and are never stored in source, task memory, or SQLite history. The runtime uses the first configured provider in `LLM_PROVIDER` plus `LLM_FALLBACK_PROVIDERS`; if a provider key is available, it tries that provider's primary model and then its own fallback model before switching provider. It keeps the same tool-call contract across all providers. For safe defaults without prompting, use `python3 setup.py --non-interactive`; inspect configuration without revealing secrets with `python3 setup.py --doctor`.

The default model order is:

1. `gemini-3.6-flash`
2. `gemini-flash-lite-latest`
3. `gemini-3.6-flash`

You can override the order with `GEMINI_MODEL` and `GEMINI_FALLBACK_MODELS`.

### 3. Run the agent

```bash
python agent.py
```

Example task:

```text
Inspect this project, find the failing tests, make the smallest safe fix, run the test suite, and report what was verified.
```

## Common commands

| Command | Purpose |
| --- | --- |
| `/help` | Show available commands. |
| `/status` | Show model, workspace, and execution settings. |
| `/tools` | List the available tools. |
| `/model` | Show the active Gemini model. |
| `/workspace` | Show the configured workspace. |
| `/permissions` | Explain the permission policy. |
| `/memory` | Review relevant stored task context. |
| `/clear-memory` | Clear redacted agent memories. |
| `/tasks` | List persisted tasks. |
| `/resume TASK_ID` | Resume a paused task. |
| `/exit` | Exit the agent. |

## Safety first

> **genagent never treats autonomy as permission to hide actions.** The user remains in control of privileged and destructive work.

The permission layer classifies actions as normal, low-risk, privileged, or destructive. Normal read-only inspection can run automatically. Privileged and destructive operations display the exact command and require an explicit confirmation. Secret-like values are redacted before read results enter terminal events, task history, or model context. The agent does not bypass operating-system authentication, extract credentials, store API keys in memory, or implement CAPTCHA bypass, credential theft, stealth scraping, or unauthorized access.

The default workspace boundary prevents accidental writes outside the configured project. File sizes, output sizes, API retries, command duration, and total agent steps are configurable. Runtime databases, JSONL audit logs, command history, and secrets are local-only artifacts and are excluded by `.gitignore`.

## Architecture

The main modules have one responsibility each:

- `agent.py` provides the interactive terminal UI and slash commands.
- `agent_loop.py` coordinates the bounded observe-plan-act-verify cycle.
- `gemini_client.py` isolates Gemini requests, retries, and tool-call parsing.
- `openai_compatible.py` adapts ChatGPT/OpenAI, xAI/Grok, and DeepSeek chat-completions APIs to the same agent tool-call contract and fallback router.
- `errors.py` defines the stable error taxonomy, correlation IDs, safe public payloads, and retry classification.
- `planner.py` defines the structured tool schemas exposed to Gemini.
- `permissions.py` classifies risk and handles confirmation.
- `tools/` contains terminal, filesystem, process, Git, browser, GUI, and verification adapters.
- `memory.py`, `state.py`, and `task_store.py` provide redacted continuity and resumable task state.
- `security.py` handles secret redaction and audit protections.
- `setup.py` and `env_manager.py` bootstrap and diagnose the complete local `.env` configuration without exposing secrets.
- `text_safety.py` prevents malformed Unicode from terminating terminal sessions on macOS and iPadOS boundaries.

## Optional adapters

The core agent runs with Python's standard library. Optional capabilities can be enabled only when needed:

- **Browser automation:** install Playwright and its browser runtime for browser helpers.
- **Desktop GUI:** install PyAutoGUI on a trusted desktop with the required accessibility/display permissions.
- **OCR:** install the native `tesseract` executable.
- **Mobile bridge:** run `python mobile_server.py --host 127.0.0.1 --port 8765`. The bridge requires a bearer token and should remain loopback-only unless a trusted private network, HTTPS, firewall rules, and a long random token are configured.

## Configuration

Configuration is loaded from environment variables or `.env`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_PROVIDER` | `gemini` | Primary provider: `gemini`, `openai`, `xai`, or `deepseek`. |
| `LLM_FALLBACK_PROVIDERS` | `openai,xai,deepseek` | Provider fallback order when the active provider is unavailable. |
| `OPENAI_API_KEY` / `XAI_API_KEY` / `DEEPSEEK_API_KEY` | empty | Optional provider credentials; never print or commit them. |
| `OPENAI_MODEL` | `gpt-6-astra` | Current OpenAI flagship model. |
| `OPENAI_FALLBACK_MODELS` | `gpt-5.6-terra` | Same-provider fallback model. |
| `XAI_MODEL` | `grok-4.7` | Current Grok flagship for agentic tool calling. |
| `XAI_FALLBACK_MODELS` | `grok-4.6` | Same-provider fallback model. |
| `DEEPSEEK_MODEL` | `deepseek-flash` | Current DeepSeek Flash API model. |
| `DEEPSEEK_FALLBACK_MODELS` | `deepseek-v4-pro` | Same-provider fallback model. |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Primary Gemini model. |
| `GEMINI_FALLBACK_MODELS` | See `.env.example` | Comma-separated fallback models. |
| `AGENT_WORKSPACE` | Current directory | Filesystem boundary for the agent. |
| `AGENT_HOST_MODE` | `false` | Permit absolute paths and command working directories outside `AGENT_WORKSPACE`; keep confirmations enabled. |
| `SKILLS_ENABLED` | `true` | Enable task-based skill-pack discovery. |
| `AGENT_SKILLS_PATH` | Project `skills/` | Directory containing `*/SKILL.md` packs. |
| `AGENT_DEBUG` | `false` | Start the event stream in developer debug mode. |
| `GEMINI_MIN_INTERVAL` | `0.2` | Minimum seconds between Gemini requests in this process. |
| `GEMINI_RATE_LIMIT` | `30` | Maximum Gemini requests in the rolling rate window. |
| `GEMINI_RATE_WINDOW` | `60` | Rolling rate window in seconds. |
| `GEMINI_BACKOFF_BASE` | `1` | Initial retry delay in seconds. |
| `GEMINI_BACKOFF_MAX` | `16` | Maximum exponential retry delay in seconds. |
| `MAX_AGENT_STEPS` | `50` | Maximum steps in one task. |
| `COMMAND_TIMEOUT` | `120` | Maximum seconds for a command. |
| `API_RETRIES` | `3` | Maximum attempts per Gemini model for retryable network/API failures. |
| `MAX_API_RESPONSE_BYTES` | `4194304` | Maximum accepted Gemini response size. |
| `MAX_PROMPT_CHARS` | `16000` | Hard cap for each generated prompt. |
| `MAX_HISTORY_CHARS` | `12000` | Newest conversation/tool history retained per API call. |
| `MAX_MEMORY_CHARS` | `3000` | Maximum relevant long-term memory included in a prompt. |
| `MAX_TOOL_RESULT_CHARS` | `5000` | Maximum serialized result retained for one tool observation. |
| `RESPONSE_CACHE_ENABLED` | `true` | Enable bounded in-process caching for identical final text responses. |
| `RESPONSE_CACHE_TTL` | `300` | Cache lifetime in seconds. Tool-call responses are never cached. |
| `RESPONSE_CACHE_SIZE` | `128` | Maximum cached responses per process. |
| `TASK_TOOL_FILTERING` | `true` | Send only task-relevant tool schemas when intent is clear. |
| `GEMINI_FAST_MODEL` | `gemini-flash-lite-latest` | First model for short read-only/status requests. |
| `MAX_RETRIES` | `3` | Recovery retry limit. |
| `REQUIRE_CONFIRMATION` | `true` | Require confirmation for protected actions. |
| `AUTONOMY_MODE` | `supervised` | `safe`, `supervised`, or `trusted`; controls when ordinary workspace actions need confirmation. |
| `AUTO_INSTALL` | `false` | Enable the known-package install → verify → fallback chain; never enables unknown package guesses. |
| `INSTALL_TIMEOUT` | `300` | Maximum seconds for an allowlisted install command. |
| `WEB_SEARCH_ENABLED` | `true` | Enable public web search fallback with returned source URLs. |
| `PLUGIN_ENABLED` | `true` | Enable validated plugin zip installation without executing plugin code. |
| `MAX_PARALLEL_AGENTS` | `3` | Maximum bounded read-only sub-agents for one parallel analysis call. |
| `AGENT_DB` | User home directory | Local SQLite task state path. |
| `AGENT_AUDIT_LOG` | User home directory | Local redacted JSONL audit path. |
| `LOG_ROTATE_HOURS` | `24` | Rotate the active audit log after this many hours; rotation is checked before every write. |
| `LOG_RETENTION` | `7` | Number of rotated audit archives to retain. |

## Development

Run the complete test suite with:

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

The project includes regression coverage for command execution, timeout handling, filesystem safety, permissions, Gemini protocol normalization, memory redaction, mobile authentication, self-update rollback, task persistence, and Unicode surrogate handling. Do not run destructive tests against a real user filesystem.

### Error handling contract

All external failures are normalized into stable error codes such as `TIMEOUT`, `NETWORK_ERROR`, `API_AUTH_ERROR`, `API_HTTP_ERROR`, `INVALID_RESPONSE`, `PERMISSION_DENIED`, and `INTERNAL_ERROR`. User-facing responses contain a bounded safe message and an `error_id`; secrets, API keys, command output credentials, and stack traces are excluded from public responses. Retryable model failures use bounded exponential backoff with jitter and model fallback, while authentication and malformed-request failures fail fast. Structured JSON logs and the mobile bridge audit log retain correlation IDs and redacted diagnostics for incident investigation. The active audit log automatically rotates after **24 hours by default**, starts a fresh JSONL file, and retains only the configured number of timestamped archives; this is lazy and deterministic, so it needs no external scheduler or dependency.

### Cross-platform execution

At startup and before each task, the agent detects a concrete profile: `linux`, `windows`, `termux`, `ios_shell`, `macos`, or `unknown`. The profile includes the shell family, display state, GUI backend, supported tools, and unsupported tools. The model receives this information as authoritative context. Tool schemas are filtered against the profile, and direct dispatch performs a second guard, so an iOS shell cannot receive desktop GUI/process controls, Termux cannot receive desktop launcher/GUI actions, and Windows rejects obvious POSIX/Linux commands. Windows tasks are guided toward `cmd.exe`/PowerShell syntax; Linux/macOS/Termux tasks use POSIX syntax only when the command is available.

### Token optimization

The agent keeps the newest conversation and tool observations within explicit character budgets instead of resending an unbounded transcript on every step. Long tool output is clipped before it enters history, relevant memory is capped, and tool descriptions are intentionally concise. These controls reduce repeated input tokens while preserving the latest evidence and all permission/safety checks. Tune the four `MAX_*_CHARS` settings only when a task genuinely needs more context; increasing them increases cost on every model step.

Identical final text responses are cached in memory with a short TTL; tool-call responses are intentionally excluded so stale actions are never replayed. Repeated identical tool observations are stored as compact references. Clear task intent selects a smaller tool schema, while ambiguous requests retain the full schema for safety. Short read-only requests prefer `GEMINI_FAST_MODEL`; write or ambiguous tasks keep the normal model order.

## Repository hygiene

The repository intentionally excludes `.env`, virtual environments, Python caches, SQLite databases, JSONL audit logs, command history, and local log files. Commit `.env.example` when configuration fields change, but never commit a real API key or runtime state.

## Skill packs and host mode

Skill packs are local `skills/<name>/SKILL.md` files with YAML frontmatter. The runtime discovers them at startup, selects the most relevant packs for each task, and adds their instructions to the model prompt. Skill text is guidance only; it cannot grant permissions or bypass tool checks. The included packs cover browser, coding, research, and DevOps workflows.

The default mode confines filesystem paths and command working directories to `AGENT_WORKSPACE`. To let the agent work across the host filesystem, set `AGENT_HOST_MODE=true` in `.env` and restart it. This expands path access for read/write/self-update and command working directories, but protected actions still require confirmation, command risk classification remains active, and read results continue to redact secret-like values. Use host mode only on a machine and account where you accept the agent's broader reach.

During interactive use, type `/debug on` or `/debug off` to switch modes without restarting. Normal mode shows concise Bengali activity updates such as `ফাইল পড়ছি`, `কমান্ড চালাচ্ছি`, and `যাচাই সম্পন্ন হয়েছে`. Debug mode adds structured JSON events suitable for troubleshooting and mobile-client logs.

To stop a running task, press **Ctrl+C once**. The agent stops at the current model/tool boundary, persists the task as `cancelled`, and avoids claiming that unfinished work succeeded. Type `/cancel` when the CLI is waiting for the next task to request cancellation before the next run starts. Resume a cancelled task with `/resume TASK_ID`.

### Advanced controls

The project also includes a threaded `TaskController` for real-time integrations, a local developer dashboard handler, task replay helpers, a structured plan with acceptance criteria, dry-run previews (`AGENT_DRY_RUN=true`), checkpointed file writes under `.agent_checkpoints/`, strict tool argument validation, process-group cleanup on timeout, and a persistent SQLite request quota. Host mode supports `AGENT_ALLOWED_PATHS` and `AGENT_DENIED_PATHS`; denied paths win, and common credential directories are documented as protected defaults for deployment policy.

Protected tool requests are represented by an `ApprovalBroker` with an approval ID, so a web/mobile approval endpoint can be added without changing tool execution. Skill packs carry trust metadata and remain guidance only; they cannot grant permissions. Model fallback tracks retryable health failures and temporarily cools down unhealthy models instead of hammering them.

Independent-agent controls include three autonomy modes, explicit plan acceptance criteria, `verify_project` test evidence, `preview_diff`, reversible `git_checkpoint` patch artifacts, resumable task state, operational tool memory, progress events, model routing, and read-only reviewer/sub-agent boundaries. A failed verification is evidence for the model's recovery loop; it is never reported as success merely because a command returned.

When a requested CLI, AI utility, package, or optional adapter is missing, the agent uses `find_alternatives` before considering installation. It checks installed commands, Python standard-library capabilities, OS-native equivalents, and existing skills. It also searches the local `apt-cache`, `apk`, `brew`, `dnf`, or `yum` index when available, without refreshing indexes or installing anything. `verify_tool` reports the executable path, exit status, and `--version` output after discovery or installation. It reports `install_attempted: false` and does not install packages unless the user explicitly asks for installation and approves the exact command. File tasks expose `create_file`, `move_file`, and approval-protected `delete_file`; move refuses to overwrite an existing destination.

The **AI makes the install-versus-alternative decision**. A `COMMAND_NOT_FOUND` result automatically includes the alternatives returned by the resolver, so Gemini can choose the best available route for the user's goal. `install_and_verify` is restricted to the known allowlist, uses argument arrays rather than shell pipelines, enforces a timeout, verifies the executable, and returns a standard-library fallback when installation fails. It remains disabled unless `AUTO_INSTALL=true`; protected install actions still pass through the approval gate.

The extension tools are deliberately bounded. `install_plugin` accepts a zip only when it contains a safe `plugin.json` manifest, rejects traversal and oversized entries, installs into the workspace plugin directory, and never executes plugin code. `search_web` uses the public HTML endpoint with a timeout and returns source URLs for the model to inspect. `parallel_analysis` runs at most four read-only sub-agents with a bounded thread pool; write, delete, GUI side-effect, and risky command tools are blocked inside those sub-agents.

## License and status

This project is an actively developed experimental agent framework. Review every proposed command before approving it, especially when the workspace or host system contains sensitive data.

## References

[1]: https://ai.google.dev/gemini-api/docs "Gemini API documentation"
[2]: https://docs.python.org/3.11/library/venv.html "Python virtual environment documentation"
[3]: https://docs.python.org/3.11/library/unittest.html "Python unittest documentation"
