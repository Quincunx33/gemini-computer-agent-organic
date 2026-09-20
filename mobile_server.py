from __future__ import annotations

import argparse
import json
import secrets
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from agent_loop import AgentLoop
from config import settings
from platform_support import capabilities
from security import AuditLogger, RateLimiter


class CommandHandler(BaseHTTPRequestHandler):
    server_version = "GeminiAgentMobile/1.1"

    def _audit(self, event: str, **fields: Any) -> None:
        logger = getattr(self.server, "audit", None)
        if logger:
            logger.write(event, ip=self.client_address[0], **fields)

    def _guard(self) -> bool:
        limiter = getattr(self.server, "limiter", None)
        if limiter and not limiter.allow(self.client_address[0]):
            self._audit("rate_limited")
            self._send(429, {"error": "Too many requests; try again later"})
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
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        if not self._guard():
            return
        if self.path != "/capabilities":
            self._audit("not_found", endpoint=self.path)
            self._send(404, {"error": "Not found"})
            return
        self._audit("capabilities")
        self._send(200, {"ok": True, "capabilities": capabilities()})

    def do_POST(self) -> None:
        if not self._guard():
            return
        if self.path != "/command":
            self._audit("not_found", endpoint=self.path)
            self._send(404, {"error": "Not found"})
            return
        if not self._authorized():
            self._send(401, {"error": "Bearer token required"})
            return
        try:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                raise ValueError("Content-Length is required")
            length = int(raw_length)
            if length < 1 or length > settings.mobile_max_body:
                self._send(413, {"error": f"Request body exceeds {settings.mobile_max_body} bytes"})
                return
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            task = str(body.get("task", "")).strip()
            if not task or len(task) > 4000:
                raise ValueError("task must be 1-4000 characters")
            self._audit("command_start", task=task[:200])
            output: list[str] = []
            result = AgentLoop(output=output.append).run(task)
            self._audit("command_complete", result=str(result)[:200])
            self._send(200, {"ok": True, "result": result, "events": output[-100:]})
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._audit("bad_request", error=str(exc))
            self._send(400, {"error": str(exc)})
        except Exception as exc:
            self._audit("command_error", error=str(exc))
            self._send(500, {"error": "Internal agent error"})

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
