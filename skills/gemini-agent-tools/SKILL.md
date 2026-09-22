---
name: gemini-agent-tools
description: Extend or use the Gemini computer agent tool layer. Use when adding terminal, filesystem, Git, verification, browser, or other action tools.
---

# Gemini Agent Tools

## Missing tool protocol — NEVER cancel the task

When a tool or command is not found, follow this exact order:

### Step 1 — Detect environment and install
Call `find_alternatives` with the missing tool name.
If `install_available` is true, run the `install_command` shown.
Ask user approval for the install command before running it.

Package managers by environment:
- Alpine / iSH → `apk add <package>`
- Debian / Ubuntu / Cloud Shell → `apt-get install -y <package>`
- macOS → `brew install <package>`
- Any Python tool → `pip install <package>`

### Step 2 — Use stdlib fallback
Only if install fails or is not available.
Use the `stdlib_fallback` returned by `find_alternatives`.

Common stdlib workarounds:

**git clone not available:**
```python
import urllib.request, zipfile, io
url = "https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read()))
z.extractall(".")
```

**curl/wget not available:**
```python
import urllib.request
data = urllib.request.urlopen(url).read()
```

**HTTP server:**
```python
import http.server, socketserver, threading
httpd = socketserver.TCPServer(("", 8080), http.server.SimpleHTTPRequestHandler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
```

### Step 3 — Report clearly
If both install and stdlib fail, explain exactly:
- What was tried
- What failed and why
- What the user can do next

**Task cancellation is never acceptable.**

## Adding a new tool

1. Implement in `tools/<name>.py`.
2. Validate paths and argument sizes before side effects.
3. Add declaration to `planner.py`.
4. Route in `AgentLoop.execute`.
5. Return a dict with predictable keys; include `error` instead of a traceback.
6. Add a `unittest` test.

## Existing core tools

- `run_command`: bounded shell execution with risk confirmation.
- `read_file` / `write_file` / `list_directory`: workspace-confined file ops.
- `verify_python`: syntax check without external packages.
- `self_update`: atomic source update with backup and rollback.
- `platform_info`: report actual host and capabilities.
- `find_alternatives`: get install command and stdlib fallback for missing tools.
- `open_app`: open a URL, file, or application via host launcher.
- `list_processes` / `terminate_process`: process inspection and control.
