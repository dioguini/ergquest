"""Servidor local do banco de testes (só em 127.0.0.1): a página e uma pequena API JSON."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Bench

PAGE = (Path(__file__).with_name("page.html")).read_text(encoding="utf-8")


def make_handler(bench: Bench):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):          # sem ruído no terminal
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif self.path == "/api/state":
                self._json(bench.state())
            else:
                self._send(404, b"", "text/plain")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            try:
                args = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "pedido inválido"}, 400)
            actions = {
                "/api/scan": lambda a: bench.scan(float(a.get("timeout", 6))),
                "/api/connect": lambda a: bench.connect(a["address"]),
                "/api/disconnect": lambda a: bench.disconnect(a["address"]),
                "/api/erg": lambda a: bench.erg(a["address"], float(a["watts"])),
                "/api/grade": lambda a: bench.grade(a["address"], float(a["pct"])),
                "/api/write": lambda a: bench.write_hex(a["address"], a["char"], a["hex"], bool(a.get("response", True))),
                "/api/record": lambda a: bench.record(bool(a["on"]), a.get("marker", "")),
                "/api/marker": lambda a: bench.set_marker(a["marker"]),
                "/api/treadmill": lambda a: bench.treadmill_action(a["action"], a.get("value")),
            }
            fn = actions.get(self.path)
            if fn is None:
                return self._json({"error": "ação desconhecida"}, 404)
            try:
                result = fn(args)
            except Exception as err:
                bench.log(f"erro em {self.path[5:]}: {err}")
                return self._json({"error": str(err)}, 500)
            self._json({"ok": True, "result": result})

    return Handler


def serve(bench: Bench, port: int = 8787) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(bench))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd
