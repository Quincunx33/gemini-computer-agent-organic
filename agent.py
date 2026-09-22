#!/usr/bin/env python3
import os
from text_safety import configure_terminal
from config import settings
from agent_loop import AgentLoop
from memory import Memory
from platform_support import detect

# Terminal colors for user-friendly UI
BLUE = "\033[94m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"

def main() -> None:
    # Subprocess and API boundaries on iPadOS/macOS can return lone UTF-16
    # surrogates. Configure the CLI before the first print so they cannot
    # terminate the interactive session.
    configure_terminal()
    memory = Memory()
    os.system("clear" if os.name != "nt" else "cls")
    print(f"{BLUE}{BOLD}" + "="*60 + f"{RESET}")
    print(f"{GREEN}{BOLD}    🤖 GEMINI COMPUTER AGENT - Grounded Local Assistant 🤖{RESET}")
    print(f"{BLUE}{BOLD}" + "="*60 + f"{RESET}")
    print(f"{BOLD}Model:{RESET} {YELLOW}{settings.gemini_model}{RESET}  |  {BOLD}Workspace:{RESET} {YELLOW}{settings.workspace}{RESET}")
    print(f"{BOLD}Type {GREEN}/help{RESET} for commands or {RED}/exit{RESET} to quit.")
    print(f"{BLUE}{BOLD}" + "-"*60 + f"{RESET}\n")

    loop = AgentLoop(output=print, memory=memory)
    while True:
        try:
            text = input(f"{GREEN}{BOLD}You ❯{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if not text:
            continue
        if text == "/exit":
            print(f"{RED}Exiting agent loop. Goodbye!{RESET}")
            break
        if text == "/help":
            print(f"\n{BOLD}💡 Available Assistant Commands:{RESET}")
            print(f"  {GREEN}/status{RESET}      - View model, workspace, and config details")
            print(f"  {GREEN}/tools{RESET}       - List all available automation tools")
            print(f"  {GREEN}/model{RESET}       - Show current active model")
            print(f"  {GREEN}/workspace{RESET}   - Show working workspace directory")
            print(f"  {GREEN}/clear-memory{RESET} - Flush agent memory")
            print(f"  {GREEN}/exit{RESET}        - Quit the program\n")
            continue
        if text == "/status":
            info = detect()
            print(f"{YELLOW}[STATUS]{RESET} Model: {settings.gemini_model} | Steps: {settings.max_agent_steps} | Platform: {info.profile} | Shell: {info.shell_family}")
            continue
        if text == "/model":
            print(f"{YELLOW}[MODEL]{RESET} {settings.gemini_model}")
            continue
        if text == "/workspace":
            print(f"{YELLOW}[WORKSPACE]{RESET} {settings.workspace}")
            continue
        if text == "/tools":
            print(f"{YELLOW}[TOOLS]{RESET} run_command, read_file, write_file, self_update, list_directory, verify_python, platform_info, open_app, list_processes, terminate_process, gui_capabilities, screenshot, ocr, mouse_click, type_text, press_key")
            continue
        if text == "/clear-memory":
            memory.clear()
            print(f"{RED}[MEMORY]{RESET} Agent memory cleared successfully.")
            continue

        print(f"\n{BLUE}⚡ Thinking... Please wait.{RESET}")
        try:
            response = loop.run(text)
            print(f"\n{BLUE}{BOLD}Agent ❯{RESET} {response}\n")
        except Exception as e:
            print(f"\n{RED}[ERROR] An error occurred: {e}{RESET}\n")

if __name__ == "__main__":
    main()
