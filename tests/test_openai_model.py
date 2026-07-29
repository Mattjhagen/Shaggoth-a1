"""Tests for the OpenAI GPT language model backend."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from shaggoth.models.openai_model import OpenAIModel, _BASE_SYSTEM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_completion(text: str):
    """Build a fake openai.ChatCompletion-shaped object."""
    msg = SimpleNamespace(content=text)
    choice = SimpleNamespace(message=msg)
    return SimpleNamespace(choices=[choice])


def _model(api_key: str = "sk-test") -> OpenAIModel:
    return OpenAIModel(api_key=api_key)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_configured_when_api_key_set(self):
        m = _model("sk-abc")
        assert m.configured

    def test_not_configured_when_no_key(self):
        m = OpenAIModel(api_key="")
        assert not m.configured

    def test_is_trained_equals_configured(self):
        m = _model()
        assert m.is_trained() == m.configured

    def test_picks_key_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fromenv")
        m = OpenAIModel()
        assert m.configured

    def test_model_defaults_to_gpt4o_mini(self):
        m = _model()
        assert m._model == "gpt-4o-mini"

    def test_model_override(self):
        m = OpenAIModel(api_key="sk-x", model="gpt-4-turbo")
        assert m._model == "gpt-4-turbo"

    def test_model_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-3.5-turbo")
        m = OpenAIModel(api_key="sk-x")
        assert m._model == "gpt-3.5-turbo"

    def test_max_tokens_defaults_to_300(self):
        m = _model()
        assert m._max_tokens == 300

    def test_max_tokens_override(self):
        m = OpenAIModel(api_key="sk-x", max_tokens=500)
        assert m._max_tokens == 500

    def test_client_starts_as_none(self):
        m = _model()
        assert m._client is None

    def test_name(self):
        assert OpenAIModel.name == "openai"


# ---------------------------------------------------------------------------
# generate() / generate_chat() when not configured
# ---------------------------------------------------------------------------

class TestUnconfigured:
    def setup_method(self):
        self.m = OpenAIModel(api_key="")

    def test_generate_returns_empty_string(self):
        assert self.m.generate("hello") == ""

    def test_generate_chat_returns_empty_string(self):
        assert self.m.generate_chat("hello") == ""

    def test_generate_chat_with_all_args_returns_empty(self):
        result = self.m.generate_chat(
            "hello",
            knowledge_context="some knowledge",
            conversation_history=[{"role": "user", "content": "hi"}],
            personality_context="grumpy",
        )
        assert result == ""


# ---------------------------------------------------------------------------
# train / save / load (no-ops)
# ---------------------------------------------------------------------------

class TestNoOps:
    def test_train_does_not_raise(self):
        m = _model()
        m.train("some text")

    def test_save_does_not_raise(self):
        m = _model()
        m.save("/tmp/nowhere")

    def test_load_does_not_raise(self):
        m = _model()
        m.load("/tmp/nowhere")


# ---------------------------------------------------------------------------
# generate_chat message assembly
# ---------------------------------------------------------------------------

class TestMessageAssembly:
    def setup_method(self):
        self.m = _model()
        self.mock_client = MagicMock()
        self.m._client = self.mock_client

    def _last_messages(self) -> list[dict]:
        call_args = self.mock_client.chat.completions.create.call_args
        return call_args.kwargs["messages"]

    def _setup_response(self, text: str):
        self.mock_client.chat.completions.create.return_value = _fake_completion(text)

    def test_basic_message_structure(self):
        self._setup_response("Hello back.")
        self.m.generate_chat("Hello")
        msgs = self._last_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "Hello"

    def test_system_prompt_contains_base(self):
        self._setup_response("x")
        self.m.generate_chat("q")
        sys_content = self._last_messages()[0]["content"]
        assert "Shaggoth" in sys_content

    def test_knowledge_context_injected_in_system(self):
        self._setup_response("x")
        self.m.generate_chat("q", knowledge_context="Aeroponics grows plants in air.")
        sys_content = self._last_messages()[0]["content"]
        assert "Aeroponics grows plants in air." in sys_content

    def test_personality_context_injected(self):
        self._setup_response("x")
        self.m.generate_chat("q", personality_context="Very sarcastic.")
        sys_content = self._last_messages()[0]["content"]
        assert "Very sarcastic." in sys_content

    def test_system_extra_appended(self):
        self._setup_response("x")
        self.m.generate_chat("q", system_extra="Extra system instruction.")
        sys_content = self._last_messages()[0]["content"]
        assert "Extra system instruction." in sys_content

    def test_conversation_history_included(self):
        self._setup_response("x")
        history = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First reply"},
        ]
        self.m.generate_chat("Second message", conversation_history=history)
        msgs = self._last_messages()
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        assert "assistant" in roles
        # system + 2 history + 1 current = 4
        assert len(msgs) == 4

    def test_history_invalid_roles_skipped(self):
        self._setup_response("x")
        history = [
            {"role": "system", "content": "Should be ignored"},
            {"role": "user", "content": "Valid"},
        ]
        self.m.generate_chat("q", conversation_history=history)
        msgs = self._last_messages()
        contents = [m["content"] for m in msgs]
        assert "Should be ignored" not in contents

    def test_history_empty_content_skipped(self):
        self._setup_response("x")
        history = [{"role": "user", "content": ""}]
        self.m.generate_chat("q", conversation_history=history)
        msgs = self._last_messages()
        # Only system + current user
        assert len(msgs) == 2

    def test_none_history_treated_as_empty(self):
        self._setup_response("x")
        self.m.generate_chat("q", conversation_history=None)
        msgs = self._last_messages()
        assert len(msgs) == 2

    def test_response_text_returned(self):
        self._setup_response("  Stripped reply.  ")
        result = self.m.generate_chat("q")
        assert result == "Stripped reply."

    def test_uses_configured_max_tokens(self):
        self.m._max_tokens = 150
        self._setup_response("x")
        self.m.generate_chat("q")
        call_kwargs = self.mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 150

    def test_max_tokens_override_in_call(self):
        self._setup_response("x")
        self.m.generate_chat("q", max_tokens=42)
        call_kwargs = self.mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 42

    def test_temperature_is_07(self):
        self._setup_response("x")
        self.m.generate_chat("q")
        call_kwargs = self.mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["temperature"] == 0.7

    def test_uses_configured_model_name(self):
        self.m._model = "gpt-4"
        self._setup_response("x")
        self.m.generate_chat("q")
        call_kwargs = self.mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4"


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

class TestExceptionHandling:
    def setup_method(self):
        self.m = _model()
        self.mock_client = MagicMock()
        self.m._client = self.mock_client

    def test_api_exception_returns_empty_string(self):
        self.mock_client.chat.completions.create.side_effect = RuntimeError("Connection refused")
        result = self.m.generate_chat("q")
        assert result == ""

    def test_exception_does_not_propagate(self):
        self.mock_client.chat.completions.create.side_effect = Exception("Some error")
        # Should not raise
        self.m.generate_chat("q")


# ---------------------------------------------------------------------------
# generate() delegates to generate_chat()
# ---------------------------------------------------------------------------

class TestGenerateDelegates:
    def test_generate_calls_generate_chat(self):
        m = _model()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_completion("answer")
        m._client = mock_client
        result = m.generate("test prompt")
        assert result == "answer"

    def test_generate_passes_max_tokens(self):
        m = _model()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _fake_completion("x")
        m._client = mock_client
        m.generate("test", max_tokens=123)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 123
