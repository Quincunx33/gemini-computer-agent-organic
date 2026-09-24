import os
import tempfile
import unittest
from pathlib import Path

from config import settings, is_configured, reload_settings
from tools.code_intel import inspect_code
from tools.snapshot import create_snapshot, restore_snapshot
from skill_registry import create_skill


class AutonomousToolsTests(unittest.TestCase):
    def test_inspect_code_ast(self):
        target_path = Path(settings.workspace) / "_temp_inspect_test.py"
        target_path.write_text("""
class Calculator:
    def add(self, a, b):
        '''Add numbers'''
        return a + b

def standalone(x):
    return x * 2
""", encoding="utf-8")
        try:
            # Test full outline
            outline = inspect_code(target_path.name)
            self.assertTrue(outline["ok"])
            self.assertEqual(len(outline["classes"]), 1)
            self.assertEqual(outline["classes"][0]["name"], "Calculator")
            self.assertEqual(len(outline["functions"]), 1)
            self.assertEqual(outline["functions"][0]["name"], "standalone")

            # Test symbol extraction
            sym = inspect_code(target_path.name, symbol="Calculator")
            self.assertTrue(sym["ok"])
            self.assertIn("class Calculator:", sym["code"])
            self.assertIn("def add", sym["code"])
        finally:
            if target_path.exists():
                target_path.unlink()

    def test_snapshot_and_restore(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = Path(temp_dir) / "sample_script.py"
            test_file.write_text("original = 1\n", encoding="utf-8")
            
            # Temporary override workspace
            original_ws = settings.workspace
            object.__setattr__(settings, "workspace", Path(temp_dir))
            try:
                snap = create_snapshot(label="test_snap")
                self.assertTrue(snap["ok"])
                snap_id = snap["snapshot_id"]

                # Modify file
                test_file.write_text("modified = 2\n", encoding="utf-8")
                self.assertEqual(test_file.read_text(), "modified = 2\n")

                # Restore
                restored = restore_snapshot(snap_id)
                self.assertTrue(restored["ok"])
                self.assertEqual(test_file.read_text(), "original = 1\n")
            finally:
                object.__setattr__(settings, "workspace", original_ws)

    def test_create_skill(self):
        res = create_skill("test_skill", "A test skill pack", "Instructions on how to test")
        self.assertTrue(res["ok"])
        skill_file = Path(res["path"])
        self.assertTrue(skill_file.exists())
        content = skill_file.read_text(encoding="utf-8")
        self.assertIn("name: test_skill", content)
        self.assertIn("Instructions on how to test", content)
        # Clean up
        if skill_file.exists():
            skill_file.unlink()
            if skill_file.parent.exists():
                skill_file.parent.rmdir()


if __name__ == "__main__":
    unittest.main()
