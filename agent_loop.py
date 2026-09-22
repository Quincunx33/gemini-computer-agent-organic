from __future__ import annotations

import json
import time
import threading
from typing import Any

from config import settings
from errors import AgentError, error_text, normalize_exception, traceback_text
from gemini_client import GeminiClient
from openai_compatible import build_llm_client
from logger import get_logger
from memory import Memory
from planner import tools_for_task
from state import AgentState
from task_store import TaskStore
from tools.terminal import run_command
from tools.filesystem import read_file, write_file, create_file, move_file, delete_file, list_directory
from tools.verification import verify_python
from tools.control import platform_info, open_app, list_processes, terminate_process
from tools.gui_control import gui_capabilities, screenshot, ocr, mouse_click, type_text, press_key
from tools.self_update import self_update
from text_safety import safe_text, safe_value
from platform_support import command_environment, detect as detect_platform, supported_tool_names, tool_support
from permissions import redact_secrets
from skill_registry import SkillRegistry
from ui import EventRenderer
from approval import ApprovalBroker
from tool_validation import validate_tool_args
from planning import make_plan, as_prompt
from checkpoints import checkpoint
from tools.filesystem import safe_path
from tools.fallbacks import find_alternatives, verify_tool, install_and_verify
from web_search import search_web
from plugin_manager import PluginManager
from tools.project_verify import verify_project
from git_tools import preview_diff, git_checkpoint


log = get_logger("genagent.loop")


