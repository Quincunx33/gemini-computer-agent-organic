from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from agent_loop import AgentLoop
from permissions import Risk, classify_command


class ReadOnlyAgentLoop(AgentLoop):
    _BLOCKED = {"write_file", "patch_file", "create_file", "move_file", "delete_file", "self_update", "open_app", "terminate_process", "mouse_click", "type_text", "press_key"}

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name in self._BLOCKED:
            return {"error": f"read-only sub-agent cannot use {name}", "code": "READ_ONLY_SUBAGENT"}
        if name == "run_command" and classify_command(str(args.get("command", ""))) != Risk.NORMAL:
            return {"error": "read-only sub-agent only permits normal commands", "code": "READ_ONLY_SUBAGENT"}
        return super().execute(name, args)


def run_parallel(tasks: list[str], max_workers: int = 3) -> dict[str, Any]:
    tasks = [str(task).strip() for task in tasks if str(task).strip()]
    if not tasks:
        return {"ok": False, "error": "tasks are required", "results": []}
    tasks = tasks[:8]
    workers = max(1, min(int(max_workers), len(tasks), 4))
    results: list[dict[str, Any] | None] = [None] * len(tasks)

    def run_one(index: int, task: str) -> dict[str, Any]:
        from gemini_client import GeminiClient
        from config import settings
        fast_client = GeminiClient(model=settings.fast_model)
        loop = ReadOnlyAgentLoop(client=fast_client, output=lambda _event: None)
        try:
            return {"index": index, "task": task, "ok": True, "summary": loop.run("Read-only analysis only: " + task)}
        except Exception as exc:
            return {"index": index, "task": task, "ok": False, "error": type(exc).__name__}

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="genagent-subagent") as pool:
        futures = [pool.submit(run_one, index, task) for index, task in enumerate(tasks)]
        for future in as_completed(futures):
            result = future.result()
            results[result["index"]] = result
    return {"ok": True, "count": len(tasks), "results": results}
