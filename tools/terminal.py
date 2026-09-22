from dataclasses import dataclass, asdict
import re
import subprocess
import os
import signal
import shlex
from typing import Optional

from config import settings
from errors import normalize_exception
from permissions import classify_command, confirm, redact_secrets
from tools.filesystem import safe_path
from platform_support import detect
from tools.fallbacks import find_alternatives


@dataclass
class CommandResult:
    command: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: dict | None = None

    def as_dict(self):
        return asdict(self)


def _output(value: object) -> str:
    return redact_secrets(str(value or ""))[-settings.max_output_chars:]


def _platform_command_error(command: str) -> dict | None:
    info = detect()
    first = command.strip().lower()
    if info.profile == "windows" and re.match(r"^(bash|sh|zsh|ls|grep|sed|awk|cat|pwd)(\s|$)", first):
        return {"code": "UNSUPPORTED_PLATFORM", "message": "POSIX/Linux command rejected on Windows; use cmd.exe or PowerShell syntax", "platform": info.profile}
    if info.profile in {"linux", "termux", "ios_shell", "macos"} and re.match(r"^(cmd|powershell|pwsh|get-childitem|get-content)(\s|$)", first):
        return {"code": "UNSUPPORTED_PLATFORM", "message": "Windows command rejected on a POSIX/iOS shell; use a supported shell command", "platform": info.profile}
    if info.profile in {"linux", "termux", "ios_shell", "macos"} and re.match(r"^[a-z]:[\\/]", first):
        return {"code": "UNSUPPORTED_PLATFORM", "message": "Windows path rejected on a POSIX/iOS shell", "platform": info.profile}
    return None


def run_command(command: str, cwd: Optional[str] = None, timeout: Optional[int] = None, approved=False) -> dict:
    if not isinstance(command, str) or not command.strip():
        return CommandResult("", None, "", "", error={"code": "INVALID_COMMAND", "message": "Command must be non-empty"}).as_dict()
    platform_error = _platform_command_error(command)
    if platform_error:
        return CommandResult(command, None, "", platform_error["message"], error=platform_error).as_dict()
    risk = classify_command(command)
    if not approved and not confirm(risk, command, settings.require_confirmation):
        return CommandResult(command, None, "", "Command not approved", error={"code": "PERMISSION_DENIED", "message": "Command was not approved"}).as_dict()
    try:
        run_cwd = safe_path(cwd or ".")
        requested_timeout = settings.command_timeout if timeout is None else int(timeout)
        requested_timeout = max(1, min(requested_timeout, 24 * 60 * 60))
        kwargs = {"shell": True, "cwd": run_cwd, "text": True, "encoding": "utf-8", "errors": "replace", "stdout": subprocess.PIPE, "stderr": subprocess.PIPE}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        process = subprocess.Popen(command, **kwargs)
        try:
            stdout, stderr = process.communicate(timeout=requested_timeout)
            result = CommandResult(command, process.returncode, _output(stdout), _output(stderr)).as_dict()
            if process.returncode == 127 or "command not found" in (stderr or "").lower() or "not recognized" in (stderr or "").lower():
                try:
                    requested = shlex.split(command)[0]
                except ValueError:
                    requested = command.strip().split()[0]
                result["error"] = {"code": "COMMAND_NOT_FOUND", "message": f"Command unavailable: {requested}", "alternatives": find_alternatives(requested)}
            return result
        except subprocess.TimeoutExpired as exc:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.kill()
            stdout, stderr = process.communicate()
            return CommandResult(command, None, _output(stdout or exc.stdout), _output(stderr or exc.stderr), True, {"code": "TIMEOUT", "message": "Command timed out; process group terminated"}).as_dict()
        except KeyboardInterrupt:
            if os.name != "nt":
                os.killpg(process.pid, signal.SIGTERM)
            else:
                process.kill()
            process.communicate()
            raise
    except Exception as exc:
        err = normalize_exception(exc, operation="command execution")
        return CommandResult(command, None, "", err.public_message, error={"code": err.code, "message": err.public_message, "error_id": err.error_id}).as_dict()
