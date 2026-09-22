from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


HTML = """<!doctype html><meta charset=utf-8><title>GenAgent Dashboard</title><style>body{font:16px system-ui;max-width:900px;margin:40px auto}pre{background:#111;color:#eee;padding:16px;border-radius:8px}</style><h1>GenAgent dashboard</h1><p>Live task controller status</p><pre id=s>loading…</pre><script>async function refresh(){const r=await fetch('/status');document.querySelector('#s').textContent=JSON.stringify(await r.json(),null,2)}setInterval(refresh,1000);refresh()</script>"""


def make_handler(controller):
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                body = HTML.encode()
                self.send_response(200); self.send_header("Content-Type", "text/html"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            elif self.path == "/status":
                body = json.dumps(controller.status_info(), default=str).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            else:
                self.send_response(404); self.end_headers()
        def log_message(self, *_args):
            return
    return DashboardHandler
