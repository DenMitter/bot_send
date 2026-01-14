from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from app.services.auth_registry import auth_flow_manager


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not self.path.startswith("/auth/"):
            self.send_response(404)
            self.end_headers()
            return

        token = self.path.split("/auth/")[-1].strip()
        html = _render_form(token)
        self._send_html(html)

    def do_POST(self):
        if not self.path.startswith("/auth/"):
            self.send_response(404)
            self.end_headers()
            return

        token = self.path.split("/auth/")[-1].strip()
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")
        data = parse_qs(raw)
        code = (data.get("code") or [None])[0]
        password = (data.get("password") or [None])[0]
        ok = auth_flow_manager.submit_web(token, code, password)
        html = _render_result(ok)
        self._send_html(html)

    def log_message(self, format, *args):
        return

    def _send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))


def _render_form(token: str) -> str:
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<title>Auth</title>
<style>
body {{ font-family: Arial, sans-serif; max-width: 520px; margin: 40px auto; }}
label {{ display: block; margin-top: 12px; }}
input {{ width: 100%; padding: 8px; font-size: 14px; }}
button {{ margin-top: 16px; padding: 10px 14px; }}
</style>
</head>
<body>
<h3>Telegram login</h3>
<form method=\"post\">
<label>Code from Telegram/SMS</label>
<input name=\"code\" placeholder=\"12345\" />
<label>2FA password (if enabled)</label>
<input name=\"password\" type=\"password\" />
<button type=\"submit\">Submit</button>
</form>
</body>
</html>"""


def _render_result(ok: bool) -> str:
    text = "Submitted. Return to bot and press 'Check status'." if ok else "Invalid link."
    return f"""<!doctype html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<title>Auth</title>
</head>
<body>
<p>{text}</p>
</body>
</html>"""


class WebAuthServer:
    def __init__(self, host: str, port: int) -> None:
        self._server = HTTPServer((host, port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()