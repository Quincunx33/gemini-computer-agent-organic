from __future__ import annotations

import threading
import time
from typing import Any


class TaskController:
    def __init__(self, loop):
        self.loop = loop
        self.thread: threading.Thread | None = None
        self.result: str | None = None
        self.started_at: float | None = None
        self.status = "idle"
        self._pause = threading.Event()

    def start(self, task: str) -> dict[str, Any]:
        if self.thread and self.thread.is_alive():
            return {"ok": False, "error": "A task is already running", "status": self.status}
        self.result = None
        self.started_at = time.time()
        self.status = "running"
        self.thread = threading.Thread(target=self._run, args=(task,), daemon=True)
        self.thread.start()
        return {"ok": True, "status": self.status}

    def _run(self, task: str) -> None:
        try:
            self.result = self.loop.run(task)
            self.status = "cancelled" if "cancelled" in self.result.lower() else "completed"
        except Exception as exc:
            self.result = str(exc)
            self.status = "failed"

    def cancel(self) -> dict[str, Any]:
        self.loop.cancel()
        self.status = "cancelling" if self.thread and self.thread.is_alive() else "cancelled"
        return self.status_info()

    def pause(self) -> dict[str, Any]:
        self._pause.set()
        return {"ok": False, "status": self.status, "message": "Pause is cooperative and will take effect at the next safe boundary."}

    def resume(self) -> dict[str, Any]:
        self._pause.clear()
        return self.status_info()

    def status_info(self) -> dict[str, Any]:
        return {"status": self.status, "result": self.result, "started_at": self.started_at, "running": bool(self.thread and self.thread.is_alive())}
