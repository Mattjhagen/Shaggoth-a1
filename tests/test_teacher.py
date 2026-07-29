"""Tests for Teacher quality-judge (quality/teacher.py)."""
from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from shaggoth.quality.teacher import (
    BAD,
    GOOD,
    WEAK,
    AnthropicTeacher,
    FallbackTeacher,
    OpenRouterTeacher,
    Teacher,
    TeacherVerdict,
    build_teacher,
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


# ---------------------------------------------------------------------------
# AnthropicTeacher / OpenRouterTeacher: cloud opt-ins, same judge() contract
#
# Both share _JudgeMixin with Teacher, so what's actually new to test is
# available() reading the right env var / constructor arg, and _generate()
# parsing each API's own response shape into the same (text, seconds, error)
# tuple the shared judge() logic already has full coverage for.
# ---------------------------------------------------------------------------

def _fake_json_response(payload: dict) -> MagicMock:
    resp = MagicMock()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    resp.read.return_value = json.dumps(payload).encode()
    return resp


def _http_error(code: int, body: bytes = b'{"error": "nope"}') -> urllib.error.HTTPError:
    err = urllib.error.HTTPError(url="http://x", code=code, msg="err", hdrs=None, fp=MagicMock())
    err.read = MagicMock(return_value=body)
    return err


class TestAnthropicTeacher:
    def test_available_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert not AnthropicTeacher().available()
        assert AnthropicTeacher(api_key="sk-ant-x").available()

    def test_available_reads_env_var(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
        assert AnthropicTeacher().available()

    def test_judge_parses_text_block(self):
        teacher = AnthropicTeacher(api_key="sk-ant-x")
        payload = {"content": [{"type": "text", "text": "good"}]}
        with patch("urllib.request.urlopen", return_value=_fake_json_response(payload)):
            v = teacher.judge("What is DNA?", "Genetic material.")
        assert v.verdict == GOOD
        assert v.model == teacher.model

    def test_judge_ignores_non_text_blocks(self):
        teacher = AnthropicTeacher(api_key="sk-ant-x")
        payload = {"content": [{"type": "tool_use", "id": "x"}, {"type": "text", "text": "bad"}]}
        with patch("urllib.request.urlopen", return_value=_fake_json_response(payload)):
            v = teacher.judge("q", "a")
        assert v.verdict == BAD

    def test_judge_without_api_key_is_unusable_and_never_calls_out(self):
        teacher = AnthropicTeacher(api_key="")
        with patch("urllib.request.urlopen") as mock_urlopen:
            v = teacher.judge("q", "a")
        mock_urlopen.assert_not_called()
        assert not v.usable

    def test_judge_http_error_is_unusable_and_records_detail(self):
        teacher = AnthropicTeacher(api_key="sk-ant-bad")
        with patch("urllib.request.urlopen", side_effect=_http_error(401, b'{"error":"invalid x-api-key"}')):
            v = teacher.judge("q", "a")
        assert not v.usable
        assert "401" in v.raw

    def test_judge_network_error_is_unusable(self):
        teacher = AnthropicTeacher(api_key="sk-ant-x")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            v = teacher.judge("q", "a")
        assert not v.usable

    def test_custom_model_is_recorded_on_verdict(self):
        teacher = AnthropicTeacher(api_key="sk-ant-x", model="claude-custom")
        payload = {"content": [{"type": "text", "text": "weak"}]}
        with patch("urllib.request.urlopen", return_value=_fake_json_response(payload)):
            v = teacher.judge("q", "a")
        assert v.model == "claude-custom"


class TestOpenRouterTeacher:
    def test_available_requires_api_key(self, monkeypatch):
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        assert not OpenRouterTeacher().available()
        assert OpenRouterTeacher(api_key="sk-or-x").available()

    def test_judge_parses_choice_content(self):
        teacher = OpenRouterTeacher(api_key="sk-or-x")
        payload = {"choices": [{"message": {"content": "good"}}]}
        with patch("urllib.request.urlopen", return_value=_fake_json_response(payload)):
            v = teacher.judge("What is DNA?", "Genetic material.")
        assert v.verdict == GOOD

    def test_judge_no_choices_is_unusable(self):
        teacher = OpenRouterTeacher(api_key="sk-or-x")
        with patch("urllib.request.urlopen", return_value=_fake_json_response({"choices": []})):
            v = teacher.judge("q", "a")
        assert not v.usable

    def test_judge_without_api_key_is_unusable_and_never_calls_out(self):
        teacher = OpenRouterTeacher(api_key="")
        with patch("urllib.request.urlopen") as mock_urlopen:
            v = teacher.judge("q", "a")
        mock_urlopen.assert_not_called()
        assert not v.usable

    def test_judge_http_error_is_unusable_and_records_detail(self):
        teacher = OpenRouterTeacher(api_key="sk-or-bad")
        with patch("urllib.request.urlopen", side_effect=_http_error(429, b'{"error":"rate limited"}')):
            v = teacher.judge("q", "a")
        assert not v.usable
        assert "429" in v.raw


# ---------------------------------------------------------------------------
# build_teacher: provider selection
#
# "ollama" is the load-bearing default -- AGENTS.md and teacher.py's own
# docstring explain why. These tests exist mainly to pin that down: adding
# a cloud provider must never change what an unconfigured install does.
# ---------------------------------------------------------------------------

class TestBuildTeacher:
    def test_default_is_ollama(self, monkeypatch):
        monkeypatch.delenv("SHAGGOTH_TEACHER_PROVIDER", raising=False)
        assert isinstance(build_teacher(), Teacher)

    def test_explicit_ollama(self):
        assert isinstance(build_teacher("ollama"), Teacher)

    def test_anthropic_provider(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        assert isinstance(build_teacher("anthropic"), AnthropicTeacher)

    def test_openrouter_provider(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
        assert isinstance(build_teacher("openrouter"), OpenRouterTeacher)

    def test_env_var_selects_provider(self, monkeypatch):
        monkeypatch.setenv("SHAGGOTH_TEACHER_PROVIDER", "anthropic")
        assert isinstance(build_teacher(), AnthropicTeacher)

    def test_explicit_argument_overrides_env_var(self, monkeypatch):
        monkeypatch.setenv("SHAGGOTH_TEACHER_PROVIDER", "anthropic")
        assert isinstance(build_teacher("openrouter"), OpenRouterTeacher)

    def test_unknown_provider_falls_back_to_ollama(self, monkeypatch, capsys):
        assert isinstance(build_teacher("not-a-real-provider"), Teacher)
        assert "not-a-real-provider" in capsys.readouterr().out

    def test_anthropic_model_override_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-custom-model")
        teacher = build_teacher("anthropic")
        assert teacher.model == "claude-custom-model"

    def test_openrouter_model_override_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_MODEL", "some/other-model")
        teacher = build_teacher("openrouter")
        assert teacher.model == "some/other-model"


# ---------------------------------------------------------------------------
# FallbackTeacher: cascade through providers when one looks exhausted
# ---------------------------------------------------------------------------

class _StubTeacher:
    """A minimal teacher stand-in with scripted availability/_generate."""

    def __init__(self, model, available=True, result=("good", 1.0, "")):
        self.model = model
        self._available = available
        self._result = result
        self.calls = 0

    def available(self):
        return self._available

    def _generate(self, prompt, max_tokens=8):
        self.calls += 1
        return self._result


class TestFallbackTeacher:
    def test_uses_first_available_teacher(self):
        a = _StubTeacher("a", result=("good", 1.0, ""))
        b = _StubTeacher("b", result=("bad", 1.0, ""))
        v = FallbackTeacher([a, b]).judge("q", "answer text")
        assert v.verdict == GOOD
        assert a.calls == 1
        assert b.calls == 0

    def test_falls_back_on_quota_error(self):
        a = _StubTeacher("a", result=("", 1.0, "HTTP 429: insufficient_quota"))
        b = _StubTeacher("b", result=("bad", 1.0, ""))
        ft = FallbackTeacher([a, b])
        v = ft.judge("q", "answer text")
        assert v.verdict == BAD
        assert ft.model == "b"

    def test_stays_advanced_across_calls(self):
        a = _StubTeacher("a", result=("", 1.0, "429 rate_limit"))
        b = _StubTeacher("b", result=("good", 1.0, ""))
        ft = FallbackTeacher([a, b])
        ft.judge("q1", "answer one")
        ft.judge("q2", "answer two")
        assert a.calls == 1  # not retried once exhausted
        assert b.calls == 2

    def test_non_exhaustion_error_is_retried_next_call(self):
        """A timeout or bad response isn't evidence the provider is *out* --
        only 429/quota/rate-limit/billing errors should burn the fallback."""
        a = _StubTeacher("a", result=("", 1.0, "Connection timed out"))
        b = _StubTeacher("b", result=("good", 1.0, ""))
        ft = FallbackTeacher([a, b])
        ft.judge("q1", "answer one")
        ft.judge("q2", "answer two")
        assert a.calls == 2  # still first in line

    def test_skips_unavailable_teachers(self):
        a = _StubTeacher("a", available=False)
        b = _StubTeacher("b", result=("weak", 1.0, ""))
        ft = FallbackTeacher([a, b])
        v = ft.judge("q", "answer text")
        assert v.verdict == WEAK
        assert ft.model == "b"

    def test_all_exhausted_returns_unusable(self):
        a = _StubTeacher("a", result=("", 1.0, "429 quota"))
        b = _StubTeacher("b", result=("", 1.0, "billing hard limit reached"))
        v = FallbackTeacher([a, b]).judge("q", "answer text")
        assert not v.usable

    def test_empty_teacher_list_raises(self):
        with pytest.raises(ValueError):
            FallbackTeacher([])

    def test_available_true_if_any_remaining_teacher_available(self):
        a = _StubTeacher("a", available=False)
        b = _StubTeacher("b", available=True)
        assert FallbackTeacher([a, b]).available()

    def test_available_false_once_all_exhausted(self):
        a = _StubTeacher("a", result=("", 1.0, "429 quota"))
        ft = FallbackTeacher([a])
        ft.judge("q", "answer text")
        assert not ft.available()


# ---------------------------------------------------------------------------
# build_teacher("auto"): the cascading chain, priority order and gating
# ---------------------------------------------------------------------------

class TestBuildTeacherAuto:
    def test_auto_builds_chain_in_priority_order(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
        teacher = build_teacher("auto")
        assert isinstance(teacher, FallbackTeacher)
        assert [type(t) for t in teacher._teachers] == [
            AnthropicTeacher, OpenRouterTeacher, Teacher,
        ]

    def test_auto_skips_cloud_providers_without_keys(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        teacher = build_teacher("auto")
        assert [type(t) for t in teacher._teachers] == [Teacher]

    def test_ollama_is_always_included_even_without_a_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-x")
        teacher = build_teacher("auto")
        assert Teacher in [type(t) for t in teacher._teachers]

    def test_fallback_and_cascade_are_aliases_for_auto(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-x")
        assert isinstance(build_teacher("fallback"), FallbackTeacher)
        assert isinstance(build_teacher("cascade"), FallbackTeacher)

    def test_env_var_selects_auto(self, monkeypatch):
        monkeypatch.setenv("SHAGGOTH_TEACHER_PROVIDER", "auto")
        assert isinstance(build_teacher(), FallbackTeacher)
