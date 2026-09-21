from dataclasses import dataclass, asdict
import subprocess
from typing import Optional
from config import settings
from permissions import classify_command, confirm, redact_secrets
from tools.filesystem import safe_path
@dataclass
class CommandResult:
    command: str; exit_code: int|None; stdout: str; stderr: str; timed_out: bool=False
    def as_dict(self): return asdict(self)
def run_command(command: str, cwd: Optional[str]=None, timeout: Optional[int]=None, approved=False) -> dict:
    risk=classify_command(command)
    if not approved and not confirm(risk, command, settings.require_confirmation):
        return CommandResult(command,None,"","Command not approved").as_dict()
    try:
        run_cwd = safe_path(cwd or ".")
        p=subprocess.run(command, shell=True, cwd=run_cwd, text=True, encoding="utf-8", errors="replace", capture_output=True, timeout=timeout or settings.command_timeout)
        return CommandResult(command,p.returncode,redact_secrets(p.stdout[-settings.max_output_chars:]),redact_secrets(p.stderr[-settings.max_output_chars:])).as_dict()
    except subprocess.TimeoutExpired as e:
        return CommandResult(command,None,e.stdout or "",e.stderr or "",True).as_dict()
