from __future__ import annotations

import ast
from pathlib import Path
from typing import Any
from tools.filesystem import safe_path


def inspect_code(path: str, symbol: str | None = None) -> dict[str, Any]:
    """Inspect Python code structure or extract a specific function/class using AST."""
    try:
        target_path = safe_path(path)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "code": "INVALID_PATH"}

    if not target_path.exists():
        return {"ok": False, "error": f"File not found: {path}", "code": "NOT_FOUND"}

    try:
        source = target_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(target_path))
    except (UnicodeDecodeError, OSError) as exc:
        return {"ok": False, "error": f"Failed to read file: {exc}"}
    except SyntaxError as exc:
        return {"ok": False, "error": f"Python syntax error at line {exc.lineno}: {exc.msg}", "code": "SYNTAX_ERROR"}

    lines = source.splitlines()

    if symbol:
        symbol_clean = symbol.strip()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == symbol_clean:
                start = max(0, node.lineno - 1)
                end = getattr(node, "end_lineno", node.lineno)
                code_snippet = "\n".join(lines[start:end])
                doc = ast.get_docstring(node) or ""
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                return {
                    "ok": True,
                    "symbol": symbol_clean,
                    "type": kind,
                    "start_line": node.lineno,
                    "end_line": end,
                    "docstring": doc,
                    "code": code_snippet,
                }
        return {"ok": False, "error": f"Symbol '{symbol}' not found in {path}", "code": "SYMBOL_NOT_FOUND"}

    # Outline summary
    classes = []
    functions = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [m.name for m in node.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
            classes.append({"name": node.name, "line": node.lineno, "methods": methods, "docstring": (ast.get_docstring(node) or "").strip()})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append({"name": node.name, "line": node.lineno, "args": [a.arg for a in node.args.args], "docstring": (ast.get_docstring(node) or "").strip()})

    imports = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)

    return {
        "ok": True,
        "path": str(target_path),
        "total_lines": len(lines),
        "classes": classes,
        "functions": functions,
        "imports": list(dict.fromkeys(imports))
    }
