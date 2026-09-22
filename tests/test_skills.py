import tempfile
import unittest
from pathlib import Path

from skill_registry import SkillRegistry


class SkillRegistryTests(unittest.TestCase):
    def test_discovers_and_selects_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills" / "coding"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text(
                "---\nname: coding\ndescription: coding and tests\n---\n\nRun tests after edits.",
                encoding="utf-8",
            )
            registry = SkillRegistry(root.parent)
            self.assertEqual(registry.list()[0]["name"], "coding")
            self.assertEqual(registry.select("fix the coding tests")[0].name, "coding")
            self.assertIn("Run tests", registry.context("fix the coding tests"))

    def test_ignores_invalid_skill_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "skills" / "bad"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text("not frontmatter", encoding="utf-8")
            self.assertEqual(SkillRegistry(Path(directory) / "skills").list(), [])


if __name__ == "__main__":
    unittest.main()
