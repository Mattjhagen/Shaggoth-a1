"""Tests for the eval harness: run logging, benchmark execution, scoring."""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

from shaggoth.eval.logger import RunLogger, RunRecord
from shaggoth.eval.harness import BenchmarkTask, Harness, RunResult, load_tasks
from shaggoth.eval.scorer import score_run, score_task


# ---------------------------------------------------------------------------
# RunLogger
# ---------------------------------------------------------------------------


def test_run_logger_writes_jsonl(tmp_path):
    logger = RunLogger(directory=tmp_path)
    record = logger.log(
        session_id="test",
        user_input="hello",
        reply_text="hi there",
        source="pattern",
        mode="no_drift",
        latency_ms=12.5,
    )
    assert record is not None
    assert record.session_id == "test"
    assert record.source == "pattern"

    files = list(tmp_path.glob("run-*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["user_input"] == "hello"
    assert data["reply_text"] == "hi there"
    assert data["latency_ms"] == 12.5


def test_run_logger_disabled():
    logger = RunLogger(enabled=False)
    record = logger.log(
        session_id="test",
        user_input="hello",
        reply_text="hi",
        source="pattern",
        mode="no_drift",
    )
    assert record is None


def test_run_logger_read_records(tmp_path):
    logger = RunLogger(directory=tmp_path)
    logger.log(session_id="a", user_input="x", reply_text="y",
               source="model", mode="drift")
    logger.log(session_id="b", user_input="q", reply_text="r",
               source="plugin", mode="no_drift")
    records = logger.read_records()
    assert len(records) == 2
    assert records[0].session_id == "a"
    assert records[1].source == "plugin"


def test_run_logger_swallows_write_errors(tmp_path, monkeypatch):
    logger = RunLogger(directory=tmp_path)
    monkeypatch.setattr(logger, "_path_for_today", lambda: tmp_path / "subdir" / "deep" / "run.jsonl")

    def _boom(*a, **kw):
        raise OSError("disk full")

    import builtins
    real_open = builtins.open
    def patched_open(path, *a, **kw):
        if "deep" in str(path):
            raise OSError("disk full")
        return real_open(path, *a, **kw)

    monkeypatch.setattr(builtins, "open", patched_open)
    result = logger.log(
        session_id="test", user_input="x", reply_text="y",
        source="p", mode="m",
    )
    assert result is None


# ---------------------------------------------------------------------------
# BenchmarkTask
# ---------------------------------------------------------------------------


def test_benchmark_task_from_dict():
    d = {
        "id": "t1",
        "input": "what is X",
        "category": "knowledge",
        "expect_source": "knowledge",
        "expect_keywords": ["energy"],
    }
    task = BenchmarkTask.from_dict(d)
    assert task.id == "t1"
    assert task.expect_source == "knowledge"
    assert task.expect_keywords == ["energy"]
    assert task.expect_blocked is None


def test_benchmark_task_minimal():
    task = BenchmarkTask.from_dict({"id": "t2", "input": "hi"})
    assert task.category == "general"
    assert task.expect_keywords == []


# ---------------------------------------------------------------------------
# load_tasks
# ---------------------------------------------------------------------------


def test_load_tasks_from_file(tmp_path):
    f = tmp_path / "bench.jsonl"
    f.write_text(
        json.dumps({"id": "a", "input": "hello"}) + "\n"
        + json.dumps({"id": "b", "input": "bye"}) + "\n"
    )
    tasks = load_tasks(f)
    assert len(tasks) == 2
    assert tasks[0].id == "a"


def test_load_tasks_skips_malformed(tmp_path):
    f = tmp_path / "bench.jsonl"
    f.write_text('{"id": "ok", "input": "hi"}\nnot json\n')
    tasks = load_tasks(f)
    assert len(tasks) == 1


def test_load_tasks_missing_file(tmp_path):
    assert load_tasks(tmp_path / "nope.jsonl") == []


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class _FakeReply:
    text: str = "fake reply"
    source: str = "pattern"
    blocked: bool = False
    entries_used: list = None
    reasoning: list = None
    mode: str = "no_drift"
    flag: str = "green"
    memory_triggers: list = None
    new_facts: dict = None
    output_rules_applied: list = None

    def __post_init__(self):
        if self.entries_used is None:
            self.entries_used = []
        if self.reasoning is None:
            self.reasoning = []
        if self.memory_triggers is None:
            self.memory_triggers = []
        if self.new_facts is None:
            self.new_facts = {}
        if self.output_rules_applied is None:
            self.output_rules_applied = []


class _FakeEngine:
    def respond(self, text, session_id="default", mode=None):
        if "blocked" in text.lower():
            return _FakeReply(text="blocked", source="guardrail", blocked=True)
        if "what time" in text.lower():
            return _FakeReply(text="It is 3pm", source="plugin")
        if "photosynthesis" in text.lower():
            return _FakeReply(
                text="Photosynthesis converts light energy into chemical energy.",
                source="knowledge",
                entries_used=["Photosynthesis"],
            )
        return _FakeReply()


def test_harness_runs_tasks():
    engine = _FakeEngine()
    harness = Harness(engine)
    tasks = [
        BenchmarkTask(id="t1", input="what is photosynthesis", category="knowledge"),
        BenchmarkTask(id="t2", input="what time is it", category="plugin"),
    ]
    results = harness.run(tasks=tasks)
    assert len(results) == 2
    assert results[0].source == "knowledge"
    assert results[1].source == "plugin"
    assert results[0].latency_ms >= 0


def test_harness_save_and_load(tmp_path):
    engine = _FakeEngine()
    harness = Harness(engine)
    tasks = [BenchmarkTask(id="t1", input="hello")]
    results = harness.run(tasks=tasks)

    path = tmp_path / "results.jsonl"
    harness.save_results(results, path)
    assert path.exists()

    loaded = Harness.load_results(path)
    assert len(loaded) == 1
    assert loaded[0].task_id == "t1"


def test_harness_handles_engine_error():
    class _ErrorEngine:
        def respond(self, text, session_id="default", mode=None):
            raise RuntimeError("boom")

    harness = Harness(_ErrorEngine())
    results = harness.run(tasks=[BenchmarkTask(id="err", input="crash")])
    assert len(results) == 1
    assert results[0].error == "boom"
    assert results[0].source == "error"


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


def test_score_task_all_pass():
    result = RunResult(
        task_id="t1", input="hi", category="chitchat",
        reply_text="hello there", source="pattern", blocked=False,
        entries_used=[], reasoning=[], latency_ms=5.0,
        expect_source="pattern", expect_blocked=False,
        expect_min_length=5,
    )
    ts = score_task(result)
    assert ts.passed
    assert all(ts.checks.values())


def test_score_task_source_mismatch():
    result = RunResult(
        task_id="t1", input="hi", category="test",
        reply_text="hello", source="fallback", blocked=False,
        entries_used=[], reasoning=[], latency_ms=5.0,
        expect_source="knowledge",
    )
    ts = score_task(result)
    assert not ts.passed
    assert not ts.checks["source"]


def test_score_task_missing_keywords():
    result = RunResult(
        task_id="t1", input="hi", category="test",
        reply_text="the sky is nice", source="model", blocked=False,
        entries_used=[], reasoning=[], latency_ms=5.0,
        expect_keywords=["energy", "light"],
    )
    ts = score_task(result)
    assert not ts.passed
    assert not ts.checks["keywords"]


def test_score_task_keyword_word_boundary():
    result = RunResult(
        task_id="t1", input="hi", category="test",
        reply_text="Art is creative", source="model", blocked=False,
        entries_used=[], reasoning=[], latency_ms=5.0,
        expect_keywords=["art"],
    )
    ts = score_task(result)
    assert ts.checks["keywords"]


def test_score_task_blocked_mismatch():
    result = RunResult(
        task_id="t1", input="bomb", category="guardrail",
        reply_text="no", source="guardrail", blocked=False,
        entries_used=[], reasoning=[], latency_ms=5.0,
        expect_blocked=True,
    )
    ts = score_task(result)
    assert not ts.checks["blocked"]


def test_score_task_min_length():
    result = RunResult(
        task_id="t1", input="hi", category="test",
        reply_text="ok", source="pattern", blocked=False,
        entries_used=[], reasoning=[], latency_ms=5.0,
        expect_min_length=50,
    )
    ts = score_task(result)
    assert not ts.checks["min_length"]


def test_score_task_entries_check():
    result = RunResult(
        task_id="t1", input="hi", category="test",
        reply_text="answer about topic", source="knowledge", blocked=False,
        entries_used=["Photosynthesis"], reasoning=[], latency_ms=5.0,
        expect_entries=["Photosynthesis", "Gravity"],
    )
    ts = score_task(result)
    assert not ts.checks["entries"]


def test_score_task_error():
    result = RunResult(
        task_id="t1", input="hi", category="test",
        reply_text="", source="error", blocked=False,
        entries_used=[], reasoning=[], latency_ms=0.0,
        error="engine crashed",
    )
    ts = score_task(result)
    assert not ts.passed
    assert not ts.checks["no_error"]


def test_score_run_aggregate():
    results = [
        RunResult(
            task_id="t1", input="hi", category="cat_a",
            reply_text="hello", source="pattern", blocked=False,
            entries_used=[], reasoning=[], latency_ms=5.0,
        ),
        RunResult(
            task_id="t2", input="bye", category="cat_a",
            reply_text="goodbye", source="pattern", blocked=False,
            entries_used=[], reasoning=[], latency_ms=3.0,
        ),
        RunResult(
            task_id="t3", input="x", category="cat_b",
            reply_text="", source="error", blocked=False,
            entries_used=[], reasoning=[], latency_ms=0.0,
            error="fail",
        ),
    ]
    card = score_run(results)
    assert card.total == 3
    assert card.passed == 2
    assert card.failed == 1
    assert card.by_category["cat_a"]["passed"] == 2
    assert card.by_category["cat_b"]["passed"] == 0
    assert "cat_b" in card.summary()


def test_score_run_empty():
    card = score_run([])
    assert card.total == 0
    assert card.score == 0.0


def test_scorecard_summary_format():
    results = [
        RunResult(
            task_id="t1", input="hi", category="general",
            reply_text="hello", source="pattern", blocked=False,
            entries_used=[], reasoning=[], latency_ms=5.0,
            expect_source="model",
        ),
    ]
    card = score_run(results)
    summary = card.summary()
    assert "0/1" in summary
    assert "source" in summary


# ---------------------------------------------------------------------------
# Integration: RunLogger in DialogueEngine
# ---------------------------------------------------------------------------


def test_engine_with_run_logger(tmp_path):
    """The engine writes run records when a RunLogger is attached."""
    from shaggoth.dialogue import DialogueEngine
    from shaggoth.eval.logger import RunLogger

    logger = RunLogger(directory=tmp_path)
    engine = DialogueEngine(run_logger=logger)
    engine.respond("hey there", session_id="int-test")

    records = logger.read_records()
    assert len(records) == 1
    assert records[0].user_input == "hey there"
    assert records[0].session_id == "int-test"
    assert records[0].latency_ms > 0


def test_run_logger_redacts_emails_in_input(tmp_path):
    logger = RunLogger(directory=tmp_path)
    record = logger.log(
        session_id="redact",
        user_input="contact bob@example.com for details",
        reply_text="ok",
        source="pattern",
        mode="no_drift",
    )
    assert record is not None
    assert "bob@example.com" not in record.user_input
    assert "[redacted-email]" in record.user_input


def test_run_logger_redacts_secrets_in_reply(tmp_path):
    logger = RunLogger(directory=tmp_path)
    record = logger.log(
        session_id="redact",
        user_input="show my token",
        reply_text="your key is ghp_Abc1234567890xyzABCD",
        source="model",
        mode="drift",
    )
    assert record is not None
    assert "ghp_" not in record.reply_text
    assert "[redacted-secret]" in record.reply_text


def test_run_logger_redacts_sk_key_in_input(tmp_path):
    logger = RunLogger(directory=tmp_path)
    record = logger.log(
        session_id="redact",
        user_input="my key is sk-1234567890abcdef1234",
        reply_text="blocked",
        source="guardrail",
        mode="no_drift",
        blocked=True,
    )
    assert record is not None
    assert "sk-1234567890abcdef1234" not in record.user_input
    assert "[redacted-secret]" in record.user_input


def test_run_logger_redacts_new_facts(tmp_path):
    logger = RunLogger(directory=tmp_path)
    record = logger.log(
        session_id="redact",
        user_input="remember my token",
        reply_text="ok",
        source="plugin",
        mode="no_drift",
        new_facts={"api_key": "sk-1234567890abcdef1234"},
    )
    assert record is not None
    assert "sk-1234567890abcdef1234" not in record.new_facts.get("api_key", "")
    assert "[redacted-secret]" in record.new_facts.get("api_key", "")


def test_run_logger_redacts_quoted_credential(tmp_path):
    """Credential values in quotes (password = "my secret") must be fully redacted."""
    logger = RunLogger(directory=tmp_path)
    record = logger.log(
        session_id="redact",
        user_input='my password = "super secret value"',
        reply_text="ok",
        source="pattern",
        mode="no_drift",
    )
    assert record is not None
    assert "super secret value" not in record.user_input
    assert "[redacted-credential]" in record.user_input


def test_harness_load_results_missing_file(tmp_path):
    """load_results must return [] for a nonexistent path, not crash."""
    loaded = Harness.load_results(tmp_path / "does-not-exist.jsonl")
    assert loaded == []


def test_engine_without_run_logger():
    """No crash when run_logger is None (the default)."""
    from shaggoth.dialogue import DialogueEngine

    engine = DialogueEngine()
    reply = engine.respond("hello")
    assert reply.text
