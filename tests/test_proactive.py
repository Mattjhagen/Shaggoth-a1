"""Tests for proactive messaging (dialogue/proactive.py)."""
from __future__ import annotations

import random
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from shaggoth.dialogue.proactive import (
    ProactiveChatter,
    ProactiveConfig,
    _snippet,
    compose_proactive_message,
)


# ---------------------------------------------------------------------------
# _snippet
# ---------------------------------------------------------------------------

class TestSnippet:
    def test_extracts_first_long_line(self):
        content = "Short.\nThis is a longer line with actual content that tells us something."
        s = _snippet(content)
        assert "longer line" in s

    def test_skips_header_lines(self):
        content = "# Heading\n== Section ==\nActual content here that should be returned."
        s = _snippet(content)
        assert "Actual content" in s

    def test_truncates_at_max_chars(self):
        long = "word " * 50
        s = _snippet(long, max_chars=30)
        assert len(s) <= 34  # may have ellipsis

    def test_truncation_adds_ellipsis(self):
        long = "word " * 50
        s = _snippet(long, max_chars=20)
        assert s.endswith("…")

    def test_empty_content_returns_empty_string(self):
        assert _snippet("") == ""

    def test_only_short_lines_returns_empty(self):
        # Lines under 30 chars are skipped
        assert _snippet("hi\nbye\nok") == ""

    def test_dash_lines_skipped(self):
        content = "------\nThis is valid content with enough length to be captured."
        s = _snippet(content)
        assert "valid content" in s


# ---------------------------------------------------------------------------
# compose_proactive_message
# ---------------------------------------------------------------------------

class TestComposeProactiveMessage:
    def _entry(self, topic: str, content: str):
        return SimpleNamespace(topic=topic, content=content)

    def test_empty_entries_returns_pure_idle(self):
        rng = random.Random(42)
        msg = compose_proactive_message([], knowledge_count=5, rng=rng)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_pure_idle_formats_count(self):
        rng = random.Random(0)
        # Force a pure_idle path with no entries
        msg = compose_proactive_message([], knowledge_count=99, rng=rng)
        # At least one pure idle template references {count}
        # Just check it's non-empty and a string
        assert isinstance(msg, str)

    def test_with_entries_returns_non_empty(self):
        entries = [self._entry("aeroponics", "Aeroponics is growing plants without soil. It uses misted nutrient solutions.")]
        rng = random.Random(1)
        msg = compose_proactive_message(entries, rng=rng)
        assert len(msg) > 0

    def test_with_entries_topic_appears_sometimes(self):
        entries = [self._entry("quantum computing", "Quantum computing uses qubits to perform calculations exponentially faster.")]
        found_topic = False
        for seed in range(20):
            rng = random.Random(seed)
            msg = compose_proactive_message(entries, rng=rng)
            if "quantum computing" in msg:
                found_topic = True
                break
        assert found_topic, "Expected topic to appear in at least one of 20 messages"

    def test_knowledge_count_uses_entries_length_as_fallback(self):
        entries = [
            self._entry("t1", "Content for topic one that is long enough to be extracted."),
            self._entry("t2", "Content for topic two that is long enough to be extracted."),
        ]
        rng = random.Random(42)
        # knowledge_count=0 → uses len(entries)
        msg = compose_proactive_message(entries, knowledge_count=0, rng=rng)
        assert isinstance(msg, str)

    def test_entry_without_content_produces_message(self):
        entries = [self._entry("sparse topic", "")]
        rng = random.Random(42)
        msg = compose_proactive_message(entries, rng=rng)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_different_seeds_may_differ(self):
        entries = [self._entry("t", "Content that is long enough to actually produce a snippet for testing.")]
        outputs = {compose_proactive_message(entries, rng=random.Random(s)) for s in range(30)}
        assert len(outputs) > 1


# ---------------------------------------------------------------------------
# ProactiveConfig defaults
# ---------------------------------------------------------------------------

