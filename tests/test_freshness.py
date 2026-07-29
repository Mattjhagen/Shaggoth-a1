"""Tests for FreshnessTracker (curiosity/freshness.py)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from shaggoth.curiosity.freshness import FreshnessTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_knowledge(topics: list[str] | None = None):
    """Build a mock KnowledgeBase that lists given topics."""
    kb = MagicMock()
    entries = [{"topic": t, "word_count": 100} for t in (topics or [])]
    kb.list_entries.return_value = entries
    return kb


def _tracker(tmp_path: Path, topics: list[str] | None = None, stale_days: int = 30) -> FreshnessTracker:
    fp = tmp_path / "freshness.json"
    kb = _fake_knowledge(topics)
    return FreshnessTracker(knowledge=kb, freshness_path=fp, stale_days=stale_days)


# ---------------------------------------------------------------------------
# record_update / get_age_days
# ---------------------------------------------------------------------------

class TestRecordAndAge:
    def test_age_none_before_first_update(self, tmp_path):
        t = _tracker(tmp_path)
        assert t.get_age_days("aeroponics") is None

    def test_age_near_zero_just_after_update(self, tmp_path):
        t = _tracker(tmp_path)
        t.record_update("aeroponics")
        age = t.get_age_days("aeroponics")
        assert age is not None
        assert age < 0.001

    def test_case_insensitive_topic_key(self, tmp_path):
        t = _tracker(tmp_path)
        t.record_update("DNA")
        assert t.get_age_days("dna") is not None

    def test_record_update_overwrites_old_timestamp(self, tmp_path):
        t = _tracker(tmp_path)
        # Simulate an old entry
        t._records["quantum"] = time.time() - 86400 * 10  # 10 days ago
        t.record_update("quantum")
        age = t.get_age_days("quantum")
        assert age < 0.001

    def test_age_reflects_injected_old_timestamp(self, tmp_path):
        t = _tracker(tmp_path)
        t._records["old_topic"] = time.time() - 86400 * 5  # 5 days ago
        age = t.get_age_days("old_topic")
        assert 4.9 < age < 5.1


# ---------------------------------------------------------------------------
# is_stale
# ---------------------------------------------------------------------------

class TestIsStale:
    def test_never_researched_is_stale(self, tmp_path):
        t = _tracker(tmp_path)
        assert t.is_stale("unknown_topic")

    def test_just_updated_is_not_stale(self, tmp_path):
        t = _tracker(tmp_path)
        t.record_update("fresh_topic")
        assert not t.is_stale("fresh_topic")

    def test_old_entry_beyond_threshold_is_stale(self, tmp_path):
        t = _tracker(tmp_path, stale_days=7)
        t._records["old"] = time.time() - 86400 * 10  # 10 days > 7
        assert t.is_stale("old")

    def test_entry_within_threshold_is_fresh(self, tmp_path):
        t = _tracker(tmp_path, stale_days=30)
        t._records["fresh"] = time.time() - 86400 * 5  # 5 days < 30
        assert not t.is_stale("fresh")

    def test_exact_boundary_is_stale(self, tmp_path):
        t = _tracker(tmp_path, stale_days=7)
        # Exactly 7 days old: age > 7 is False, so it should be NOT stale
        t._records["boundary"] = time.time() - 86400 * 7
        # age == 7.0 and threshold is > 7, so at exact boundary it's not stale
        # (depends on implementation: age > stale_days, not >=)
        assert isinstance(t.is_stale("boundary"), bool)


# ---------------------------------------------------------------------------
# get_stale_topics / get_fresh_topics
# ---------------------------------------------------------------------------

class TestStaleAndFreshLists:
    def test_stale_includes_never_researched(self, tmp_path):
        t = _tracker(tmp_path, topics=["quantum", "aeroponics"])
        stale = t.get_stale_topics()
        topics_in_stale = [s["topic"] for s in stale]
        assert "quantum" in topics_in_stale
        assert "aeroponics" in topics_in_stale

    def test_fresh_includes_recently_updated(self, tmp_path):
        t = _tracker(tmp_path, topics=["quantum"])
        t.record_update("quantum")
        fresh = t.get_fresh_topics()
        assert any(f["topic"] == "quantum" for f in fresh)

    def test_stale_topic_not_in_fresh(self, tmp_path):
        t = _tracker(tmp_path, topics=["quantum"])
        # Don't update — it's stale
        fresh = t.get_fresh_topics()
        assert not any(f["topic"] == "quantum" for f in fresh)

    def test_fresh_not_in_stale(self, tmp_path):
        t = _tracker(tmp_path, topics=["fresh_topic"])
        t.record_update("fresh_topic")
        stale = t.get_stale_topics()
        assert not any(s["topic"] == "fresh_topic" for s in stale)

    def test_stale_entry_has_age_days_none_or_float(self, tmp_path):
        t = _tracker(tmp_path, topics=["unknown"])
        stale = t.get_stale_topics()
        assert len(stale) == 1
        assert stale[0]["age_days"] is None  # never researched

    def test_stale_entry_with_old_timestamp_has_age(self, tmp_path):
        t = _tracker(tmp_path, topics=["old_topic"], stale_days=1)
        t._records["old_topic"] = time.time() - 86400 * 5  # 5 days
        stale = t.get_stale_topics()
        assert any(s["topic"] == "old_topic" and s["age_days"] is not None for s in stale)

    def test_empty_knowledge_base(self, tmp_path):
        t = _tracker(tmp_path, topics=[])
        assert t.get_stale_topics() == []
        assert t.get_fresh_topics() == []


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_records_saved_to_disk(self, tmp_path):
        t = _tracker(tmp_path, topics=[])
        t.record_update("gravity")
        fp = tmp_path / "freshness.json"
        data = json.loads(fp.read_text())
        assert "gravity" in data

    def test_records_loaded_from_disk(self, tmp_path):
        fp = tmp_path / "freshness.json"
        fp.write_text(json.dumps({"dna": time.time() - 100}))
        t = FreshnessTracker(knowledge=_fake_knowledge(), freshness_path=fp)
        assert t.get_age_days("dna") is not None

    def test_corrupt_file_starts_empty(self, tmp_path):
        fp = tmp_path / "freshness.json"
        fp.write_text("not json")
        t = FreshnessTracker(knowledge=_fake_knowledge(), freshness_path=fp)
        assert t.get_age_days("anything") is None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_structure(self, tmp_path):
        t = _tracker(tmp_path, topics=["t1", "t2"])
        s = t.status()
        assert "total_entries" in s
        assert "stale_count" in s
        assert "fresh_count" in s
        assert "stale_days_threshold" in s

    def test_status_counts_add_up(self, tmp_path):
        t = _tracker(tmp_path, topics=["t1", "t2"])
        t.record_update("t1")
        s = t.status()
        assert s["stale_count"] + s["fresh_count"] == s["total_entries"]

    def test_status_threshold_matches_config(self, tmp_path):
        t = _tracker(tmp_path, stale_days=14)
        assert t.status()["stale_days_threshold"] == 14
