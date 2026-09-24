from __future__ import annotations

import base64
import json
import mimetypes
import urllib.request
from typing import Any

from config import settings
from tools.filesystem import safe_path


def inspect_image(path: str, prompt: str = "Describe what is shown in this image, including any text, UI elements, or errors.") -> dict[str, Any]:
    """Inspect and understand an image using Gemini's native vision without third-party dependencies."""
    target = safe_path(path)
    if not target.is_file():
        return {"ok": False, "error": f"Image file not found: {target}"}

    mime_type, _ = mimetypes.guess_type(str(target))
    if not mime_type or not mime_type.startswith("image/"):
        suffix = target.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            mime_type = "image/png" if suffix == ".png" else f"image/{suffix.strip('.')}"
        else:
            return {"ok": False, "error": f"Unsupported image format: {target.name}"}

    try:
        raw_bytes = target.read_bytes()
        if len(raw_bytes) > 20 * 1024 * 1024:
            return {"ok": False, "error": "Image file exceeds 20MB limit"}
        b64_data = base64.b64encode(raw_bytes).decode("ascii")

        models = [settings.gemini_model, *settings.gemini_fallback_models]
        last_error = None
        for model in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={settings.gemini_api_key}"
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {"inlineData": {"mimeType": mime_type, "data": b64_data}}
                    ]
                }]
            }
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    analysis = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    return {"ok": True, "path": str(target), "model": model, "analysis": analysis}
            except Exception as exc:
                last_error = exc
                continue
        return {"ok": False, "error": f"Vision failed on all models: {last_error}", "path": str(target)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "path": str(target)}
