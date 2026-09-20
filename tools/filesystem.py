from pathlib import Path
import shutil
from config import settings
def safe_path(path: str, allow_outside=False) -> Path:
    p=Path(path).expanduser(); p=(p if p.is_absolute() else settings.workspace/p).resolve()
    if not allow_outside and p != settings.workspace and settings.workspace not in p.parents: raise PermissionError(f"Path outside workspace: {p}")
    return p
def list_directory(path="."): return [p.name for p in safe_path(path).iterdir()]
def read_file(path):
    p = safe_path(path)
    if p.stat().st_size > settings.max_file_size:
        raise ValueError(f"File exceeds MAX_FILE_SIZE ({settings.max_file_size} bytes): {p}")
    return p.read_text(encoding="utf-8")
def write_file(path, content, allow_outside=False):
    if len(content.encode("utf-8")) > settings.max_file_size:
        raise ValueError(f"Content exceeds MAX_FILE_SIZE ({settings.max_file_size} bytes)")
    p=safe_path(path,allow_outside); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding="utf-8"); return str(p)
def append_file(path, content):
    p=safe_path(path); p.parent.mkdir(parents=True,exist_ok=True); p.open("a",encoding="utf-8").write(content); return str(p)
def create_directory(path): p=safe_path(path); p.mkdir(parents=True,exist_ok=True); return str(p)
def move_file(src,dst): shutil.move(str(safe_path(src)),str(safe_path(dst))); return str(safe_path(dst))
def copy_file(src,dst): shutil.copy2(safe_path(src),safe_path(dst)); return str(safe_path(dst))
def delete_file(path, approved=False):
    p=safe_path(path)
    if not approved: raise PermissionError("delete_file requires explicit approval")
    if p.is_dir(): shutil.rmtree(p)
    else: p.unlink()
def search_files(pattern, path="."): return [str(p) for p in safe_path(path).rglob(pattern)]
