from __future__ import annotations

import importlib.util
import shlex
import shutil
import subprocess
from typing import Any
from config import settings


# Known install commands: tool → {package_manager: command}
# None means this PM cannot install this tool.
_INSTALL_COMMANDS: dict[str, dict[str, str | None]] = {
    "git":         {"apk": "apk add git",          "apt": "apt-get install -y git",                   "brew": "brew install git",        "dnf": "dnf install -y git",    "yum": "yum install -y git",    "pip": None},
    "curl":        {"apk": "apk add curl",          "apt": "apt-get install -y curl",                  "brew": "brew install curl",       "dnf": "dnf install -y curl",   "yum": "yum install -y curl",   "pip": None},
    "wget":        {"apk": "apk add wget",          "apt": "apt-get install -y wget",                  "brew": "brew install wget",       "dnf": "dnf install -y wget",   "yum": "yum install -y wget",   "pip": None},
    "ffmpeg":      {"apk": "apk add ffmpeg",        "apt": "apt-get install -y ffmpeg",                "brew": "brew install ffmpeg",     "dnf": "dnf install -y ffmpeg", "yum": "yum install -y ffmpeg", "pip": None},
    "tesseract":   {"apk": "apk add tesseract-ocr", "apt": "apt-get install -y tesseract-ocr",         "brew": "brew install tesseract",  "dnf": "dnf install -y tesseract", "pip": None},
    "exiftool":    {"apk": "apk add exiftool",      "apt": "apt-get install -y libimage-exiftool-perl","brew": "brew install exiftool",   "pip": "pip install pyexiftool"},
    "jq":          {"apk": "apk add jq",            "apt": "apt-get install -y jq",                    "brew": "brew install jq",         "dnf": "dnf install -y jq",     "yum": "yum install -y jq",     "pip": None},
    "node":        {"apk": "apk add nodejs npm",    "apt": "apt-get install -y nodejs npm",            "brew": "brew install node",       "dnf": "dnf install -y nodejs", "pip": None},
    "nodejs":      {"apk": "apk add nodejs",        "apt": "apt-get install -y nodejs",                "brew": "brew install node",       "dnf": "dnf install -y nodejs", "pip": None},
    "npm":         {"apk": "apk add npm",           "apt": "apt-get install -y npm",                   "brew": "brew install node",       "pip": None},
    "python3":     {"apk": "apk add python3",       "apt": "apt-get install -y python3",               "brew": "brew install python",     "pip": None},
    "pip":         {"apk": "apk add py3-pip",       "apt": "apt-get install -y python3-pip",           "brew": "brew install python",     "pip": None},
    "rsync":       {"apk": "apk add rsync",         "apt": "apt-get install -y rsync",                 "brew": "brew install rsync",      "pip": None},
    "zip":         {"apk": "apk add zip",           "apt": "apt-get install -y zip",                   "brew": "brew install zip",        "pip": None},
    "unzip":       {"apk": "apk add unzip",         "apt": "apt-get install -y unzip",                 "brew": "brew install unzip",      "pip": None},
    "tar":         {"apk": "apk add tar",           "apt": "apt-get install -y tar",                   "brew": "brew install gnu-tar",    "pip": None},
    "ssh":         {"apk": "apk add openssh",       "apt": "apt-get install -y openssh-client",        "brew": "brew install openssh",    "pip": None},
    "vim":         {"apk": "apk add vim",           "apt": "apt-get install -y vim",                   "brew": "brew install vim",        "pip": None},
    "nano":        {"apk": "apk add nano",          "apt": "apt-get install -y nano",                  "brew": "brew install nano",       "pip": None},
    "htop":        {"apk": "apk add htop",          "apt": "apt-get install -y htop",                  "brew": "brew install htop",       "pip": None},
    "netstat":     {"apk": "apk add net-tools",     "apt": "apt-get install -y net-tools",             "brew": None,                      "pip": None},
    "ss":          {"apk": "apk add iproute2",      "apt": "apt-get install -y iproute2",              "brew": None,                      "pip": None},
    "ip":          {"apk": "apk add iproute2",      "apt": "apt-get install -y iproute2",              "brew": None,                      "pip": None},
    "ping":        {"apk": "apk add iputils",       "apt": "apt-get install -y iputils-ping",          "brew": None,                      "pip": None},
    "nmap":        {"apk": "apk add nmap",          "apt": "apt-get install -y nmap",                  "brew": "brew install nmap",       "pip": None},
    "sqlite3":     {"apk": "apk add sqlite",        "apt": "apt-get install -y sqlite3",               "brew": "brew install sqlite",     "pip": None},
    "mysql":       {"apk": "apk add mysql-client",  "apt": "apt-get install -y mysql-client",          "brew": "brew install mysql",      "pip": None},
    "psql":        {"apk": "apk add postgresql-client","apt":"apt-get install -y postgresql-client",   "brew": "brew install postgresql", "pip": None},
    "docker":      {"apk": "apk add docker",        "apt": "apt-get install -y docker.io",             "brew": "brew install --cask docker","pip": None},
    "make":        {"apk": "apk add make",          "apt": "apt-get install -y make",                  "brew": "brew install make",       "pip": None},
    "gcc":         {"apk": "apk add gcc",           "apt": "apt-get install -y gcc",                   "brew": "brew install gcc",        "pip": None},
    "java":        {"apk": "apk add openjdk17",     "apt": "apt-get install -y default-jdk",           "brew": "brew install openjdk",    "pip": None},
    "ruby":        {"apk": "apk add ruby",          "apt": "apt-get install -y ruby",                  "brew": "brew install ruby",       "pip": None},
    "php":         {"apk": "apk add php",           "apt": "apt-get install -y php",                   "brew": "brew install php",        "pip": None},
    "go":          {"apk": "apk add go",            "apt": "apt-get install -y golang",                "brew": "brew install go",         "pip": None},
    "rust":        {"apk": "apk add rust cargo",    "apt": "apt-get install -y rustc cargo",           "brew": "brew install rust",       "pip": None},
    "rg":          {"apk": "apk add ripgrep",       "apt": "apt-get install -y ripgrep",               "brew": "brew install ripgrep",    "pip": None},
    "ripgrep":     {"apk": "apk add ripgrep",       "apt": "apt-get install -y ripgrep",               "brew": "brew install ripgrep",    "pip": None},
    "fd":          {"apk": "apk add fd",            "apt": "apt-get install -y fd-find",               "brew": "brew install fd",         "pip": None},
    "bat":         {"apk": "apk add bat",           "apt": "apt-get install -y bat",                   "brew": "brew install bat",        "pip": None},
    "yq":          {"apk": "apk add yq",            "apt": "apt-get install -y yq",                    "brew": "brew install yq",         "pip": "pip install yq"},
    "tree":        {"apk": "apk add tree",          "apt": "apt-get install -y tree",                  "brew": "brew install tree",       "pip": None},
    "imagemagick": {"apk": "apk add imagemagick",   "apt": "apt-get install -y imagemagick",           "brew": "brew install imagemagick","pip": None},
    "convert":     {"apk": "apk add imagemagick",   "apt": "apt-get install -y imagemagick",           "brew": "brew install imagemagick","pip": None},
    "pandoc":      {"apk": "apk add pandoc",        "apt": "apt-get install -y pandoc",                "brew": "brew install pandoc",     "pip": None},
}

