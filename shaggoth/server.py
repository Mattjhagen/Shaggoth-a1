"""REST API server — the backend the iOS/Android apps and web dashboard talk to.

Standard-library only (http.server), JSON in/out, CORS enabled so web and
mobile clients can call it directly. Now serves the web dashboard too.

Endpoints:
    GET  /health                     → {"ok": true, "version": ...}
    POST /chat                       → body {"message", "session_id"?}
                                       → {"reply", "source", "blocked", ...}
    GET  /history?session_id=ID      → {"messages": [...]}
    GET  /facts                      → {"facts": {...}}
    GET  /guardrails                 → full guardrail config
    POST /guardrails/rules           → add a rule (JSON body)
    DELETE /guardrails/rules/<id>    → remove a rule
    POST /learn/start                → start a learning session
    GET  /learn/status               → current learning status
    GET  /learn/history              → past learning sessions
    POST /scrape/url                 → scrape a single URL
    GET  /scrape/stats               → scraper statistics
    GET  /                           → web dashboard (static files)

Run: ``python3 -m shaggoth serve --port 8420``
"""

from __future__ import annotations

import json
import mimetypes
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .dialogue import DialogueEngine
from .learner.pipeline import LearnerPipeline
from .scraper.engine import ScraperEngine

STATIC_DIR = Path(__file__).parent / "static"


def make_handler(engine: DialogueEngine, learner: LearnerPipeline):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"Shaggoth/{__version__}"

        # ------------------------------------------------------- helpers
        def _send(self, status: int, payload: dict | str | bytes | None = None, content_type: str = "application/json; charset=utf-8") -> None:
            if payload is None:
                body = b""
            elif isinstance(payload, (dict, list)):
                body = json.dumps(payload).encode("utf-8")
            elif isinstance(payload, str):
                body = payload.encode("utf-8")
            else:
                body = payload
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status: int, payload: dict) -> None:
            self._send(status, payload)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length == 0:
                return {}
            try:
                return json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return {}

        def _send_static(self, path: Path) -> None:
            """Serve a file from the static directory."""
            if not path.exists() or not path.is_file():
                self._send(404, {"error": "not found"})
                return
            ct, _ = mimetypes.guess_type(str(path))
            ct = ct or "application/octet-stream"
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            pass

        # -------------------------------------------------------- routes
        def do_OPTIONS(self):
            self._send(204)

        def do_GET(self):
            url = urlparse(self.path)
            path = url.path

            # --- API routes ---
            if path == "/health":
                self._send_json(200, {"ok": True, "version": __version__})

            elif path == "/history":
                params = parse_qs(url.query)
                session_id = (params.get("session_id") or ["default"])[0]
                self._send_json(200, {"messages": engine.memory.history(session_id)})

            elif path == "/facts":
                self._send_json(200, {"facts": engine.memory.all_facts()})

            elif path == "/guardrails":
                engine.guardrails.maybe_reload()
                self._send_json(200, engine.guardrails.config)

            elif path == "/learn/status":
                self._send_json(200, learner.status())

            elif path == "/learn/history":
                self._send_json(200, {"sessions": learner.history()})

            elif path == "/scrape/stats":
                self._send_json(200, learner.scraper.stats())

            # --- Static files (dashboard) ---
            elif path == "/" or path == "":
                self._send_static(STATIC_DIR / "index.html")
            else:
                # Try serving from static dir
                file_path = STATIC_DIR / path.lstrip("/")
                if file_path.exists() and file_path.is_file():
                    self._send_static(file_path)
                else:
                    self._send_json(404, {"error": "not found"})

        def do_POST(self):
            url = urlparse(self.path)
            path = url.path

            if path == "/chat":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    self._send_json(400, {"error": "message is required"})
                    return
                session_id = body.get("session_id") or "default"
                reply = engine.respond(message, session_id=session_id)
                payload = asdict(reply)
                payload["reply"] = payload.pop("text")
                self._send_json(200, payload)

            elif path == "/guardrails/rules":
                rule = self._read_json()
                try:
                    engine.guardrails.add_rule(rule)
                except ValueError as exc:
                    self._send_json(400, {"error": str(exc)})
                    return
                self._send_json(201, {"ok": True, "rule_id": rule["id"]})

            elif path == "/learn/start":
                body = self._read_json()
                session = learner.learn(
                    urls=body.get("urls"),
                    crawl_depth=body.get("crawl_depth", 1),
                    max_pages=body.get("max_pages", 20),
                    training_steps=body.get("training_steps", 1000),
                    background=True,
                )
                self._send_json(202, {"ok": True, "session_id": session.session_id})

            elif path == "/scrape/url":
                body = self._read_json()
                url_to_scrape = (body.get("url") or "").strip()
                if not url_to_scrape:
                    self._send_json(400, {"error": "url is required"})
                    return
                page = learner.scraper.fetch_page(url_to_scrape)
                if page:
                    self._send_json(200, {
                        "ok": True,
                        "url": page.url,
                        "title": page.title,
                        "word_count": page.word_count,
                    })
                else:
                    self._send_json(500, {"error": "failed to fetch page"})

            elif path == "/scrape/seed":
                body = self._read_json()
                urls = body.get("urls") or []
                if not urls:
                    self._send_json(400, {"error": "urls is required"})
                    return
                added = learner.scraper.add_seeds(urls)
                self._send_json(200, {"ok": True, "added": added})

            else:
                self._send_json(404, {"error": "not found"})

        def do_DELETE(self):
            url = urlparse(self.path)
            prefix = "/guardrails/rules/"
            if url.path.startswith(prefix):
                rule_id = url.path[len(prefix):]
                if engine.guardrails.remove_rule(rule_id):
                    self._send_json(200, {"ok": True})
                else:
                    self._send_json(404, {"error": f"no rule with id {rule_id!r}"})
            else:
                self._send_json(404, {"error": "not found"})

    return Handler


def serve(engine: DialogueEngine, host: str = "127.0.0.1", port: int = 8420) -> None:
    learner = LearnerPipeline()
    httpd = ThreadingHTTPServer((host, port), make_handler(engine, learner))
    print(f"Shaggoth API listening on http://{host}:{port}")
    print(f"  Dashboard: http://{host}:{port}/")
    print("  POST /chat   GET /history   GET /facts   GET /guardrails")
    print("  POST /learn/start   GET /learn/status   GET /learn/history")
    print("  POST /scrape/url    GET /scrape/stats")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()
