"""Continuous self-critique: learning while nobody is probing it.

The learning loop grew *breadth* on its own but never *quality*, because
quality depended on a human noticing an answer was bad. This closes that gap:
Shaggoth asks itself its own past questions, has the local teacher grade the
answers, and files the failures as feedback -- which the curiosity scheduler
already drains as a repair queue, ahead of anything refreshed for being merely
old.

Three constraints shape the design, all of them learned on this hardware:

1. **It must yield.** One judgement costs ~20 s of CPU on a box that also
   serves chat and renders a dashboard on tty1. The loop checks load before
   every judgement and stands down when the machine is busy. Idle time is
   free; contended time is not.
2. **It must be bounded.** A batch has a hard cap. An unbounded critic will
   happily chew 480 entries and peg the machine for hours.
3. **It must never outrank a human.** Its verdicts are recorded as
   ``critic-llm`` and are always overridable by a thumbs-down.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from .teacher import Teacher

#: 1-minute load average above which the loop stands down. The box has 16
#: cores; this leaves plenty of headroom for chat, the scheduler and tty1.
DEFAULT_MAX_LOAD = 6.0

#: Judgements per batch. At ~20 s each this is roughly 10 minutes of work.
DEFAULT_BATCH = 30

#: Seconds between batches when there is nothing to do.
DEFAULT_IDLE_SLEEP = 300.0

#: Pause between judgements, so the loop never monopolises a core outright.
DEFAULT_PACE = 2.0


@dataclass
class CriticStats:
    judged: int = 0
    good: int = 0
    weak: int = 0
    bad: int = 0
    skipped_busy: int = 0
    unusable: int = 0
    last_run: float = 0.0
    last_error: str = ""
    seconds_spent: float = 0.0

    def as_dict(self) -> dict:
        return {
            "judged": self.judged,
            "good": self.good,
            "weak": self.weak,
            "bad": self.bad,
            "skipped_busy": self.skipped_busy,
            "unusable": self.unusable,
            "last_run": self.last_run,
            "last_error": self.last_error,
            "seconds_spent": round(self.seconds_spent, 1),
            "avg_seconds": round(self.seconds_spent / self.judged, 1) if self.judged else 0.0,
        }


def machine_busy(max_load: float = DEFAULT_MAX_LOAD) -> bool:
    """Whether the box is under enough load that the critic should stand down."""
    try:
        return os.getloadavg()[0] > max_load
    except (OSError, AttributeError):
        return False


class CriticLoop:
    """Grades Shaggoth's answers to its own past questions, on idle capacity."""

    def __init__(
        self,
        engine,
        feedback,
        memory=None,
        teacher: Optional[Teacher] = None,
        batch: int = DEFAULT_BATCH,
        max_load: float = DEFAULT_MAX_LOAD,
        idle_sleep: float = DEFAULT_IDLE_SLEEP,
        pace: float = DEFAULT_PACE,
    ) -> None:
        self.engine = engine
        self.feedback = feedback
        self.memory = memory if memory is not None else getattr(engine, "memory", None)
        self.teacher = teacher or Teacher()
        self.batch = batch
        self.max_load = max_load
        self.idle_sleep = idle_sleep
        self.pace = pace

        self.stats = CriticStats()
        self._seen: set = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="shaggoth-critic", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        return {
            "running": bool(self._thread and self._thread.is_alive()),
            "model": self.teacher.model,
            "available": self.teacher.available(),
            "batch": self.batch,
            "max_load": self.max_load,
            "questions_seen": len(self._seen),
            **self.stats.as_dict(),
        }

    # -- work --------------------------------------------------------------

    def questions(self, limit: int) -> list:
        """Real questions people have asked, not synthetic ones.

        Grading invented questions would measure the corpus against a fiction.
        These are what was actually asked, so a bad verdict is a bad answer
        someone actually received.
        """
        if self.memory is None:
            return []
        try:
            # Locked accessor -- this loop runs on the critic's own background
            # thread, concurrently with request-handling threads on the same
            # sqlite3.Connection. Reaching into memory.db directly here raced
            # them (SQLITE_MISUSE, silently caught below).
            rows = self.memory.recent_user_messages(limit * 6)
        except Exception as exc:  # noqa: BLE001
            self.stats.last_error = str(exc)[:200]
            return []

        out = []
        for text in rows:
            text = (text or "").strip()
            if len(text) < 8 or text.lower() in self._seen:
                continue
            out.append(text)
            if len(out) >= limit:
                break
        return out

    def judge_once(self, question: str) -> Optional[str]:
        """Answer a question, grade it, and file a complaint if it is bad."""
        # research=False equivalent: this is Shaggoth talking to itself and
        # must not steer what it goes and learns.
        reply = self.engine.respond(question, session_id="critic", mode="no_drift")
        verdict = self.teacher.judge(question, reply.text)

        self.stats.seconds_spent += verdict.seconds
        self._seen.add(question.lower())

        if not verdict.usable:
            self.stats.unusable += 1
            return None

        self.stats.judged += 1
        setattr(self.stats, verdict.verdict, getattr(self.stats, verdict.verdict) + 1)

        # Only a clear failure is filed. "weak" is not enough to spend a
        # research cycle on, and filing it would drown the genuine failures.
        if verdict.negative and reply.entries_used:
            self.feedback.record(
                question=question,
                verdict="bad",
                answer=reply.text,
                source="critic-llm",
                entries_used=reply.entries_used,
                reasoning=reply.reasoning,
                note=f"auto-graded bad by {verdict.model}",
                session_id="critic",
            )
        return verdict.verdict

    def run_batch(self, limit: Optional[int] = None) -> dict:
        """One bounded pass. Returns what it did."""
        limit = self.batch if limit is None else limit
        if not self.teacher.available():
            self.stats.last_error = f"{self.teacher.model} not available"
            return {"judged": 0, "reason": self.stats.last_error}

        done = 0
        for question in self.questions(limit):
            if self._stop.is_set():
                break
            if machine_busy(self.max_load):
                # Stand down rather than queue: the point is to use idle
                # capacity, not to compete for busy capacity.
                self.stats.skipped_busy += 1
                break
            try:
                self.judge_once(question)
                done += 1
            except Exception as exc:  # noqa: BLE001
                self.stats.last_error = str(exc)[:200]
                print(f"[critic] {exc}")
            self._stop.wait(self.pace)

        self.stats.last_run = time.time()
        return {"judged": done, **self.stats.as_dict()}

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_batch()
            except Exception as exc:  # noqa: BLE001
                # A failed batch must never kill the thread; a dead critic
                # looks exactly like an idle one from outside.
                self.stats.last_error = str(exc)[:200]
                print(f"[critic] batch failed: {exc}")
            self._stop.wait(self.idle_sleep)
