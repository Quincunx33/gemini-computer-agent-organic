from __future__ import annotations

import importlib.util
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any
from config import settings

_INSTALL_COMMANDS: dict[str, dict[str, str | None]] = {
    "git": {"apk": "apk add git", "apt": "apt-get install -y git", "brew": "brew install git", "pkg": "pkg install -y git"},
    "curl": {"apk": "apk add curl", "apt": "apt-get install -y curl", "brew": "brew install curl", "pkg": "pkg install -y curl"},
    "wget": {"apk": "apk add wget", "apt": "apt-get install -y wget", "brew": "brew install wget", "pkg": "pkg install -y wget"},
    "ffmpeg": {"apk": "apk add ffmpeg", "apt": "apt-get install -y ffmpeg", "brew": "brew install ffmpeg", "pkg": "pkg install -y ffmpeg"},
    "tesseract": {"apk": "apk add tesseract-ocr", "apt": "apt-get install -y tesseract-ocr", "brew": "brew install tesseract", "pkg": "pkg install -y tesseract"},
    "jq": {"apk": "apk add jq", "apt": "apt-get install -y jq", "brew": "brew install jq", "pkg": "pkg install -y jq"},
    "node": {"apk": "apk add nodejs npm", "apt": "apt-get install -y nodejs npm", "brew": "brew install node", "pkg": "pkg install -y nodejs"},
    "zip": {"apk": "apk add zip", "apt": "apt-get install -y zip", "brew": "brew install zip", "pkg": "pkg install -y zip"},
    "unzip": {"apk": "apk add unzip", "apt": "apt-get install -y unzip", "brew": "brew install unzip", "pkg": "pkg install -y unzip"},
    "tar": {"apk": "apk add tar", "apt": "apt-get install -y tar", "brew": "brew install gnu-tar", "pkg": "pkg install -y tar"},
    "rg": {"apk": "apk add ripgrep", "apt": "apt-get install -y ripgrep", "brew": "brew install ripgrep", "pkg": "pkg install -y ripgrep"},
}

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
    "rg": {"name": "grep / python re", "how": "grep -r pattern dir"},
    "jq": {"name": "python json", "how": "import json\nobj = json.loads(text)"},
    "zip": {"name": "python zipfile", "how": "import zipfile\nwith zipfile.ZipFile('out.zip','w') as z: z.write(file)"},
    "unzip": {"name": "python zipfile", "how": "import zipfile\nwith zipfile.ZipFile('file.zip') as z: z.extractall('.')"},
}


def _detect_package_manager() -> str | None:
    for pm in ("pkg", "apk", "apt-get", "brew", "dnf", "yum"):
        if shutil.which(pm):
            return pm.replace("apt-get", "apt")
    return None


def verify_tool(requested: str) -> dict[str, Any]:
    requested = (requested or "").strip()
    path = shutil.which(requested)
    if not path:
        # Check if it is a python importable module
        try:
            if importlib.util.find_spec(requested) is not None:
                return {"ok": True, "requested": requested, "installed": True, "kind": "python_module"}
        except (ImportError, ValueError, AttributeError):
            pass
        return {"ok": False, "requested": requested, "installed": False, "error": "tool is not installed"}
    try:
        completed = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=8, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "requested": requested, "installed": True, "path": path, "error": str(exc)}
    version = (completed.stdout or completed.stderr or "").strip().splitlines()[0] if (completed.stdout or completed.stderr) else "unknown"
    return {"ok": completed.returncode == 0, "requested": requested, "installed": True, "path": path, "version": version, "exit_code": completed.returncode}


