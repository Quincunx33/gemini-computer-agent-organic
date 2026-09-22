from dataclasses import dataclass, asdict
import re
import subprocess
from typing import Optional

from config import settings
from errors import normalize_exception
from permissions import classify_command, confirm, redact_secrets
from tools.filesystem import safe_path
from platform_support import detect


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
        process = subprocess.run(command, shell=True, cwd=run_cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=requested_timeout)
        return CommandResult(command, process.returncode, _output(process.stdout), _output(process.stderr)).as_dict()
    except subprocess.TimeoutExpired as exc:
        return CommandResult(command, None, _output(exc.stdout), _output(exc.stderr), True, {"code": "TIMEOUT", "message": "Command timed out"}).as_dict()
    except Exception as exc:
        err = normalize_exception(exc, operation="command execution")
        return CommandResult(command, None, "", err.public_message, error={"code": err.code, "message": err.public_message, "error_id": err.error_id}).as_dict()
