from __future__ import annotations

import json
from typing import Any

from config import settings
from gemini_client import GeminiClient
from memory import Memory
from planner import TOOLS
from state import AgentState
from task_store import TaskStore
from tools.terminal import run_command
from tools.filesystem import read_file, write_file, list_directory
from tools.verification import verify_python
from tools.control import platform_info, open_app, list_processes, terminate_process
from tools.gui_control import gui_capabilities, screenshot, ocr, mouse_click, type_text, press_key
from tools.self_update import self_update
from text_safety import safe_text, safe_value


class AgentLoop:
    """Bounded observe-plan-act-verify loop with continuity and recovery.

    The model decides the next useful action, while this class owns state,
    safety boundaries, progress detection, persistence, and user-visible
    summaries. No hidden chain-of-thought is stored or displayed.
    """

    def __init__(self, client=None, output=print, store=None, memory=None):
        self.client = client or GeminiClient()
        self.output = output
        self.store = store or TaskStore(settings.db_path)
        self.memory = memory or Memory()
        self.last_task_id: str | None = None

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        from permissions import classify_command, Risk

        # Determine if we should ask for confirmation based on action risk
        requires_confirm = True
        if name in ["list_directory", "read_file", "platform_info", "gui_capabilities"]:
            requires_confirm = False
        elif name == "run_command":
            cmd_risk = classify_command(args.get("command", ""))
            if cmd_risk == Risk.NORMAL:
                requires_confirm = False

        if requires_confirm:
            print(safe_text(f"\n[PERMISSION REQUIRED] The agent wants to execute tool: '{name}' with arguments: {args}"))
            confirm = input("Allow execution? [y/N]: ").strip().lower()
            if confirm not in ['y', 'yes']:
                print(safe_text(f"Execution of '{name}' was denied by the user."))
                return {"error": f"Permission denied by user for tool: {name}"}
        else:
            # Quietly notify user of automatic tool execution
            print(safe_text(f"\n[AUTO-EXECUTING] Running tool '{name}'..."))

        if name == "run_command": return run_command(command=args.get("command"), cwd=args.get("cwd"), timeout=args.get("timeout"), approved=not requires_confirm)
        if name == "read_file": return {"content": read_file(args["path"])}
        if name == "write_file": return {"written": write_file(args["path"], args["content"])}
        if name == "self_update": return self_update(args["path"], args["content"])
        if name == "list_directory": return {"files": list_directory(args.get("path", "."))}
        if name == "verify_python": return verify_python(args["path"])
        if name == "platform_info": return platform_info()
        if name == "open_app": return open_app(args["target"])
        if name == "list_processes": return list_processes()
        if name == "terminate_process": return terminate_process(args["pid"])
        if name == "gui_capabilities": return gui_capabilities()
        if name == "screenshot": return screenshot(args.get("path", "screen.png"))
        if name == "ocr": return ocr(args["path"])
        if name == "mouse_click": return mouse_click(args["x"], args["y"], args.get("clicks", 1))
        if name == "type_text": return type_text(args["text"])
        if name == "press_key": return press_key(args["key"])
        return {"error": f"Unknown tool: {name}"}

    @staticmethod
    def _call_key(call: dict[str, Any]) -> str:
        return json.dumps(
            {"name": call.get("name"), "args": call.get("args", {})},
            sort_keys=True,
            ensure_ascii=False,
        )

    def _prompt(self, task: str, state: AgentState, previous_result: str | None = None) -> str:
        memory_context = self.memory.context(task)
        progress = previous_result or "No tool has been used yet. Start by understanding the request."
        return f"""You are operating as a thoughtful, grounded local computer assistant.

User request:
{task}

Workspace:
{settings.workspace}

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

    def run(self, task: str, task_id: str | None = None) -> str:
        if task_id:
            saved = self.store.load(task_id)
            if not saved:
                return f"Task not found: {task_id}"
            state = AgentState(task=saved["task"], step=saved["step"], history=saved["history"])
            task = saved["task"]
        else:
            state = AgentState(task=task)
            task_id = self.store.create(task)
        self.last_task_id = task_id

        previous_result: str | None = None
        recent_calls: list[str] = []
        for _ in range(settings.max_agent_steps):
            state.step += 1
            prompt = self._prompt(task, state, previous_result)
            try:
                result = self.client.generate(prompt, TOOLS, state.history)
            except Exception as exc:
                self.store.save(task_id, task, "failed", state.step, state.history)
                return f"Agent error (task {task_id}): {exc}"

            state.add("assistant", {"text": result.get("text", ""), "tool_calls": result.get("tool_calls", [])})
            calls = result.get("tool_calls", [])
            if result.get("type") == "text" or not calls:
                text = result.get("text", "").strip() or "I could not produce a useful final summary."
                self.output(text)
                failure = text.startswith("All configured Gemini models failed") or text.startswith("Gemini is not configured")
                status = "failed" if failure else "completed"
                self.store.save(task_id, task, status, state.step, state.history)
                if not failure:
                    self.memory.save("completed_task", {"task": task, "summary": text})
                return text

            tool_results = []
            for call in calls:
                key = self._call_key(call)
                recent_calls.append(key)
                recent_calls = recent_calls[-4:]
                if len(recent_calls) >= 3 and len(set(recent_calls[-3:])) == 1:
                    message = {"error": "The same tool call was requested repeatedly without progress. Choose a different safe approach or explain the blocker."}
                    self.output(safe_text(f"[RESULT] {message}"))
                    tool_results.append(message)
                    continue
                name, args = call.get("name", ""), call.get("args", {})
                self.output(safe_text(f"[TOOL] {name} {args}"))
                try:
                    tool_result = self.execute(name, args)
                except Exception as exc:
                    tool_result = {"error": str(exc)}
                tool_result = safe_value(tool_result)
                self.output(safe_text(f"[RESULT] {str(tool_result)[:1000]}"))
                state.add("tool", {"tool": name, "args": args, "result": tool_result})
                tool_results.append(tool_result)

            previous_result = json.dumps(safe_value(tool_results), ensure_ascii=False, default=str)[:12000]
            self.store.save(task_id, task, "running", state.step, state.history)

        self.store.save(task_id, task, "paused", state.step, state.history)
        return f"Task paused at step limit. Resume with task_id={task_id}."

    def resume(self, task_id: str) -> str:
        return self.run("", task_id=task_id)
