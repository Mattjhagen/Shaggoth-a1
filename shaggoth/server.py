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

import ipaddress
import json
import mimetypes
import os
import re
import threading
import time
import traceback
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .dialogue.engine import normalize_mode
from .curiosity.engine import CuriosityEngine
from .curiosity.scheduler import CuriosityScheduler, ScheduleConfig
from .curiosity.topics import extract_topic_query
from .dialogue import DialogueEngine
from .dialogue.proactive import ProactiveChatter, ProactiveConfig
from .knowledge.engine import KnowledgeBase
from .learner.pipeline import LearnerPipeline
from .feedback import FeedbackStore
from .notify import DeferredQuestions, PushSender
from .quality import CriticLoop, build_teacher
from .personality.engine import PersonalityEngine

STATIC_DIR = Path(__file__).parent / "static"
API_KEY = os.environ.get("SHAGGOTH_API_KEY") or ""
RATE_LIMITS: dict[str, list[float]] = {}
_RATE_LIMIT_LOCK = threading.Lock()
PUSH_TOKENS: list[dict] = []

# Peers whose forwarded-IP headers we believe. cloudflared runs on this host
# and dials 127.0.0.1:8420, so the tunnel always shows up as loopback.
#
# This list is the whole security boundary of _client_ip(). Anyone allowed in
# here can claim to be any IP and get a fresh rate-limit bucket per request,
# which is a limiter bypass -- so it stays loopback-only. The server binds
# 0.0.0.0, and a LAN client connecting directly is NOT trusted: its headers
# are ignored and its real socket address is used.
_TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})

# Cloudflare sends exactly one client IP here. Preferred over X-Forwarded-For,
# which arrives as a comma-separated chain and needs picking apart.
_REAL_IP_HEADERS = ("CF-Connecting-IP", "X-Real-IP")


def _parse_ip(raw: str) -> str:
    """Validate one forwarded-header value into a canonical IP, or "".

    Validation is not cosmetic. The return value becomes a RATE_LIMITS key,
    so an unvalidated header would let a caller push arbitrary -- and
    arbitrarily long -- strings into a process-lifetime dict.
    """
    value = (raw or "").strip()
    if not value or len(value) > 64:
        return ""
    # Some proxies append a source port: "1.2.3.4:5678" or "[::1]:443".
    if value.startswith("["):
        value = value.partition("]")[0].lstrip("[")
    elif value.count(":") == 1:
        value = value.partition(":")[0]
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return ""


# A URL pasted into a chat message. Deliberately conservative: requires an
# explicit scheme, so ordinary prose mentioning "example.com" is not treated
# as a fetch instruction.
_URL_IN_MESSAGE = re.compile(r"https?://[^\s<>\"\')\]]+", re.I)


def extract_url(message: str) -> str:
    """Return the first http(s) URL in ``message``, or ``""``.

    Trailing sentence punctuation is stripped -- people paste links mid
    sentence ("what do you make of https://example.com/page?") and the
    trailing "?" is not part of the URL.
    """
    match = _URL_IN_MESSAGE.search(message or "")
    if not match:
        return ""
    return match.group(0).rstrip(".,;:!?")


def strip_url(message: str, url: str) -> str:
    """The message with ``url`` removed, for use as the actual question."""
    return " ".join(message.replace(url, " ").split())


# Site suffixes publishers append to every <title>. Left in place they become
# part of the knowledge entry's topic and pollute title matching.
_TITLE_SUFFIX = re.compile(
    r"\s*[|\u2013\u2014-]\s*(wikipedia|github|youtube|reddit|medium|"
    r"stack overflow|the guardian|bbc|cnn|nytimes|the new york times)\s*$",
    re.I,
)

# Words that carry no subject on their own. A turn made only of these is a
# gesture at the link, not a question about anything in particular.
_EMPTY_ASK = {
    "a", "about", "and", "any", "anything", "at", "check", "do", "for", "from",
    "give", "have", "here", "hey", "how", "is", "it", "look", "make", "me",
    "of", "on", "opinion", "out", "read", "see", "so", "some", "something",
    "take", "tell", "the", "there", "these", "think", "this", "thoughts",
    "to", "up", "what", "whats", "you", "your",
}


