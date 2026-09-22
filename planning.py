from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class TaskPlan:
    goal: str
    steps: list[str]
    acceptance_criteria: list[str]


def make_plan(task: str) -> TaskPlan:
    text = (task or "").strip()
    write = any(word in text.lower() for word in ("write", "edit", "fix", "implement", "create", "change"))
    steps = ["Understand the request and inspect relevant state"]
    if write:
        steps += ["Identify the smallest safe change", "Apply the change", "Verify the result"]
        criteria = ["The requested change is applied", "Verification evidence is available", "No unrelated data is changed"]
    else:
        steps += ["Collect evidence with read-only tools", "Cross-check the result", "Summarize findings and limitations"]
        criteria = ["The answer is supported by observed evidence", "Uncertainty or blockers are reported"]
    return TaskPlan(text, steps, criteria)


def as_prompt(plan: TaskPlan) -> str:
    lines = ["Goal: " + plan.goal, "Plan:"]
    lines += [f"{i + 1}. {step}" for i, step in enumerate(plan.steps)]
    lines += ["Acceptance criteria:"]
    lines += [f"- {item}" for item in plan.acceptance_criteria]
    return "\n".join(lines)
