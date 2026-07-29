"""Curiosity scheduler: the loop that is supposed to make it learn unattended.

The bug these were written for: `_cycle` drained the message buffer *before*
testing it against `min_message_count`, so every quiet cycle threw away what
had accumulated and the count restarted at zero. Unless enough messages landed
inside a single interval, the scheduler never researched anything -- the
dashboard showed thread alive, clues buffered, and no research in 12 hours.
"""
from __future__ import annotations

import pytest

from shaggoth.curiosity.scheduler import CuriosityScheduler, ScheduleConfig


class FakeCuriosity:
    """Stands in for CuriosityEngine, recording what it was asked to do."""

    def __init__(self, topic_for=None):
        self.is_running = False
        self.researched: list = []
        self.stale_refreshes = 0
        self._topic_for = topic_for or (lambda msg: msg.strip() or None)

    def analyze_message(self, message):
        return self._topic_for(message)

    def research_topic(self, topic, **kwargs):
        self.researched.append(topic)

    def refresh_stale(self, max_topics=1):
        self.stale_refreshes += 1
        return {"stale_found": 1, "refreshed": 1}


def _scheduler(curiosity=None, **config):
    config.setdefault("refresh_stale_when_idle", False)
    config.setdefault("proactive_research", False)
    return CuriosityScheduler(curiosity or FakeCuriosity(), ScheduleConfig(**config))


# --------------------------------------------------------------------------
# The buffer-drain bug
# --------------------------------------------------------------------------


def test_a_below_threshold_cycle_keeps_the_messages():
    """The regression. Messages must survive a cycle that cannot use them."""
    sched = _scheduler(min_message_count=3)
    sched.record_message("aeroponics")
    sched._cycle()

    assert sched.status()["buffered_messages"] == 1


def test_messages_accumulate_across_quiet_cycles_until_they_fire():
    sched = _scheduler(FakeCuriosity(), min_message_count=3)
    for i in range(6):
        if i % 2 == 0:
            sched.record_message(f"topic {i}")
        sched._cycle()

    assert sched.curiosity.researched, "never researched despite reaching threshold"


def test_the_buffer_is_spent_once_it_is_analysed():
    """Otherwise the same messages would be re-researched every cycle."""
    curiosity = FakeCuriosity()
    sched = _scheduler(curiosity, min_message_count=2)
    sched.record_message("aeroponics")
    sched.record_message("hydroponics")
    sched._cycle()

    assert sched.status()["buffered_messages"] == 0
    before = len(curiosity.researched)
    sched._cycle()
    assert len(curiosity.researched) == before


def test_messages_arriving_during_a_cycle_are_not_lost():
    """Only the messages actually analysed are removed, not the whole list."""
    curiosity = FakeCuriosity()
    sched = _scheduler(curiosity, min_message_count=2)
    sched.record_message("one")
    sched.record_message("two")

    original = curiosity.analyze_message

    def analyze_and_interrupt(message):
        # Simulate a chat message landing mid-cycle.
        if not getattr(analyze_and_interrupt, "fired", False):
            analyze_and_interrupt.fired = True
            sched.record_message("three")
        return original(message)

    curiosity.analyze_message = analyze_and_interrupt
    sched._cycle()

    assert sched.status()["buffered_messages"] == 1


# --------------------------------------------------------------------------
# Researching
# --------------------------------------------------------------------------


def test_topics_are_deduplicated():
    curiosity = FakeCuriosity()
    sched = _scheduler(curiosity, min_message_count=1)
    for _ in range(4):
        sched.record_message("aeroponics")
    sched._cycle()

    assert curiosity.researched == ["aeroponics"]


def test_topics_per_cycle_are_capped():
    curiosity = FakeCuriosity()
    sched = _scheduler(curiosity, min_message_count=1, max_topics_per_cycle=2)
    for word in ("a", "b", "c", "d"):
        sched.record_message(word)
    sched._cycle()

    assert len(curiosity.researched) == 2


def test_a_cycle_is_skipped_while_research_is_already_running():
    curiosity = FakeCuriosity()
    curiosity.is_running = True
    sched = _scheduler(curiosity, min_message_count=1)
    sched.record_message("aeroponics")
    sched._cycle()

    assert not curiosity.researched
    # ...and the messages are still there for the next cycle.
    assert sched.status()["buffered_messages"] == 1


# --------------------------------------------------------------------------
# Learning while nobody is talking to it
# --------------------------------------------------------------------------


def test_an_idle_cycle_refreshes_stale_knowledge():
    """"Always learning" cannot depend on someone being in the chat window."""
    curiosity = FakeCuriosity()
    sched = CuriosityScheduler(curiosity, ScheduleConfig(refresh_stale_when_idle=True))
    sched._cycle()

    assert curiosity.stale_refreshes == 1


def test_stale_refresh_does_not_run_when_there_was_real_curiosity():
    curiosity = FakeCuriosity()
    sched = CuriosityScheduler(
        curiosity, ScheduleConfig(refresh_stale_when_idle=True, min_message_count=1)
    )
    sched.record_message("aeroponics")
    sched._cycle()

    assert curiosity.researched == ["aeroponics"]
    assert curiosity.stale_refreshes == 0


def test_stale_refresh_can_be_switched_off():
    curiosity = FakeCuriosity()
    sched = CuriosityScheduler(curiosity, ScheduleConfig(refresh_stale_when_idle=False))
    sched._cycle()

    assert curiosity.stale_refreshes == 0


def test_messages_that_yield_no_topic_fall_through_to_stale_refresh():
    curiosity = FakeCuriosity(topic_for=lambda msg: None)
    sched = CuriosityScheduler(
        curiosity, ScheduleConfig(refresh_stale_when_idle=True, min_message_count=1)
    )
    sched.record_message("hello")
    sched._cycle()

    assert curiosity.stale_refreshes == 1


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------


def test_the_buffer_stays_bounded():
    sched = _scheduler()
    for i in range(500):
        sched.record_message(f"message {i}")
    assert sched.status()["buffered_messages"] <= 100


def test_status_reports_the_configured_interval():
    sched = _scheduler(interval_minutes=15)
    status = sched.status()
    assert status["interval_minutes"] == 15
    assert status["enabled"] is True


def test_defaults_are_tuned_for_continuous_learning():
    """The old 60min/5-message defaults meant a quiet hour learned nothing."""
    config = ScheduleConfig()
    assert config.interval_minutes <= 15
    assert config.min_message_count <= 2
    assert config.refresh_stale_when_idle is True
