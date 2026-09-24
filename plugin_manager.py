from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from config import settings


class PluginError(ValueError):
    pass


class PluginManager:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.workspace / "plugins").resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def install_zip(self, archive: str) -> dict[str, Any]:
        path = Path(archive).expanduser().resolve()
        if not path.is_file() or not zipfile.is_zipfile(path):
            raise PluginError("plugin archive is not a valid zip file")
        with zipfile.ZipFile(path) as bundle:
            members = bundle.infolist()
            if len(members) > 500:
                raise PluginError("plugin contains too many files")
            for member in members:
                name = Path(member.filename)
                if name.is_absolute() or ".." in name.parts:
                    raise PluginError("plugin contains an unsafe path")
                if member.file_size > settings.max_file_size:
                    raise PluginError(f"plugin file exceeds MAX_FILE_SIZE: {member.filename}")
            manifest_member = next((m for m in members if Path(m.filename).name == "plugin.json"), None)
            if not manifest_member:
                raise PluginError("plugin.json manifest is required")
            manifest = json.loads(bundle.read(manifest_member).decode("utf-8"))
            name = str(manifest.get("name", "")).strip()
            version = str(manifest.get("version", "")).strip()
            permissions = manifest.get("permissions", {})
            if not isinstance(permissions, dict):
                raise PluginError("manifest permissions must be an object")
            if manifest.get("auto_execute") is True:
                raise PluginError("plugins cannot request automatic code execution")
            if not name or not version or not all(char.isalnum() or char in "-_" for char in name):
                raise PluginError("manifest requires a safe name and version")
            target = self.root / name
            with tempfile.TemporaryDirectory(dir=self.root) as temp:
                staging = Path(temp) / name
                bundle.extractall(staging)
                target_tmp = self.root / f".{name}.staging"
                if target_tmp.exists():
                    shutil.rmtree(target_tmp)
                shutil.move(str(staging), target_tmp)
                if target.exists():
                    shutil.rmtree(target)
                target_tmp.rename(target)
            return {"ok": True, "name": name, "version": version, "path": str(target), "executed": False, "trusted": False, "requires_review": True, "permissions": permissions, "manifest": manifest}
