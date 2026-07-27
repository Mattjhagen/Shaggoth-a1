"""Knowledge freshness tracker — monitors entry age and triggers re-research.

Tracks when knowledge entries were created and identifies stale entries
that should be re-researched to keep the knowledge base current.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from ..config import DATA_DIR
from ..knowledge.engine import KnowledgeBase

FRESHNESS_PATH = DATA_DIR / "knowledge_freshness.json"


class FreshnessTracker:
    """Tracks when knowledge entries were last updated and identifies stale ones."""

    def __init__(
        self,
        knowledge: KnowledgeBase | None = None,
        freshness_path: str | Path | None = None,
        stale_days: int = 30,
    ):
        self.knowledge = knowledge or KnowledgeBase()
        self.freshness_path = Path(freshness_path) if freshness_path else FRESHNESS_PATH
        self.freshness_path.parent.mkdir(parents=True, exist_ok=True)
        self.stale_days = stale_days
        self._records: dict[str, float] = self._load()

    def _load(self) -> dict[str, float]:
        if self.freshness_path.exists():
            try:
                return json.loads(self.freshness_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self) -> None:
        self.freshness_path.write_text(
            json.dumps(self._records, indent=2), encoding="utf-8"
        )

    def record_update(self, topic: str) -> None:
        """Record that a topic was just researched/updated."""
        self._records[topic.lower()] = time.time()
        self._save()

    def get_age_days(self, topic: str) -> float | None:
        """Return how many days since a topic was last updated, or None."""
        ts = self._records.get(topic.lower())
        if ts is None:
            return None
        return (time.time() - ts) / 86400

    def is_stale(self, topic: str) -> bool:
        """Check if a topic's knowledge is older than the stale threshold."""
        age = self.get_age_days(topic)
        if age is None:
            return True  # never researched = stale
        return age > self.stale_days

    def get_stale_topics(self) -> list[dict]:
        """Find all knowledge entries that are stale or never researched."""
        stale: list[dict] = []
        for entry in self.knowledge.list_entries():
            topic = entry["topic"]
            age = self.get_age_days(topic)
            if age is None or age > self.stale_days:
                stale.append({
                    "topic": topic,
                    "age_days": round(age, 1) if age is not None else None,
                    "word_count": entry["word_count"],
                })
        return stale

    def get_fresh_topics(self) -> list[dict]:
        """Find all knowledge entries that are still fresh."""
        fresh: list[dict] = []
        for entry in self.knowledge.list_entries():
            topic = entry["topic"]
            age = self.get_age_days(topic)
            if age is not None and age <= self.stale_days:
                fresh.append({
                    "topic": topic,
                    "age_days": round(age, 1),
                    "word_count": entry["word_count"],
                })
        return fresh

    def status(self) -> dict:
        stale = self.get_stale_topics()
        fresh = self.get_fresh_topics()
        return {
            "total_entries": len(self.knowledge.list_entries()),
            "stale_count": len(stale),
            "fresh_count": len(fresh),
            "stale_days_threshold": self.stale_days,
            "stale_topics": stale,
            "fresh_topics": fresh,
        }
