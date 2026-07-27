"""Feedback, and the repair queue it drives."""
from __future__ import annotations

import pytest

from shaggoth.feedback import FeedbackStore
from shaggoth.feedback.store import BAD, GOOD, normalize_verdict


@pytest.fixture
def store(tmp_path):
    return FeedbackStore(tmp_path / "feedback.json", cooldown=100.0)


@pytest.mark.parametrize("value,expected", [
    ("good", GOOD), ("bad", BAD), (True, GOOD), (False, BAD),
    ("up", GOOD), ("down", BAD), ("wrong", BAD), ("helpful", GOOD),
])
def test_normalize_verdict(value, expected):
    assert normalize_verdict(value) == expected


def test_unusable_feedback_is_refused(store):
    assert store.record("", "bad") is None
    assert store.record("what is x", "sideways") is None


def test_a_complaint_targets_the_entry_the_answer_came_from(store):
    """entries_used is what makes feedback actionable rather than just noise."""
    store.record("what is an atom", "bad", entries_used=["Atom"], note="that's a caption")
    queue = store.repair_queue(now=0)
    assert [t.topic for t in queue] == ["Atom"]
    assert queue[0].last_note == "that's a caption"


def test_praise_offsets_complaints(store):
    store.record("q", "bad", entries_used=["Atom"])
    store.record("q", "good", entries_used=["Atom"])
    assert store.repair_queue(now=0) == []


def test_worst_entry_comes_first(store):
    for _ in range(3):
        store.record("q", "bad", entries_used=["Atom"])
    store.record("q", "bad", entries_used=["Gravity"])
    assert [t.topic for t in store.repair_queue(now=0)] == ["Atom", "Gravity"]


def test_a_repaired_entry_leaves_the_queue(store):
    store.record("q", "bad", entries_used=["Atom"])
    store.mark_repaired("Atom", now=0)
    assert store.repair_queue(now=10) == []


def test_the_cooldown_expires(store):
    store.record("q", "bad", entries_used=["Atom"])
    store.mark_repaired("Atom", now=0)
    assert [t.topic for t in store.repair_queue(now=1000)] == ["Atom"]


def test_a_fresh_complaint_reopens_a_repaired_entry(store):
    """The repair evidently did not work; pretending otherwise makes it
    permanent."""
    store.record("q", "bad", entries_used=["Atom"])
    store.mark_repaired("Atom", now=0)
    store.record("q", "bad", entries_used=["Atom"], now=1)
    assert [t.topic for t in store.repair_queue(now=2)] == ["Atom"]


def test_feedback_survives_a_restart(tmp_path):
    path = tmp_path / "feedback.json"
    FeedbackStore(path).record("q", "bad", entries_used=["Atom"])
    assert [t.topic for t in FeedbackStore(path).repair_queue(now=0)] == ["Atom"]


def test_status_counts(store):
    store.record("q", "good", entries_used=["A"])
    store.record("q", "bad", entries_used=["B"])
    s = store.status()
    assert s["good"] == 1 and s["bad"] == 1 and s["total"] == 2


# --------------------------------------------------------------------------
# The scheduler drains repairs before refreshing merely-old entries
# --------------------------------------------------------------------------


class FakeCuriosity:
    def __init__(self):
        self.is_running = False
        self.researched = []
        self.stale_refreshes = 0

    def analyze_message(self, message):
        return None

    def research_topic(self, topic, **kw):
        self.researched.append(topic)

    def refresh_stale(self, max_topics=1):
        self.stale_refreshes += 1


def _scheduler(feedback, curiosity=None):
    from shaggoth.curiosity.scheduler import CuriosityScheduler, ScheduleConfig

    return CuriosityScheduler(
        curiosity or FakeCuriosity(),
        ScheduleConfig(refresh_stale_when_idle=True),
        feedback=feedback,
    )


def test_a_known_bad_entry_is_repaired_before_a_merely_old_one(store):
    store.record("what is an atom", "bad", entries_used=["Atom"])
    sched = _scheduler(store)
    sched._cycle()
    assert sched.curiosity.researched == ["Atom"]
    assert sched.curiosity.stale_refreshes == 0


def test_with_nothing_to_repair_it_falls_back_to_stale_refresh(store):
    sched = _scheduler(store)
    sched._cycle()
    assert sched.curiosity.stale_refreshes == 1


def test_a_repair_is_marked_before_research_not_after(store):
    """If research throws, the cooldown must still apply -- otherwise one
    broken topic captures every future cycle."""
    class Exploding(FakeCuriosity):
        def research_topic(self, topic, **kw):
            raise RuntimeError("network down")

    store.record("q", "bad", entries_used=["Atom"])
    sched = _scheduler(store, Exploding())
    with pytest.raises(RuntimeError):
        sched._cycle()
    assert store.repair_queue(now=0) == []


def test_a_scheduler_without_feedback_still_works(tmp_path):
    from shaggoth.curiosity.scheduler import CuriosityScheduler, ScheduleConfig

    sched = CuriosityScheduler(FakeCuriosity(), ScheduleConfig(refresh_stale_when_idle=True))
    sched._cycle()
    assert sched.curiosity.stale_refreshes == 1
