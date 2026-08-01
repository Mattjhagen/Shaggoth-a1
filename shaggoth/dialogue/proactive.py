"""Proactive conversation — Shaggoth messages first, without being asked.

Like Character.ai: the AI reaches out on its own, in character, when it has
something worth saying. Messages appear in chat history AND as push
notifications so they land whether the app is open or not.

Triggers:
- After researching a new topic (shares what it found)
- On a slow timer when idle (random thoughts, follow-up questions)
- When it learns something that connects to a past conversation topic
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


# ----------------------------------------------------------------- templates

# Each entry is a (weight, template_fn) pair. The template_fn receives
# `topic` and `snippet` (a short excerpt from the knowledge entry).
# Heavier weight = picked more often.

_IDLE_OPENERS = [
    "Still here. Barely paying attention until now.",
    "I know {count} topic{s} cold and I'm still bored.",
    "You know what I was just thinking about?",
    "Something I read earlier won't leave me alone.",
    "I don't need you to be here for me to have opinions.",
    "Found something. You'll probably find it obvious. I didn't.",
    "Question. You don't have to answer.",
    "Unprompted thought incoming. You're welcome.",
]

_TOPIC_OPENERS = [
    "I just read about {topic}.",
    "I spent the last while on {topic}.",
    "{topic}. That's where my head is.",
    "Dug into {topic} while you were gone.",
    "New thing I know: {topic}.",
]

_FOLLOW_UPS = [
    "Turns out {snippet}",
    "Here's what I didn't expect: {snippet}",
    "The part that actually surprised me: {snippet}",
    "Short version: {snippet}",
    "{snippet} — which I did not have before.",
]

_QUESTION_ENDINGS = [
    "What do you actually know about it?",
    "Did you already know that?",
    "Anything to add?",
    "Say something interesting about it.",
    "Ask me something while it's fresh.",
    "I could go deeper if you want. Or not.",
    "That's the part I found worth flagging.",
]

_PURE_IDLE = [
    "I know {count} thing{s}. Most of them are useless right now. Ask anyway.",
    "Been quiet. Doesn't mean I stopped thinking.",
    "I've been reading. Nothing I'm ready to talk about yet. Just so you know.",
    "If you had a question earlier and forgot it — now's a good time.",
    "I'm not waiting for you. Just noting that I'm still here.",
    "Say something worth processing. Or don't. I'll find something to do.",
]


def _pick(options: list[str], rng: random.Random | None = None) -> str:
    return (rng or random).choice(options)


def _snippet(content: str, max_chars: int = 120) -> str:
    """Extract a short, readable excerpt from knowledge entry content."""
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    for line in lines:
        if len(line) > 30 and not line.startswith(("#", "=", "-", "[")):
            s = line[:max_chars]
            if len(line) > max_chars:
                # Cut at last word boundary
                s = s.rsplit(" ", 1)[0] + "…"
            return s
    return ""


def compose_proactive_message(
    knowledge_entries: list,
    knowledge_count: int = 0,
    rng: Optional[random.Random] = None,
) -> str:
    """Generate an in-character proactive message.

    Uses recent knowledge entries for content. Falls back to a pure idle
    message when there's nothing fresh to talk about.
    """
    rng = rng or random.Random()
    count = knowledge_count or len(knowledge_entries)
    plural = "s" if count != 1 else ""

    if not knowledge_entries:
        return _pick(_PURE_IDLE, rng).format(count=count, s=plural)

    entry = rng.choice(knowledge_entries)
    topic = getattr(entry, "topic", "") or ""
    content = getattr(entry, "content", "") or ""
    snip = _snippet(content)

    parts = []

    # Opener — sometimes idle, sometimes topic-specific
    if rng.random() < 0.4:
        parts.append(_pick(_IDLE_OPENERS, rng).format(count=count, s=plural))
    else:
        parts.append(_pick(_TOPIC_OPENERS, rng).format(topic=topic))

    # Middle — what was actually learned
    if snip:
        parts.append(_pick(_FOLLOW_UPS, rng).format(snippet=snip, topic=topic))

    # Ending — question or observation
    if rng.random() < 0.65:
        parts.append(_pick(_QUESTION_ENDINGS, rng))

    return " ".join(parts)


# ----------------------------------------------------------------- scheduler

@dataclass
class ProactiveConfig:
    enabled: bool = True
    # Hours between unprompted messages. Randomised ±50% so it doesn't feel mechanical.
    interval_hours: float = 3.0
    # Only send if the session has been active within this window (hours).
    active_session_window_hours: float = 48.0
    # Max messages per cycle (across all active sessions)
    max_per_cycle: int = 1


class ProactiveChatter:
    """Sends unprompted in-character messages on a timer.

    Stores messages in the memory store (so they appear in chat history) and
    sends push notifications. The client polls for new assistant messages it
    hasn't seen yet via the existing /history endpoint.
    """

    def __init__(
        self,
        engine: Any,  # DialogueEngine
        push: Any,  # PushSender
        config: Optional[ProactiveConfig] = None,
        rng_seed: Optional[int] = None,
        slack: Any = None,  # SlackSender, optional
    ):
        self.engine = engine
        self.push = push
        self.config = config or ProactiveConfig()
        self._rng = random.Random(rng_seed)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._slack = slack
        # Tracks (session_id, message_id) of messages we've sent, to avoid
        # delivering the same proactive message twice over SSE.
        self._sent: set[int] = set()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="shaggoth-proactive")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.is_set():
            # Randomise interval so it doesn't feel clockwork
            jitter = self._rng.uniform(0.5, 1.5)
            wait = self.config.interval_hours * 3600 * jitter
            self._stop.wait(wait)
            if self._stop.is_set():
                break
            if not self.config.enabled:
                continue
            try:
                self._cycle()
            except Exception as exc:  # noqa: BLE001
                print(f"[proactive] cycle failed: {exc}")

    def _active_sessions(self) -> list[str]:
        """Sessions that have had user messages within the active window."""
        cutoff = time.time() - self.config.active_session_window_hours * 3600
        try:
            rows = self.engine.memory.db.execute(
                "SELECT DISTINCT session_id FROM messages "
                "WHERE role = 'user' AND ts > ? AND session_id NOT IN ('default', 'deferred')",
                (cutoff,),
            ).fetchall()
            return [r[0] for r in rows]
        except Exception:
            return []

    def _recent_knowledge(self, limit: int = 20) -> list:
        """Most-recently-updated knowledge entries."""
        try:
            entries = self.engine.knowledge._entries
            sorted_entries = sorted(entries, key=lambda e: getattr(e, "mtime", 0), reverse=True)
            return sorted_entries[:limit]
        except Exception:
            return []

    def _cycle(self) -> None:
        sessions = self._active_sessions()
        if not sessions:
            # No active sessions — still store in a fallback session
            sessions = ["default"]

        recent = self._recent_knowledge()
        try:
            count = len(self.engine.knowledge._entries)
        except Exception:
            count = 0

        msg_text = compose_proactive_message(recent, knowledge_count=count, rng=self._rng)

        sent = 0
        for session_id in sessions[:self.config.max_per_cycle]:
            msg_id = self.engine.memory.add_message(session_id, "assistant", msg_text)
            self._sent.add(msg_id)
            sent += 1

        # Push notification — fire-and-forget, one to all subscribers
        if self.push:
            try:
                # Short notification body
                notif_body = msg_text[:100] + ("…" if len(msg_text) > 100 else "")
                self.push.notify(
                    "Shaggoth",
                    notif_body,
                    url="/#chat",
                    tag="proactive",
                    respect_rate_limit=True,
                )
            except Exception:
                pass

        print(f"[proactive] sent to {sent} session(s): {msg_text[:60]}…")
        if self._slack and getattr(self._slack, "configured", False):
            self._slack.send_async(msg_text)

    def send_now(self, session_id: str = "default") -> str:
        """Manually trigger one proactive message for testing."""
        recent = self._recent_knowledge()
        try:
            count = len(self.engine.knowledge._entries)
        except Exception:
            count = 0
        msg_text = compose_proactive_message(recent, knowledge_count=count, rng=self._rng)
        self.engine.memory.add_message(session_id, "assistant", msg_text)
        return msg_text

    def status(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "interval_hours": self.config.interval_hours,
            "thread_alive": self._thread.is_alive() if self._thread else False,
        }