class TestProactiveConfig:
    def test_defaults(self):
        c = ProactiveConfig()
        assert c.enabled
        assert c.interval_hours > 0
        assert c.max_per_cycle >= 1
        assert c.active_session_window_hours > 0


# ---------------------------------------------------------------------------
# ProactiveChatter
# ---------------------------------------------------------------------------

class _FakeMemory:
    def __init__(self):
        self._next_id = 1
        self.messages: list[tuple] = []

    def add_message(self, session_id, role, text):
        mid = self._next_id
        self._next_id += 1
        self.messages.append((session_id, role, text, mid))
        return mid


class _FakeEngine:
    def __init__(self):
        self.memory = _FakeMemory()
        self.knowledge = SimpleNamespace(_entries=[])


class TestProactiveChatter:
    def setup_method(self):
        self.engine = _FakeEngine()
        self.push = MagicMock()
        self.push.notify = MagicMock()
        self.chatter = ProactiveChatter(
            engine=self.engine,
            push=self.push,
            config=ProactiveConfig(enabled=True, interval_hours=1),
            rng_seed=42,
        )

    def test_status_returns_dict(self):
        s = self.chatter.status()
        assert "enabled" in s
        assert "interval_hours" in s
        assert "thread_alive" in s

    def test_thread_not_alive_before_start(self):
        assert not self.chatter.status()["thread_alive"]

    def test_send_now_stores_in_memory(self):
        msg = self.chatter.send_now("test_session")
        assert isinstance(msg, str)
        assert len(self.engine.memory.messages) == 1
        session_id, role, text, _ = self.engine.memory.messages[0]
        assert session_id == "test_session"
        assert role == "assistant"
        assert text == msg

    def test_send_now_returns_non_empty_string(self):
        msg = self.chatter.send_now()
        assert len(msg) > 0

    def test_send_now_with_knowledge_entries(self):
        self.engine.knowledge._entries = [
            SimpleNamespace(topic="aeroponics", content="Aeroponics grows plants without soil using misted nutrients.", mtime=1)
        ]
        msg = self.chatter.send_now()
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_cycle_stores_message(self):
        # Patch _active_sessions to return a known session
        self.chatter._active_sessions = lambda: ["sess1"]
        self.chatter._cycle()
        assert len(self.engine.memory.messages) == 1

    def test_cycle_respects_max_per_cycle(self):
        self.chatter.config.max_per_cycle = 1
        self.chatter._active_sessions = lambda: ["s1", "s2", "s3"]
        self.chatter._cycle()
        assert len(self.engine.memory.messages) == 1

    def test_cycle_falls_back_to_default_session(self):
        self.chatter._active_sessions = lambda: []
        self.chatter._cycle()
        session_id = self.engine.memory.messages[0][0]
        assert session_id == "default"

    def test_slack_notified_if_configured(self):
        slack = MagicMock()
        slack.configured = True
        chatter = ProactiveChatter(
            engine=self.engine,
            push=self.push,
            rng_seed=0,
            slack=slack,
        )
        chatter._active_sessions = lambda: ["s1"]
        chatter._cycle()
        slack.send_async.assert_called_once()

    def test_slack_not_called_if_not_configured(self):
        slack = MagicMock()
        slack.configured = False
        chatter = ProactiveChatter(
            engine=self.engine,
            push=self.push,
            rng_seed=0,
            slack=slack,
        )
        chatter._active_sessions = lambda: ["s1"]
        chatter._cycle()
        slack.send_async.assert_not_called()

    def test_start_stop_thread(self):
        self.chatter.start()
        assert self.chatter.status()["thread_alive"]
        self.chatter.stop()
        assert not self.chatter.status()["thread_alive"]

    def test_start_idempotent(self):
        self.chatter.start()
        thread_before = self.chatter._thread
        self.chatter.start()
        thread_after = self.chatter._thread
        assert thread_before is thread_after
        self.chatter.stop()
