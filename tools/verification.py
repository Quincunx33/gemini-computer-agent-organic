import py_compile
from pathlib import Path
from tools.filesystem import safe_path

def verify_python(path: str) -> dict:
    target = safe_path(path)
    if target.suffix != ".py":
        return {"valid": False, "error": "verify_python requires a .py file"}
    try:
        py_compile.compile(str(target), doraise=True, cfile=str(Path("/tmp") / (target.name + ".pyc")))
        return {"valid": True, "path": str(target)}
    except (py_compile.PyCompileError, SyntaxError, OSError, ValueError) as exc:
        return {"valid": False, "path": str(target), "error": str(exc)}
