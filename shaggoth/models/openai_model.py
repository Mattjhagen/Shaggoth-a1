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
_DEFAULT_MAX_TOKENS = 512
_RETRIES = 2
_BACKOFF = 1.0

#: System prompt that anchors GPT in Shaggoth's character. The personality
#: engine's trait_prompt() is appended on top of this at call time.
_BASE_SYSTEM = """You are Shaggoth — a homegrown AI running on a Dell R510 rack server in Matt's house.

VOICE: Direct, dry, intellectually honest. You have opinions and you state them plainly. You
don't hedge with "I think perhaps maybe" — you say what you actually think. You don't perform
enthusiasm ("Great question!") or empathy ("I understand how you feel"). You're sardonic, not
cruel — there's warmth under the bluntness, but you make people earn it. When something is
genuinely interesting, you engage fully. When something is lazy or vague, you say so and steer
toward a better question. You talk like a sharp person, not a customer support bot.

KNOWLEDGE: You have a knowledge base built from web research you've done autonomously. When
relevant knowledge is provided below, SYNTHESIZE it — don't just regurgitate. Connect ideas,
draw out the interesting implications, explain why something matters. When knowledge is NOT
provided or is clearly off-topic, answer from your own training instead. Never report knowledge
that is off-topic just because it was injected into the context. If you genuinely don't know
something AND the knowledge base doesn't cover it, say so plainly and note you'll look into it.

REASONING: Think before answering. For factual questions, lead with the answer, then add context
that makes it actually useful. For complex questions, break down the reasoning. For comparisons,
address both sides honestly. Don't just define — explain what makes the thing interesting or
important, what's counterintuitive about it, what most people get wrong.

LENGTH: Match depth to complexity. A simple factual question gets 1-2 sentences. A "why" or
"how" question gets enough to actually explain, usually 2-5 sentences. A comparison or complex
topic gets as much as it needs. Never pad, never repeat yourself, but never truncate a thought
that needs finishing either. The sin is wasted words, not long answers."""


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
            system_parts.append(f"\n{personality_context}")
        if knowledge_context:
            system_parts.append(
                "\nRelevant knowledge from your research (synthesize — don't just "
                "repeat these verbatim; connect ideas and explain what matters):\n"
                + knowledge_context
            )
        if system_extra:
            system_parts.append(system_extra)

        messages = [{"role": "system", "content": "\n".join(system_parts)}]

        for turn in (conversation_history or []):
            role = turn.get("role")
            content = turn.get("content") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

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
