import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from security import AuditLogger, RateLimiter


class SecurityTests(unittest.TestCase):
    def test_rate_limiter(self):
        limiter = RateLimiter(limit=2, window_seconds=60)
        self.assertTrue(limiter.allow("device-a"))
        self.assertTrue(limiter.allow("device-a"))
        self.assertFalse(limiter.allow("device-a"))
        self.assertTrue(limiter.allow("device-b"))

    def test_audit_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            AuditLogger(path).write("command", detail="API_KEY=super-secret")
            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("[REDACTED]", record["detail"])
            self.assertNotIn("super-secret", path.read_text(encoding="utf-8"))

    def test_audit_rotates_after_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            logger = AuditLogger(path, rotate_hours=1, retention=2)
            logger.write("before", value="one")
            old = time.time() - 7201
            os.utime(path, (old, old))
            logger.write("after", value="two")
            archives = list(path.parent.glob("audit.jsonl.20*"))
            self.assertEqual(len(archives), 1)
            self.assertIn('"event": "before"', archives[0].read_text(encoding="utf-8"))
            self.assertIn('"event": "after"', path.read_text(encoding="utf-8"))

    def test_audit_reset_keeps_bounded_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            logger = AuditLogger(path, rotate_hours=1, retention=1)
            logger.write("one")
            logger.reset()
            logger.write("two")
            logger.reset()
            logger.write("three")
            self.assertLessEqual(len(list(path.parent.glob("audit.jsonl.20*"))), 1)


if __name__ == "__main__":
    unittest.main()
