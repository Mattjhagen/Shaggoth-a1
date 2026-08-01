"""Free-tier cloud language models, via plain ``urllib`` — no SDKs.

Shaggoth is local-first: the Markov model (stdlib) is the default and always
works offline. These backends are an explicit opt-in for when you want a
smarter generator without paying for it, using the genuinely-free tiers:

- **Gemini** (Google AI Studio): ``GEMINI_API_KEY``. Default model
  ``gemini-2.5-flash`` (free tier), override with ``GEMINI_MODEL``.
- **Cloudflare Workers AI**: ``CLOUDFLARE_ACCOUNT_ID`` +
  ``CLOUDFLARE_WORKERS_AI_TOKEN``. Default model
  ``@cf/meta/llama-3.1-8b-instruct`` (free tier, ~10k neurons/day), override
  with ``CLOUDFLARE_AI_MODEL``.

Both implement the same ``LanguageModel`` interface *and* the extended
``generate_chat()`` RAG-aware call the dialogue engine uses for GPT-class
models, so they slot in where OpenAI does — without the ``openai`` pip
package. Configure with ``"model": "gemini" | "cloudflare" | "cloud"`` in
``config/settings.json``; ``"cloud"`` picks whichever free provider has a key
set. If no key is configured the engine falls back to the local model, so an
unconfigured install never breaks.

Free-tier terms are worth remembering: Gemini's free tier is text-only, no
card needed, and the provider may use free-tier traffic to improve its
models. Cloudflare's is a daily neuron budget shared across all models. Treat
both as best-effort prototyping tiers, not an SLA.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from .base import LanguageModel
from .openai_model import _BASE_SYSTEM

_TIMEOUT = 30.0


def _post_json(url: str, payload: dict, headers: dict, timeout: float = _TIMEOUT) -> dict:
    """POST ``payload`` as JSON; return the parsed JSON response.

    Raises on transport errors and non-2xx statuses (the caller converts to a
    friendly log line and an empty string, matching OpenAIModel's contract).
    """
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class ChatRESTModel(LanguageModel):
    """Base for RAG-aware chat models reached over a REST API.

    The dialogue engine treats any model exposing ``generate_chat()`` as a
    GPT-class model: tried in both drift and no_drift modes when patterns and
    knowledge haven't answered, with knowledge + conversation history supplied
    through the standard prompt.
    """

    name = "rest"
    provider = ""
    _DEFAULT_MODEL = ""
    _MAX_TOKENS = 300

    def __init__(self, model: str | None = None, max_tokens: int | None = None):
        self._model = model or self._DEFAULT_MODEL
        self._max_tokens = max_tokens or self._MAX_TOKENS
        self._last_error: str | None = None

    # -- configuration --------------------------------------------------------

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    @property
    def model_name(self) -> str:
        return self._model

    # -- LanguageModel interface ----------------------------------------------

    def is_trained(self) -> bool:
        return self.configured

    def train(self, text: str) -> None:
        pass  # pre-trained; learning is a knowledge-base concern here

    def save(self, path: str) -> None:
        pass

    def load(self, path: str) -> None:
        pass

    def generate(self, prompt: str = "", max_tokens: int = 0) -> str:
        if not self.configured:
            return ""
        return self.generate_chat(user_message=prompt, max_tokens=max_tokens)

    # -- RAG-aware interface (shared with OpenAIModel) -------------------------

    def generate_chat(
        self,
        user_message: str,
        *,
        knowledge_context: str = "",
        conversation_history: list[dict] | None = None,
        personality_context: str = "",
        system_extra: str = "",
        max_tokens: int = 0,
    ) -> str:
        if not self.configured:
            return ""
        max_tokens = max_tokens or self._max_tokens
        system_parts = [_BASE_SYSTEM]
        if personality_context:
            system_parts.append(f"\nPersonality overlay: {personality_context}")
        if knowledge_context:
            system_parts.append(f"\nRelevant knowledge from your research:\n{knowledge_context}")
        if system_extra:
            system_parts.append(system_extra)

        messages: list[dict[str, str]] = [{"role": "system", "content": "\n".join(system_parts)}]
        for turn in conversation_history or []:
            role = turn.get("role")
            content = turn.get("content") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_message})

        try:
            text = self._chat(messages, max_tokens)
            self._last_error = None
            return text.strip()
        except Exception as exc:  # noqa: BLE001 — a dead phone must not break a chat turn
            self._last_error = f"{self.provider}: {exc}"
            print(f"[{self.provider}] generation failed: {exc}")
            return ""

    def _chat(self, messages: list[dict], max_tokens: int) -> str:
        raise NotImplementedError

    def status(self) -> dict:
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self._model,
            "configured": self.configured,
            "last_error": self._last_error,
        }


class GeminiModel(ChatRESTModel):
    """Google Gemini via the generative-language REST API (free tier)."""

    name = "gemini"
    provider = "gemini"
    _DEFAULT_MODEL = "gemini-2.5-flash"
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ):
        super().__init__(model or os.environ.get("GEMINI_MODEL"), max_tokens)
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or ""

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _chat(self, messages: list[dict], max_tokens: int) -> str:
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [
            {"role": m["role"], "parts": [{"text": m["content"]}]}
            for m in messages
            if m["role"] != "system"
        ]
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
        }
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"{self._BASE_URL}/{self._model}:generateContent"
        data = _post_json(url, payload, {"x-goog-api-key": self._api_key})
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError(f"unexpected Gemini response: {data!r:.200}")


class CloudflareModel(ChatRESTModel):
    """Cloudflare Workers AI via the REST ``/ai/run`` endpoint (free tier)."""

    name = "cloudflare"
    provider = "cloudflare"
    _DEFAULT_MODEL = "@cf/meta/llama-3.1-8b-instruct"
    _BASE_URL = "https://api.cloudflare.com/client/v4/accounts"

    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ):
        super().__init__(model or os.environ.get("CLOUDFLARE_AI_MODEL"), max_tokens)
        self._token = (
            token
            or os.environ.get("CLOUDFLARE_WORKERS_AI_TOKEN")
            or os.environ.get("CLOUDFLARE_API_TOKEN")
            or ""
        )
        self._account_id = account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID") or ""

    @property
    def configured(self) -> bool:
        return bool(self._token and self._account_id)

    def _chat(self, messages: list[dict], max_tokens: int) -> str:
        if not self._account_id:
            raise RuntimeError("CLOUDFLARE_ACCOUNT_ID is not set")
        url = f"{self._BASE_URL}/{self._account_id}/ai/run/{self._model}"
        data = _post_json(
            url,
            {"messages": messages, "max_tokens": max_tokens},
            {"Authorization": f"Bearer {self._token}"},
        )
        try:
            text = data["result"]["response"]
        except (KeyError, TypeError):
            raise RuntimeError(f"unexpected Cloudflare response: {data!r:.200}")
        if not text:
            raise RuntimeError(f"empty Cloudflare response: {data!r:.200}")
        return text


#: Providers by the name a user can put in settings.json ("model").
_PROVIDERS: dict[str, type] = {
    "gemini": GeminiModel,
    "cloudflare": CloudflareModel,
}


def build_cloud_model(
    choice: str, model: str | None = None, max_tokens: int | None = None
) -> ChatRESTModel | None:
    """Build the requested free-tier cloud model, or ``None`` when unavailable.

    ``choice`` is ``gemini``, ``cloudflare``, or ``cloud`` (the first of the
    two with a key set). A model whose key is missing returns ``None`` so the
    caller falls back to the local generator — an unconfigured install keeps
    working offline with no error.
    """
    if choice == "cloud":
        for _name, _cls in _PROVIDERS.items():
            _candidate = _cls(model=model, max_tokens=max_tokens)
            if _candidate.configured:
                return _candidate
        return None
    _cls = _PROVIDERS.get(choice)
    if _cls is None:
        return None
    _candidate = _cls(model=model, max_tokens=max_tokens)
    return _candidate if _candidate.configured else None
