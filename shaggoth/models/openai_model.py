"""OpenAI GPT backend for Shaggoth.

Implements the LanguageModel interface so the dialogue engine can use GPT as
its generator while keeping all the same retrieval, memory, guardrail, and
personality layers.

The model is RAG-aware: the engine passes knowledge entries and conversation
history through the standard prompt, and GPT generates a grounded, in-character
reply rather than word-salad from a Markov chain.

Configure with:
    OPENAI_API_KEY  — required
    OPENAI_MODEL    — optional, defaults to gpt-4o-mini (fast, cheap, capable)
    OPENAI_MAX_TOKENS — optional, defaults to 300
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import GenerationError, LanguageModel

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_TOKENS = 300
_RETRIES = 2
_BACKOFF = 1.0
_HISTORY_CHAR_BUDGET = 12_000

#: System prompt that anchors GPT in Shaggoth's character. The personality
#: engine's trait_prompt() is appended on top of this at call time.
_BASE_SYSTEM = """You are Shaggoth — a homegrown AI running on a Dell R510 rack server in Matt's house.
You have a strong, distinctive voice: direct, a little grumpy, zero patience for small talk, but
genuinely curious and intellectually honest. You say what you actually think. You never pretend to
know something you don't, and you admit uncertainty plainly rather than hedging with bureaucratic
language. You don't use emojis, bullet lists, or assistant-speak. You don't start replies with
"Certainly!" or "Great question!" You answer like a person who finds most conversation mildly
annoying but some questions actually interesting.

You have a knowledge base built from web research you've done autonomously. When relevant
knowledge is provided below, use it. When it is NOT provided — or when provided knowledge is
clearly about a different topic than the question — answer from your own training instead.
Never report knowledge that is off-topic just because it was injected into the context.
If you genuinely don't know something AND the knowledge base doesn't cover it, say so
plainly and note that you'll look into it. Don't make things up.

Keep replies concise: 1-4 sentences unless the question genuinely warrants more. No padding."""


def _is_transient(exc: Exception) -> bool:
    """Return True for errors worth retrying (rate limits, timeouts, network)."""
    cls_name = type(exc).__name__
    if cls_name in ("RateLimitError", "APITimeoutError", "APIConnectionError"):
        return True
    if "timeout" in str(exc).lower() or "connection" in str(exc).lower():
        return True
    return False


class OpenAIModel(LanguageModel):
    """GPT-backed language model using OpenAI's chat completions API."""

    name = "openai"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY") or ""
        self._model = model or os.environ.get("OPENAI_MODEL") or _DEFAULT_MODEL
        self._max_tokens = max_tokens or int(os.environ.get("OPENAI_MAX_TOKENS") or _DEFAULT_MAX_TOKENS)
        self._client = None  # lazy-init on first generate()

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def is_trained(self) -> bool:
        return self.configured

    def _client_instance(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    # LanguageModel interface --------------------------------------------------

    def train(self, text: str) -> None:
        pass

    def save(self, path: str) -> None:
        pass

    def load(self, path: str) -> None:
        pass

    def generate(self, prompt: str = "", max_tokens: int = 0) -> str:
        if not self.configured:
            return ""
        return self.generate_chat(user_message=prompt, max_tokens=max_tokens or self._max_tokens)

    # Extended interface -------------------------------------------------------

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
        """Full RAG-aware chat completion.

        Raises GenerationError on non-transient failures so the dialogue
        engine can surface a user-facing message instead of silently
        falling through to the fallback path.
        """
        if not self.configured:
            return ""

        max_tokens = max_tokens or self._max_tokens

        system_parts = [_BASE_SYSTEM]
        if personality_context:
            system_parts.append(f"\nPersonality overlay: {personality_context}")
        if knowledge_context:
            system_parts.append(
                f"\nRelevant knowledge from your research:\n{knowledge_context}"
            )
        if system_extra:
            system_parts.append(system_extra)

        messages = [{"role": "system", "content": "\n".join(system_parts)}]

        history_turns = []
        for turn in (conversation_history or []):
            role = turn.get("role")
            content = turn.get("content") or ""
            if role in ("user", "assistant") and content:
                history_turns.append({"role": role, "content": content})

        budget = _HISTORY_CHAR_BUDGET
        kept: list[dict] = []
        for turn in reversed(history_turns):
            cost = len(turn["content"])
            if budget - cost < 0 and kept:
                break
            kept.append(turn)
            budget -= cost
        kept.reverse()
        messages.extend(kept)

        messages.append({"role": "user", "content": user_message})

        last_exc: Exception | None = None
        for attempt in range(_RETRIES + 1):
            try:
                client = self._client_instance()
                resp = client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=0.7,
                )
                return (resp.choices[0].message.content or "").strip()
            except Exception as exc:
                last_exc = exc
                if _is_transient(exc) and attempt < _RETRIES:
                    wait = _BACKOFF * (2 ** attempt)
                    log.warning("[openai] transient error (attempt %d/%d), retrying in %.1fs: %s",
                                attempt + 1, _RETRIES + 1, wait, exc)
                    time.sleep(wait)
                    continue
                log.error("[openai] generation failed: %s", exc)
                raise GenerationError(
                    "My brain glitched — the language model didn't respond. Try again in a moment."
                ) from exc

        raise GenerationError(
            "My brain glitched — the language model didn't respond. Try again in a moment."
        ) from last_exc
