from __future__ import annotations

import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.services.auth_registry import auth_flow_manager

WEB_AUTH_DIST = Path(__file__).resolve().parent.parent / "web_auth" / "dist"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/assets/"):
            self._send_static(path)
            return

        if not path.startswith("/auth/"):
            self.send_response(404)
            self.end_headers()
            return

        if (WEB_AUTH_DIST / "index.html").exists():
            self._send_file(WEB_AUTH_DIST / "index.html", "text/html; charset=utf-8")
            return

        token = path.split("/auth/")[-1].strip()
        self._send_html(_render_form(token))

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

    def _send_file(self, filepath: Path, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        with filepath.open("rb") as f:
            self.wfile.write(f.read())

    def _send_static(self, path: str) -> None:
        rel = path.lstrip("/")
        target = (WEB_AUTH_DIST / rel).resolve()
        if not str(target).startswith(str(WEB_AUTH_DIST.resolve())) or not target.exists():
            self.send_response(404)
            self.end_headers()
            return
        mime, _ = mimetypes.guess_type(str(target))
        self._send_file(target, mime or "application/octet-stream")


def _render_form(token: str) -> str:
    return f"""<!doctype html>
<html lang=\"uk\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Telegram Auth</title>
<style>
@import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&display=swap");
:root {{
  --bg-1: #0b1120;
  --bg-2: #111827;
  --bg-3: #0f172a;
  --card: #0f1c2e;
  --card-2: #13243b;
  --accent: #22d3ee;
  --accent-2: #38bdf8;
  --text: #e5e7eb;
  --muted: #9aa4b2;
  --danger: #ef4444;
  --glow: rgba(56, 189, 248, 0.2);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  min-height: 100vh;
  font-family: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
  color: var(--text);
  background:
    radial-gradient(1200px 600px at 10% -10%, #1f2937 0%, transparent 60%),
    radial-gradient(900px 500px at 100% 0%, #0ea5e9 0%, transparent 55%),
    linear-gradient(180deg, var(--bg-1), var(--bg-2) 45%, var(--bg-3));
  display: grid;
  place-items: center;
  padding: 24px;
}}
.shell {{
  width: min(720px, 100%);
  display: grid;
  gap: 16px;
}}
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(34, 211, 238, 0.12);
  border: 1px solid rgba(34, 211, 238, 0.35);
  color: var(--accent);
  font-weight: 600;
  letter-spacing: 0.3px;
  border-radius: 999px;
  width: fit-content;
}}
.card {{
  background: linear-gradient(180deg, var(--card), var(--card-2));
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 20px;
  padding: 24px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.35), 0 0 40px var(--glow);
  position: relative;
  overflow: hidden;
}}
.card::after {{
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(260px 140px at 100% 0%, rgba(34,211,238,0.18), transparent 60%),
    radial-gradient(220px 120px at 0% 100%, rgba(56,189,248,0.18), transparent 60%);
  pointer-events: none;
}}
h1 {{
  margin: 8px 0 6px;
  font-size: 28px;
}}
p {{
  margin: 0 0 18px;
  color: var(--muted);
  line-height: 1.5;
}}
form {{
  display: grid;
  gap: 14px;
}}
label {{
  font-size: 13px;
  letter-spacing: 0.2px;
  color: var(--muted);
}}
input {{
  width: 100%;
  padding: 14px 14px;
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(148, 163, 184, 0.25);
  color: var(--text);
  border-radius: 12px;
  font-size: 16px;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}}
input:focus {{
  border-color: var(--accent-2);
  box-shadow: 0 0 0 4px rgba(56,189,248,0.15);
}}
.row {{
  display: grid;
  gap: 8px;
}}
.actions {{
  display: grid;
  gap: 10px;
  margin-top: 4px;
}}
button {{
  background: linear-gradient(90deg, var(--accent), var(--accent-2));
  color: #04131f;
  border: none;
  padding: 14px 16px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.3px;
}}
.hint {{
  font-size: 12px;
  color: var(--muted);
}}
.footer {{
  font-size: 12px;
  color: var(--muted);
  display: flex;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}}
.divider {{
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(148,163,184,0.35), transparent);
  margin: 8px 0 2px;
}}
</style>
</head>
<body>
  <div class=\"shell\">
    <span class=\"badge\">Telegram Login</span>
    <div class=\"card\">
      <h1>Вхід в акаунт</h1>
      <p>Введіть код, який прийшов у Telegram або SMS. Якщо увімкнено 2FA — додайте пароль.</p>
      <form method=\"post\">
        <div class=\"row\">
          <label>Код з Telegram/SMS</label>
          <input name=\"code\" inputmode=\"numeric\" autocomplete=\"one-time-code\" placeholder=\"12345\" />
        </div>
        <div class=\"row\">
          <label>Пароль 2FA (якщо увімкнено)</label>
          <input name=\"password\" type=\"password\" autocomplete=\"current-password\" placeholder=\"••••••••\" />
        </div>
        <div class=\"actions\">
          <button type=\"submit\">Підтвердити вхід</button>
          <div class=\"hint\">Після відправки поверніться в бот і натисніть «Перевірити вхід».</div>
        </div>
      </form>
      <div class=\"divider\"></div>
      <div class=\"footer\">
        <span>Безпека: код діє обмежений час</span>
        <span>Підтримка: напишіть у бот</span>
      </div>
    </div>
  </div>
</body>
</html>"""


def _render_result(ok: bool) -> str:
    text = "Готово! Поверніться в бот і натисніть «Перевірити вхід»." if ok else "Невірне посилання."
    tone = "#22d3ee" if ok else "#ef4444"
    return f"""<!doctype html>
<html lang=\"uk\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>Telegram Auth</title>
<style>
@import url("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;600&display=swap");
body {{
  margin: 0;
  min-height: 100vh;
  font-family: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
  background: linear-gradient(180deg, #0b1120, #0f172a);
  color: #e5e7eb;
  display: grid;
  place-items: center;
  padding: 24px;
}}
.card {{
  background: #111c2f;
  border: 1px solid rgba(148,163,184,0.2);
  border-radius: 18px;
  padding: 24px;
  max-width: 560px;
  text-align: center;
  box-shadow: 0 20px 50px rgba(0,0,0,0.35);
}}
.dot {{
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: {tone};
  display: inline-block;
  margin-right: 8px;
}}
p {{
  margin: 0;
  font-size: 16px;
}}
</style>
</head>
<body>
  <div class=\"card\">
    <p><span class=\"dot\"></span>{text}</p>
  </div>
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
