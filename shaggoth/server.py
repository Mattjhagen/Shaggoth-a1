"""REST API server — the backend the iOS/Android apps will talk to.

Standard-library only (http.server), JSON in/out, CORS enabled so web and
mobile clients can call it directly. Endpoints:

    GET  /health                     → {"ok": true, "version": ...}
    POST /chat                       → body {"message", "session_id"?}
                                       → {"reply", "source", "blocked", ...}
    GET  /history?session_id=ID      → {"messages": [...]}
    GET  /facts                      → {"facts": {...}}
    GET  /guardrails                 → full guardrail config
    POST /guardrails/rules           → add a rule (JSON body)
    DELETE /guardrails/rules/<id>    → remove a rule

Run: ``python3 -m shaggoth serve --port 8420``

Phase 2 (docs/ROADMAP.md) adds auth tokens, streaming responses, and TLS —
don't expose this Phase-1 server beyond localhost/Tailscale.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import __version__
from .dialogue import DialogueEngine


def make_handler(engine: DialogueEngine):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"Shaggoth/{__version__}"

        # ------------------------------------------------------- helpers
        def _send(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return {}

        def log_message(self, fmt, *args):  # quieter default logging
            pass

        # -------------------------------------------------------- routes
        def do_OPTIONS(self):
            self._send(204, {})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/health":
                self._send(200, {"ok": True, "version": __version__})
            elif url.path == "/history":
                params = parse_qs(url.query)
                session_id = (params.get("session_id") or ["default"])[0]
                self._send(200, {"messages": engine.memory.history(session_id)})
            elif url.path == "/facts":
                self._send(200, {"facts": engine.memory.all_facts()})
            elif url.path == "/guardrails":
                engine.guardrails.maybe_reload()
                self._send(200, engine.guardrails.config)
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            if url.path == "/chat":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    self._send(400, {"error": "message is required"})
                    return
                session_id = body.get("session_id") or "default"
                reply = engine.respond(message, session_id=session_id)
                payload = asdict(reply)
                payload["reply"] = payload.pop("text")
                self._send(200, payload)
            elif url.path == "/guardrails/rules":
                rule = self._read_json()
                try:
                    engine.guardrails.add_rule(rule)
                except ValueError as exc:
                    self._send(400, {"error": str(exc)})
                    return
                self._send(201, {"ok": True, "rule_id": rule["id"]})
            else:
                self._send(404, {"error": "not found"})

        def do_DELETE(self):
            url = urlparse(self.path)
            prefix = "/guardrails/rules/"
            if url.path.startswith(prefix):
                rule_id = url.path[len(prefix):]
                if engine.guardrails.remove_rule(rule_id):
                    self._send(200, {"ok": True})
                else:
                    self._send(404, {"error": f"no rule with id {rule_id!r}"})
            else:
                self._send(404, {"error": "not found"})

    return Handler


def serve(engine: DialogueEngine, host: str = "127.0.0.1", port: int = 8420) -> None:
    httpd = ThreadingHTTPServer((host, port), make_handler(engine))
    print(f"Shaggoth API listening on http://{host}:{port}")
    print("  POST /chat   GET /history   GET /facts   GET|POST|DELETE /guardrails…")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()
