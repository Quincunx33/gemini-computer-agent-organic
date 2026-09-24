from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import settings
from errors import AgentError


PROVIDERS = {
    "openai": ("openai_api_key", "openai_model", "openai_fallback_models", "openai_base_url"),
    "xai": ("xai_api_key", "xai_model", "xai_fallback_models", "xai_base_url"),
    "deepseek": ("deepseek_api_key", "deepseek_model", "deepseek_fallback_models", "deepseek_base_url"),
}


class OpenAICompatibleClient:
    def __init__(self, provider: str, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        if provider not in PROVIDERS:
            raise ValueError(f"Unsupported provider: {provider}")
        key_name, model_name, fallback_name, url_name = PROVIDERS[provider]
        self.provider = provider
        self.api_key = api_key if api_key is not None else getattr(settings, key_name)
        self.model = model or getattr(settings, model_name)
        self.base_url = (base_url or getattr(settings, url_name)).rstrip("/")
        self.models = tuple(dict.fromkeys((self.model, *getattr(settings, fallback_name))))

    def available(self) -> bool:
        return bool(self.api_key)

    def set_task_route(self, task: str) -> None:
        pass

    @staticmethod
    def _messages(prompt: str, history: list | None) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": "You are a grounded local computer assistant. Use tools for evidence, respect safety boundaries, and never reveal secrets or private chain-of-thought."}]
        for item in history or []:
            if not isinstance(item, dict):
                continue
            role = item.get("role", "user")
            is_tool = role == "tool"
            role = "assistant" if role in {"assistant", "model"} else "user"
            content = item.get("content", "")
            if isinstance(content, (dict, list)):
                content = json.dumps(content, ensure_ascii=False)
            if is_tool:
                content = "[Tool result]\n" + str(content)
            messages.append({"role": role, "content": str(content)[:12000]})
        messages.append({"role": "user", "content": prompt[:settings.max_prompt_chars]})
        return messages

    @staticmethod
    def _tools(tools: list[dict] | None) -> list[dict]:
        return [{"type": "function", "function": {"name": item["name"], "description": item.get("description", ""), "parameters": item.get("parameters", {"type": "object", "properties": {}})}} for item in tools or []]

    @staticmethod
    def parse_response(data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValueError(f"{data.get('error') or 'provider response has no choices'}")
        message = choices[0].get("message", {})
        text = message.get("content") or ""
        calls = []
        for call in message.get("tool_calls", []) or []:
            function = call.get("function", {}) if isinstance(call, dict) else {}
            name = function.get("name")
            if not name:
                continue
            raw_args = function.get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    raw_args = {}
            calls.append({"name": str(name), "args": raw_args if isinstance(raw_args, dict) else {}})
        if not calls and isinstance(text, str) and text.lstrip().startswith("{"):
            try:
                encoded = json.loads(text)
                calls = [{"name": item["name"], "args": item.get("args", {})} for item in encoded.get("tool_calls", []) if isinstance(item, dict) and item.get("name")]
                if calls:
                    text = encoded.get("text", "")
            except (ValueError, TypeError):
                pass
        return {"type": "tool_call" if calls else "text", "text": str(text), "tool_calls": calls}

    def generate(self, prompt: str, tools: list[dict] | None = None, history: list | None = None, cancel_event=None) -> dict[str, Any]:
        if not self.api_key:
            return {"type": "error", "text": f"{self.provider} API key is not configured. Run 'python setup.py'.", "tool_calls": [], "error": {"code": "NOT_CONFIGURED"}}
        if cancel_event is not None and cancel_event.is_set():
            return {"type": "cancelled", "text": "Request cancelled.", "tool_calls": [], "error": {"code": "CANCELLED"}}
        last_error = None
        for model in self.models:
            payload: dict[str, Any] = {"model": model, "messages": self._messages(prompt, history), "temperature": 0.2}
            if tools:
                payload["tools"] = self._tools(tools)
                payload["tool_choice"] = "auto"
            request = Request(self.base_url + "/chat/completions", data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}, method="POST")
            try:
                with urlopen(request, timeout=settings.command_timeout) as response:
                    raw = response.read(settings.max_api_response_bytes)
                result = self.parse_response(json.loads(raw.decode("utf-8")))
                self.model = model
                return result
            except HTTPError as exc:
                if exc.code in {401, 403}:
                    return {"type": "error", "text": f"{self.provider} authentication failed.", "tool_calls": [], "error": {"code": "API_AUTH_ERROR", "http_status": exc.code}}
                last_error = {"type": "error", "text": f"{self.provider} model {model} failed (HTTP {exc.code}).", "tool_calls": [], "error": {"code": "API_HTTP_ERROR", "http_status": exc.code}}
            except (URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
                last_error = {"type": "error", "text": f"{self.provider} model {model} failed: {type(exc).__name__}.", "tool_calls": [], "error": {"code": "API_REQUEST_ERROR"}}
        return last_error or {"type": "error", "text": f"No {self.provider} model is available.", "tool_calls": [], "error": {"code": "API_UNAVAILABLE"}}


def build_llm_client():
    from gemini_client import GeminiClient
    providers = [settings.llm_provider, *settings.llm_fallback_providers]
    clients = []
    for provider in dict.fromkeys(providers):
        if provider == "gemini" and settings.gemini_api_key:
            clients.append(GeminiClient())
        elif provider in PROVIDERS and getattr(settings, PROVIDERS[provider][0], ""):
            clients.append(OpenAICompatibleClient(provider))
    if len(clients) > 1:
        return MultiProviderClient(clients)
    if clients:
        return clients[0]
    if settings.llm_provider in PROVIDERS:
        return OpenAICompatibleClient(settings.llm_provider)
    return GeminiClient()


class MultiProviderClient:
    def __init__(self, clients):
        self.clients = clients
        self.active = clients[0]

    def set_task_route(self, task: str) -> None:
        for client in self.clients:
            client.set_task_route(task)

    def generate(self, prompt, tools=None, history=None, cancel_event=None):
        last = None
        for client in self.clients:
            result = client.generate(prompt, tools, history, cancel_event=cancel_event)
            if result.get("type") != "error":
                self.active = client
                return result
            last = result
        return last or {"type": "error", "text": "No configured LLM provider is available.", "tool_calls": [], "error": {"code": "NOT_CONFIGURED"}}
