import unittest
import sqlite3
import json
from errors import (
    AgentError,
    ErrorCategory,
    normalize_exception,
    error_payload,
    error_text,
    TracebackInspector,
    RetryPolicy,
    ASTErrorAnalyzer,
    AutoRecoveryHandler,
    SecurityViolationError,
    RateLimitExceededError,
    SyntaxCompilationError
)

class TestErrors(unittest.TestCase):
    def test_normalize_syntax_error(self):
        try:
            compile("def bad_func(: pass", "sample.py", "exec")
        except SyntaxError as exc:
            err = normalize_exception(exc, operation="code compilation")
            self.assertEqual(err.code, "SYNTAX_ERROR")
            self.assertEqual(err.category, ErrorCategory.SYNTAX)
            self.assertFalse(err.retryable)
            self.assertEqual(err.status, 400)
            self.assertIn("line 1", err.public_message)
            self.assertIn("fix the syntax", err.suggestion)

    def test_ast_error_analyzer(self):
        analysis = ASTErrorAnalyzer.analyze_source("def broken_code(\n  return 42", filename="test.py")
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis["lineno"], 1)
        self.assertIn("^", analysis["visual_snippet"])
        self.assertIn("Inspect line 1", analysis["suggestion"])

        clean = ASTErrorAnalyzer.analyze_source("def good_code():\n    return 42")
        self.assertIsNone(clean)

    def test_auto_recovery_handler(self):
        AutoRecoveryHandler.reset()
        exc = FileNotFoundError(2, "No such file or directory", "new_project/deep_folder/app.py")
        plan = AutoRecoveryHandler.record_error(exc)
        self.assertFalse(plan["should_halt"])
        self.assertEqual(plan["consecutive_count"], 1)
        self.assertIn("mkdir -p", plan.get("auto_action", ""))

    def test_normalize_timeout(self):
        exc = TimeoutError("Connection timed out after 30 seconds")
        err = normalize_exception(exc, operation="network request")
        self.assertEqual(err.code, "TIMEOUT")
        self.assertEqual(err.category, ErrorCategory.TIMEOUT)
        self.assertTrue(err.retryable)
        self.assertEqual(err.status, 504)
        self.assertIn("Increase the timeout", err.suggestion)

    def test_normalize_file_not_found(self):
        exc = FileNotFoundError(2, "No such file or directory", "missing_config.yaml")
        err = normalize_exception(exc, operation="read file")
        self.assertEqual(err.code, "NOT_FOUND")
        self.assertEqual(err.category, ErrorCategory.SYSTEM)
        self.assertFalse(err.retryable)
        self.assertEqual(err.status, 404)
        self.assertIn("missing_config.yaml", err.public_message)
        self.assertIn("list_directory", err.suggestion)

    def test_normalize_permission_denied(self):
        exc = PermissionError(13, "Permission denied", "/etc/shadow")
        err = normalize_exception(exc, operation="file access")
        self.assertEqual(err.code, "PERMISSION_DENIED")
        self.assertEqual(err.category, ErrorCategory.SECURITY)
        self.assertEqual(err.status, 403)
        self.assertIn("Check file permissions", err.suggestion)

    def test_normalize_sqlite_table_error(self):
        conn = sqlite3.connect(":memory:")
        try:
            conn.execute("SELECT * FROM non_existent_table")
        except sqlite3.OperationalError as exc:
            err = normalize_exception(exc, operation="database query")
            self.assertEqual(err.code, "DATABASE_SCHEMA_ERROR")
            self.assertIn("non_existent_table", err.public_message)
            self.assertIn("Run the database schema initialization", err.suggestion)
        finally:
            conn.close()

    def test_secret_redaction_in_errors(self):
        exc = ValueError("Invalid token passed: api_key=AIzaSySecretKey123456789")
        err = normalize_exception(exc, operation="token validation")
        self.assertNotIn("AIzaSySecretKey123456789", err.message)
        self.assertIn("[REDACTED]", err.message)

    def test_retry_policy_backoff(self):
        delay_0 = RetryPolicy.compute_backoff(0, base_delay=1.0)
        self.assertTrue(0.5 <= delay_0 <= 1.0)
        delay_2 = RetryPolicy.compute_backoff(2, base_delay=1.0)
        self.assertTrue(2.0 <= delay_2 <= 4.0)

    def test_diagnostic_summary_formatting(self):
        err = AgentError(
            code="TEST_ERROR",
            message="Internal failure occurred",
            public_message="Failed to connect to backend",
            category=ErrorCategory.NETWORK,
            suggestion="Check if server is active on localhost:8000",
            root_cause="Connection refused on port 8000",
            retryable=True,
            status=503
        )
        summary = err.diagnostic_summary()
        self.assertIn("[ERROR: TEST_ERROR]", summary)
        self.assertIn("Root Cause: Connection refused on port 8000", summary)
        self.assertIn("Suggestion: Check if server is active", summary)
        self.assertIn("Retryable : Yes (HTTP 503)", summary)

if __name__ == "__main__":
    unittest.main()
