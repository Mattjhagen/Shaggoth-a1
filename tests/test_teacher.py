"""Tests for Teacher quality-judge (quality/teacher.py)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from shaggoth.quality.teacher import (
    BAD,
    GOOD,
    WEAK,
    Teacher,
    TeacherVerdict,
)


# ---------------------------------------------------------------------------
# TeacherVerdict
# ---------------------------------------------------------------------------

class TestTeacherVerdict:
    def test_good_is_usable(self):
        v = TeacherVerdict(verdict=GOOD)
        assert v.usable

    def test_weak_is_usable(self):
        v = TeacherVerdict(verdict=WEAK)
        assert v.usable

    def test_bad_is_usable(self):
        v = TeacherVerdict(verdict=BAD)
        assert v.usable

    def test_empty_verdict_not_usable(self):
        v = TeacherVerdict(verdict="")
        assert not v.usable

    def test_garbage_verdict_not_usable(self):
        v = TeacherVerdict(verdict="maybe")
        assert not v.usable

    def test_bad_is_negative(self):
        v = TeacherVerdict(verdict=BAD)
        assert v.negative

    def test_good_is_not_negative(self):
        v = TeacherVerdict(verdict=GOOD)
        assert not v.negative

    def test_weak_is_not_negative(self):
        v = TeacherVerdict(verdict=WEAK)
        assert not v.negative


# ---------------------------------------------------------------------------
# Teacher.available
# ---------------------------------------------------------------------------

def _fake_tags_response(model_names: list[str]) -> MagicMock:
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = json.dumps({
        "models": [{"name": n} for n in model_names]
    }).encode()
    return resp


class TestTeacherAvailable:
    def test_available_when_model_listed(self):
        teacher = Teacher(model="qwen2.5-coder:7b")
        fake_ctx = _fake_tags_response(["qwen2.5-coder:7b", "other:model"])
        with patch("urllib.request.urlopen", return_value=fake_ctx):
            assert teacher.available()

    def test_not_available_when_model_absent(self):
        teacher = Teacher(model="qwen2.5-coder:7b")
        fake_ctx = _fake_tags_response(["other:model"])
        with patch("urllib.request.urlopen", return_value=fake_ctx):
            assert not teacher.available()

    def test_not_available_on_connection_error(self):
        import urllib.error
        teacher = Teacher()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            assert not teacher.available()

    def test_not_available_on_timeout(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timeout")):
            assert not teacher.available()

    def test_not_available_on_bad_json(self):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = b"not json"
        with patch("urllib.request.urlopen", return_value=resp):
            teacher = Teacher()
            assert not teacher.available()


# ---------------------------------------------------------------------------
# Teacher.judge
# ---------------------------------------------------------------------------

def _fake_generate_response(response_text: str) -> MagicMock:
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = json.dumps({"response": response_text}).encode()
    return resp


class TestTeacherJudge:
    def test_judge_returns_good(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("good")):
            v = teacher.judge("What is DNA?", "Deoxyribonucleic acid, the genetic material.")
        assert v.verdict == GOOD
        assert v.usable

    def test_judge_returns_weak(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("  weak  ")):
            v = teacher.judge("Explain recursion.", "It's complicated.")
        assert v.verdict == WEAK

    def test_judge_returns_bad(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("BAD")):
            v = teacher.judge("What is entropy?", "I like turtles.")
        assert v.verdict == BAD

    def test_judge_extracts_verdict_from_longer_response(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("I'd say this is weak, honestly.")):
            v = teacher.judge("q", "a")
        assert v.verdict == WEAK

    def test_judge_empty_question_returns_unusable(self):
        teacher = Teacher()
        v = teacher.judge("", "Some answer.")
        assert not v.usable

    def test_judge_empty_answer_returns_unusable(self):
        teacher = Teacher()
        v = teacher.judge("What is X?", "")
        assert not v.usable

    def test_judge_network_error_returns_unusable(self):
        import urllib.error
        teacher = Teacher()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            v = teacher.judge("q", "a")
        assert not v.usable

    def test_judge_garbage_response_returns_unusable(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("I have no idea")):
            v = teacher.judge("q", "a")
        assert not v.usable

    def test_judge_records_seconds(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("good")):
            v = teacher.judge("q", "a")
        assert v.seconds >= 0

    def test_judge_records_model(self):
        teacher = Teacher(model="my-model:3b")
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("good")):
            v = teacher.judge("q", "a")
        assert v.model == "my-model:3b"

    def test_judge_records_raw_response(self):
        teacher = Teacher()
        with patch("urllib.request.urlopen", return_value=_fake_generate_response("good response here")):
            v = teacher.judge("q", "a")
        assert v.raw  # should be non-empty

    def test_judge_case_insensitive_verdict_extraction(self):
        teacher = Teacher()
        for word in ("GOOD", "Good", "gOoD"):
            with patch("urllib.request.urlopen", return_value=_fake_generate_response(word)):
                v = teacher.judge("q", "a")
            assert v.verdict == GOOD

    def test_judge_bad_json_from_server_returns_unusable(self):
        resp = MagicMock()
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        resp.read.return_value = b"not json"
        with patch("urllib.request.urlopen", return_value=resp):
            teacher = Teacher()
            v = teacher.judge("q", "a")
        assert not v.usable
