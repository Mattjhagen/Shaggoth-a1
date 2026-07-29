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

import os
from typing import Optional

from .base import LanguageModel

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_MAX_TOKENS = 300

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
        # GPT is a pre-trained model; training is a no-op here.
        pass

    def save(self, path: str) -> None:
        pass

    def load(self, path: str) -> None:
        pass

    def generate(self, prompt: str = "", max_tokens: int = 0) -> str:
        """Generate a reply for a pre-built prompt string.

        This is the simple interface used by the dialogue engine for drift mode.
        For the full RAG-aware call, use generate_chat().
        """
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

        Builds a proper OpenAI messages array with:
        - System prompt (character + personality traits + knowledge)
        - Prior conversation turns
        - The user's current message
        """
        if not self.configured:
            return ""

        max_tokens = max_tokens or self._max_tokens

        # Build the system message
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

        # Inject recent conversation turns
        for turn in (conversation_history or []):
            role = turn.get("role")
            content = turn.get("content") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

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
            print(f"[openai] generation failed: {exc}")
            return ""
