from __future__ import annotations

import json
from typing import Any

from config import settings
from errors import AgentError, error_text, normalize_exception, traceback_text
from gemini_client import GeminiClient
from logger import get_logger
from memory import Memory
from planner import tools_for_task
from state import AgentState
from task_store import TaskStore
from tools.terminal import run_command
from tools.filesystem import read_file, write_file, list_directory
from tools.verification import verify_python
from tools.control import platform_info, open_app, list_processes, terminate_process
from tools.gui_control import gui_capabilities, screenshot, ocr, mouse_click, type_text, press_key
from tools.self_update import self_update
from text_safety import safe_text, safe_value
from platform_support import command_environment, detect as detect_platform, supported_tool_names, tool_support


log = get_logger("genagent.loop")


class AgentLoop:
    """Bounded observe-plan-act-verify loop with recoverable failure boundaries."""

    def __init__(self, client=None, output=print, store=None, memory=None):
        self.client = client or GeminiClient()
        self.output = output
        self.store = store or TaskStore(settings.db_path)
        self.memory = memory or Memory()
        self.last_task_id: str | None = None

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
        supported, reason = tool_support(name)
        if not supported:
            return {"error": f"Tool '{name}' is unavailable on this platform: {reason}", "code": "UNSUPPORTED_PLATFORM", "platform": detect_platform().profile}

        requires_confirm = settings.require_confirmation
        if name in {"list_directory", "read_file", "platform_info", "gui_capabilities"}:
            requires_confirm = False
        elif name == "run_command" and classify_command(str(args.get("command", ""))) == Risk.NORMAL:
            requires_confirm = False

        if requires_confirm:
            self.output(safe_text(f"\n[PERMISSION REQUIRED] The agent wants to execute tool: '{name}' with arguments: {args}"))
            try:
                confirm = input("Allow execution? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt) as exc:
                raise AgentError("CONFIRMATION_UNAVAILABLE", "User confirmation was interrupted", "User confirmation was not available.", False, 409) from exc
            if confirm not in {"y", "yes"}:
                return {"error": "Permission denied by user for tool: " + name, "code": "PERMISSION_DENIED"}
        else:
            self.output(safe_text(f"\n[AUTO-EXECUTING] Running tool '{name}'..."))

        dispatch: dict[str, Any] = {
            "run_command": lambda: run_command(command=args.get("command"), cwd=args.get("cwd"), timeout=args.get("timeout"), approved=not requires_confirm),
            "read_file": lambda: {"content": read_file(args["path"])},
            "write_file": lambda: {"written": write_file(args["path"], args["content"])},
            "self_update": lambda: self_update(args["path"], args["content"]),
            "list_directory": lambda: {"files": list_directory(args.get("path", "."))},
            "verify_python": lambda: verify_python(args["path"]),
            "platform_info": platform_info,
            "open_app": lambda: open_app(args["target"]),
            "list_processes": list_processes,
            "terminate_process": lambda: terminate_process(args["pid"]),
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
        prompt = f"""You are operating as a thoughtful, grounded local computer assistant.

User request:
{task}

Workspace:
{settings.workspace}

Execution platform (authoritative; never assume another OS):
{platform_context}

Relevant prior memory (optional hints; verify anything important):
{memory_context}

Latest progress:
{progress}

Working contract:
- Understand the user's actual intent before acting; ask for clarification only when a missing choice would materially change the result.
- Choose the smallest useful next action. Do not call tools merely to appear busy.
- For multi-step work, keep a quiet working plan and move through observe -> act -> verify.
- After every change, inspect or verify the result. If something fails, diagnose and recover safely instead of repeating blindly.
- Respect tool permissions and never attempt to obtain, expose, or store secrets.
- When the work is complete, respond in natural language with what happened, what was verified, and any user action still needed.
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
        self._platform_info = detect_platform()
        tools = tools_for_task(task, settings.task_tool_filtering, self._platform_info)
        if isinstance(self.client, GeminiClient):
            self.client.set_task_route(task)

        previous_result: str | None = None
        recent_calls: list[str] = []
        seen_results: dict[str, str] = {}
        for _ in range(settings.max_agent_steps):
            state.step += 1
            try:
                result = self.client.generate(self._prompt(task, state, previous_result), tools, state.history)
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
            calls = result.get("tool_calls", [])
            if result.get("type") == "text" or not calls:
                text = str(result.get("text", "")).strip() or "I could not produce a useful final summary."
                self.output(text)
                self._save(task_id, task, "completed", state)
                self.memory.save("completed_task", {"task": task, "summary": text})
                return text

            if not isinstance(calls, list):
                err = AgentError("INVALID_MODEL_RESPONSE", "Model tool_calls must be a list", "The AI service returned invalid tool calls.", False, 502)
                self._save(task_id, task, "failed", state)
                return f"{err.public_message} (error_id={err.error_id}, task_id={task_id})"
            tool_results = []
            for call in calls:
                if not isinstance(call, dict):
                    tool_results.append({"error": "Invalid tool call", "code": "INVALID_TOOL_CALL"})
                    continue
                key = self._call_key(call)
                recent_calls = (recent_calls + [key])[-4:]
                if len(recent_calls) >= 3 and len(set(recent_calls[-3:])) == 1:
                    message = {"error": "The same tool call was requested repeatedly without progress. Choose a different safe approach or explain the blocker.", "code": "NO_PROGRESS"}
                    self.output(safe_text(f"[RESULT] {message}"))
                    tool_results.append(message)
                    continue
                name, args = call.get("name", ""), call.get("args", {})
                self.output(safe_text(f"[TOOL] {name} {args}"))
                tool_result = self.execute(name, args)
                tool_result = safe_value(tool_result)
                self.output(safe_text(f"[RESULT] {str(tool_result)[:1000]}"))
                result_key = json.dumps(tool_result, sort_keys=True, ensure_ascii=False, default=str)
                if result_key in seen_results:
                    compact_result = {"deduplicated": True, "same_as": seen_results[result_key], "note": "identical result already present in recent context"}
                    tool_results.append(compact_result)
                    state.add("tool", {"tool": name, "args": args, "result": compact_result})
                else:
                    seen_results[result_key] = name
                    state.add("tool", {"tool": name, "args": args, "result": tool_result})
                    tool_results.append(tool_result)

            previous_result = json.dumps(safe_value(tool_results), ensure_ascii=False, default=str)[:12000]
            self._save(task_id, task, "running", state)

        self._save(task_id, task, "paused", state)
        return f"Task paused at step limit. Resume with task_id={task_id}."

    def resume(self, task_id: str) -> str:
        return self.run("", task_id=task_id)