# Python pip-installable packages (for tools not in system repos)
_PIP_PACKAGES: dict[str, str] = {
    "requests":    "pip install requests",
    "flask":       "pip install flask",
    "fastapi":     "pip install fastapi uvicorn",
    "numpy":       "pip install numpy",
    "pandas":      "pip install pandas",
    "pillow":      "pip install pillow",
    "beautifulsoup4": "pip install beautifulsoup4",
    "scrapy":      "pip install scrapy",
    "playwright":  "pip install playwright && playwright install",
    "selenium":    "pip install selenium",
    "pytest":      "pip install pytest",
    "black":       "pip install black",
    "pyautogui":   "pip install pyautogui",
    "pytesseract": "pip install pytesseract",
    "pyexiftool":  "pip install pyexiftool",
    "httpx":       "pip install httpx",
    "rich":        "pip install rich",
    "typer":       "pip install typer",
}

# stdlib fallbacks — when installation is not possible
_STDLIB_FALLBACKS: dict[str, dict[str, str]] = {
    "git": {
        "name": "urllib ZIP download",
        "how": (
            "import urllib.request, zipfile, io\n"
            "url = 'https://github.com/{owner}/{repo}/archive/refs/heads/main.zip'\n"
            "z = zipfile.ZipFile(io.BytesIO(urllib.request.urlopen(url).read()))\n"
            "z.extractall('.')"
        ),
    },
    "curl": {"name": "urllib.request", "how": "import urllib.request\ndata = urllib.request.urlopen(url).read()"},
    "wget": {"name": "urllib.request", "how": "import urllib.request\nurllib.request.urlretrieve(url, filename)"},
    "rg":   {"name": "grep / python re", "how": "grep -r pattern dir\n# or: import re; re.findall(pattern, text)"},
    "ripgrep": {"name": "grep / python re", "how": "grep -r pattern dir\n# or: import re; re.findall(pattern, text)"},
    "jq":   {"name": "python json", "how": "import json\nobj = json.loads(text)"},
    "yq":   {"name": "python json/configparser", "how": "import json\n# For YAML: pip install pyyaml first"},
    "exiftool": {
        "name": "python struct",
        "how": (
            "import struct\n"
            "with open(path, 'rb') as f: data = f.read()\n"
            "# Find 0xFFE1 for EXIF, parse TIFF header with struct.unpack"
        ),
    },
    "ffmpeg": {"name": "python wave (WAV only)", "how": "import wave\n# For other formats, ffmpeg install is needed"},
    "convert": {"name": "python pillow", "how": "pip install pillow\nfrom PIL import Image\nImage.open(src).save(dst)"},
    "netstat": {"name": "python socket/psutil", "how": "import socket\n# or: pip install psutil"},
    "ip":   {"name": "python socket", "how": "import socket\nsocket.gethostbyname(socket.gethostname())"},
    "ping": {"name": "python socket", "how": "import socket\nsocket.connect((host, 80))"},
    "sqlite3": {"name": "python sqlite3", "how": "import sqlite3\ndb = sqlite3.connect('file.db')"},
    "make": {"name": "python subprocess", "how": "import subprocess\nsubprocess.run(['python3', 'build.py'])"},
    "tree": {"name": "python pathlib", "how": "from pathlib import Path\nlist(Path('.').rglob('*'))"},
    "zip":  {"name": "python zipfile", "how": "import zipfile\nwith zipfile.ZipFile('out.zip','w') as z: z.write(file)"},
    "unzip":{"name": "python zipfile", "how": "import zipfile\nwith zipfile.ZipFile('file.zip') as z: z.extractall('.')"},
    "tar":  {"name": "python tarfile", "how": "import tarfile\nwith tarfile.open('file.tar.gz') as t: t.extractall('.')"},
}