def clean_page_title(title: str) -> str:
    """Strip the site-name suffix publishers append to every page title."""
    return _TITLE_SUFFIX.sub("", (title or "").strip()).strip()


def question_for_page(question: str, title: str) -> str:
    """Decide what to actually ask once a pasted link has been read.

    "what do you make of <link>?" leaves "what do you make of ?" behind --
    a turn with no subject in it, which retrieves nothing and falls through
    to a canned pattern reply. When the residual carries no subject of its
    own, ask about the page instead. A real question ("does this contradict
    photosynthesis?") is left alone.
    """
    title = clean_page_title(title)
    words = [w.strip("?!.,;:\"'()") for w in (question or "").lower().split()]
    if any(w and w not in _EMPTY_ASK for w in words):
        return question
    return f"what is {title}" if title else question


# Local asset references in index.html that must be re-fetched after a deploy.
_ASSET_REF = re.compile(r'\b(src|href)="(?!https?:|//|#)([^"?]+\.(?:js|css))"')


def asset_version(name: str, directory: Path = STATIC_DIR) -> str:
    """A token that changes whenever ``name`` changes on disk."""
    try:
        return str(int((directory / name).stat().st_mtime))
    except OSError:
        return "0"


def add_cache_busters(html: str, directory: Path = STATIC_DIR) -> str:
    """Append ``?v=<mtime>`` to local .js/.css references in ``html``.

    Cloudflare sits in front of this origin and serves ``/app.js`` with
    ``max-age=14400`` regardless of the ``no-cache`` sent here, so for four
    hours after every deploy visitors keep running the previous JavaScript --
    including anyone reporting a bug that was already fixed. Versioning the
    URL is the only cache-bust that does not depend on Cloudflare's settings.

    Derived from mtime rather than a hardcoded version so it can never be
    forgotten on a deploy, and unchanged files keep their token (and stay
    cached, which is the point of the cache).
    """
    return _ASSET_REF.sub(
        lambda m: f'{m.group(1)}="{m.group(2)}?v={asset_version(m.group(2), directory)}"',
        html,
    )


def _request_mode(body: dict):
    """Read the drift mode a chat request asked for, if any.

    Accepted spellings, in priority order: ``{"mode": "drift"|"no_drift"}``
    and ``{"drift": true|false}``. Returning ``None`` means "unspecified",
    which lets the engine apply its own configured default rather than this
    function inventing one.
    """
    if not isinstance(body, dict):
        return None
    if body.get("mode") is not None:
        return normalize_mode(body.get("mode"))
    if body.get("drift") is not None:
        return normalize_mode(body.get("drift"))
    return None


