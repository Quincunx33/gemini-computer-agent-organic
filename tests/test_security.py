import json
import tempfile
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


if __name__ == "__main__":
    unittest.main()
