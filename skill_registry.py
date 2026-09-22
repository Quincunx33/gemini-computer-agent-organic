from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path
    trust: str = "local"


class SkillRegistry:
    """Discover local SKILL.md packs and select relevant guidance per task."""

    def __init__(self, root: Path | None = None):
        self.root = Path(root or Path(__file__).resolve().parent / "skills")
        self.skills = self._discover()

    def _discover(self) -> list[Skill]:
        found: list[Skill] = []
        for path in sorted(self.root.glob("*/SKILL.md")):
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                continue
            match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, re.S)
            if not match:
                continue
            metadata, body = match.groups()
            values = {}
            for line in metadata.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    values[key.strip()] = value.strip().strip("'\"")
            if values.get("name") and values.get("description"):
                found.append(Skill(values["name"], values["description"], body.strip(), path, values.get("trust", "local")))
        return found

    def list(self) -> list[dict[str, str]]:
        return [{"name": skill.name, "description": skill.description, "trust": skill.trust} for skill in self.skills]

    def select(self, task: str, limit: int = 2) -> list[Skill]:
        text = (task or "").lower()
        scored = []
        for skill in self.skills:
            haystack = f"{skill.name} {skill.description} {skill.body}".lower()
            tokens = set(re.findall(r"[a-z][a-z0-9_-]{2,}", haystack))
            score = sum(1 for token in set(re.findall(r"[a-z][a-z0-9_-]{2,}", text)) if token in tokens)
            if score:
                scored.append((score, skill))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [skill for _, skill in scored[:max(1, limit)]]

    def context(self, task: str, limit: int = 2, max_chars: int = 5000) -> str:
        selected = self.select(task, limit)
        if not selected:
            return "No specialized skill pack selected."
        sections = []
        for skill in selected:
            sections.append(f"## Skill: {skill.name}\n{skill.body}")
        return "\n\n".join(sections)[:max_chars]


__all__ = ["Skill", "SkillRegistry"]
