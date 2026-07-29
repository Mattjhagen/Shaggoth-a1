"""Built-in plugins: time, arithmetic, and explicit memory commands.

These double as examples of the plugin API — copy one to add a feature.
"""

from __future__ import annotations

import ast
import operator
import re
from datetime import datetime

from . import PluginRegistry

_MATH_RE = re.compile(r"^\s*(?:what(?:'s| is)\s+)?([\d\s+\-*/().%]+)\s*\??\s*$")

# Injected by server.py serve() so the curiosity plugin uses the shared engine
# and fires the same deferred-answer and Slack callbacks as server-side research.
_curiosity_engine = None

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(expr: str) -> float:
    """Evaluate arithmetic via the AST — no eval(), no names, no calls."""

    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand))
        raise ValueError("unsupported expression")

    return walk(ast.parse(expr, mode="eval"))


def build_registry() -> PluginRegistry:
    """Build the default plugin registry with all built-in plugins."""
    registry = PluginRegistry()

    @registry.register("time")
    def time_plugin(text: str, **_) -> str | None:
        if re.search(r"(?i)\bwhat time is it\b|\bcurrent time\b|\btoday'?s date\b", text):
            now = datetime.now()
            return f"It's {now.strftime('%H:%M')} on {now.strftime('%A, %B %d, %Y')}."
        return None

    @registry.register("calculator")
    def calc_plugin(text: str, **_) -> str | None:
        match = _MATH_RE.match(text)
        if not match:
            return None
        expr = match.group(1).strip()
        # Require an actual operation, not just a number.
        if not re.search(r"\d\s*[+\-*/%]|\*\*", expr):
            return None
        try:
            result = _safe_eval(expr)
        except (ValueError, SyntaxError, ZeroDivisionError):
            return None
        pretty = int(result) if isinstance(result, float) and result.is_integer() else result
        return f"{expr} = {pretty}"

    @registry.register("remember")
    def remember_plugin(text: str, memory=None, **_) -> str | None:
        match = re.match(r"(?i)^/?remember (?:that )?([\w ]+?) (?:is|=) (.+)$", text.strip())
        if match and memory is not None:
            key = match.group(1).strip().lower().replace(" ", "_")
            value = match.group(2).strip().rstrip(".")
            # Delegate to MemoryStore rather than re-inlining the schema --
            # this call site had drifted out of sync with the facts table and
            # raised on every fresh database.
            memory.set_fact(key, value)
            return f"Got it — I'll remember {match.group(1).strip()} is {value}."
        return None

    @registry.register("recall_facts")
    def facts_plugin(text: str, memory=None, **_) -> str | None:
        if re.search(r"(?i)\bwhat do you (?:know|remember) about me\b", text) and memory:
            facts = memory.all_facts()
            if not facts:
                return "Nothing yet! Tell me about yourself — your name, what you like, what you're building."
            lines = "; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in facts.items())
            return f"Here's what I remember — {lines}."
        return None

    @registry.register("curiosity")
    def curiosity_plugin(text: str, **_) -> str | None:
        """Trigger curiosity research when user explicitly asks."""
        if re.search(r"(?i)\b(?:research|look up|learn about|go find|go search|go read about)\s+(.+)", text):
            from ..curiosity.engine import CuriosityEngine
            from ..knowledge.engine import KnowledgeBase

            match = re.search(r"(?i)\b(?:research|look up|learn about|go find|go search|go read about)\s+(.+)", text)
            if match:
                topic = match.group(1).strip().rstrip(".?!")
                engine = _curiosity_engine or CuriosityEngine()
                episode = engine.research_topic(topic, background=True)
                return f"I'm researching \"{topic}\" now — I'll let you know when I find something. (episode {episode.episode_id})"
        return None

    @registry.register("what_i_learned")
    def learned_plugin(text: str, **_) -> str | None:
        """Show what Shaggoth has learned recently."""
        if re.search(r"(?i)\bwhat (?:did you|have you) learn(?:ed)?\b|\bwhat(?:'s| is) in (?:your )?knowledge\b|\bwhat do you know\b", text):
            from ..knowledge.engine import KnowledgeBase
            kb = KnowledgeBase()
            entries = kb.list_entries()
            if not entries:
                return "I haven't learned anything yet — tell me about something or ask me to research a topic!"
            recent = sorted(entries, key=lambda e: e.get("word_count", 0), reverse=True)[:5]
            lines = []
            for e in recent:
                lines.append(f"  {e['topic']} ({e['word_count']} words)")
            summary = "\n".join(lines)
            return f"I know about {len(entries)} topics so far:\n{summary}\n\nAsk me to research something new, or say 'teach me' to add knowledge directly."
        return None

    @registry.register("teach")
    def teach_plugin(text: str, **_) -> str | None:
        """User teaches Shaggoth directly — adds to knowledge base."""
        match = re.match(r"(?i)^/?teach (?:me |you )?(?:about )?(.+?)(?:\s*[-–—:]\s*(.+))?$", text.strip())
        if match:
            topic = match.group(1).strip().rstrip(".?!")
            content = match.group(2).strip() if match.group(2) else ""
            if not content:
                return f"What would you like me to know about {topic}? Say something like:\n  teach {topic} - <your explanation>"
            from ..knowledge.engine import KnowledgeBase
            kb = KnowledgeBase()
            path = kb.add_entry(topic, content)
            return f"Got it — I now know about {topic}. (saved to {path.name})"
        return None

    @registry.register("know_about")
    def know_about_plugin(text: str, **_) -> str | None:
        """Look up a specific topic in the knowledge base."""
        match = re.match(r"(?i)^what do you know about (.+?)\??$", text.strip())
        if match:
            topic_query = match.group(1).strip()
            from ..knowledge.engine import KnowledgeBase
            kb = KnowledgeBase()
            results = kb.query(topic_query, limit=3, min_score=0.1)
            if not results:
                return f"I don't know much about \"{topic_query}\" yet. Want me to research it?"
            lines = []
            for entry, score in results:
                snippet = entry.content[:200].strip()
                if len(entry.content) > 200:
                    snippet += "..."
                lines.append(f"**{entry.topic}** (relevance: {score:.2f}):\n{snippet}")
            return "\n\n".join(lines)
        return None

    @registry.register("wiki")
    def wiki_plugin(text: str, **_) -> str | None:
        """Fetch a Wikipedia article."""
        match = re.match(r"(?i)^/?wiki(?:pedia)?\s+(.+)$", text.strip())
        if match:
            query = match.group(1).strip()
            from ..curiosity.wikipedia import fetch_summary, search_wikipedia
            summary = fetch_summary(query)
            if summary:
                return f"**{query}** (Wikipedia):\n{summary}\n\nWant me to dig deeper into this?"
            results = search_wikipedia(query, max_results=3)
            if results:
                titles = ", ".join(r["title"] for r in results)
                return f"I couldn't find an exact article for \"{query}\", but did you mean: {titles}?"
            return f"I couldn't find anything on Wikipedia for \"{query}\"."
        return None

    return registry
