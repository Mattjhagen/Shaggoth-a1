"""Dialogue engine — the conductor.

Every user message flows through a fixed, inspectable pipeline:

    1. guardrails  — input rules may block/refuse before anything else runs
    2. plugins     — feature commands get first crack at handling the message
    3. memory      — extract facts; find topic overlaps with past conversations
    4. generation  — pattern engine (deterministic), else language model
    5. recall      — if an earlier conversation strongly overlaps, weave in a
                     topic callback ("last time we talked about ...")
    6. guardrails  — output rules (redaction, length) filter the reply
    7. persist     — both sides of the exchange are stored in memory

Each stage is swappable: pass in your own GuardrailEngine, MemoryStore,
LanguageModel, or plugin registry to reuse Shaggoth as a base platform.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..guardrails import GuardrailEngine
from ..memory import MemoryStore
from ..models.base import LanguageModel
from ..plugins import PluginRegistry, default_registry
from .patterns import PatternEngine


@dataclass
class Reply:
    text: str
    source: str  # guardrail | plugin | pattern | model | fallback
    blocked: bool = False
    rule_id: str | None = None
    output_rules_applied: list[str] = field(default_factory=list)
    memory_triggers: list[str] = field(default_factory=list)
    new_facts: dict = field(default_factory=dict)


class DialogueEngine:
    def __init__(
        self,
        guardrails: GuardrailEngine | None = None,
        memory: MemoryStore | None = None,
        model: LanguageModel | None = None,
        plugins: PluginRegistry | None = None,
        bot_name: str = "Shaggoth",
        recall_threshold: float = 0.35,
        seed: int | None = None,
    ):
        self.guardrails = guardrails or GuardrailEngine()
        self.memory = memory or MemoryStore()
        self.model = model
        self.plugins = plugins if plugins is not None else default_registry()
        self.patterns = PatternEngine(seed=seed)
        self.bot_name = bot_name
        self.recall_threshold = recall_threshold
        # Avoid repeating the same callback within a session.
        self._recalled: dict[str, set[int]] = {}

    def respond(self, text: str, session_id: str = "default") -> Reply:
        text = text.strip()
        if not text:
            return Reply("Say something and I'll do my best.", source="fallback")

        # 1. Guardrails: input check.
        verdict = self.guardrails.check_input(text)
        if not verdict.allowed:
            reply = Reply(
                verdict.message or "I can't help with that.",
                source="guardrail",
                blocked=True,
                rule_id=verdict.rule_id,
            )
            self._persist(session_id, text, reply)
            return reply

        # 2. Plugins.
        plugin_response = self.plugins.dispatch(text, memory=self.memory)
        if plugin_response is not None:
            reply = self._finish(Reply(plugin_response, source="plugin"))
            self._persist(session_id, text, reply)
            return reply

        # 3. Memory: facts + topic recall (before storing the new message,
        #    so the query can't match itself).
        new_facts = self.memory.extract_and_store_facts(text)
        recalls = self.memory.recall(
            text, current_session=session_id, limit=1,
            min_score=self.recall_threshold,
        )

        # 4. Generation.
        body = self.patterns.respond(text)
        source = "pattern"
        if body is None and self.model is not None and self.model.is_trained():
            generated = self.model.generate(prompt=text, max_tokens=40).strip()
            if generated:
                body, source = generated, "model"
        if body is None:
            body, source = self.patterns.fallback(), "fallback"

        # Personalize with a remembered name occasionally.
        name = self.memory.get_fact("name")
        if name and name.lower() not in body.lower() and len(body) < 80:
            if hash(text) % 4 == 0:  # deterministic, ~25% of short replies
                body = f"{body[:-1]}, {name}{body[-1]}" if body[-1] in ".!?" else f"{body}, {name}"

        # 5. Topic callback from a past conversation.
        triggers: list[str] = []
        seen = self._recalled.setdefault(session_id, set())
        for recall in recalls:
            if recall.message_id in seen:
                continue
            seen.add(recall.message_id)
            topic = ", ".join(recall.shared_words[:3])
            when = _humanize_age(time.time() - recall.ts)
            body += (
                f" By the way — {when} you mentioned something related "
                f"({topic}): “{_snippet(recall.content)}”. "
                "Has anything changed there?"
            )
            triggers.append(topic)

        reply = self._finish(
            Reply(body, source=source, memory_triggers=triggers, new_facts=new_facts)
        )
        self._persist(session_id, text, reply)
        return reply

    # ------------------------------------------------------------------
    def _finish(self, reply: Reply) -> Reply:
        reply.text, reply.output_rules_applied = self.guardrails.filter_output(reply.text)
        return reply

    def _persist(self, session_id: str, user_text: str, reply: Reply) -> None:
        self.memory.add_message(session_id, "user", user_text)
        self.memory.add_message(session_id, "assistant", reply.text)


def _snippet(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _humanize_age(seconds: float) -> str:
    if seconds < 3600:
        return "a little while ago"
    if seconds < 86400:
        return "earlier today"
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return "a while back"
