#!/usr/bin/env python3
"""AI-Native File Manager for GenAgent.

Provides workspace analytics, visual trees, smart deduplication,
junk cleanup, and JSON output for AI decision-making.
100% Python Standard Library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from config import settings


class TerminalTheme:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and sys.stdout.isatty()
        self.bold = "\033[1m" if self.enabled else ""
        self.cyan = "\033[36m" if self.enabled else ""
        self.green = "\033[32m" if self.enabled else ""
        self.yellow = "\033[33m" if self.enabled else ""
        self.red = "\033[31m" if self.enabled else ""
        self.magenta = "\033[35m" if self.enabled else ""
        self.blue = "\033[34m" if self.enabled else ""
        self.gray = "\033[90m" if self.enabled else ""
        self.reset = "\033[0m" if self.enabled else ""

    def paint(self, color: str, text: str) -> str:
        return f"{color}{text}{self.reset}" if self.enabled else str(text)


t = TerminalTheme()


def format_size(bytes_val: int) -> str:
    """Format bytes into readable human size."""
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.1f}KB"
    elif bytes_val < 1024 * 1024 * 1024:
        return f"{bytes_val / (1024 * 1024):.1f}MB"
    return f"{bytes_val / (1024 * 1024 * 1024):.1f}GB"


def get_file_icon(path: Path) -> str:
    """Return an icon/emoji for the file type."""
    if path.is_dir():
        return "📁"
    ext = path.suffix.lower()
    icon_map = {
        ".py": "🐍",
        ".sh": "🐚",
        ".bash": "🐚",
        ".md": "📝",
        ".txt": "📄",
        ".json": "⚙️",
        ".yaml": "⚙️",
        ".yml": "⚙️",
        ".toml": "⚙️",
        ".env": "🔒",
        ".sqlite3": "🗄️",
        ".db": "🗄️",
        ".zip": "📦",
        ".tar": "📦",
        ".gz": "📦",
        ".png": "🖼️",
        ".jpg": "🖼️",
        ".jpeg": "🖼️",
        ".svg": "🎨",
        ".html": "🌐",
        ".css": "🎨",
        ".js": "📜",
        ".ts": "📜",
    }
    return icon_map.get(ext, "📄")


class AIFileManager:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.workspace).expanduser().resolve()

    def _is_excluded(self, path: Path, ignore_hidden: bool = True) -> bool:
        """Check if path is inside ignored folders like .git or __pycache__."""
        for part in path.parts:
            if part in {"__pycache__", ".pytest_cache", ".git", "venv", ".venv"}:
                return True
            if ignore_hidden and part.startswith(".") and part not in {".env.example"}:
                return True
        return False

    def tree(self, max_depth: int = 3, show_hidden: bool = False) -> dict[str, Any]:
        """Generate directory tree structure."""
        result: dict[str, Any] = {
            "root": str(self.root),
            "directories": 0,
            "files": 0,
            "total_size": 0,
            "tree": []
        }

        def build_tree(current_dir: Path, current_depth: int, prefix: str = ""):
            if current_depth > max_depth:
                return
            try:
                entries = sorted(list(current_dir.iterdir()), key=lambda e: (not e.is_dir(), e.name.lower()))
            except (PermissionError, OSError):
                return

            filtered = [
                e for e in entries
                if (show_hidden or not e.name.startswith(".")) and e.name not in {"__pycache__", ".git"}
            ]

            for idx, entry in enumerate(filtered):
                is_last = (idx == len(filtered) - 1)
                connector = "└── " if is_last else "├── "
                sub_prefix = "    " if is_last else "│   "

                if entry.is_dir():
                    result["directories"] += 1
                    result["tree"].append(f"{prefix}{connector}{get_file_icon(entry)} {t.paint(t.bold + t.cyan, entry.name)}/")
                    build_tree(entry, current_depth + 1, prefix + sub_prefix)
                else:
                    result["files"] += 1
                    size = entry.stat().st_size
                    result["total_size"] += size
                    size_str = t.paint(t.gray, f"({format_size(size)})")
                    result["tree"].append(f"{prefix}{connector}{get_file_icon(entry)} {entry.name} {size_str}")

        build_tree(self.root, 1)
        return result

    def summary(self) -> dict[str, Any]:
        """Provide comprehensive workspace analytics (code lines, size, extensions)."""
        stats: dict[str, Any] = {
            "workspace": str(self.root),
            "total_files": 0,
            "total_directories": 0,
            "total_bytes": 0,
            "total_code_lines": 0,
            "by_extension": {},
            "largest_files": [],
        }
        all_files: list[tuple[Path, int]] = []

        for p in self.root.rglob("*"):
            if self._is_excluded(p, ignore_hidden=True):
                continue
            if p.is_dir():
                stats["total_directories"] += 1
            elif p.is_file():
                try:
                    size = p.stat().st_size
                    stats["total_files"] += 1
                    stats["total_bytes"] += size
                    all_files.append((p, size))

                    ext = p.suffix.lower() or "(no-ext)"
                    if ext not in stats["by_extension"]:
                        stats["by_extension"][ext] = {"count": 0, "bytes": 0, "lines": 0}
                    stats["by_extension"][ext]["count"] += 1
                    stats["by_extension"][ext]["bytes"] += size

                    # Count lines for text/code files
                    if ext in {".py", ".sh", ".json", ".md", ".txt", ".yaml", ".yml", ".html", ".js", ".ts", ".css"}:
                        try:
                            lines = len(p.read_text(encoding="utf-8", errors="ignore").splitlines())
                            stats["by_extension"][ext]["lines"] += lines
                            stats["total_code_lines"] += lines
                        except Exception:
                            pass
                except (OSError, PermissionError):
                    continue

        all_files.sort(key=lambda item: item[1], reverse=True)
        stats["largest_files"] = [
            {"path": str(f[0].relative_to(self.root)), "size": format_size(f[1]), "bytes": f[1]}
            for f in all_files[:8]
        ]
        stats["total_size_human"] = format_size(stats["total_bytes"])
        return stats

    def find_duplicates(self) -> dict[str, Any]:
        """Find identical duplicate files using SHA256 checksums."""
        hashes: dict[str, list[str]] = {}
        for p in self.root.rglob("*"):
            if not p.is_file() or self._is_excluded(p):
                continue
            try:
                # Fast check for files > 0 bytes
                if p.stat().st_size == 0:
                    continue
                hasher = hashlib.sha256()
                with p.open("rb") as f:
                    while chunk := f.read(65536):
                        hasher.update(chunk)
                h = hasher.hexdigest()
                hashes.setdefault(h, []).append(str(p.relative_to(self.root)))
            except (OSError, PermissionError):
                continue

        duplicates = {h: paths for h, paths in hashes.items() if len(paths) > 1}
        return {
            "duplicate_groups": len(duplicates),
            "duplicates": duplicates
        }

    def clean_junk(self, dry_run: bool = True) -> dict[str, Any]:
        """Find and optionally delete orphaned temp files (__pycache__, .pyc, .bak, .tmp)."""
        junk_patterns = ["*.pyc", "*.pyo", "*.bak", "*.tmp", "*~"]
        junk_dirs = ["__pycache__", ".pytest_cache"]
        found_files: list[str] = []
        found_dirs: list[str] = []
        bytes_reclaimed = 0

        # Find junk files
        for pat in junk_patterns:
            for p in self.root.rglob(pat):
                try:
                    if p.is_file():
                        bytes_reclaimed += p.stat().st_size
                        found_files.append(str(p.relative_to(self.root)))
                        if not dry_run:
                            p.unlink(missing_ok=True)
                except (OSError, PermissionError):
                    continue

        # Find junk directories
        for dname in junk_dirs:
            for d in self.root.rglob(dname):
                try:
                    if d.is_dir():
                        found_dirs.append(str(d.relative_to(self.root)))
                        if not dry_run:
                            shutil.rmtree(d, ignore_errors=True)
                except (OSError, PermissionError):
                    continue

        return {
            "dry_run": dry_run,
            "junk_files_found": len(found_files),
            "junk_dirs_found": len(found_dirs),
            "reclaimed_bytes": bytes_reclaimed,
            "reclaimed_human": format_size(bytes_reclaimed),
            "files": found_files,
            "directories": found_dirs,
            "action": "Preview only (run with --do-clean to delete)" if dry_run else "Cleaned successfully"
        }

    def search(self, query: str, content: bool = False, max_results: int = 30) -> list[dict[str, Any]]:
        """Search files by name or search inside text file contents."""
        q = (query or "").lower().strip()
        results: list[dict[str, Any]] = []

        for p in self.root.rglob("*"):
            if not p.is_file() or self._is_excluded(p):
                continue
            rel = str(p.relative_to(self.root))
            match_name = q in p.name.lower() or q in rel.lower()

            if match_name:
                results.append({"path": rel, "match_type": "filename", "size": format_size(p.stat().st_size)})
                if len(results) >= max_results:
                    break
                continue

            if content:
                ext = p.suffix.lower()
                if ext in {".py", ".sh", ".md", ".txt", ".json", ".yaml", ".yml", ".html", ".css", ".js"}:
                    try:
                        text = p.read_text(encoding="utf-8", errors="ignore")
                        if q in text.lower():
                            # Find matching line
                            matched_lines = [line.strip() for line in text.splitlines() if q in line.lower()][:2]
                            results.append({
                                "path": rel,
                                "match_type": "content",
                                "snippets": matched_lines,
                                "size": format_size(p.stat().st_size)
                            })
                            if len(results) >= max_results:
                                break
                    except Exception:
                        continue
        return results

    def pack(self, output_path: str = "workspace_backup.zip") -> dict[str, Any]:
        """Pack the workspace into a clean, sanitized zip file."""
        import zipfile
        out = Path(output_path).expanduser().resolve()
        count = 0
        total_size = 0

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for p in self.root.rglob("*"):
                if not p.is_file() or self._is_excluded(p, ignore_hidden=True):
                    continue
                if p.name in {".env", "agent.log", "db.sqlite3"} or p.suffix in {".pyc", ".db"}:
                    continue
                rel = p.relative_to(self.root)
                z.write(p, arcname=str(rel))
                count += 1
                total_size += p.stat().st_size

        return {
            "ok": True,
            "archive": str(out),
            "packed_files": count,
            "archive_size": format_size(out.stat().st_size),
            "uncompressed_size": format_size(total_size),
        }


# =====================================================================
# CLI Entrypoint
# =====================================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="GenAgent AI-Native File Manager")
    parser.add_argument("command", nargs="?", default="summary", choices=["summary", "tree", "clean", "find", "duplicates", "pack"], help="File manager command")
    parser.add_argument("--query", "-q", help="Search query for 'find'")
    parser.add_argument("--content", "-c", action="store_true", help="Search inside file contents")
    parser.add_argument("--depth", "-d", type=int, default=3, help="Max depth for 'tree'")
    parser.add_argument("--do-clean", action="store_true", help="Perform actual deletion for 'clean'")
    parser.add_argument("--out", "-o", default="workspace_clean.zip", help="Output file for 'pack'")
    parser.add_argument("--json", action="store_true", help="Output in machine-readable JSON format for AI")
    parser.add_argument("--path", "-p", default=".", help="Target workspace path")

    args = parser.parse_args()
    fm = AIFileManager(args.path)

    if args.command == "summary":
        res = fm.summary()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(t.paint(t.bold + t.cyan, "\n=== WORKSPACE ANALYTICS ==="))
            print(f"  {t.paint(t.gray, 'Workspace:')}    {res['workspace']}")
            print(f"  {t.paint(t.gray, 'Files:')}        {t.paint(t.green, str(res['total_files']))} across {res['total_directories']} directories")
            print(f"  {t.paint(t.gray, 'Disk Usage:')}   {t.paint(t.yellow, res['total_size_human'])}")
            code_lines = f"{res['total_code_lines']:,}"
            print(f"  {t.paint(t.gray, 'Code Lines:')}   {t.paint(t.cyan, code_lines)} total lines\n")

            print(t.paint(t.bold + t.green, "  File Breakdown by Type:"))
            for ext, d in sorted(res["by_extension"].items(), key=lambda i: i[1]["bytes"], reverse=True)[:8]:
                lines_info = f"({d['lines']:,} lines)" if d['lines'] else ""
                print(f"    {t.paint(t.cyan, f'{ext:<10}')} {d['count']:>3} files  · {format_size(d['bytes']):>8}  {t.paint(t.gray, lines_info)}")

            print(t.paint(t.bold + t.yellow, "\n  Largest Files:"))
            for f in res["largest_files"][:5]:
                print(f"    {f['size']:>8}  {f['path']}")
            print()

    elif args.command == "tree":
        res = fm.tree(max_depth=args.depth)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(t.paint(t.bold + t.cyan, f"\n📁 {res['root']}"))
            for line in res["tree"]:
                print(f"  {line}")
            print(t.paint(t.gray, f"\n  Total: {res['files']} files, {res['directories']} directories ({format_size(res['total_size'])})\n"))

    elif args.command == "clean":
        res = fm.clean_junk(dry_run=not args.do_clean)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(t.paint(t.bold + t.yellow, "\n=== JUNK CLEANUP ==="))
            print(f"  Status: {res['action']}")
            print(f"  Found:  {res['junk_files_found']} junk files, {res['junk_dirs_found']} cache dirs")
            print(f"  Space:  {res['reclaimed_human']} reclaimable\n")
            if res["files"]:
                for f in res["files"][:8]:
                    print(f"    {t.paint(t.gray, f)}")
            print()

    elif args.command == "find":
        if not args.query:
            print(t.paint(t.red, "Error: --query is required for 'find' command"))
            sys.exit(1)
        res = fm.search(args.query, content=args.content)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(t.paint(t.bold + t.cyan, f"\n=== SEARCH RESULTS FOR '{args.query}' ({len(res)} matches) ==="))
            for r in res:
                sz_str = f"({r['size']})"
                print(f"  {t.paint(t.green, r['path'])}  {t.paint(t.gray, sz_str)}")
                if "snippets" in r:
                    for s in r["snippets"]:
                        print(f"    {t.paint(t.gray, '↳ ' + s[:100])}")
            print()

    elif args.command == "duplicates":
        res = fm.find_duplicates()
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(t.paint(t.bold + t.cyan, f"\n=== DUPLICATE FILES ({res['duplicate_groups']} groups) ==="))
            if not res["duplicates"]:
                print(t.paint(t.green, "  ✓ No duplicate files found! Clean workspace."))
            else:
                for h, paths in res["duplicates"].items():
                    print(f"  {t.paint(t.yellow, 'Hash ' + h[:12] + '...')}")
                    for p in paths:
                        print(f"    - {p}")
            print()

    elif args.command == "pack":
        res = fm.pack(args.out)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(t.paint(t.bold + t.green, f"\n✓ Workspace packed to {res['archive']}"))
            print(f"  Packed {res['packed_files']} files ({res['archive_size']})\n")


if __name__ == "__main__":
    main()
