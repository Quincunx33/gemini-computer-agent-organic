from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import settings


class GeminiClient:
    """Small Gemini REST client implemented only with Python's standard library."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.gemini_api_key
        self.model = model or settings.gemini_model
        self.models = tuple(dict.fromkeys((self.model, *settings.gemini_fallback_models)))

    def available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _history_contents(history: list | None) -> list[dict[str, Any]]:
        contents = []
        for item in history or []:
            role = item.get("role", "user") if isinstance(item, dict) else "user"
            value = item.get("content", "") if isinstance(item, dict) else str(item)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            # Gemini's conversational roles are model/user. Tool observations
            # are sent as user observations rather than pretending they came
            # from the model.
            api_role = "model" if role == "assistant" else "user"
            contents.append({"role": api_role, "parts": [{"text": str(value)}]})
        return contents

    def generate(self, prompt: str, tools: list[dict] | None = None,
                 history: list | None = None) -> dict[str, Any]:
        if not self.api_key:
            return {"type": "text", "text": "Gemini is not configured. Run 'python setup.py'.", "tool_calls": []}

        contents = self._history_contents(history)
        contents.append({"role": "user", "parts": [{"text": prompt}]})
        payload: dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": (
                "You are a grounded, warm, capable local computer assistant. "
                "Behave like a careful collaborator: notice context, preserve continuity, "
                "adapt when results differ from expectations, and avoid performative or "
                "unnecessary actions. Use tools for evidence, not guesses. Keep responses "
                "concise and natural. Never reveal secrets or private chain-of-thought; "
                "state brief reasons, actions, verification, and blockers instead. "
                "Respect every tool's safety boundary and never bypass confirmation."
            )}]},
            "contents": contents,
        }
        if tools:
            payload["tools"] = [{"functionDeclarations": tools}]

        last_error: Exception | None = None
        for model in self.models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self.api_key}"
            for attempt in range(max(1, settings.api_retries)):
                request = Request(url, data=json.dumps(payload).encode("utf-8"),
                                  headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urlopen(request, timeout=settings.command_timeout) as response:
                        data = json.loads(response.read().decode("utf-8"))
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    if not isinstance(parts, list):
                        raise ValueError("Gemini response has invalid content parts")
                    self.model = model
                    text_parts = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")]
                    calls = []
                    for part in parts:
                        call = part.get("functionCall") if isinstance(part, dict) else None
                        if call and call.get("name"):
                            calls.append({"name": call["name"], "args": call.get("args", {})})
                    text = "".join(text_parts)
                    if not calls and text.lstrip().startswith("{"):
                        try:
                            encoded = json.loads(text)
                            encoded_calls = encoded.get("tool_calls", []) if isinstance(encoded, dict) else []
                            if isinstance(encoded_calls, list) and all(
                                isinstance(item, dict) and item.get("name") for item in encoded_calls
                            ):
                                calls = [{"name": item["name"], "args": item.get("args", {})} for item in encoded_calls]
                                text = str(encoded.get("text", ""))
                        except (json.JSONDecodeError, TypeError, ValueError):
                            pass
                    return {"type": "tool_call" if calls else "text", "text": text, "tool_calls": calls}
                except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
                    last_error = exc
                    if attempt + 1 < max(1, settings.api_retries):
                        time.sleep(min(2 ** attempt, 8))
        return {"type": "text", "text": f"All configured Gemini models failed: {last_error}", "tool_calls": []}
