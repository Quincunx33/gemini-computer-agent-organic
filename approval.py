from __future__ import annotations

from dataclasses import dataclass, asdict
import secrets
import time
from typing import Any


@dataclass
class Approval:
    approval_id: str
    tool: str
    args: dict[str, Any]
    created_at: float
    status: str = "pending"


class ApprovalBroker:
    def __init__(self):
        self.pending: dict[str, Approval] = {}

    def create(self, tool: str, args: dict[str, Any]) -> Approval:
        approval = Approval(secrets.token_urlsafe(12), tool, args, time.time())
        self.pending[approval.approval_id] = approval
        return approval

    def resolve(self, approval_id: str, approved: bool) -> bool:
        item = self.pending.get(approval_id)
        if not item or item.status != "pending":
            return False
        item.status = "approved" if approved else "rejected"
        return True

    def list(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in self.pending.values()]
