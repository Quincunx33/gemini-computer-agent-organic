<div align="center">

## Chatbot to Agent🤖



[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Gemini](https://img.shields.io/badge/AI-Google%20Gemini-8E75B2?style=for-the-badge&logo=googlegemini&logoColor=white)](https://ai.google.dev/)
[![Tests](https://img.shields.io/badge/tests-73%20passing-22C55E?style=for-the-badge)](tests/)
[![Security](https://img.shields.io/badge/safety-bounded%20%26%20audited-F59E0B?style=for-the-badge)](#safety-first)

<p align="center">
  <img src="docs/architecture.png" alt="genagent architecture diagram" width="100%" />
</p></div>

`genagent` is an experimental, terminal-based computer agent for local development and controlled workspace automation. It uses a language model to choose from a set of explicitly implemented tools, executes those tools through a bounded loop, and reports the observed results.

The project is intentionally local-first. It does not provide a hosted service, a sandbox by itself, or a guarantee that model-generated plans are correct. Treat it as an automation assistant that requires configuration, review, and ordinary operating-system security.

## What it can do

The interactive agent can use the following categories of tools when the task and platform allow them:

- Inspect, create, write, move, list, and delete files inside the configured workspace.
- Run shell commands with a configurable timeout and output limit.
- Verify Python source syntax and run project-level verification helpers.
- Inspect platform capabilities and selected processes.
- Create Git previews and checkpoints through the project’s Git helpers.
- Search the public web when web search is enabled.
- Use optional browser, desktop GUI, OCR, plugin, mobile, and parallel-analysis adapters when their dependencies and platform support are available.

The model does not automatically have access to every tool on every platform. Tool schemas are filtered using the detected platform, and dispatch performs a second compatibility check before execution.

## Current limitations

This project is under active development. The following limitations are important:

- A model response can be incomplete, incorrect, or unrelated to the user’s intent. The agent reports tool evidence when available, but it cannot independently prove that a model’s interpretation is correct.
- Live model calls require a valid provider API key, a supported model name, network access, and provider quota. API behavior and model availability can change.
- The default workspace boundary is a policy implemented by this application. It is not a replacement for OS permissions, containers, a VM, or a security review.
- Host mode can allow paths outside the workspace. Enable it only when necessary and keep protected-action confirmation enabled.
- GUI, browser, OCR, and mobile features are optional adapters. They may require extra packages, native programs, display access, or a compatible device.
- The test suite uses mocks and temporary paths for many cases. Passing tests do not mean that arbitrary commands, external services, or production data are safe.
- The repository does not promise autonomous privilege escalation. Privileged or destructive operations are subject to the application’s permission checks and, depending on configuration, explicit confirmation.

## Requirements

- Python 3.11 or newer is recommended.
- The core runtime uses Python’s standard library and has no required third-party runtime dependency.
- A supported language-model provider is required for live agent tasks. Gemini is the default provider in this repository. OpenAI-compatible adapters for OpenAI, xAI, and DeepSeek are also present in the codebase.
- Optional adapters may require their own packages or native tools. Install them only when you need those features.

## Quick start

Clone the repository and create an isolated Python environment:

```bash
git clone https://github.com/Quincunx33/genagent.git
cd genagent
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, use `.venv\\Scripts\\Activate.ps1` instead of `source .venv/bin/activate`.

Create a local configuration file with safe defaults:

```bash
python3 setup.py --non-interactive
```

To configure provider credentials and other settings interactively, use:

```bash
python3 setup.py
```

To inspect configuration without printing secrets:

```bash
python3 setup.py --doctor
```

The setup wizard writes `.env` in the project directory. Keep that file private. Do not commit it or paste API keys into issues, logs, screenshots, or chat messages.

Set at least one provider and a valid model. For Gemini, the minimum useful configuration is:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=your_supported_gemini_model
GEMINI_FALLBACK_MODELS=
AGENT_WORKSPACE=.
AUTONOMY_MODE=supervised
REQUIRE_CONFIRMATION=true
```

The exact model name must be checked against the provider’s current model list. The example model names in a repository configuration are not a guarantee that those models remain available.

Start the interactive agent:

```bash
python3 agent.py
```

Example request:

```text
Inspect this project, run the tests, explain any failures, and make no changes unless I approve them.
```

## Interactive commands

| Command | Purpose |
| --- | --- |
| `/help` | Show the available commands. |
| `/status` | Show model, mode, step limit, platform, shell, and debug state. |
| `/tools` | Show the main available tool names. |
| `/model` | Show the configured model. |
| `/workspace` | Show the configured workspace. |
| `/clear-memory` | Clear saved task memory. |
| `/cancel` | Request cooperative cancellation at the next safe boundary. |
| `/approvals` | Show pending protected-action approvals. |
| `/debug on` or `/debug off` | Enable or disable structured developer events. |
| `/exit` | Exit the interactive session. |

## How execution works

For each task, `AgentLoop` creates a bounded state, builds a small task plan, selects task-relevant tool schemas, and asks the configured model for the next step. A model response can be either a final text response or one or more structured tool calls. Each tool call is validated, checked against platform support and policy, executed, recorded in task state, and returned to the next model step as evidence.

The loop is limited by `MAX_AGENT_STEPS`. Model requests and shell commands have separate retry and timeout controls. Repeated identical tool calls are detected and converted into a no-progress observation rather than being executed indefinitely.

Final responses are formatted for the terminal. Markdown emphasis, JSON-wrapped response text, and escaped newlines are normalized before display. Developer debug mode remains structured JSON so it can be inspected by scripts.

## Safety and permissions

The default configuration uses a workspace boundary. Relative paths resolve inside `AGENT_WORKSPACE`; attempts to access paths outside it are rejected unless host mode is explicitly enabled. Denied-path rules can add further restrictions.

The permission layer classifies shell commands and protected tools. Read-only inspection is generally the least restricted. Destructive operations such as deletion and potentially privileged commands may require confirmation. `AUTONOMY_MODE` changes how ordinary actions are handled, but it does not make an unsafe command safe and should not be treated as an operating-system permission.

Recommended defaults for normal development are:

```env
AGENT_HOST_MODE=false
AUTONOMY_MODE=supervised
REQUIRE_CONFIRMATION=true
AUTO_INSTALL=false
AGENT_DRY_RUN=false
```

Use `AGENT_DRY_RUN=true` when you want to inspect proposed side effects without executing supported write or command tools. Review commands before approving them, especially commands involving `sudo`, permissions, deletion, package installation, credentials, network access, or broad filesystem paths.

API keys are loaded from environment variables or `.env`. The code contains redaction and bounded logging paths, but no software can guarantee that a user will never paste a secret into a task or a third-party command. Do not place secrets in prompts or command arguments.

## Configuration reference

The complete list of supported settings is in `.env.example`. The most commonly used settings are:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `gemini` | Selects the primary provider. |
| `LLM_FALLBACK_PROVIDERS` | `openai,xai,deepseek` | Provider order after the primary provider fails. |
| `GEMINI_API_KEY` | empty | Gemini credential. |
| `GEMINI_MODEL` | repository default | Primary Gemini model. Verify it is currently supported. |
| `GEMINI_FALLBACK_MODELS` | repository default | Comma-separated Gemini fallback models. |
| `AGENT_WORKSPACE` | current directory | Filesystem boundary for relative paths. |
| `AGENT_HOST_MODE` | `false` | Allows configured paths outside the workspace. Use cautiously. |
| `AUTONOMY_MODE` | `supervised` | `safe`, `supervised`, or `trusted` action policy. |
| `REQUIRE_CONFIRMATION` | `true` | Requests confirmation for protected actions. |
| `AGENT_DRY_RUN` | `false` | Reports supported side effects without executing them. |
| `MAX_AGENT_STEPS` | `50` | Maximum model/tool loop steps per task. |
| `COMMAND_TIMEOUT` | `120` | Maximum shell-command duration in seconds. |
| `API_RETRIES` | `3` | Attempts for retryable provider failures. |
| `WEB_SEARCH_ENABLED` | `true` | Enables the public web-search fallback. |
| `PLUGIN_ENABLED` | `true` | Enables validated plugin archive handling. |
| `MAX_PARALLEL_AGENTS` | `3` | Limit for bounded read-only parallel analysis. |
| `AGENT_DB` | user home | SQLite task-state path. |
| `AGENT_AUDIT_LOG` | user home | Redacted JSONL audit-log path. |

Provider-specific API keys and base URLs are documented in `.env.example`. Provider adapters should be treated as integrations that need current provider documentation and valid model identifiers.

## Optional adapters

The standard-library core is enough for terminal, filesystem, model, and many verification paths. Optional features have additional requirements:

- **Browser helpers:** Playwright and a browser runtime may be required.
- **Desktop GUI:** PyAutoGUI and a display/accessibility permission may be required.
- **OCR:** a working `tesseract` executable may be required.
- **Mobile bridge:** run `python3 mobile_server.py --host 127.0.0.1 --port 8765` and configure a bearer token. Keep it loopback-only unless you have deliberately configured network security.

If an optional tool is missing, the agent can report alternatives for some tools. It does not silently install arbitrary packages. Automatic installation is opt-in and limited by the project’s allowlist logic.

## Project layout

```text
agent.py                 Interactive terminal entrypoint
agent_loop.py            Bounded observe/plan/act/verify loop
gemini_client.py         Gemini REST client and response parsing
openai_compatible.py     OpenAI-compatible provider adapters
planner.py               Tool schemas and task-relevant tool selection
permissions.py           Risk classification and confirmation policy
config.py                Environment and .env configuration
tools/                   Terminal, filesystem, verification, Git, GUI, and control adapters
skills/                  Optional task guidance packs
tests/                   Standard-library regression tests
docs/                    Architecture source and diagram
```

## Testing and development

The project uses Python’s built-in `unittest` runner. No pytest installation is required for the core suite:

```bash
python3 -m compileall -q .
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

The tests cover tool contracts, command execution and timeouts, filesystem boundaries, permissions, response parsing, error handling, redaction, task persistence, platform checks, optional-feature guards, and UI rendering. Tests should run against temporary or test workspaces. Do not point destructive tests at personal files or production systems.

## Contributing safely

Keep changes small and testable. Update the relevant unit tests when changing a tool contract, parser, permission rule, or configuration field. Never commit `.env`, provider keys, local databases, audit logs, screenshots containing secrets, or generated cache directories.

Before opening a pull request, run the compile and `unittest` commands above. Describe external-service tests separately from local tests, including the provider, model, workspace, and any limitations.

