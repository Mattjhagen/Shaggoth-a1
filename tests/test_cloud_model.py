"""Tests for the free-tier cloud model backends (Gemini / Cloudflare).

These exercise request shaping, response parsing and the factory — never a
live API (no keys on the dev box). The real network behaviour is deliberately
out of scope: this pins the wire format so a future live integration has
something to regress against.
"""
from __future__ import annotations

import shaggoth.models.cloud as cloud_mod
from shaggoth.models.cloud import (
    CloudflareModel,
    GeminiModel,
    build_cloud_model,
)


def _gemini_response(text: str) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _cf_response(text: str) -> dict:
    return {"result": {"response": text}}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_gemini_configured_when_key_set(self):
        assert GeminiModel(api_key="k").configured

    def test_gemini_not_configured_when_no_key(self):
        assert not GeminiModel(api_key="").configured

    def test_gemini_picks_key_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "from-env")
        assert GeminiModel().configured

    def test_gemini_model_default(self):
        assert GeminiModel(api_key="k")._model == "gemini-2.5-flash"

    def test_gemini_model_override(self):
        assert GeminiModel(api_key="k", model="gemini-3-flash")._model == "gemini-3-flash"

    def test_gemini_model_from_env(self, monkeypatch):
        monkeypatch.setenv("GEMINI_MODEL", "gemini-3-flash")
        assert GeminiModel(api_key="k")._model == "gemini-3-flash"

    def test_cf_configured_with_token_and_account(self):
        assert CloudflareModel(token="t", account_id="a").configured

    def test_cf_not_configured_without_account(self):
        assert not CloudflareModel(token="t", account_id="").configured

    def test_cf_not_configured_without_token(self):
        assert not CloudflareModel(token="", account_id="a").configured

    def test_cf_picks_from_env(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
        monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_TOKEN", "tok")
        assert CloudflareModel().configured

    def test_cf_model_default(self):
        assert CloudflareModel(token="t", account_id="a")._model == "@cf/meta/llama-3.1-8b-instruct"

    def test_cf_model_override(self):
        assert CloudflareModel(token="t", account_id="a", model="@cf/qwen/qwen1.5")._model == "@cf/qwen/qwen1.5"

    def test_is_trained_equals_configured(self):
        assert GeminiModel(api_key="k").is_trained()
        assert not GeminiModel(api_key="").is_trained()

    def test_names(self):
        assert GeminiModel.name == "gemini"
        assert CloudflareModel.name == "cloudflare"


# ---------------------------------------------------------------------------
# Unconfigured behaviour
# ---------------------------------------------------------------------------

class TestUnconfigured:
    def test_generate_returns_empty(self):
        assert GeminiModel(api_key="").generate("hi") == ""

    def test_generate_chat_returns_empty(self):
        assert GeminiModel(api_key="").generate_chat("hi") == ""

    def test_cf_generate_returns_empty(self):
        assert CloudflareModel(token="", account_id="a").generate("hi") == ""


# ---------------------------------------------------------------------------
# No-ops (LanguageModel interface)
# ---------------------------------------------------------------------------

class TestNoOps:
    def test_train_does_not_raise(self):
        GeminiModel(api_key="k").train("text")

    def test_save_does_not_raise(self):
        GeminiModel(api_key="k").save("/tmp/x")

    def test_load_does_not_raise(self):
        GeminiModel(api_key="k").load("/tmp/x")


# ---------------------------------------------------------------------------
# Gemini wire format
# ---------------------------------------------------------------------------

class TestGeminiWire:
    def setup_method(self):
        self.m = GeminiModel(api_key="secret")
        self.calls = []

        def fake_post(url, payload, headers, timeout=None):
            self.calls.append((url, payload, headers))
            return _gemini_response("  Gemini says hi.  ")

        self.m._post = fake_post

    def test_url_and_headers(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        self.m.generate_chat("hello")
        url, _payload, headers = self.calls[0]
        assert url.endswith("/models/gemini-2.5-flash:generateContent")
        assert headers["x-goog-api-key"] == "secret"

    def test_payload_structure(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        self.m.generate_chat("hello", conversation_history=[{"role": "user", "content": "prev"}])
        _url, payload, _headers = self.calls[0]
        assert payload["contents"][-1]["parts"] == [{"text": "hello"}]
        assert payload["generationConfig"]["maxOutputTokens"] == 300

    def test_system_instruction_from_personality_and_knowledge(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        self.m.generate_chat("q", knowledge_context="Plants grow in air.", personality_context="Sarcastic.")
        _url, payload, _headers = self.calls[0]
        system_text = payload["systemInstruction"]["parts"][0]["text"]
        assert "Plants grow in air." in system_text
        assert "Sarcastic." in system_text

    def test_response_text_extracted_and_stripped(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        assert self.m.generate_chat("q") == "Gemini says hi."

    def test_uses_override_max_tokens(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        self.m.generate_chat("q", max_tokens=77)
        assert self.calls[0][1]["generationConfig"]["maxOutputTokens"] == 77


# ---------------------------------------------------------------------------
# Cloudflare wire format
# ---------------------------------------------------------------------------

class TestCloudflareWire:
    def setup_method(self):
        self.m = CloudflareModel(token="tok", account_id="acc")
        self.calls = []

        def fake_post(url, payload, headers, timeout=None):
            self.calls.append((url, payload, headers))
            return _cf_response("  CF says hi.  ")

        self.m._post = fake_post

    def test_url_headers_and_payload(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        self.m.generate_chat("hello")
        url, payload, headers = self.calls[0]
        assert url.endswith("/accounts/acc/ai/run/@cf/meta/llama-3.1-8b-instruct")
        assert headers["Authorization"] == "Bearer tok"
        assert payload["messages"][-1] == {"role": "user", "content": "hello"}
        assert payload["max_tokens"] == 300

    def test_response_text_extracted(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        assert self.m.generate_chat("q") == "CF says hi."

    def test_system_role_in_messages(self, monkeypatch):
        monkeypatch.setattr(cloud_mod, "_post_json", self.m._post)
        self.m.generate_chat("q")
        assert self.calls[0][1]["messages"][0]["role"] == "system"


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

class TestFailures:
    def test_gemini_api_error_returns_empty_and_records(self, monkeypatch):
        m = GeminiModel(api_key="k")
        monkeypatch.setattr(cloud_mod, "_post_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        assert m.generate_chat("q") == ""
        assert m._last_error is not None

    def test_cf_malformed_response_records_error(self, monkeypatch):
        m = CloudflareModel(token="t", account_id="a")
        monkeypatch.setattr(cloud_mod, "_post_json", lambda *a, **k: {"result": {}})
        assert m.generate_chat("q") == ""
        assert m._last_error is not None

    def test_success_clears_last_error(self, monkeypatch):
        m = GeminiModel(api_key="k")
        monkeypatch.setattr(cloud_mod, "_post_json", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        m.generate_chat("q")
        assert m._last_error is not None
        monkeypatch.setattr(cloud_mod, "_post_json", lambda *a, **k: _gemini_response("ok"))
        assert m.generate_chat("q") == "ok"
        assert m._last_error is None


# ---------------------------------------------------------------------------
# generate() delegates
# ---------------------------------------------------------------------------

class TestGenerateDelegates:
    def test_generate_calls_generate_chat(self, monkeypatch):
        m = GeminiModel(api_key="k")
        monkeypatch.setattr(cloud_mod, "_post_json", lambda *a, **k: _gemini_response("answer"))
        assert m.generate("prompt") == "answer"


# ---------------------------------------------------------------------------
# status()
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_shape(self):
        s = GeminiModel(api_key="k").status()
        assert s["name"] == "gemini"
        assert s["configured"] is True
        assert "model" in s
        assert "last_error" in s


# ---------------------------------------------------------------------------
# factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_unknown_choice_returns_none(self):
        assert build_cloud_model("bogus") is None

    def test_cloud_returns_none_without_keys(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
        monkeypatch.delenv("CLOUDFLARE_WORKERS_AI_TOKEN", raising=False)
        monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
        assert build_cloud_model("cloud") is None

    def test_gemini_explicit_needs_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        assert build_cloud_model("gemini") is None

    def test_gemini_explicit_with_key(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        m = build_cloud_model("gemini")
        assert m is not None and isinstance(m, GeminiModel)

    def test_cloud_prefers_gemini_when_both_configured(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "gk")
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_TOKEN", "t")
        m = build_cloud_model("cloud")
        assert isinstance(m, GeminiModel)

    def test_cloud_falls_back_to_cf(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_TOKEN", "t")
        m = build_cloud_model("cloud")
        assert isinstance(m, CloudflareModel)

    def test_cloudflare_explicit_with_key(self, monkeypatch):
        monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a")
        monkeypatch.setenv("CLOUDFLARE_WORKERS_AI_TOKEN", "t")
        m = build_cloud_model("cloudflare")
        assert m is not None and isinstance(m, CloudflareModel)

    def test_built_model_passes_model_and_max_tokens(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "k")
        m = build_cloud_model("gemini", model="gemini-3-flash", max_tokens=99)
        assert m._model == "gemini-3-flash"
        assert m._max_tokens == 99