class AgentLoop:
    """Bounded observe-plan-act-verify loop with recoverable failure boundaries."""

    def __init__(self, client=None, output=print, store=None, memory=None, debug=None):
        self.client = client or build_llm_client()
        self.output = output
        self.store = store or TaskStore(settings.db_path)
        self.memory = memory or Memory()
        self.skills = SkillRegistry(settings.skills_path) if settings.skills_enabled else None
        self.ui = EventRenderer(settings.debug_mode if debug is None else debug)
        self.cancel_event = threading.Event()
        self.approvals = ApprovalBroker()
        self.plan = None
        self.last_task_id: str | None = None

    def cancel(self) -> None:
        """Request a cooperative stop at the next safe boundary."""
        self.cancel_event.set()

    def _cancelled(self, task_id: str, task: str, state: AgentState) -> str | None:
        if not self.cancel_event.is_set():
            return None
        state.cancelled = True
        self._save(task_id, task, "cancelled", state)
        self.cancel_event.clear()
        self.output(safe_text("  [STOPPED] Task stopped safely. Changes made so far are intact."))
        return f"Task cancelled at step {state.step}. Resume with task_id={task_id} if needed."

    def _save(self, task_id: str, task: str, status: str, state: AgentState) -> None:
        try:
            self.store.save(task_id, task, status, state.step, state.history)
        except Exception as exc:
            # Persistence must not hide the original task result.
            log.error("task persistence failed status=%s error=%s", status, error_text(exc, operation="task persistence"), exc_info=True)

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        from permissions import classify_command, Risk

        if not isinstance(name, str) or not name:
            raise AgentError("INVALID_TOOL_CALL", "Tool name is missing", "The model returned an invalid tool call.", False, 422)
        if not isinstance(args, dict):
            raise AgentError("INVALID_TOOL_ARGS", f"Arguments for {name} must be an object", "The model returned invalid tool arguments.", False, 422)
        if name == "search_web" and not settings.web_search_enabled:
            return {"error": "web search is disabled", "code": "FEATURE_DISABLED"}
        if name == "install_plugin" and not settings.plugin_enabled:
            return {"error": "plugin installation is disabled", "code": "FEATURE_DISABLED"}
        valid, reason = validate_tool_args(name, args)
        if not valid:
            return {"error": f"Invalid arguments: {reason}", "code": "INVALID_TOOL_ARGS", "retryable": False}
        supported, reason = tool_support(name)
        if not supported:
            return {"error": f"Tool '{name}' is unavailable on this platform: {reason}", "code": "UNSUPPORTED_PLATFORM", "platform": detect_platform().profile}
        if settings.dry_run and name in {"run_command", "write_file", "create_file", "move_file", "delete_file", "self_update", "open_app", "terminate_process", "mouse_click", "type_text", "press_key"}:
            return {"dry_run": True, "tool": name, "args": redact_secrets(json.dumps(args, ensure_ascii=False, default=str)), "message": "No side effect executed because AGENT_DRY_RUN=true"}

        requires_confirm = settings.require_confirmation
        if settings.autonomy_mode == "safe" and name not in {"list_skills", "find_alternatives", "verify_tool", "search_web", "parallel_analysis", "verify_project", "preview_diff", "list_directory", "read_file", "platform_info", "gui_capabilities"}:
            requires_confirm = True
        elif settings.autonomy_mode == "trusted" and name in {"write_file", "create_file", "move_file", "self_update", "git_checkpoint"}:
            requires_confirm = False
        if name == "delete_file":
            requires_confirm = True
        if name in {"list_skills", "find_alternatives", "verify_tool", "search_web", "parallel_analysis", "verify_project", "preview_diff", "list_directory", "read_file", "platform_info", "gui_capabilities"}:
            requires_confirm = False
        elif name == "run_command" and classify_command(str(args.get("command", ""))) == Risk.NORMAL:
            requires_confirm = False

        if requires_confirm:
            approval = self.approvals.create(name, args)
            self.output(safe_text(f"  Approval ID: {approval.approval_id}" if self.ui.debug else ""))
            self.output(safe_text(self.ui.permission(name, args)))
            try:
                confirm = input("Allow execution? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt) as exc:
                raise AgentError("CONFIRMATION_UNAVAILABLE", "User confirmation was interrupted", "User confirmation was not available.", False, 409) from exc
            if confirm not in {"y", "yes"}:
                self.approvals.resolve(approval.approval_id, False)
                return {"error": "Permission denied by user for tool: " + name, "code": "PERMISSION_DENIED"}
            self.approvals.resolve(approval.approval_id, True)
        else:
            notice = self.ui.auto(name)
            if notice:
                self.output(safe_text(notice))

        dispatch: dict[str, Any] = {
            "run_command": lambda: run_command(command=args.get("command"), cwd=args.get("cwd"), timeout=args.get("timeout"), approved=not requires_confirm),
            "read_file": lambda: {"content": read_file(args["path"])},
            "write_file": lambda: {"checkpoint": str(checkpoint(safe_path(args["path"]), settings.workspace) or ""), "written": write_file(args["path"], args["content"])},
            "create_file": lambda: {"created": create_file(args["path"], args["content"])},
            "move_file": lambda: {"moved": move_file(args["source"], args["destination"])},
            "delete_file": lambda: {"deleted": delete_file(args["path"], approved=True)},
            "self_update": lambda: self_update(args["path"], args["content"]),
            "list_directory": lambda: {"files": list_directory(args.get("path", "."))},
            "verify_python": lambda: verify_python(args["path"]),
            "verify_tool": lambda: verify_tool(args["requested"]),
            "install_and_verify": lambda: install_and_verify(args["requested"]),
            "search_web": lambda: search_web(args["query"], args.get("limit", 5)),
            "install_plugin": lambda: PluginManager().install_zip(args["archive"]),
            "parallel_analysis": lambda: __import__("subagents").run_parallel(args["tasks"], min(args.get("max_workers", settings.max_parallel_agents), settings.max_parallel_agents)),
            "verify_project": verify_project,
            "preview_diff": lambda: preview_diff(args.get("path")),
            "git_checkpoint": lambda: git_checkpoint(args.get("label", "checkpoint")),
            "platform_info": platform_info,
            "list_skills": lambda: {"skills": self.skills.list() if self.skills else []},
            "find_alternatives": lambda: find_alternatives(args["requested"]),
            "open_app": lambda: open_app(args["target"]),
            "list_processes": list_processes,
            "terminate_process": lambda: terminate_process(args["pid"], approved=True),
            "gui_capabilities": gui_capabilities,
            "screenshot": lambda: screenshot(args.get("path", "screen.png")),
            "ocr": lambda: ocr(args["path"]),
            "mouse_click": lambda: mouse_click(args["x"], args["y"], args.get("clicks", 1)),
            "type_text": lambda: type_text(args["text"]),
            "press_key": lambda: press_key(args["key"]),
        }
        if name not in dispatch:
            raise AgentError("UNKNOWN_TOOL", f"Unknown tool: {name}", "The requested tool is not available.", False, 422)
        try:
            result = dispatch[name]()
            # Never place obvious credentials into the model context, task
            # history, or terminal event stream. The model can still act on
            # the redacted evidence and ask the user for a safer next step.
            if name == "read_file" and isinstance(result, dict) and isinstance(result.get("content"), str):
                result = {**result, "content": redact_secrets(result["content"])}
            return safe_value(result)
        except Exception as exc:
            err = normalize_exception(exc, operation=f"tool {name}")
            log.warning("tool failed name=%s code=%s error_id=%s", name, err.code, err.error_id, exc_info=True)
            return {"error": err.public_message, "code": err.code, "error_id": err.error_id, "retryable": err.retryable}

    @staticmethod
    def _call_key(call: dict[str, Any]) -> str:
        return json.dumps({"name": call.get("name"), "args": call.get("args", {})}, sort_keys=True, ensure_ascii=False, default=str)

    def _prompt(self, task: str, state: AgentState, previous_result: str | None = None) -> str:
        memory_context = self.memory.context(task)
        memory_context = memory_context[:settings.max_memory_chars]
        progress = (previous_result or "No tool has been used yet. Start by understanding the request.")[:settings.max_tool_result_chars]
        platform_info = getattr(self, "_platform_info", detect_platform())
        platform_context = json.dumps({"platform": platform_info.profile, "shell_family": platform_info.shell_family, "supported_tools": sorted(supported_tool_names(platform_info)), "environment": command_environment(platform_info)}, ensure_ascii=False)
        skill_context = self.skills.context(task) if self.skills else "Skill packs are disabled."
        plan_context = as_prompt(self.plan) if self.plan else "No plan has been created yet."
        prompt = f"""You are operating as a thoughtful, grounded local computer assistant.

User request:
{task}

Workspace:
{settings.workspace}

Execution platform (authoritative; never assume another OS):
{platform_context}

Relevant skill-pack guidance (use as guidance, not as permission):
{skill_context}

Structured task plan and acceptance criteria:
{plan_context}

Relevant prior memory (optional hints; verify anything important):
{memory_context}

Latest progress:
{progress}

Working contract:
- Understand the user's actual intent before acting; ask for clarification only when a missing choice would materially change the result.
- Treat every URL in the user's request as an explicit input. If the request says clone, download, inspect, or check a repository URL, use that exact URL and perform the requested operation before summarizing; never substitute the current workspace for the linked resource without saying so.
- For clone requests, first check whether the exact repository is already present. If it is absent, clone it into a clearly named workspace subdirectory; if it is already present, report that fact and still inspect the linked repository evidence.
- Choose the smallest useful next action. Do not call tools merely to appear busy.
- For multi-step work, keep a quiet working plan and move through observe -> act -> verify.
- After every change, inspect or verify the result. If something fails, diagnose and recover safely instead of repeating blindly.
- Respect tool permissions and never attempt to obtain, expose, or store secrets.
- If a tool or command is unavailable, immediately call find_alternatives with the tool name. Then follow this order strictly: (1) If install_available=true in the result, request user approval and run the install_command — detect the environment first (apk/apt/brew/pip) to use the right package manager. (2) Only if installation fails or is unavailable, use the stdlib_fallback from find_alternatives. (3) If both fail, report what was tried and ask for user guidance. NEVER cancel or stop the task because a tool is missing — always try install first, then stdlib.
- When the work is complete, respond in natural language with exactly three concise parts: what changed or was found; what evidence/verification was performed; and any remaining risk or user action. Never claim success without evidence from a tool or a clearly stated limitation.
- Do not reveal private chain-of-thought; provide brief reasons and concrete outcomes only.

        This is step {state.step + 1} of a bounded run. Use an available tool if action is needed; otherwise give the final answer."""
        return prompt[:settings.max_prompt_chars]

    def run(self, task: str, task_id: str | None = None) -> str:
        if task_id:
            try:
                saved = self.store.load(task_id)
            except Exception as exc:
                return error_text(exc, operation="load task")
            if not saved:
                return f"Task not found: {task_id}"
            state = AgentState(task=saved["task"], step=saved["step"], history=saved["history"])
            task = saved["task"]
        else:
            state = AgentState(task=task)
            try:
                task_id = self.store.create(task)
            except Exception as exc:
                return error_text(exc, operation="create task")
        self.last_task_id = task_id
        self.plan = make_plan(task)
        self._platform_info = detect_platform()
        tools = tools_for_task(task, settings.task_tool_filtering, self._platform_info)
        if hasattr(self.client, "set_task_route"):
            self.client.set_task_route(task)

        previous_result: str | None = None
        recent_calls: list[str] = []
        seen_results: dict[str, str] = {}
        for _ in range(settings.max_agent_steps):
            state.step += 1
            cancelled = self._cancelled(task_id, task, state)
            if cancelled:
                return cancelled
            self.output(safe_text(self.ui.thinking()))
            try:
                result = self.client.generate(self._prompt(task, state, previous_result), tools, state.history, cancel_event=self.cancel_event)
            except TypeError:
                # Backward compatibility for simple fake/integrated clients.
                result = self.client.generate(self._prompt(task, state, previous_result), tools, state.history)
            except KeyboardInterrupt:
                self.cancel_event.set()
                return self._cancelled(task_id, task, state) or "Task cancelled."
            except Exception as exc:
                err = normalize_exception(exc, operation="agent model request")
                self._save(task_id, task, "failed", state)
                log.error("model request failed error_id=%s", err.error_id, exc_info=True)
                return f"{err.public_message} (error_id={err.error_id}, task_id={task_id})"

            if not isinstance(result, dict):
                err = AgentError("INVALID_MODEL_RESPONSE", "Model client returned a non-object", "The AI service returned an invalid response.", False, 502)
                self._save(task_id, task, "failed", state)
                return f"{err.public_message} (error_id={err.error_id}, task_id={task_id})"
            state.add("assistant", {"text": result.get("text", ""), "tool_calls": result.get("tool_calls", [])})
            if result.get("type") == "error":
                text = str(result.get("text") or "The model request failed.")
                self._save(task_id, task, "failed", state)
                self.output(safe_text(text))
                return text
            if result.get("type") == "cancelled" or self.cancel_event.is_set():
                return self._cancelled(task_id, task, state) or "Task cancelled."
            calls = result.get("tool_calls", [])
            if result.get("type") == "text" or not calls:
                text = str(result.get("text", "")).strip() or "I could not produce a useful final summary."
                self._save(task_id, task, "completed", state)
                self.memory.save("completed_task", {"task": task, "summary": text})
                return text

            if not isinstance(calls, list):
                err = AgentError("INVALID_MODEL_RESPONSE", "Model tool_calls must be a list", "The AI service returned invalid tool calls.", False, 502)
                self._save(task_id, task, "failed", state)
                return f"{err.public_message} (error_id={err.error_id}, task_id={task_id})"
            tool_results = []
            for call in calls:
                cancelled = self._cancelled(task_id, task, state)
                if cancelled:
                    return cancelled
                if not isinstance(call, dict):
                    tool_results.append({"error": "Invalid tool call", "code": "INVALID_TOOL_CALL"})
                    continue
                key = self._call_key(call)
                recent_calls = (recent_calls + [key])[-4:]
                if len(recent_calls) >= 3 and len(set(recent_calls[-3:])) == 1:
                    message = {"error": "The same tool call was requested repeatedly without progress. Choose a different safe approach or explain the blocker.", "code": "NO_PROGRESS"}
                    self.output(safe_text(self.ui.result("recovery", message, 0)))
                    tool_results.append(message)
                    continue
                name, args = call.get("name", ""), call.get("args", {})
                self.output(safe_text(self.ui.start(name, args)))
                started = time.perf_counter()
                try:
                    tool_result = self.execute(name, args)
                except KeyboardInterrupt:
                    self.cancel_event.set()
                    return self._cancelled(task_id, task, state) or "Task cancelled."
                tool_result = safe_value(tool_result)
                self.output(safe_text(self.ui.result(name, tool_result, (time.perf_counter() - started) * 1000)))
                if name in {"find_alternatives", "verify_tool", "install_and_verify", "search_web"}:
                    self.memory.save("tool_outcome", {"tool": name, "args": redact_secrets(json.dumps(args, ensure_ascii=False)), "result": tool_result})
                result_key = json.dumps(tool_result, sort_keys=True, ensure_ascii=False, default=str)
                if result_key in seen_results:
                    compact_result = {"deduplicated": True, "same_as": seen_results[result_key], "note": "identical result already present in recent context"}
                    tool_results.append(compact_result)
                    state.add("tool", {"tool": name, "args": args, "result": compact_result})
                else:
                    seen_results[result_key] = name
                    state.add("tool", {"tool": name, "args": args, "result": tool_result})
                    tool_results.append(tool_result)

            previous_result = json.dumps(safe_value(tool_results), ensure_ascii=False, default=str)[:settings.max_tool_result_chars]
            self._save(task_id, task, "running", state)

        self._save(task_id, task, "paused", state)
        return f"Task paused at step limit. Resume with task_id={task_id}."

    def resume(self, task_id: str) -> str:
        return self.run("", task_id=task_id)