def _detect_package_manager() -> str | None:
    for pm in ("apk", "apt-get", "brew", "dnf", "yum"):
        if shutil.which(pm):
            return pm.replace("apt-get", "apt")
    return None


def _generic_install_cmd(tool: str, pm: str | None) -> str | None:
    """For unknown tools not in _INSTALL_COMMANDS, build a best-guess command."""
    if not pm:
        return None
    pm_map = {
        "apk":  f"apk add {tool}",
        "apt":  f"apt-get install -y {tool}",
        "brew": f"brew install {tool}",
        "dnf":  f"dnf install -y {tool}",
        "yum":  f"yum install -y {tool}",
    }
    return pm_map.get(pm)


def _runtime_package_search(requested: str, pm: str | None) -> list[dict[str, str]]:
    """Search local package indexes without installing or refreshing them."""
    commands = {
        "apt": ["apt-cache", "search", requested],
        "apk": ["apk", "search", requested],
        "brew": ["brew", "search", requested],
        "dnf": ["dnf", "search", requested],
        "yum": ["yum", "search", requested],
    }
    command = commands.get(pm)
    if not command or (command[0] != "brew" and not shutil.which(command[0])):
        return []
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    results = []
    for line in (completed.stdout or "").splitlines()[:20]:
        line = line.strip()
        if line:
            results.append({"name": line.split()[0], "source": pm or "runtime-index"})
    return results


def verify_tool(requested: str) -> dict[str, Any]:
    """Verify an installed executable and return its version output."""
    requested = (requested or "").strip()
    path = shutil.which(requested)
    if not path:
        return {"ok": False, "requested": requested, "installed": False, "error": "tool is not installed"}
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "requested": requested, "installed": True, "path": path, "error": str(exc)}
    version = (completed.stdout or completed.stderr or "").strip().splitlines()[0] if (completed.stdout or completed.stderr) else "unknown"
    return {"ok": completed.returncode == 0, "requested": requested, "installed": True, "path": path, "version": version, "exit_code": completed.returncode}


