"""Autonomous background task scheduler / heartbeat runner."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from agent_loop import AgentLoop
from config import settings
from logger import get_logger

log = get_logger("genagent.autonomous")

class AutonomousDaemon:
    def __init__(self, task_file: Path | None = None, interval_seconds: int = 30):
        self.task_file = task_file or (settings.workspace / "tasks_queue.json")
        self.interval = interval_seconds
        self.loop = AgentLoop(non_interactive=True)

    def run_pending_tasks(self) -> None:
        if not self.task_file.exists():
            return
        try:
            data = json.loads(self.task_file.read_text(encoding="utf-8"))
        except Exception as exc:
            log.warning("Could not read task file: %s", exc)
            return

        if not isinstance(data, list):
            return

        unprocessed = []
        for item in data:
            if isinstance(item, dict) and item.get("status") == "pending":
                task_id = item.get("id", "autotask")
                prompt = item.get("task", "")
                print(f"[AUTONOMOUS DAEMON] Executing task: {prompt}")
                item["status"] = "in_progress"
                item["started_at"] = time.time()
                try:
                    result = self.loop.run(prompt)
                    item["status"] = "completed"
                    item["result"] = result
                except Exception as exc:
                    item["status"] = "failed"
                    item["error"] = str(exc)
                item["finished_at"] = time.time()
            unprocessed.append(item)

        self.task_file.write_text(json.dumps(unprocessed, indent=2, ensure_ascii=False), encoding="utf-8")

    def start(self, once: bool = False) -> None:
        print(f"[AUTONOMOUS DAEMON] Started. Monitoring {self.task_file} (interval: {self.interval}s)")
        while True:
            self.run_pending_tasks()
            if once:
                break
            time.sleep(self.interval)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Autonomous daemon for genagent")
    parser.add_argument("--once", action="store_true", help="Run pending tasks once and exit")
    parser.add_argument("--interval", type=int, default=15, help="Polling interval in seconds")
    args = parser.parse_args()
    daemon = AutonomousDaemon(interval_seconds=args.interval)
    daemon.start(once=args.once)
