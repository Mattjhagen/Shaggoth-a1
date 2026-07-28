"""The self-critique loop: grading answers on idle capacity."""
from __future__ import annotations

import pytest

from shaggoth.feedback import FeedbackStore
from shaggoth.quality.critic import CriticLoop, machine_busy
from shaggoth.quality.teacher import Teacher, TeacherVerdict


class FakeTeacher:
    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.model = "fake"
        self.asked = []

    def available(self):
        return True

    def judge(self, question, answer):
        self.asked.append(question)
        v = self.verdicts.pop(0) if self.verdicts else ""
        return TeacherVerdict(verdict=v, seconds=0.01, model=self.model)


class FakeReply:
    def __init__(self, text, entries_used=None):
        self.text = text
        self.entries_used = entries_used or ["Atom"]
        self.reasoning = ["lookup: Atom"]


class FakeEngine:
    def __init__(self):
        self.memory = None
        self.asked = []

    def respond(self, text, session_id="default", mode=None):
        self.asked.append((text, session_id, mode))
        return FakeReply("The black bar is one angstrom.")


def _loop(verdicts, tmp_path, **kw):
    return CriticLoop(
        FakeEngine(),
        FeedbackStore(tmp_path / "fb.json"),
        teacher=FakeTeacher(verdicts),
        pace=0,
        **kw,
    )


def test_a_bad_verdict_files_a_complaint_against_the_entry(tmp_path):
    loop = _loop(["bad"], tmp_path)
    loop.judge_once("what is an atom")
    assert [t.topic for t in loop.feedback.repair_queue(now=0)] == ["Atom"]


def test_the_complaint_is_attributed_to_the_model_not_a_human(tmp_path):
    """A human thumbs-down must always be distinguishable from an auto-grade."""
    loop = _loop(["bad"], tmp_path)
    loop.judge_once("what is an atom")
    assert loop.feedback.recent()[0]["source"] == "critic-llm"


def test_good_and_weak_do_not_file_complaints(tmp_path):
    """Filing "weak" would drown the genuine failures."""
    loop = _loop(["good", "weak"], tmp_path)
    loop.judge_once("q1")
    loop.judge_once("q2")
    assert loop.feedback.repair_queue(now=0) == []


def test_an_unusable_verdict_is_counted_not_guessed_at(tmp_path):
    loop = _loop([""], tmp_path)
    assert loop.judge_once("q") is None
    assert loop.stats.unusable == 1
    assert loop.stats.judged == 0


def test_it_asks_in_no_drift_so_it_grades_the_grounded_path(tmp_path):
    loop = _loop(["good"], tmp_path)
    loop.judge_once("what is an atom")
    assert loop.engine.asked[0][2] == "no_drift"


def test_it_stands_down_when_the_machine_is_busy(tmp_path, monkeypatch):
    """Idle capacity is free; contended capacity is not."""
    loop = _loop(["good"] * 5, tmp_path)
    monkeypatch.setattr(loop, "questions", lambda n: ["a", "b", "c"])
    monkeypatch.setattr("shaggoth.quality.critic.machine_busy", lambda m: True)
    result = loop.run_batch(3)
    assert result["judged"] == 0
    assert loop.stats.skipped_busy == 1


def test_it_works_when_the_machine_is_idle(tmp_path, monkeypatch):
    loop = _loop(["good"] * 5, tmp_path)
    monkeypatch.setattr(loop, "questions", lambda n: ["a", "b", "c"])
    monkeypatch.setattr("shaggoth.quality.critic.machine_busy", lambda m: False)
    assert loop.run_batch(3)["judged"] == 3


def test_a_batch_is_bounded(tmp_path, monkeypatch):
    """An unbounded critic will chew the whole corpus and peg the box."""
    loop = _loop(["good"] * 50, tmp_path)
    monkeypatch.setattr(loop, "questions", lambda n: ["q%d" % i for i in range(n)])
    monkeypatch.setattr("shaggoth.quality.critic.machine_busy", lambda m: False)
    assert loop.run_batch(5)["judged"] == 5


def test_a_question_is_not_regraded(tmp_path):
    loop = _loop(["good", "good"], tmp_path)
    loop.judge_once("what is an atom")
    assert "what is an atom" in loop._seen


def test_an_unavailable_teacher_degrades_quietly(tmp_path):
    class Gone(FakeTeacher):
        def available(self):
            return False

    loop = CriticLoop(FakeEngine(), FeedbackStore(tmp_path / "fb.json"),
                      teacher=Gone([]), pace=0)
    assert loop.run_batch(3)["judged"] == 0
    assert "not available" in loop.stats.last_error


def test_machine_busy_reads_load():
    assert machine_busy(max_load=0.0) is True
    assert machine_busy(max_load=10_000.0) is False


def test_teacher_never_raises_on_a_dead_ollama():
    t = Teacher(host="127.0.0.1", port=9, timeout=1)   # closed port
    assert t.available() is False
    assert t.judge("q", "a").usable is False


def test_teacher_refuses_empty_input():
    assert Teacher().judge("", "answer").verdict == ""