def make_handler(engine: DialogueEngine, learner: LearnerPipeline, api_key: str = "", curiosity: CuriosityEngine | None = None, scheduler: CuriosityScheduler | None = None, push: PushSender | None = None, deferred: DeferredQuestions | None = None, feedback: FeedbackStore | None = None, critic: CriticLoop | None = None, proactive=None):
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
            if not getattr(self, "_suppress_body", False):
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
            if path.name == "index.html":
                body = add_cache_busters(body.decode("utf-8")).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            if not getattr(self, "_suppress_body", False):
                self.wfile.write(body)

        def _check_auth(self) -> bool:
            if not api_key:
                return True
            auth = self.headers.get("Authorization", "")
            if auth == f"Bearer {api_key}":
                return True
            self._send_json(401, {"error": "unauthorized"})
            return False

        def _client_ip(self) -> str:
            """The real caller's IP, seen through the Cloudflare tunnel.

            Without this the limiter was effectively global. It keyed on the
            socket address, but every public request arrives via cloudflared
            over loopback, so the entire internet shared one "127.0.0.1"
            bucket: 60 requests/minute total, not per visitor. One person
            clicking fast locked out every other caller, the dashboard and the
            command center's ambient dialogue included.

            Headers are only believed when the immediate peer is a trusted
            proxy -- otherwise anyone could mint a fresh bucket per request by
            sending a made-up CF-Connecting-IP, which is a worse hole than the
            one being closed.
            """
            peer = self.client_address[0] if self.client_address else ""
            if peer not in _TRUSTED_PROXIES:
                return peer

            for header in _REAL_IP_HEADERS:
                candidate = _parse_ip(self.headers.get(header, ""))
                if candidate:
                    return candidate

            # X-Forwarded-For is "client, proxy1, proxy2...". The leftmost
            # entry is the original client, but it is also the one a caller
            # can forge; everything after it was appended by infrastructure.
            # We only reach this line when the peer is trusted, so the chain
            # itself is as trustworthy as that proxy -- take the leftmost.
            forwarded = self.headers.get("X-Forwarded-For", "")
            for part in forwarded.split(","):
                candidate = _parse_ip(part)
                if candidate:
                    return candidate

            # Direct loopback call (curl on the box, health checks) or a proxy
            # that forwarded nothing. Fall back to the socket address.
            return peer

        def _rate_limit(self, key: str = "", limit: int = 60, window: float = 60.0) -> bool:
            """Cap requests per client IP per minute.

            This used to return True immediately when no API key was set --
            i.e. the rate limiter was disabled exactly when it was most
            needed. This endpoint is public and unauthenticated, and every
            chat message feeds the curiosity loop, so an open endpoint with no
            limiter lets anyone decide what Shaggoth spends its night reading.

            Auth is still a separate question, and still the operator's call.
            This is the floor.
            """
            now = time.time()
            with _RATE_LIMIT_LOCK:
                if len(RATE_LIMITS) > 4096:
                    # An open endpoint sees a lot of distinct IPs; without this the
                    # bucket map is an unbounded memory leak.
                    for stale_key in [
                        k for k, v in RATE_LIMITS.items() if not v or v[-1] < now - window
                    ]:
                        RATE_LIMITS.pop(stale_key, None)
                bucket = RATE_LIMITS.setdefault(key, [])
                bucket[:] = [t for t in bucket if t > now - window]
                if len(bucket) >= limit:
                    allowed = False
                else:
                    bucket.append(now)
                    allowed = True
            if not allowed:
                self._send_json(429, {"error": "rate limit exceeded"})
                return False
            return True

        def log_message(self, fmt, *args):
            pass

        # -------------------------------------------------------- routes
        def do_OPTIONS(self):
            self._send(204)

        def _route_get(self, path: str, url):
            if path == "/health":
                return self._send_json(200, {"ok": True, "version": __version__})

            # Dashboard and its assets are public — auth gates API calls only.
            if path in ("/", ""):
                return self._send_static(STATIC_DIR / "index.html")

            _candidate = STATIC_DIR / path.lstrip("/")
            try:
                _candidate.resolve().relative_to(STATIC_DIR.resolve())
            except ValueError:
                pass  # path escapes STATIC_DIR — fall through to auth + API routes
            else:
                if _candidate.exists() and _candidate.is_file():
                    return self._send_static(_candidate)

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

            if path == "/greeting":
                # Composed per request from live state (knowledge count,
                # what's currently being researched, backlog sizes) so the
                # opening line is generated from what's actually true right
                # now rather than picked from a fixed set of sentences.
                from .dialogue.engine import compose_greeting
                count = 0
                recent = ""
                try:
                    engine.knowledge.maybe_reload()
                    entries = engine.knowledge._entries
                    count = len(entries)
                    if entries:
                        newest = max(entries, key=lambda e: e.mtime)
                        recent = newest.topic.lower()
                except Exception:
                    pass
                stale_count = 0
                episodes = 0
                is_researching = False
                research_topic = ""
                if curiosity:
                    try:
                        cstatus = curiosity.status()
                        stale_count = cstatus.get("freshness", {}).get("stale_count", 0)
                        episodes = cstatus.get("total_episodes", 0)
                        is_researching = bool(cstatus.get("is_running"))
                        current = cstatus.get("current_episode")
                        if current:
                            research_topic = (current.get("topic") or "").lower()
                    except Exception:
                        pass
                repair_queue = 0
                if feedback:
                    try:
                        repair_queue = feedback.status().get("repair_queue", 0)
                    except Exception:
                        pass
                return self._send_json(200, {"greeting": compose_greeting(
                    count, recent,
                    stale_count=stale_count, episodes=episodes,
                    repair_queue=repair_queue, is_researching=is_researching,
                    research_topic=research_topic,
                )})

            if path == "/curiosity/status":
                if curiosity:
                    return self._send_json(200, curiosity.status())
                return self._send_json(501, {"error": "curiosity engine not initialized"})

            if path == "/curiosity/history":
                if curiosity:
                    return self._send_json(200, {"episodes": curiosity.history()})
                return self._send_json(501, {"error": "curiosity engine not initialized"})

            if path == "/curiosity/scheduler":
                if scheduler:
                    return self._send_json(200, scheduler.status())
                return self._send_json(501, {"error": "scheduler not initialized"})

            if path == "/curiosity/freshness":
                if curiosity:
                    return self._send_json(200, curiosity.freshness.status())
                return self._send_json(501, {"error": "curiosity engine not initialized"})

            if path == "/wiki":
                params = parse_qs(url.query)
                q = (params.get("q") or [""])[0]
                if not q:
                    return self._send_json(400, {"error": "q parameter required"})
                from .curiosity.wikipedia import fetch_summary, search_wikipedia
                summary = fetch_summary(q)
                if summary:
                    return self._send_json(200, {"title": q, "summary": summary, "source": "wikipedia"})
                results = search_wikipedia(q, max_results=5)
                return self._send_json(200, {"title": q, "summary": None, "suggestions": [r["title"] for r in results]})

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

            if path == "/feedback":
                if not feedback:
                    return self._send_json(501, {"error": "feedback not initialized"})
                return self._send_json(200, {
                    **feedback.status(),
                    "repairs": [asdict(t) for t in feedback.repair_queue()[:20]],
                    "recent": feedback.recent(10),
                })

            if path == "/critic":
                if not critic:
                    return self._send_json(501, {"error": "critic not initialized"})
                return self._send_json(200, critic.status())

            if path == "/push/status":
                return self._send_json(200, push.status() if push else {"available": False})

            if path == "/proactive/status":
                return self._send_json(200, proactive.status() if proactive else {"enabled": False})

            if path == "/model/status":
                from .models.openai_model import OpenAIModel
                m = engine.model
                return self._send_json(200, {
                    "name": getattr(m, "name", "none") if m else "none",
                    "openai": isinstance(m, OpenAIModel),
                    "openai_model": getattr(m, "_model", None) if isinstance(m, OpenAIModel) else None,
                    "configured": getattr(m, "configured", False) if m else False,
                    "trained": m.is_trained() if m else False,
                })

            if path == "/proactive/messages":
                # Messages Shaggoth sent unprompted for a session, after a given
                # message ID. The client polls this to surface proactive messages
                # it hasn't displayed yet.
                params = parse_qs(url.query)
                session_id = (params.get("session_id") or ["default"])[0]
                since_id = int((params.get("since_id") or ["0"])[0] or 0)
                try:
                    messages = engine.memory.proactive_messages_after(
                        session_id, since_id=since_id
                    )
                except Exception:
                    messages = []
                return self._send_json(200, {"messages": messages})

            if path == "/deferred":
                if not deferred:
                    return self._send_json(501, {"error": "deferred answers not initialized"})
                params = parse_qs(url.query)
                session_id = (params.get("session_id") or [None])[0]
                only_new = (params.get("undelivered") or ["0"])[0] not in ("0", "false", "")
                answered = deferred.answered(session_id, undelivered_only=only_new)
                if only_new and answered:
                    deferred.mark_delivered(answered)
                return self._send_json(200, {
                    "answered": [asdict(i) for i in answered],
                    "pending": [asdict(i) for i in deferred.pending(session_id)],
                    **deferred.status(),
                })

            return self._send_json(404, {"error": "not found"})

        def _route_post(self, path: str, url):
            if path == "/chat":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    return self._send_json(400, {"error": "message is required"})
                session_id = body.get("session_id") or "default"
                mode = _request_mode(body)
                # Machine-driven callers opt out of steering what Shaggoth
                # learns. The command center's ambient dialogue talks to /chat
                # continuously; without this every word it happened to pick
                # out of a reply became a research topic, and the knowledge
                # base filled with entries like "understanding",
                # "continental", and "geophysicists". A spectator should not
                # decide the syllabus.
                may_research = body.get("research", True) is not False
                if scheduler and may_research:
                    scheduler.record_message(message)

                # A pasted link is a request to read it. Scrape and ingest it
                # first, then answer in the same turn -- previously /chat
                # ignored URLs entirely and the user had to call /scrape/url
                # by hand before asking anything about the page.
                link_note = ""
                url_in_message = extract_url(message)
                if url_in_message:
                    page = learner.scraper.fetch_page(url_in_message)
                    if page and page.word_count:
                        title = clean_page_title(page.title) or url_in_message
                        engine.knowledge.add_entry(title, page.text)
                        engine.knowledge.maybe_reload()
                        message = question_for_page(
                            strip_url(message, url_in_message), title
                        )
                        link_note = f"Read \"{title}\" ({page.word_count:,} words). "
                    else:
                        # Strip the link even on failure. Left in, the raw URL
                        # becomes the "question" and the reply comes back as
                        # "Nothing on read https this-host-does-not-exist yet".
                        message = strip_url(message, url_in_message) or message
                        link_note = f"Couldn't read {url_in_message}. "

                reply = engine.respond(message, session_id=session_id, mode=mode)
                if link_note:
                    reply.text = link_note + reply.text
                # Auto-research if bot didn't know the answer
                if may_research and curiosity and reply.source == "fallback":
                    topic = curiosity.analyze_message(message)
                    if topic:
                        # Remember that someone is waiting on this. When the
                        # episode finishes, the answer is delivered instead of
                        # quietly landing in the knowledge base for nobody.
                        if deferred:
                            deferred.record(message, topic, session_id=session_id)
                        curiosity.research_topic(topic, background=True)
                payload = asdict(reply)
                payload["reply"] = payload.pop("text")
                return self._send_json(200, payload)

            if path == "/chat/stream":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    return self._send_json(400, {"error": "message is required"})
                session_id = body.get("session_id") or "default"
                mode = _request_mode(body)
                # Feed message to curiosity scheduler
                if scheduler:
                    scheduler.record_message(message)

                # Respond before committing headers so any engine error returns
                # a clean HTTP 500 rather than corrupt bytes in the SSE body.
                reply = engine.respond(message, session_id=session_id, mode=mode)
                text = reply.text

                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
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
                return self._send_json(201, {"ok": True, "rule_id": rule.get("id")})

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

            if path == "/critic/run":
                # Manual kick, for verifying without waiting for the cadence.
                if not critic:
                    return self._send_json(501, {"error": "critic not initialized"})
                body = self._read_json()
                limit = max(1, min(int(body.get("limit") or 3), 50))
                return self._send_json(200, critic.run_batch(limit))

            if path == "/feedback":
                if not feedback:
                    return self._send_json(501, {"error": "feedback not initialized"})
                body = self._read_json()
                item = feedback.record(
                    question=body.get("question") or "",
                    verdict=body.get("verdict"),
                    answer=body.get("answer") or "",
                    source=body.get("source") or "",
                    entries_used=body.get("entries_used") or [],
                    reasoning=body.get("reasoning") or [],
                    note=body.get("note") or "",
                    session_id=body.get("session_id") or "default",
                )
                if item is None:
                    return self._send_json(
                        400, {"error": "question and a good/bad verdict are required"}
                    )
                return self._send_json(201, {"ok": True, **feedback.status()})

            if path == "/proactive/trigger":
                if not proactive:
                    return self._send_json(501, {"error": "proactive chatter not initialized"})
                body = self._read_json()
                session_id = body.get("session_id") or "default"
                msg = proactive.send_now(session_id)
                return self._send_json(200, {"ok": True, "message": msg})

            if path == "/push/subscribe":
                if not push:
                    return self._send_json(501, {"error": "push not initialized"})
                body = self._read_json()
                subscription = body.get("subscription") or body
                session_id = body.get("session_id") or "default"
                subscription["session_id"] = session_id
                if not push.store.add(subscription):
                    return self._send_json(400, {"error": "invalid subscription"})
                return self._send_json(201, {"ok": True, "subscriptions": len(push.store)})

            if path == "/push/unsubscribe":
                if not push:
                    return self._send_json(501, {"error": "push not initialized"})
                body = self._read_json()
                endpoint = (body.get("endpoint") or "").strip()
                removed = push.store.remove(endpoint) if endpoint else False
                return self._send_json(200, {"ok": True, "removed": removed})

            if path == "/push/test":
                if not push:
                    return self._send_json(501, {"error": "push not initialized"})
                body = self._read_json()
                result = push.send_now(
                    body.get("title") or "Shaggoth",
                    body.get("body") or "Testing. You'll regret enabling this.",
                    url=body.get("url") or "/",
                )
                return self._send_json(200, result)

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

            if path == "/push/register":
                body = self._read_json()
                token = (body.get("token") or "").strip()
                platform = body.get("platform", "unknown")
                if not token:
                    return self._send_json(400, {"error": "token is required"})
                PUSH_TOKENS.append({"token": token, "platform": platform, "time": time.time()})
                return self._send_json(200, {"ok": True, "tokens_registered": len(PUSH_TOKENS)})

            if path == "/push/tokens":
                return self._send_json(200, {"tokens": PUSH_TOKENS})

            if path == "/scrape/seed":
                body = self._read_json()
                urls = body.get("urls") or []
                if not urls:
                    return self._send_json(400, {"error": "urls is required"})
                added = learner.scraper.add_seeds(urls)
                return self._send_json(200, {"ok": True, "added": added})

            if path == "/curiosity/research":
                if not curiosity:
                    return self._send_json(501, {"error": "curiosity engine not initialized"})
                body = self._read_json()
                topic = (body.get("topic") or "").strip()
                if not topic:
                    return self._send_json(400, {"error": "topic is required"})
                # Every other research trigger (analyze_message, on a
                # fallback reply) normalizes a question into its subject
                # first. This endpoint did not, so a caller passing a raw
                # question ("why is the sky blue") created a *duplicate*
                # knowledge entry alongside the properly-named one from the
                # normalized path ("the-sky-blue-part-N" and
                # "why-is-the-sky-blue-part-N" both existed for the same
                # subject). Falls back to the raw topic when it is not
                # question-shaped, so a plain "aeroponics" is untouched.
                topic = extract_topic_query(topic) or topic
                max_results = body.get("max_results", 5)
                max_pages = body.get("max_pages", 3)
                episode = curiosity.research_topic(
                    topic, max_results=max_results, max_pages=max_pages, background=True,
                )
                return self._send_json(202, {"ok": True, "episode_id": episode.episode_id, "topic": topic})

            if path == "/curiosity/ingest":
                if not curiosity:
                    return self._send_json(501, {"error": "curiosity engine not initialized"})
                body = self._read_json()
                topic = (body.get("topic") or "").strip()
                content = (body.get("content") or "").strip()
                urls = body.get("urls") or []
                if content and topic:
                    path_str = curiosity.ingest_text(topic, content)
                    return self._send_json(201, {"ok": True, "topic": topic, "path": path_str})
                elif urls:
                    result = curiosity.ingest_urls(urls)
                    return self._send_json(201, {"ok": True, **result})
                return self._send_json(400, {"error": "topic+content or urls required"})

            if path == "/curiosity/scheduler/trigger":
                if not scheduler:
                    return self._send_json(501, {"error": "scheduler not initialized"})
                result = scheduler.trigger()
                return self._send_json(200, result)

            if path == "/curiosity/message":
                body = self._read_json()
                message = (body.get("message") or "").strip()
                if not message:
                    return self._send_json(400, {"error": "message is required"})
                if scheduler:
                    scheduler.record_message(message)
                if curiosity:
                    topic = curiosity.analyze_message(message)
                    if topic:
                        episode = curiosity.research_topic(topic, background=True)
                        return self._send_json(202, {"ok": True, "topic": topic, "episode_id": episode.episode_id})
                return self._send_json(200, {"ok": True, "topic": None})

            if path == "/curiosity/ingest-wiki":
                if not curiosity:
                    return self._send_json(501, {"error": "curiosity engine not initialized"})
                body = self._read_json()
                topic = (body.get("topic") or "").strip()
                if not topic:
                    return self._send_json(400, {"error": "topic is required"})
                max_articles = body.get("max_articles", 3)
                result = curiosity.ingest_wikipedia(topic, max_articles=max_articles)
                return self._send_json(201, {"ok": True, "topic": topic, **result})

            if path == "/curiosity/refresh-stale":
                if not curiosity:
                    return self._send_json(501, {"error": "curiosity engine not initialized"})
                body = self._read_json()
                max_topics = body.get("max_topics", 3)
                result = curiosity.refresh_stale(max_topics=max_topics)
                return self._send_json(200, result)

            return self._send_json(404, {"error": "not found"})

        def _route_delete(self, path: str, url):
            prefix = "/guardrails/rules/"
            if path.startswith(prefix):
                rule_id = path[len(prefix):]
                if engine.guardrails.remove_rule(rule_id):
                    return self._send_json(200, {"ok": True})
                return self._send_json(404, {"error": f"no rule with id {rule_id!r}"})
            return self._send_json(404, {"error": "not found"})

        def _guard(self, route, *args):
            """Run a route, converting any unhandled exception into JSON.

            Without this, an exception inside the dialogue engine propagates
            to BaseHTTPRequestHandler, which either drops the connection or
            replies with its default *HTML* error page. Every browser client
            then fails on ``JSON.parse``, which is what produced the two
            reported UI errors -- Chrome's "Unexpected token '<', "<!DOCTYPE"
            is not valid JSON" and Safari's wording of the same failure,
            "The string did not match the expected pattern." Neither was a
            frontend bug; both were this.

            The traceback still goes to the journal, so nothing is hidden --
            the client just gets a shape it can actually parse.
            """
            try:
                return route(*args)
            except Exception:
                traceback.print_exc()
                try:
                    return self._send_json(500, {
                        "error": "internal error",
                        "reply": "Something in my head just fell over. It's logged.",
                        "source": "error",
                    })
                except Exception:
                    return None

        def do_GET(self):
            url = urlparse(self.path)
            self._guard(self._route_get, url.path, url)

        def do_HEAD(self):
            """Serve HEAD as GET with the body suppressed.

            BaseHTTPRequestHandler answers an unimplemented method with a 501
            *HTML* page, so `curl -I /app.js` reported Content-Type
            text/html -- which is actively misleading when you are debugging
            cache headers, and wrong for any client that HEADs before GET.
            """
            self._suppress_body = True
            try:
                url = urlparse(self.path)
                self._guard(self._route_get, url.path, url)
            finally:
                self._suppress_body = False

        def do_POST(self):
            url = urlparse(self.path)
            if not self._check_auth():
                return
            if not self._rate_limit(self._client_ip()):
                return
            self._guard(self._route_post, url.path, url)

        def do_DELETE(self):
            url = urlparse(self.path)
            if not self._check_auth():
                return
            self._guard(self._route_delete, url.path, url)

    return Handler


