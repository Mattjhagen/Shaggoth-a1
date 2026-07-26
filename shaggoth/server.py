"""REST API server with optional auth, SSE streaming, and web dashboard.

Endpoints:
    GET  /                           → web dashboard (static files)
    GET  /health                     → {"ok": true, "version": ...}
    POST /chat                       → body {"message", "session_id"?}
    POST /chat/stream                → SSE stream (same body)
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

Auth: If SHAGGOTH_API_KEY env var or api_key setting is set, all API
routes (except /health, /, and static files) require
"Authorization: Bearer <key>".
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .dialogue import DialogueEngine
from .knowledge.engine import KnowledgeBase
from .learner.pipeline import LearnerPipeline
from .personality.engine import PersonalityEngine

STATIC_DIR = Path(__file__).parent / "static"
API_KEY = os.environ.get("SHAGGOTH_API_KEY") or ""
RATE_LIMITS: dict[str, list[float]] = {}


def make_handler(engine: DialogueEngine, learner: LearnerPipeline, api_key: str = ""):
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
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
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
            if not path.exists() or not path.is_file():
                self._send_json(404, {"error": "not found"})
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

        def _check_auth(self) -> bool:
            if not api_key:
                return True
            auth = self.headers.get("Authorization", "")
            if auth == f"Bearer {api_key}":
                return True
            self._send_json(401, {"error": "unauthorized"})
            return False

        def _rate_limit(self, key: str = "", limit: int = 60, window: float = 60.0) -> bool:
            if not api_key:
                return True
            now = time.time()
            bucket = RATE_LIMITS.setdefault(key, [])
            bucket[:] = [t for t in bucket if t > now - window]
            if len(bucket) >= limit:
                self._send_json(429, {"error": "rate limit exceeded"})
                return False
            bucket.append(now)
            return True

        def log_message(self, fmt, *args):
            pass

        # -------------------------------------------------------- routes
        def do_OPTIONS(self):
            self._send(204)

        def _route_get(self, path: str, url):
            if path == "/health":
                return self._send_json(200, {"ok": True, "version": __version__})

            if not self._check_auth():
                return

            if path == "/history":
                params = parse_qs(url.query)
                session_id = (params.get("session_id") or ["default"])[0]
                return self._send_json(200, {"messages": engine.memory.history(session_id)})

            if path == "/facts":
                return self._send_json(200, {"facts": engine.memory.all_facts()})

            if path == "/guardrails":
                engine.guardrails.maybe_reload()
                return self._send_json(200, engine.guardrails.config)

            if path == "/learn/status":
                return self._send_json(200, learner.status())

            if path == "/learn/history":
                return self._send_json(200, {"sessions": learner.history()})

            if path == "/scrape/stats":
                return self._send_json(200, learner.scraper.stats())

            if path == "/personality":
                engine.personality.maybe_reload()
                return self._send_json(200, engine.personality.as_dict())

            if path == "/knowledge":
                return self._send_json(200, {"entries": engine.knowledge.list_entries()})

            if path == "/knowledge/query":
                params = parse_qs(url.query)
                q = (params.get("q") or [""])[0]
                results = engine.knowledge.query(q, limit=5, min_score=0.1)
                return self._send_json(200, {
                    "results": [{"topic": e.topic, "content": e.content[:500], "score": round(s, 3)} for e, s in results]
                })

            if path in ("/", ""):
                return self._send_static(STATIC_DIR / "index.html")

            file_path = STATIC_DIR / path.lstrip("/")
            if file_path.exists() and file_path.is_file():
                return self._send_static(file_path)

            return self._send_json(404, {"error": "not found"})

        def _route_post(self, path: str, url):
            if path == "/chat":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    return self._send_json(400, {"error": "message is required"})
                session_id = body.get("session_id") or "default"
                reply = engine.respond(message, session_id=session_id)
                payload = asdict(reply)
                payload["reply"] = payload.pop("text")
                return self._send_json(200, payload)

            if path == "/chat/stream":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    return self._send_json(400, {"error": "message is required"})
                session_id = body.get("session_id") or "default"

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()

                reply = engine.respond(message, session_id=session_id)
                text = reply.text
                chunk_size = max(1, len(text) // 20)
                for i in range(0, len(text), chunk_size):
                    chunk = text[i : i + chunk_size]
                    self.wfile.write(f"data: {json.dumps({'token': chunk})}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.02)

                meta = asdict(reply)
                meta["reply"] = meta.pop("text")
                self.wfile.write(f"data: {json.dumps({'done': True, **meta})}\n\n".encode())
                return

            if path == "/guardrails/rules":
                rule = self._read_json()
                try:
                    engine.guardrails.add_rule(rule)
                except ValueError as exc:
                    return self._send_json(400, {"error": str(exc)})
                return self._send_json(201, {"ok": True, "rule_id": rule["id"]})

            if path == "/learn/start":
                body = self._read_json()
                session = learner.learn(
                    urls=body.get("urls"),
                    crawl_depth=body.get("crawl_depth", 1),
                    max_pages=body.get("max_pages", 20),
                    training_steps=body.get("training_steps", 1000),
                    background=True,
                )
                return self._send_json(202, {"ok": True, "session_id": session.session_id})

            if path == "/knowledge/add":
                body = self._read_json()
                topic = (body.get("topic") or "").strip()
                content = (body.get("content") or "").strip()
                if not topic or not content:
                    return self._send_json(400, {"error": "topic and content required"})
                fpath = engine.knowledge.add_entry(topic, content)
                return self._send_json(201, {"ok": True, "topic": topic, "path": str(fpath)})

            if path == "/knowledge/remove":
                body = self._read_json()
                topic = (body.get("topic") or "").strip()
                if engine.knowledge.remove_entry(topic):
                    return self._send_json(200, {"ok": True})
                return self._send_json(404, {"error": f"no entry found: {topic}"})

            if path == "/scrape/url":
                body = self._read_json()
                url_to_scrape = (body.get("url") or "").strip()
                if not url_to_scrape:
                    return self._send_json(400, {"error": "url is required"})
                page = learner.scraper.fetch_page(url_to_scrape)
                if page:
                    return self._send_json(200, {"ok": True, "url": page.url, "title": page.title, "word_count": page.word_count})
                return self._send_json(500, {"error": "failed to fetch page"})

            if path == "/scrape/seed":
                body = self._read_json()
                urls = body.get("urls") or []
                if not urls:
                    return self._send_json(400, {"error": "urls is required"})
                added = learner.scraper.add_seeds(urls)
                return self._send_json(200, {"ok": True, "added": added})

            return self._send_json(404, {"error": "not found"})

        def _route_delete(self, path: str, url):
            prefix = "/guardrails/rules/"
            if path.startswith(prefix):
                rule_id = path[len(prefix):]
                if engine.guardrails.remove_rule(rule_id):
                    return self._send_json(200, {"ok": True})
                return self._send_json(404, {"error": f"no rule with id {rule_id!r}"})
            return self._send_json(404, {"error": "not found"})

        def do_GET(self):
            url = urlparse(self.path)
            self._route_get(url.path, url)

        def do_POST(self):
            url = urlparse(self.path)
            if not self._check_auth():
                return
            if not self._rate_limit(self.client_address[0]):
                return
            self._route_post(url.path, url)

        def do_DELETE(self):
            url = urlparse(self.path)
            if not self._check_auth():
                return
            self._route_delete(url.path, url)

    return Handler


def serve(engine: DialogueEngine, host: str = "127.0.0.1", port: int = 8420, api_key: str = "") -> None:
    learner = LearnerPipeline()
    httpd = ThreadingHTTPServer((host, port), make_handler(engine, learner, api_key))
    auth_status = "enabled" if api_key else "disabled"
    print(f"Shaggoth API listening on http://{host}:{port}")
    print(f"  Dashboard: http://{host}:{port}/")
    print(f"  Auth: {auth_status}")
    print(f"  POST /chat   GET /history   GET /facts   GET /guardrails")
    print(f"  POST /chat/stream (SSE)   POST /learn/start   GET /learn/status")
    print(f"  POST /scrape/url    GET /scrape/stats")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        httpd.server_close()
