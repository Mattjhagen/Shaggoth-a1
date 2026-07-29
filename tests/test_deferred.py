"""Tests for the deferred question queue (notify/deferred.py)."""
from __future__ import annotations

import time
import tempfile
from pathlib import Path

import pytest

from shaggoth.notify.deferred import DeferredQuestions, PendingQuestion, _norm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _store(tmp_path: Path | None = None, max_age: float = 86400) -> DeferredQuestions:
    if tmp_path is None:
        tmp_path = Path(tempfile.mktemp(suffix=".json"))
    return DeferredQuestions(path=tmp_path, max_age=max_age)


# ---------------------------------------------------------------------------
# _norm
# ---------------------------------------------------------------------------

class TestNorm:
    def test_lowercases(self):
        assert _norm("Hello World") == "hello world"

    def test_collapses_spaces(self):
        assert _norm("  a  b  c  ") == "a b c"

    def test_empty(self):
        assert _norm("") == ""

    def test_none_like_empty_string(self):
        assert _norm("   ") == ""


# ---------------------------------------------------------------------------
# record
# ---------------------------------------------------------------------------

class TestRecord:
    def test_records_a_question(self):
        store = _store()
        item = store.record("What is aeroponics?", "aeroponics")
        assert item is not None
        assert item.question == "What is aeroponics?"
        assert item.topic == "aeroponics"

    def test_record_returns_none_for_empty_question(self):
        store = _store()
        assert store.record("", "aeroponics") is None

    def test_record_returns_none_for_empty_topic(self):
        store = _store()
        assert store.record("What is X?", "") is None

    def test_record_returns_none_for_duplicate_question_same_session(self):
        store = _store()
        store.record("What is DNA?", "dna", session_id="s1")
        dupe = store.record("What is DNA?", "dna", session_id="s1")
        assert dupe is None

    def test_duplicate_different_session_is_allowed(self):
        store = _store()
        store.record("What is DNA?", "dna", session_id="s1")
        second = store.record("What is DNA?", "dna", session_id="s2")
        assert second is not None

    def test_answered_question_allows_new_identical_question(self):
        store = _store()
        item = store.record("What is DNA?", "dna", session_id="s1")
        # Force it to answered state
        item.answered_at = time.time()
        new = store.record("What is DNA?", "dna", session_id="s1")
        assert new is not None

    def test_asked_at_is_set(self):
        before = time.time()
        store = _store()
        item = store.record("test?", "test")
        assert item.asked_at >= before

    def test_stores_session_id(self):
        store = _store()
        item = store.record("test?", "test", session_id="sess42")
        assert item.session_id == "sess42"

    def test_default_session_is_default(self):
        store = _store()
        item = store.record("test?", "test")
        assert item.session_id == "default"


# ---------------------------------------------------------------------------
# pending / answered
# ---------------------------------------------------------------------------

class TestPendingAnswered:
    def test_pending_includes_new_item(self):
        store = _store()
        store.record("What is RNA?", "rna")
        pending = store.pending()
        assert len(pending) == 1
        assert pending[0].topic == "rna"

    def test_answered_not_in_pending(self):
        store = _store()
        item = store.record("What is RNA?", "rna")
        item.answered_at = time.time()
        assert store.pending() == []

    def test_pending_filtered_by_session(self):
        store = _store()
        store.record("Q1?", "t1", session_id="s1")
        store.record("Q2?", "t2", session_id="s2")
        assert len(store.pending("s1")) == 1
        assert store.pending("s1")[0].topic == "t1"

    def test_answered_includes_answered_items(self):
        store = _store()
        item = store.record("What?", "something")
        item.answered_at = time.time()
        item.answer = "It's this."
        assert len(store.answered()) == 1

    def test_answered_undelivered_only(self):
        store = _store()
        item = store.record("Q?", "t")
        item.answered_at = time.time()
        item.delivered = True
        assert store.answered(undelivered_only=True) == []
        assert len(store.answered(undelivered_only=False)) == 1


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------

class TestMatching:
    def test_exact_topic_match(self):
        store = _store()
        store.record("What is aeroponics?", "aeroponics")
        matches = store.matching("aeroponics")
        assert len(matches) == 1

    def test_subset_topic_matches(self):
        # Stored: "aeroponic farming"; episode: "aeroponic farming systems".
        # stored <= wanted → all stored words appear in wanted → matches.
        store = _store()
        store.record("Q?", "aeroponic farming")
        matches = store.matching("aeroponic farming systems")
        assert len(matches) == 1

    def test_superset_topic_matches(self):
        store = _store()
        store.record("Q?", "farming")
        matches = store.matching("aeroponic farming")
        assert len(matches) == 1

    def test_no_overlap_no_match(self):
        store = _store()
        store.record("Q?", "aeroponics")
        assert store.matching("quantum computing") == []

    def test_answered_item_not_in_matching(self):
        store = _store()
        item = store.record("Q?", "aeroponics")
        item.answered_at = time.time()
        assert store.matching("aeroponics") == []

    def test_expired_item_not_in_matching(self):
        store = _store(max_age=1)
        old_time = time.time() - 10
        store.record("Q?", "aeroponics", now=old_time)
        assert store.matching("aeroponics") == []


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

