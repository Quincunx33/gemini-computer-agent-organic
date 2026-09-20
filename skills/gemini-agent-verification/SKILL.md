---
name: gemini-agent-verification
description: Verify changes made by the Gemini computer agent. Use after editing Python files, running tools, or completing a multi-step task that needs evidence of correctness.
---

# Gemini Agent Verification

## Change workflow

1. Inspect the target and record the intended change.
2. Apply the smallest safe edit.
3. Run `python -m unittest discover -s tests -p 'test_*.py'`.
4. Run `verify_python` for every changed Python file.
5. Review the resulting output, file boundaries, and relevant Git diff.
6. Report pass/fail evidence and any unverified external dependency.

## Python checks

Use `python -m py_compile path/to/file.py` or the built-in `verify_python` tool. Run tests from the project root so workspace-relative paths and imports match normal operation. Do not call live Gemini APIs in unit tests; inject a fake client.

## Recovery loop

If a check fails, capture the first actionable error, fix only that issue, rerun the narrow check, then rerun the complete suite. Stop after the configured retry limit and report the remaining failure instead of hiding it.

## Completion criteria

A task is complete only when the requested files exist, tests pass, syntax checks pass, no secret is exposed in output, and the final artifact can be opened or extracted successfully.
