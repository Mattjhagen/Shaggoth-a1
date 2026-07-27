"""Background curiosity scheduler — autonomous learning on a timer.

Periodically scans recent conversations for knowledge gaps and
researches them automatically. Extends the existing LearnerPipeline
pattern with curiosity-specific scheduling.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, asdict
from typing import Any

from .engine import CuriosityEngine


@dataclass
class ScheduleConfig:
    """Configuration for the curiosity scheduler.

    The interval and threshold are deliberately low. The goal is continuous
    learning, and the previous defaults (60 minutes / 5 messages) meant a
    quiet hour produced nothing at all -- see :meth:`CuriosityScheduler._cycle`
    for why that was worse than it sounds.
    """
    enabled: bool = True
    interval_minutes: int = 15
    max_topics_per_cycle: int = 3
    max_results_per_topic: int = 5
    max_pages_per_topic: int = 3
    min_message_count: int = 2  # need this many messages before auto-research

    #: When conversation yields no topic, re-research the stalest knowledge
    #: entry instead of idling. Without this the loop only ever learns while
    #: someone is talking to it, which is not "always learning".
    refresh_stale_when_idle: bool = True
    max_stale_per_cycle: int = 1


class CuriosityScheduler:
    """Runs curiosity research in the background on a timer.

    Integrates with the dialogue engine to detect knowledge gaps
    from recent conversations and trigger autonomous research.
    """

    def __init__(
        self,
        curiosity: CuriosityEngine,
        config: ScheduleConfig | None = None,
        feedback=None,
    ):
        self.curiosity = curiosity
        self.config = config or ScheduleConfig()
        #: Optional FeedbackStore. When present, entries someone marked wrong
        #: are repaired before anything is refreshed for being merely old.
        self.feedback = feedback
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._message_buffer: list[str] = []
        self._lock = threading.Lock()

    def record_message(self, text: str) -> None:
        """Record a user message for later analysis."""
        with self._lock:
            self._message_buffer.append(text)
            # Keep buffer bounded
            if len(self._message_buffer) > 100:
                self._message_buffer = self._message_buffer[-50:]

    def start(self) -> None:
        """Start the background scheduler thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the background scheduler."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run_loop(self) -> None:
        interval = max(60, self.config.interval_minutes * 60)
        while not self._stop_event.is_set():
            self._stop_event.wait(interval)
            if self._stop_event.is_set():
                break
            # Checked every pass, not once at startup, so toggling `enabled`
            # on a live scheduler actually takes effect.
            if not self.config.enabled:
                continue
            try:
                self._cycle()
            except Exception as exc:  # noqa: BLE001
                # A failed cycle must never kill the thread. A dead thread
                # looks identical to an idle one from outside, and the daemon
                # would go on answering requests while silently never
                # learning again.
                print(f"[curiosity] cycle failed: {exc}")

    def _cycle(self) -> None:
        """Run one curiosity cycle: analyze buffered messages, research gaps."""
        if self.curiosity.is_running:
            return

        # Peek, do not drain.
        #
        # This used to clear the buffer before testing it against
        # min_message_count, so every cycle threw away whatever had
        # accumulated. Unless five messages happened to land inside one
        # 60-minute window, the count restarted at zero forever and the
        # scheduler never researched anything -- which is exactly what the
        # dashboard was reporting as STALLED: thread alive, 7 clues buffered,
        # nothing researched in 12 hours.
        with self._lock:
            messages = list(self._message_buffer)

        topics: list[str] = []
        if len(messages) >= self.config.min_message_count:
            for msg in messages:
                topic = self.curiosity.analyze_message(msg)
                if topic and topic not in topics:
                    topics.append(topic)
                if len(topics) >= self.config.max_topics_per_cycle:
                    break
            # Only now is the buffer spent: the messages have been analysed.
            with self._lock:
                del self._message_buffer[: len(messages)]

        if topics:
            for topic in topics:
                if self.curiosity.is_running:
                    break
                self.curiosity.research_topic(
                    topic,
                    max_results=self.config.max_results_per_topic,
                    max_pages=self.config.max_pages_per_topic,
                    background=False,
                )
            return

        # Nothing from conversation. Fix what is known to be *wrong* before
        # refreshing what is merely *old*: someone judging an answer bad is a
        # far better reason to spend a research cycle than an entry's age.
        if self._repair_one():
            return

        # Otherwise refresh the stalest thing it knows, so a quiet night still
        # teaches it something.
        if self.config.refresh_stale_when_idle and not self.curiosity.is_running:
            self.curiosity.refresh_stale(max_topics=self.config.max_stale_per_cycle)

    def _repair_one(self) -> bool:
        """Re-research the worst-performing entry. True if one was attempted."""
        if not self.feedback or self.curiosity.is_running:
            return False
        target = self.feedback.next_repair()
        if target is None:
            return False
        print(
            f"[curiosity] repairing {target.topic!r} "
            f"({target.bad} complaint(s)): {target.last_question!r}"
        )
        # Marked before researching, not after: if the research throws, the
        # cooldown still applies and one broken topic cannot capture every
        # future cycle.
        self.feedback.mark_repaired(target.topic)
        self.curiosity.research_topic(
            target.topic,
            max_results=self.config.max_results_per_topic,
            max_pages=self.config.max_pages_per_topic,
            background=False,
        )
        return True

    def trigger(self) -> dict:
        """Manually trigger an immediate curiosity cycle.

        Returns status of the triggered cycle.
        """
        with self._lock:
            messages = list(self._message_buffer)

        topics: list[str] = []
        for msg in messages:
            topic = self.curiosity.analyze_message(msg)
            if topic and topic not in topics:
                topics.append(topic)
            if len(topics) >= self.config.max_topics_per_cycle:
                break

        if not topics:
            return {"triggered": False, "reason": "no unknown topics found"}

        # Research the first topic in background
        episode = self.curiosity.research_topic(
            topics[0],
            max_results=self.config.max_results_per_topic,
            max_pages=self.config.max_pages_per_topic,
            background=True,
        )

        return {
            "triggered": True,
            "episode_id": episode.episode_id,
            "topic": episode.topic,
            "queued_topics": topics[1:],
        }

    def status(self) -> dict:
        return {
            "enabled": self.config.enabled,
            "interval_minutes": self.config.interval_minutes,
            "buffered_messages": len(self._message_buffer),
            "thread_alive": self._thread.is_alive() if self._thread else False,
        }
