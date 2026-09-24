from enum import Enum
import re
class Risk(str, Enum):
    NORMAL="normal"; LOW_RISK="low_risk"; PRIVILEGED="privileged"; DESTRUCTIVE="destructive"
_DESTRUCTIVE = re.compile(r"(^|\s)(rm\s+-[^\n]*r|rm\s+-r|mkfs|fdisk|parted|dd\s+if=|git\s+(reset|clean)|shutdown|reboot)(\s|$)", re.I)
_PRIVILEGED = re.compile(r"(^|\s)(sudo\b|su\s+-|systemctl\s+(restart|stop|disable)|apt(-get)?\s+(install|remove)|chmod\s+777)(\s|$)", re.I)
_CONFIRM_REQUIRED = re.compile(r"(curl|wget)\s+[^\n|]+\|\s*(sh|bash|zsh)|(^|\s)(cat|less|head|tail)\s+[^\n]*(\.env|id_rsa|credentials|token)(\s|$)", re.I)
def classify_command(command: str) -> Risk:
    if _CONFIRM_REQUIRED.search(command): return Risk.DESTRUCTIVE
    if _DESTRUCTIVE.search(command): return Risk.DESTRUCTIVE
    if _PRIVILEGED.search(command): return Risk.PRIVILEGED
    if any(x in command.lower() for x in ["curl", "wget", "pip install", "npm install"]): return Risk.LOW_RISK
    return Risk.NORMAL

def redact_secrets(value: str) -> str:
    value = re.sub(r"(?i)(api[_-]?key|token|password|secret)\s*([=:])\s*([^\s,;]+)", r"\1\2[REDACTED]", value)
    value = re.sub(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----.*?-----END [A-Z ]+ PRIVATE KEY-----", "[PRIVATE_KEY_REDACTED]", value, flags=re.I | re.S)
    value = re.sub(r"\beyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b", "[JWT_REDACTED]", value)
    value = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[CLOUD_KEY_REDACTED]", value)
    return re.sub(
        r'(?i)(["\']?(?:api[_-]?key|token|password|secret)["\']?\s*:\s*["\']?)([^,"\'}\s]+)',
        r"\1[REDACTED]",
        value,
    )

def confirm(risk: Risk, command: str, required=True) -> bool:
    if not required or risk in {Risk.NORMAL, Risk.LOW_RISK}: return True
    print(f"\n[{risk.value.upper()}] Permission required. The exact command is:\n  {command}")
    return input("Type 'yes' to confirm: ").strip().lower() == "yes"
