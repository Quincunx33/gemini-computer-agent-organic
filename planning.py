from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskPlan:
    goal: str
    steps: list[str]
    acceptance_criteria: list[str]
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[dict[str, str]] = field(default_factory=list)
    active_step_index: int = 0

    def mark_completed(self, step: str) -> None:
        if step not in self.completed_steps:
            self.completed_steps.append(step)
        if self.active_step_index < len(self.steps) - 1:
            self.active_step_index += 1

    def record_failure_and_replan(self, failed_step: str, reason: str, alternative_step: str | None = None) -> None:
        self.failed_steps.append({"step": failed_step, "reason": reason})
        if alternative_step and alternative_step not in self.steps:
            self.steps.insert(self.active_step_index + 1, alternative_step)


def make_plan(task: str) -> TaskPlan:
    """Universal AI-driven plan without language-biased keyword hardcoding."""
    text = (task or "").strip()
    steps = [
        "Understand user intent and determine necessary actions",
        "Execute required operations (create, patch, run, or inspect based on intent)",
        "Verify results with tests/syntax checks and confirm acceptance criteria"
    ]
    criteria = [
        "The user's goal is fully and accurately accomplished",
        "Any workspace change or command execution is verified for correctness",
        "No unverified assumptions or ungrounded claims"
    ]
    return TaskPlan(text, steps, criteria)


def as_prompt(plan: TaskPlan) -> str:
    lines = ["Goal: " + plan.goal, "Plan & Progress:"]
    for i, step in enumerate(plan.steps):
        status = "[DONE]" if step in plan.completed_steps else (
            "[ACTIVE]" if i == plan.active_step_index else "[PENDING]"
        )
        lines.append(f"{i + 1}. {status} {step}")
    if plan.failed_steps:
        lines.append("Recovered / Failed steps:")
        for failure in plan.failed_steps:
            lines.append(f"- Failed: {failure['step']} (Reason: {failure['reason']})")
    lines += ["Acceptance criteria:"]
    lines += [f"- {item}" for item in plan.acceptance_criteria]
    return "\n".join(lines)
