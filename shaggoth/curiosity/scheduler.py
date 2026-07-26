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
    """Configuration for the curiosity scheduler."""
    enabled: bool = True
    interval_minutes: int = 60
    max_topics_per_cycle: int = 3
    max_results_per_topic: int = 5
    max_pages_per_topic: int = 3
    min_message_count: int = 5  # need this many messages before auto-research


class CuriosityScheduler:
    """Runs curiosity research in the background on a timer.

    Integrates with the dialogue engine to detect knowledge gaps
    from recent conversations and trigger autonomous research.
    """

    def __init__(
        self,
        curiosity: CuriosityEngine,
        config: ScheduleConfig | None = None,
    ):
        self.curiosity = curiosity
        self.config = config or ScheduleConfig()
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
        interval = self.config.interval_minutes * 60
        while not self._stop_event.is_set():
            self._stop_event.wait(interval)
            if self._stop_event.is_set():
                break
            self._cycle()

    def _cycle(self) -> None:
        """Run one curiosity cycle: analyze buffered messages, research gaps."""
        if self.curiosity.is_running:
            return

        with self._lock:
            messages = list(self._message_buffer)
            self._message_buffer.clear()

        if len(messages) < self.config.min_message_count:
            return

        # Find topics from recent messages
        topics: list[str] = []
        for msg in messages:
            topic = self.curiosity.analyze_message(msg)
            if topic and topic not in topics:
                topics.append(topic)
            if len(topics) >= self.config.max_topics_per_cycle:
                break

        # Research each topic
        for topic in topics:
            if self.curiosity.is_running:
                break
            self.curiosity.research_topic(
                topic,
                max_results=self.config.max_results_per_topic,
                max_pages=self.config.max_pages_per_topic,
                background=False,
            )

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