class TestResolve:
    def test_resolve_calls_answer_for_and_marks_answered(self):
        store = _store()
        store.record("What is aeroponics?", "aeroponics")
        resolved = store.resolve("aeroponics", lambda q: "Growing without soil.")
        assert len(resolved) == 1
        assert resolved[0].answered
        assert resolved[0].answer == "Growing without soil."

    def test_resolve_does_not_answer_if_callback_returns_empty(self):
        store = _store()
        store.record("Q?", "aeroponics")
        resolved = store.resolve("aeroponics", lambda q: "")
        assert resolved == []
        assert len(store.pending()) == 1  # still pending

    def test_resolve_answers_multiple_matching_questions(self):
        store = _store()
        store.record("Q1?", "dna", session_id="s1")
        store.record("Q2?", "dna", session_id="s2")
        resolved = store.resolve("dna", lambda q: "Deoxyribonucleic acid.")
        assert len(resolved) == 2

    def test_resolve_skips_already_answered(self):
        store = _store()
        item = store.record("Q?", "dna")
        item.answered_at = time.time()
        resolved = store.resolve("dna", lambda q: "Some answer.")
        assert resolved == []

    def test_resolve_exception_in_callback_leaves_item_pending(self):
        store = _store()
        store.record("Q?", "dna")
        def failing_cb(q):
            raise RuntimeError("DB connection failed")
        resolved = store.resolve("dna", failing_cb)
        assert resolved == []
        assert len(store.pending()) == 1


# ---------------------------------------------------------------------------
# mark_delivered / prune
# ---------------------------------------------------------------------------

class TestMarkDeliveredAndPrune:
    def test_mark_delivered_sets_flag(self):
        store = _store()
        item = store.record("Q?", "t")
        item.answered_at = time.time()
        store.mark_delivered([item])
        assert item.delivered

    def test_prune_removes_expired_unanswered(self):
        store = _store(max_age=1)
        old_time = time.time() - 10
        store.record("Q?", "old topic", now=old_time)
        removed = store.prune()
        assert removed == 1
        assert store.pending() == []

    def test_prune_keeps_answered_even_if_old(self):
        store = _store(max_age=1)
        old_time = time.time() - 10
        item = store.record("Q?", "topic", now=old_time)
        item.answered_at = time.time()
        removed = store.prune()
        assert removed == 0

    def test_prune_keeps_fresh_unanswered(self):
        store = _store(max_age=3600)
        store.record("Q?", "topic")
        removed = store.prune()
        assert removed == 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_counts(self):
        store = _store()
        store.record("Q1?", "t1")
        item = store.record("Q2?", "t2")
        item.answered_at = time.time()
        s = store.status()
        assert s["pending"] == 1
        assert s["answered"] == 1

    def test_status_undelivered_count(self):
        store = _store()
        item = store.record("Q?", "t")
        item.answered_at = time.time()
        s = store.status()
        assert s["undelivered"] == 1
        store.mark_delivered([item])
        s2 = store.status()
        assert s2["undelivered"] == 0


# ---------------------------------------------------------------------------
# persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_items_survive_reload(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        store1 = _store(path)
        store1.record("What is gravity?", "gravity")

        store2 = _store(path)
        assert len(store2.pending()) == 1
        assert store2.pending()[0].topic == "gravity"

    def test_answered_items_survive_reload(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = Path(f.name)

        store1 = _store(path)
        item = store1.record("Q?", "t")
        item.answered_at = time.time()
        item.answer = "Yes."
        store1._save()

        store2 = _store(path)
        answered = store2.answered()
        assert len(answered) == 1
        assert answered[0].answer == "Yes."


# ---------------------------------------------------------------------------
# PendingQuestion dataclass
# ---------------------------------------------------------------------------

class TestPendingQuestion:
    def test_answered_property(self):
        q = PendingQuestion(question="Q?", topic="t", asked_at=time.time())
        assert not q.answered
        q.answered_at = time.time()
        assert q.answered

    def test_age(self):
        now = time.time()
        q = PendingQuestion(question="Q?", topic="t", asked_at=now - 100)
        assert 99 < q.age(now) < 101

    def test_age_uses_time_time_when_now_not_given(self):
        q = PendingQuestion(question="Q?", topic="t", asked_at=time.time() - 5)
        assert q.age() >= 4
