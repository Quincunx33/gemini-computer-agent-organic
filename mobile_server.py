from __future__ import annotations

import argparse
import json
import secrets
import ssl
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent_loop import AgentLoop
from config import settings
from errors import AgentError, error_payload, normalize_exception, traceback_text
from logger import get_logger
from platform_support import capabilities
from security import AuditLogger, RateLimiter


log = get_logger("genagent.mobile")


class CommandHandler(BaseHTTPRequestHandler):
    server_version = "GenAgentMobile/2.0"

    def _request_id(self) -> str:
        return getattr(self, "request_id", "unknown")

    def _audit(self, event: str, **fields: Any) -> None:
        logger = getattr(self.server, "audit", None)
        if logger:
            try:
                logger.write(event, request_id=self._request_id(), ip=self.client_address[0], **fields)
            except Exception:
                log.exception("audit write failed request_id=%s", self._request_id())

    def _guard(self) -> bool:
        limiter = getattr(self.server, "limiter", None)
        if limiter and not limiter.allow(self.client_address[0]):
            self._audit("rate_limited")
            self._send(429, {"error": {"code": "RATE_LIMITED", "message": "Too many requests; try again later", "retryable": True, "error_id": self._request_id()}})
            return False
        return True

    def _authorized(self) -> bool:
        expected = getattr(self.server, "agent_token", "")
        supplied = self.headers.get("Authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[7:]
        valid = bool(expected) and secrets.compare_digest(supplied, expected)
        self._audit("auth_success" if valid else "auth_failure", endpoint=self.path)
        return valid

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Request-ID", self._request_id())
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            log.info("client disconnected before response request_id=%s", self._request_id())

    def _begin(self) -> bool:
        self.request_id = uuid.uuid4().hex[:16]
        return self._guard()

    def do_GET(self) -> None:
        if not self._begin():
            return
        if self.path != "/capabilities":
            self._audit("not_found", endpoint=self.path)
            self._send(404, {"error": {"code": "NOT_FOUND", "message": "Not found", "error_id": self._request_id()}})
            return
        try:
            self._audit("capabilities")
            self._send(200, {"ok": True, "request_id": self._request_id(), "capabilities": capabilities()})
        except Exception as exc:
            self._handle_error(exc, "capabilities")

    def do_POST(self) -> None:
        if not self._begin():
            return
        if self.path != "/command":
            self._audit("not_found", endpoint=self.path)
            self._send(404, {"error": {"code": "NOT_FOUND", "message": "Not found", "error_id": self._request_id()}})
            return
        if not self._authorized():
            self._send(401, {"error": {"code": "UNAUTHORIZED", "message": "Bearer token required", "error_id": self._request_id()}})
            return
        try:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise AgentError("INVALID_REQUEST", "Content-Length is required", "Content-Length is required.", False, 411)
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise AgentError("INVALID_REQUEST", "Content-Length must be an integer", "Invalid request length.", False, 400) from exc
            if length < 1:
                raise AgentError("INVALID_REQUEST", "Request body is empty", "Request body is required.", False, 400)
            if length > settings.mobile_max_body:
                self._send(413, {"error": {"code": "PAYLOAD_TOO_LARGE", "message": f"Request body exceeds {settings.mobile_max_body} bytes", "error_id": self._request_id()}})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise AgentError("INVALID_REQUEST", "Request body was truncated", "Request body was truncated.", False, 400)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AgentError("INVALID_JSON", "Request body is not valid UTF-8 JSON", "Request body must be valid JSON.", False, 400) from exc
            if not isinstance(body, dict):
                raise AgentError("INVALID_REQUEST", "Request JSON must be an object", "Request JSON must be an object.", False, 400)
            task = body.get("task")
            if not isinstance(task, str):
                raise AgentError("INVALID_REQUEST", "task must be a string", "task must be a string.", False, 400)
            task = task.strip()
            if not task or len(task) > 4000:
                raise AgentError("INVALID_REQUEST", "task must be 1-4000 characters", "task must be 1-4000 characters.", False, 400)
            self._audit("command_start", task=task[:200])
            output: list[str] = []
            result = AgentLoop(output=output.append).run(task)
            self._audit("command_complete", result=str(result)[:200])
            self._send(200, {"ok": True, "request_id": self._request_id(), "result": result, "events": output[-100:]})
        except AgentError as exc:
            self._audit("bad_request" if exc.status < 500 else "command_error", code=exc.code, error_id=exc.error_id)
            self._send(exc.status, exc.to_dict())
        except Exception as exc:
            err = normalize_exception(exc, operation="mobile command")
            self._audit("command_error", code=err.code, error_id=err.error_id, diagnostic=traceback_text(exc))
            self._send(err.status, err.to_dict())

    def _handle_error(self, exc: BaseException, operation: str) -> None:
        err = normalize_exception(exc, operation=operation)
        self._audit("request_error", code=err.code, error_id=err.error_id)
        self._send(err.status, error_payload(err))

    def log_message(self, *_args: Any) -> None:
        return


def _is_loopback(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Token-protected mobile command bridge")
    parser.add_argument("--host", default="127.0.0.1", help="Use 0.0.0.0 only with TLS on a trusted LAN")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="", help="Bearer token; generated if omitted")
    parser.add_argument("--certfile", default="", help="TLS certificate PEM for non-loopback use")
    parser.add_argument("--keyfile", default="", help="TLS private key PEM for non-loopback use")
    parser.add_argument("--audit-log", default=str(settings.audit_log_path))
    args = parser.parse_args()
    if bool(args.certfile) != bool(args.keyfile):
        parser.error("--certfile and --keyfile must be provided together")
    if not _is_loopback(args.host) and not (args.certfile and args.keyfile):
        parser.error("Non-loopback binding requires --certfile and --keyfile (HTTPS)")
    token = args.token or secrets.token_urlsafe(32)
    server = ThreadingHTTPServer((args.host, args.port), CommandHandler)
    server.agent_token = token  # type: ignore[attr-defined]
    server.limiter = RateLimiter(settings.mobile_rate_limit, settings.mobile_rate_window)  # type: ignore[attr-defined]
    server.audit = AuditLogger(Path(args.audit_log))  # type: ignore[attr-defined]
    scheme = "https" if args.certfile else "http"
    if args.certfile:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.certfile, args.keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
    print(f"Mobile bridge listening on {scheme}://{args.host}:{args.port}")
    print(f"Bearer token: {token}")
    print(f"Audit log: {args.audit_log}")
    print("Keep the token and private key private.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mobile bridge.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
