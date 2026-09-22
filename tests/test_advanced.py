import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from approval import ApprovalBroker
from planning import make_plan
from tool_validation import validate_tool_args
from tools.filesystem import safe_path


class AdvancedFeatureTests(unittest.TestCase):
    def test_plan_has_acceptance_criteria(self):
        plan = make_plan("fix the tests")
        self.assertTrue(plan.steps)
        self.assertTrue(plan.acceptance_criteria)

    def test_tool_validation_rejects_missing_required_argument(self):
        ok, reason = validate_tool_args("read_file", {})
        self.assertFalse(ok)
        self.assertIn("path", reason)

    def test_approval_broker_resolves_once(self):
        broker = ApprovalBroker()
        approval = broker.create("run_command", {"command": "echo hi"})
        self.assertTrue(broker.resolve(approval.approval_id, True))
        self.assertFalse(broker.resolve(approval.approval_id, False))

    def test_host_allowlist_and_denylist(self):
        settings = SimpleNamespace(workspace=Path("/tmp/project"), host_mode=True, allowed_paths="/tmp/project:/tmp/allowed", denied_paths="/tmp/project/private")
        with patch("tools.filesystem.settings", settings):
            self.assertEqual(safe_path("/tmp/allowed/a.txt"), Path("/tmp/allowed/a.txt"))
            with self.assertRaises(PermissionError):
                safe_path("/tmp/other/a.txt")
            with self.assertRaises(PermissionError):
                safe_path("/tmp/project/private/key")


if __name__ == "__main__":
    unittest.main()