def install_package(package: str, manager: str = "auto") -> dict[str, Any]:
    """Autonomous package installation tool for Python and system CLI tools."""
    pkg = (package or "").strip()
    if not pkg:
        return {"ok": False, "error": "Package name is required"}

    pm = manager.lower().strip() if manager else "auto"
    detected_pm = _detect_package_manager()

    if pm == "auto":
        # Check if known CLI system tool
        if pkg in _INSTALL_COMMANDS and detected_pm:
            pm = detected_pm
        else:
            pm = "pip"

    clean_pkg = shlex.quote(pkg.split()[0])
    if pm == "pip":
        clean_pip_pkg = clean_pkg.lstrip("'\"")
        cmd = f"{sys.executable} -m pip install --break-system-packages --no-input {clean_pip_pkg}"
    elif pm in {"apt", "apt-get"}:
        cmd = f"apt-get install -y {clean_pkg}"
    elif pm == "brew":
        cmd = f"brew install {clean_pkg}"
    elif pm == "apk":
        cmd = f"apk add {clean_pkg}"
    elif pm == "pkg":
        cmd = f"pkg install -y {clean_pkg}"
    else:
        cmd = f"{sys.executable} -m pip install --break-system-packages --no-input {clean_pkg}"

    try:
        completed = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=settings.install_timeout,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "package": pkg,
            "manager": pm,
            "command": cmd,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-1000:] if completed.stdout else "",
            "stderr": completed.stderr[-1000:] if completed.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "package": pkg, "error": "Installation timed out"}
    except Exception as exc:
        return {"ok": False, "package": pkg, "error": str(exc)}


def install_and_verify(requested: str) -> dict[str, Any]:
    """Install a package or tool and verify its operational status."""
    requested = (requested or "").strip().lower()
    existing = verify_tool(requested)
    if existing.get("ok"):
        return {"ok": True, "requested": requested, "install_attempted": False, "already_installed": True, "verification": existing}

    pm = _detect_package_manager()
    command = None
    if requested in _INSTALL_COMMANDS and pm:
        command = _INSTALL_COMMANDS[requested].get(pm)
    
    # Run installation
    if command:
        try:
            completed = subprocess.run(shlex.split(command), capture_output=True, text=True, timeout=settings.install_timeout, check=False)
            verification = verify_tool(requested)
            return {"ok": completed.returncode == 0 and verification.get("ok", False), "requested": requested, "install_attempted": True, "exit_code": completed.returncode, "verification": verification}
        except Exception as exc:
            return {"ok": False, "requested": requested, "error": str(exc)}

    # Fallback to python pip installation
    result = install_package(requested, manager="pip")
    verification = verify_tool(requested)
    return {
        "ok": result.get("ok", False) or verification.get("ok", False),
        "requested": requested,
        "install_attempted": True,
        "manager": "pip",
        "verification": verification,
        "details": result,
    }


def find_alternatives(requested: str) -> dict[str, Any]:
    requested = (requested or "").strip().lower()
    if not requested:
        return {"ok": False, "error": "requested capability is required", "code": "INVALID_REQUEST"}
    direct = bool(shutil.which(requested)) or (importlib.util.find_spec(requested) is not None)
    pm = _detect_package_manager()
    install_cmd = None
    if not direct:
        if requested in _INSTALL_COMMANDS and pm:
            install_cmd = _INSTALL_COMMANDS[requested].get(pm)
        else:
            install_cmd = f"pip install {requested}"
    stdlib = _STDLIB_FALLBACKS.get(requested)
    alternatives = []
    if direct:
        alternatives.append({"name": requested, "preferred": True, "kind": "installed", "path": shutil.which(requested) or "python_module"})
    if stdlib:
        alternatives.append({"name": stdlib["name"], "preferred": False, "kind": "stdlib"})
    return {
        "ok": True,
        "requested": requested,
        "installed": direct,
        "package_manager": pm,
        "install_available": install_cmd is not None and not direct,
        "install_command": install_cmd,
        "install_attempted": False,
        "alternatives": alternatives,
        "package_candidates": [],
        "verification": verify_tool(requested) if direct else {"installed": False},
        "stdlib_fallback": stdlib,
    }
