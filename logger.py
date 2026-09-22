"""Small structured logger built on Python's standard library."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from permissions import redact_secrets


class SafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage())[:4000],
        }
        if hasattr(record, "error_id"):
            payload["error_id"] = getattr(record, "error_id")
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))[:8000]
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str = "genagent") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(SafeFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    level = os.getenv("AGENT_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    return logger


logger = get_logger()

__all__ = ["get_logger", "logger"]