def install_and_verify(requested: str) -> dict[str, Any]:
    """Install only a known package using argv, then verify or return a fallback."""
    requested = (requested or "").strip().lower()
    existing = verify_tool(requested)
    if existing.get("ok"):
        return {"ok": True, "requested": requested, "install_attempted": False, "already_installed": True, "verification": existing}
    if not getattr(settings, "auto_install", False):
        return {"ok": False, "requested": requested, "install_attempted": False, "error": "AUTO_INSTALL is disabled", "fallback": _STDLIB_FALLBACKS.get(requested)}
    pm = _detect_package_manager()
    command = None
    if requested in _INSTALL_COMMANDS and pm:
        command = _INSTALL_COMMANDS[requested].get(pm)
    if command is None and requested in _PIP_PACKAGES:
        command = _PIP_PACKAGES[requested]
    if not command or requested not in _INSTALL_COMMANDS and requested not in _PIP_PACKAGES:
        return {"ok": False, "requested": requested, "install_attempted": False, "error": "package is not in the known allowlist", "fallback": _STDLIB_FALLBACKS.get(requested)}
    argv = shlex.split(command)
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=settings.install_timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "requested": requested, "install_attempted": True, "error": type(exc).__name__, "fallback": _STDLIB_FALLBACKS.get(requested)}
    verification = verify_tool(requested)
    return {"ok": completed.returncode == 0 and verification.get("ok", False), "requested": requested, "install_attempted": True, "exit_code": completed.returncode, "verification": verification, "fallback": None if verification.get("ok") else _STDLIB_FALLBACKS.get(requested)}


def find_alternatives(requested: str) -> dict[str, Any]:
    """Return environment-aware install command and stdlib fallback for ANY missing tool.

    Works for every tool — not just the ones in the known list.
    Agent must follow install → stdlib → report order. Never cancel the task.
    """
    requested = (requested or "").strip().lower()
    if not requested:
        return {"ok": False, "error": "requested capability is required", "code": "INVALID_REQUEST"}

    direct = bool(shutil.which(requested))
    pm = _detect_package_manager()

    # Find install command
    install_cmd: str | None = None
    install_source = "unknown"

    if not direct:
        if requested in _INSTALL_COMMANDS:
            pkg_map = _INSTALL_COMMANDS[requested]
            if pm and pkg_map.get(pm):
                install_cmd = pkg_map[pm]
                install_source = "known"
            elif pkg_map.get("pip"):
                install_cmd = pkg_map["pip"]
                install_source = "pip"
        elif requested in _PIP_PACKAGES:
            install_cmd = _PIP_PACKAGES[requested]
            install_source = "pip"
        else:
            # Unknown tool — try generic system install, then pip as fallback
            sys_cmd = _generic_install_cmd(requested, pm)
            pip_cmd = f"pip install {requested}"
            install_cmd = sys_cmd or pip_cmd
            install_source = "generic-guess"

    install_available = install_cmd is not None and not direct
    stdlib = _STDLIB_FALLBACKS.get(requested)
    discovered = _runtime_package_search(requested, pm) if not direct else []
    alternatives = []
    if direct:
        alternatives.append({"name": requested, "preferred": True, "kind": "installed", "path": shutil.which(requested) or ""})
    for candidate in discovered:
        alternatives.append({**candidate, "preferred": False, "kind": "package"})
    if stdlib:
        alternatives.append({"name": stdlib["name"], "preferred": False, "kind": "stdlib"})

    return {
        "ok": True,
        "requested": requested,
        "installed": direct,
        "package_manager": pm,
        "install_available": install_available,
        "install_command": install_cmd,
        "install_source": install_source,
        "install_attempted": False,
        "alternatives": alternatives,
        "package_candidates": discovered,
        "verification": verify_tool(requested) if direct else {"installed": False},
        "stdlib_fallback": stdlib,
        "agent_instruction": (
            "Follow this order — do NOT cancel the task:\n"
            "1. If install_available=true, request user approval and run install_command.\n"
            "   Note: if install_source='generic-guess', verify the package name first.\n"
            "2. If install fails or install_available=false, use stdlib_fallback if present.\n"
            "3. If both fail, report exactly what was tried and ask the user for guidance.\n"
            "A missing tool is always a solvable problem — never stop the task."
        ),
    }