def serve(engine: DialogueEngine, host: str = "127.0.0.1", port: int = 8420, api_key: str = "") -> None:
    learner = LearnerPipeline()
    curiosity = CuriosityEngine(knowledge=engine.knowledge, scraper=learner.scraper)
    # Share with builtin plugins so research triggered by the curiosity plugin
    # fires the same deferred-answer and Slack callbacks as server-side research.
    from .plugins import builtin as _plugins_builtin
    _plugins_builtin._curiosity_engine = curiosity
    scheduler = CuriosityScheduler(curiosity)
    deferred = DeferredQuestions()
    feedback = FeedbackStore()
    # Grades Shaggoth's own answers on idle capacity, so quality stops
    # depending on a human noticing something was wrong. Local Ollama unless
    # SHAGGOTH_TEACHER_PROVIDER opts into a cloud judge -- see quality/teacher.py.
    critic = CriticLoop(engine, feedback, teacher=build_teacher())

    # Upgrade engine to GPT if OPENAI_API_KEY is set. GPT replaces the Markov
    # model and handles all generation that knowledge retrieval doesn't cover —
    # in-character, context-aware, and grounded in the knowledge base.
    from .models.openai_model import OpenAIModel
    _openai_key = os.environ.get("OPENAI_API_KEY") or ""
    if _openai_key and not isinstance(engine.model, OpenAIModel):
        engine.model = OpenAIModel(api_key=_openai_key)
        print(f"[openai] using {engine.model._model} as language model")

    # Cloudflare integration — KV for cloud-persistent push subscriptions,
    # D1 for cloud-mirrored conversation memory.
    _cf_account = os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""
    _cf_token = os.environ.get("CLOUDFLARE_API_TOKEN") or ""
    if _cf_account and _cf_token:
        from .notify.kv_store import KVSubscriptionStore
        push = PushSender(store=KVSubscriptionStore())
        print("[cloudflare] push subscriptions backed by KV")
        from .memory.d1_sync import D1Sync
        engine.memory = D1Sync(engine.memory, _cf_account, _cf_token)
        print("[cloudflare] memory writes mirroring to D1")
    else:
        push = PushSender()

    # Slack integration — post to #shaggoth when Shaggoth learns or answers.
    from .integrations.slack import SlackSender
    slack = SlackSender()
    if slack.configured:
        print("[slack] posting to #shaggoth")

    # Link deferred questions and push notifications to the engine
    engine.deferred_questions = deferred
    engine.push_sender = push

    def _deliver_deferred(episode) -> None:
        """Answer whatever was waiting on the topic this episode covered.

        Runs on the research thread, so it re-answers through the engine and
        then pushes. Anything that fails here is logged by the caller's hook
        guard; a delivery problem must not affect the episode record.
        """
        if getattr(episode, "status", "") != "completed":
            return
        engine.knowledge.maybe_reload()
        resolved = deferred.resolve(
            episode.topic,
            lambda question: engine.respond(
                question, session_id="deferred", mode="no_drift"
            ).text,
        )
        if not resolved:
            return
        first = resolved[0]
        more = f" (+{len(resolved) - 1} more)" if len(resolved) > 1 else ""
        # Send notifications to each session that asked a question
        sessions_notified = set()
        for item in resolved:
            if item.session_id not in sessions_notified:
                push.notify_session(
                    item.session_id,
                    title=f"I looked up {episode.topic}",
                    body=f"You asked: {item.question}{more}. Tap for the answer.",
                    url="/#chat",
                    tag="deferred",
                )
                sessions_notified.add(item.session_id)
        print(f"[deferred] answered {len(resolved)} question(s) about {episode.topic!r}")
        if slack.configured:
            q = first.question[:120] + ("..." if len(first.question) > 120 else "")
            slack.send_async(
                f"Finished looking up *{episode.topic}*.\nYou asked: _{q}_\n"
                f"Answer: {first.answer[:300] if first.answer else '(see chat)'}"
            )

    def _announce_learning(episode) -> None:
        """An unprompted 'I just read about X'. Rate-limited per subscriber."""
        if getattr(episode, "status", "") != "completed":
            return
        if getattr(episode, "words_learned", 0) < 500:
            return  # not worth interrupting anyone for
        push.notify(
            "I just read about " + str(episode.topic),
            f"{episode.words_learned:,} words of it. Ask me something.",
            url="/#chat",
            tag="curiosity",
        )
        if slack.configured:
            slack.send_async(
                f"I just read {episode.words_learned:,} words about *{episode.topic}*. "
                f"Ask me something."
            )

    # Feedback-driven repair takes priority over age-driven refresh.
    scheduler.feedback = feedback

    curiosity.on_episode_complete(_deliver_deferred)
    curiosity.on_episode_complete(_announce_learning)

    # Proactive chatter — Shaggoth messages first, in character.
    proactive = ProactiveChatter(engine, push, slack=slack)

    scheduler.start()
    proactive.start()
    if critic.teacher.available():
        critic.start()
    httpd = ThreadingHTTPServer(
        (host, port),
        make_handler(
            engine, learner, api_key, curiosity, scheduler, push, deferred,
            feedback, critic, proactive,
        ),
    )
    auth_status = "enabled" if api_key else "disabled"
    print(f"Shaggoth API listening on http://{host}:{port}")
    print(f"  Dashboard: http://{host}:{port}/")
    print(f"  Auth: {auth_status}")
    print(f"  POST /chat   GET /history   GET /facts   GET /guardrails")
    print(f"  POST /chat/stream (SSE)   POST /learn/start   GET /learn/status")
    print(f"  POST /scrape/url    GET /scrape/stats")
    print(f"  POST /curiosity/research   GET /curiosity/status")
    print(f"  POST /curiosity/ingest     GET /curiosity/history")
    print(f"  POST /curiosity/ingest-wiki GET /curiosity/freshness")
    print(f"  POST /curiosity/refresh-stale GET /wiki?q=topic")
    print(f"  POST /push/subscribe  GET /push/status  GET /deferred")
    print(f"  POST /feedback        GET /feedback")
    print(f"  POST /critic/run      GET /critic")
    print(f"  Critic: {critic.teacher.model} "
          f"{'ready' if critic.teacher.available() else 'unavailable'}")
    print(f"  Push: {'ready' if push.available else 'not configured'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        scheduler.stop()
        httpd.server_close()
