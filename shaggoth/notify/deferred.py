"""Questions Shaggoth could not answer yet, kept until it can.

When a turn ends in ``fallback`` the engine admits it does not know and
curiosity goes off to research the topic. Until now the answer landed in the
knowledge base and nobody was ever told: you had to think to ask again.

A pending question is recorded instead, and when a research episode finishes
covering that topic it is re-answered and delivered -- pushed if the browser
has opted in, and always available from ``GET /deferred``.

Persisted to disk, because the whole point is that the answer may arrive long
after the process that took the question.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

from ..config import DATA_DIR

DEFERRED_PATH = DATA_DIR / "deferred_questions.json"

#: Questions older than this are dropped unanswered. Curiosity may simply
#: never cover the topic, and a queue that only grows is a leak.
DEFAULT_MAX_AGE_SECONDS = 7 * 24 * 3600

#: Cap on stored questions, newest kept.
MAX_PENDING = 200


@dataclass
class PendingQuestion:
    """A question awaiting the knowledge to answer it."""

    question: str
    topic: str
    session_id: str = "default"
    asked_at: float = 0.0
    answered_at: Optional[float] = None
    answer: str = ""
    delivered: bool = False

    @property
    def answered(self) -> bool:
        return self.answered_at is not None

    def age(self, now: Optional[float] = None) -> float:
        return (time.time() if now is None else now) - self.asked_at


def _norm(text: str) -> str:
    return " ".join((text or "").lower().split())


class DeferredQuestions:
    """The pending-question queue. Safe to use from several threads."""

    def __init__(
        self,
        path: Optional[Path] = None,
        max_age: float = DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        self.path = Path(path) if path else DEFERRED_PATH
        self.max_age = max_age
        self._lock = threading.Lock()
        self._items: list[PendingQuestion] = []
        self._load()

    # -- persistence ------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, list):
            return
        for item in raw:
            if isinstance(item, dict) and item.get("question"):
                self._items.append(PendingQuestion(**{
                    k: v for k, v in item.items()
                    if k in PendingQuestion.__dataclass_fields__
                }))

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps([asdict(i) for i in self._items], indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    # -- recording --------------------------------------------------------

    def record(self, question: str, topic: str, session_id: str = "default",
               now: Optional[float] = None) -> Optional[PendingQuestion]:
        """Remember a question Shaggoth could not answer.

        Returns the stored item, or ``None`` when there is nothing usable to
        store or the same question is already pending for that session.
        """
        question = (question or "").strip()
        topic = (topic or "").strip()
        if not question or not topic:
            return None

        now = time.time() if now is None else now
        with self._lock:
            for existing in self._items:
                if (
                    not existing.answered
                    and existing.session_id == session_id
                    and _norm(existing.question) == _norm(question)
                ):
                    return None  # already waiting on this one
            item = PendingQuestion(
                question=question, topic=topic,
                session_id=session_id, asked_at=now,
            )
            self._items.append(item)
            if len(self._items) > MAX_PENDING:
                del self._items[: len(self._items) - MAX_PENDING]
            self._save()
        return item

    # -- resolution -------------------------------------------------------

    def matching(self, topic: str, now: Optional[float] = None) -> list[PendingQuestion]:
        """Unanswered questions this topic would satisfy.

        Matched on shared words rather than string equality: the question was
        "what is aeroponic farming" and the episode is filed under
        "aeroponic farming", or vice versa.
        """
        wanted = set(_norm(topic).split())
        if not wanted:
            return []
        now = time.time() if now is None else now
        out = []
        with self._lock:
            for item in self._items:
                if item.answered or item.age(now) > self.max_age:
                    continue
                stored = set(_norm(item.topic).split())
                if stored and (stored <= wanted or wanted <= stored):
                    out.append(item)
        return out

    def resolve(self, topic: str, answer_for: Callable[[str], str],
                now: Optional[float] = None) -> list[PendingQuestion]:
        """Answer everything waiting on ``topic``.

        ``answer_for`` is called with the original question text and should
        return a reply, or ``""`` if it still cannot be answered -- in which
        case the question stays pending rather than being marked done with
        nothing to show.
        """
        now = time.time() if now is None else now
        resolved: list[PendingQuestion] = []
        for item in self.matching(topic, now):
            try:
                answer = (answer_for(item.question) or "").strip()
            except Exception as exc:  # noqa: BLE001
                print(f"[deferred] could not answer {item.question!r}: {exc}")
                continue
            if not answer:
                continue
            with self._lock:
                if item.answered:
                    continue  # another thread resolved it first
                item.answer = answer
                item.answered_at = now
            resolved.append(item)
        if resolved:
            with self._lock:
                self._save()
        return resolved

    def mark_delivered(self, items: list[PendingQuestion]) -> None:
        with self._lock:
            for item in items:
                item.delivered = True
            self._save()

    # -- reading ----------------------------------------------------------

    def pending(self, session_id: Optional[str] = None) -> list[PendingQuestion]:
        with self._lock:
            return [
                i for i in self._items
                if not i.answered and (session_id is None or i.session_id == session_id)
            ]

    def answered(self, session_id: Optional[str] = None,
                 undelivered_only: bool = False) -> list[PendingQuestion]:
        with self._lock:
            return [
                i for i in self._items
                if i.answered
                and (session_id is None or i.session_id == session_id)
                and (not undelivered_only or not i.delivered)
            ]

    def prune(self, now: Optional[float] = None) -> int:
        """Drop questions too old to still be worth answering."""
        now = time.time() if now is None else now
        with self._lock:
            before = len(self._items)
            self._items = [
                i for i in self._items
                if i.answered or i.age(now) <= self.max_age
            ]
            removed = before - len(self._items)
            if removed:
                self._save()
        return removed

    def status(self) -> dict:
        with self._lock:
            return {
                "pending": sum(1 for i in self._items if not i.answered),
                "answered": sum(1 for i in self._items if i.answered),
                "undelivered": sum(1 for i in self._items if i.answered and not i.delivered),
            }
