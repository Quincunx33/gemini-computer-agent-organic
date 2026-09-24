import os
import shutil
import unittest
from pathlib import Path

from config import settings
from tools.log_analyzer import analyze_logs
from tools.watchdog import check_port, check_process_resources
from tools.safety_preview import preview_impact
from tools.tool_synthesis import synthesize_tool, execute_synthesized_tool


class AdvancedToolsTests(unittest.TestCase):
    def test_log_analyzer_extracts_traceback_and_root_cause(self):
        log_sample = """
2026-09-24 10:00:01 INFO Starting web application
2026-09-24 10:00:02 DEBUG Loading configuration
Traceback (most recent call last):
  File "app.py", line 42, in <module>
    import nonexistent_library
ModuleNotFoundError: No module named 'nonexistent_library'
2026-09-24 10:00:03 CRITICAL Service stopped
"""
        res = analyze_logs(log_text=log_sample)
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res["error_count"], 1)
        self.assertIn("ModuleNotFoundError: No module named 'nonexistent_library'", res["root_cause"])
        self.assertIsNotNone(res["suggested_fix"])
        self.assertIn("nonexistent_library", res["suggested_fix"])

    def test_check_port_closed(self):
        # Port 65432 is typically free/closed
        res = check_port(host="127.0.0.1", port=65432, timeout=0.5)
        self.assertTrue(res["ok"])
        self.assertFalse(res["listening"])
        self.assertEqual(res["status"], "closed")

    def test_check_process_resources(self):
        res = check_process_resources()
        self.assertTrue(res["ok"])
        self.assertIn("total_processes", res)

    def test_safety_preview_dry_run_file_patch(self):
        test_file = Path(settings.workspace) / "_temp_preview_test.py"
        test_file.write_text("x = 10\ny = 20\n", encoding="utf-8")
        try:
            preview = preview_impact(
                tool="patch_file",
                args={"path": test_file.name, "search": "x = 10", "replace": "x = 99", "count": 1}
            )
            self.assertTrue(preview["ok"])
            self.assertIn("-x = 10", preview["diff_preview"])
            self.assertIn("+x = 99", preview["diff_preview"])
            self.assertEqual(preview["risk_level"], "low")
        finally:
            if test_file.exists():
                test_file.unlink()

    def test_safety_preview_flags_destructive_command(self):
        preview = preview_impact(command="rm -rf /some/directory")
        self.assertTrue(preview["ok"])
        self.assertEqual(preview["risk_level"], "high")
        self.assertFalse(preview["safe_to_proceed"])

    def test_dynamic_tool_synthesis_and_execution(self):
        code = """def add_five(val: int) -> int:
    return val + 5
"""
        test_code = "assert add_five(10) == 15"
        res = synthesize_tool("test_adder", code=code, test_code=test_code, description="Adder test tool")
        self.assertTrue(res["ok"])
        self.assertTrue(res["verified"])

        # Execute synthesized tool
        exec_res = execute_synthesized_tool("test_adder", "add_five", {"val": 20})
        self.assertTrue(exec_res["ok"])
        self.assertEqual(exec_res["result"], 25)

        # Cleanup synthesized skill
        skill_dir = Path(settings.skills_path) / "test_adder"
        if skill_dir.exists():
            shutil.rmtree(skill_dir)


if __name__ == "__main__":
    unittest.main()
