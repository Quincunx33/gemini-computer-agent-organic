#!/usr/bin/env python3
from config import settings
from agent_loop import AgentLoop
from memory import Memory


def main() -> None:
    memory = Memory()
    print("=" * 64)
    print("GEMINI COMPUTER AGENT - Grounded Local AI Assistant")
    print(f"Model: {settings.gemini_model}  Workspace: {settings.workspace}")
    print("Type /help for commands or /exit to quit.")
    loop = AgentLoop(output=print, memory=memory)
    while True:
        try:
            text = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/exit":
            break
        if text == "/help":
            print("/status /tools /model /workspace /permissions /memory /clear-memory /tasks /resume TASK_ID /exit")
            continue
        if text == "/status":
            print({"model": settings.gemini_model, "workspace": str(settings.workspace), "steps": settings.max_agent_steps})
            continue
        if text == "/model":
            print(settings.gemini_model)
            continue
        if text == "/workspace":
            print(settings.workspace)
            continue
        if text == "/tools":
            print("run_command, read_file, write_file, self_update, list_directory, verify_python, platform_info, open_app, list_processes, terminate_process, gui_capabilities, screenshot, ocr, mouse_click, type_text, press_key")
            continue
        if text == "/permissions":
            print("normal/low_risk run automatically; privileged/destructive require exact-command confirmation")
            continue
        if text == "/memory":
            print(memory.recent())
            continue
        if text == "/clear-memory":
            memory.clear()
            print("Memory cleared.")
            continue
        if text == "/tasks":
            print(memory.recent())
            latest = loop.store.latest()
            print({"latest_task": latest and {"task_id": latest["task_id"], "status": latest["status"], "step": latest["step"]}})
            continue
        if text.startswith("/resume "):
            loop.resume(text.split(None, 1)[1].strip())
            continue
        memory.save("user_task", text)
        loop.run(text)


if __name__ == "__main__":
    main()
