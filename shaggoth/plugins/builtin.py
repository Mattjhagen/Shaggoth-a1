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
            memory.db.execute(
                "INSERT INTO facts (key, value, ts) VALUES (?, ?, strftime('%s','now')) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, ts = excluded.ts",
                (key, value),
            )
            memory.db.commit()
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
                engine = CuriosityEngine()
                episode = engine.research_topic(topic, background=True)
                return f"I'm researching \"{topic}\" now — I'll let you know when I find something. (episode {episode.episode_id})"
        return None

    return registry
