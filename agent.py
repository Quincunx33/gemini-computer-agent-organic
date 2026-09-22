#!/usr/bin/env python3
"""Interactive terminal entrypoint for genagent."""
import os

from text_safety import configure_terminal
from config import settings
from agent_loop import AgentLoop
from memory import Memory
from platform_support import detect
from ui import EventRenderer, format_response


class Console:
    """Small standard-library-only terminal presentation layer."""

    def __init__(self):
        self.ui = EventRenderer(color=True)
        self.enabled = self.ui.theme.enabled
        self.t = self.ui.theme

    def c(self, color: str, text: str) -> str:
        return self.t.paint(color, text)

    def width(self) -> int:
        try:
            return max(56, min(100, os.get_terminal_size().columns))
        except OSError:
            return 72

    def fit(self, value: str, limit: int | None = None) -> str:
        """Keep long paths and labels on one mobile-terminal line."""
        limit = limit or max(28, self.width() - 16)
        value = str(value)
        if len(value) <= limit:
            return value
        return "..." + value[-(limit - 3):]

    def clear(self) -> None:
        if os.getenv("NO_CLEAR") is None:
            print("\033[2J\033[H", end="")

    def header(self) -> None:
        width = self.width()
        line = "-" * width
        # Plain ASCII borders render consistently in iOS, Android and basic shells.
        print(self.c(self.t.blue, "+" + line + "+"))
        title = " GENAGENT  /  GROUNDED LOCAL ASSISTANT "
        print(self.c(self.t.blue, "|") + self.c(self.t.bold + self.t.cyan, title.center(width)) + self.c(self.t.blue, "|"))
        print(self.c(self.t.blue, "+" + line + "+"))
        print(f"  {self.c(self.t.gray, 'Model')}     {self.c(self.t.yellow, settings.gemini_model)}")
        print(f"  {self.c(self.t.gray, 'Workspace')} {self.c(self.t.yellow, self.fit(settings.workspace, min(48, width - 20)))}")
        print(f"  {self.c(self.t.gray, 'Mode')}      {self.c(self.t.green, settings.autonomy_mode)}  {self.c(self.t.gray, '- type /help for commands')}")
        print()

    def help(self) -> None:
        print(self.ui.divider())
        print(self.c(self.t.bold + self.t.cyan, "  COMMANDS"))
        rows = [
            ("/status", "Show model, mode, platform and step limits"),
            ("/tools", "List available automation tools"),
            ("/model", "Show active model"),
            ("/workspace", "Show current workspace"),
            ("/approvals", "Show protected-action approvals"),
            ("/clear-memory", "Clear saved task memory"),
            ("/debug on|off", "Toggle structured developer events"),
            ("/cancel", "Stop the current task safely"),
            ("/exit", "Close the agent"),
        ]
        for command, description in rows:
            print(f"  {self.c(self.t.green, command):<24} {self.c(self.t.gray, description)}")
        print(self.ui.divider())


def main() -> None:
    configure_terminal()
    console = Console()
    memory = Memory()
    console.clear()
    console.header()
    loop = AgentLoop(output=print, memory=memory, debug=settings.debug_mode)

    while True:
        try:
            text = input(f"{console.c(console.t.green, '  You')} {console.c(console.t.cyan, '>')} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{console.c(console.t.gray, 'Session closed.')}")
            break
        if not text:
            continue
        if text == "/exit":
            print(f"{console.c(console.t.gray, 'Session closed. Goodbye.')}")
            break
        if text == "/help":
            console.help()
            continue
        if text == "/status":
            info = detect()
            print(console.ui.divider())
            print(f"  {console.c(console.t.cyan, 'STATUS')}")
            print(f"  Model      {settings.gemini_model}")
            print(f"  Mode       {settings.autonomy_mode}")
            print(f"  Steps      {settings.max_agent_steps}")
            print(f"  Platform   {info.profile}  ·  {info.shell_family}")
            print(f"  Debug      {'on' if loop.ui.debug else 'off'}")
            print(console.ui.divider())
            continue
        if text == "/model":
            print(f"  {console.c(console.t.cyan, 'MODEL')}  {settings.gemini_model}")
            continue
        if text == "/workspace":
            print(f"  {console.c(console.t.cyan, 'WORKSPACE')}  {settings.workspace}")
            continue
        if text == "/tools":
            print(f"  {console.c(console.t.cyan, 'TOOLS')}  run_command, read_file, write_file, create_file, move_file, delete_file, verify_python, verify_project, git_checkpoint, list_directory, platform_info, search_web, parallel_analysis")
            continue
        if text == "/clear-memory":
            memory.clear()
            print(f"  {console.c(console.t.green, '✓')} Memory cleared")
            continue
        if text == "/cancel":
            loop.cancel()
            print(f"  {console.c(console.t.yellow, '⚠')} Current task will stop at the next safe boundary")
            continue
        if text == "/approvals":
            print(f"  {console.c(console.t.cyan, 'APPROVALS')}  {loop.approvals.list()}")
            continue
        if text.startswith("/debug"):
            parts = text.split(maxsplit=1)
            if len(parts) == 1:
                print(f"  {console.c(console.t.cyan, 'DEBUG')}  {'on' if loop.ui.debug else 'off'}")
            else:
                enabled = parts[1].strip().lower() in {"on", "true", "1", "yes"}
                loop.ui.set_debug(enabled)
                print(f"  {console.c(console.t.cyan, 'DEBUG')}  {'on' if enabled else 'off'}")
            continue

        print(f"\n{console.ui.divider()}")
        print(f"  {console.c(console.t.cyan, 'TASK')}  {text[:160]}")
        try:
            response = loop.run(text)
            print(f"\n{console.ui.divider()}")
            clean_response = format_response(response)
            print(f"  {console.c(console.t.bold + console.t.green, 'AGENT')}")
            print("  " + clean_response.replace("\n", "\n  "))
            print()
        except Exception as exc:
            print(f"\n  {console.c(console.t.red, '✕ Error')}  {exc}\n")


if __name__ == "__main__":
    main()
