"""Built-in tools that the model can invoke during generation.

Each tool wraps an existing Shaggoth subsystem — the calculator reuses
the safe-eval from the plugin, the knowledge tool queries the knowledge
base, and so on.  Tools are constructed with live references to the
engine's subsystems so they operate on the same state.
"""

from __future__ import annotations

import ast
import operator
import re
from datetime import datetime
from typing import Any

from . import Tool, ToolRegistry

# --------------------------------------------------------------------------
# Arithmetic (reused from plugins/builtin.py)
# --------------------------------------------------------------------------

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

_MAX_EXPONENT = 1000
_MAX_AST_DEPTH = 20
_MAX_RESULT_BITS = 10_000


def _safe_eval(expr: str) -> float:
    def walk(node, depth=0):
        if depth > _MAX_AST_DEPTH:
            raise ValueError("expression too deeply nested")
        if isinstance(node, ast.Expression):
            return walk(node.body, depth + 1)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left = walk(node.left, depth + 1)
            right = walk(node.right, depth + 1)
            if isinstance(node.op, ast.Pow) and abs(right) > _MAX_EXPONENT:
                raise ValueError(f"exponent too large (max {_MAX_EXPONENT})")
            result = _OPS[type(node.op)](left, right)
            if isinstance(result, int) and result.bit_length() > _MAX_RESULT_BITS:
                raise ValueError("intermediate result too large")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](walk(node.operand, depth + 1))
        raise ValueError("unsupported expression")
    return walk(ast.parse(expr, mode="eval"))


def _calculator(expression: str) -> str:
    result = _safe_eval(expression)
    pretty = int(result) if isinstance(result, float) and result.is_integer() else result
    return str(pretty)


# --------------------------------------------------------------------------
# Clock
# --------------------------------------------------------------------------

def _get_current_time(**_: Any) -> str:
    now = datetime.now()
    return now.strftime("%H:%M on %A, %B %d, %Y")


# --------------------------------------------------------------------------
# Knowledge lookup
# --------------------------------------------------------------------------

def _make_knowledge_search(knowledge_base):
    def _knowledge_search(query: str) -> str:
        if knowledge_base is None:
            return "No knowledge base available."
        hits = knowledge_base.query(query, limit=3, min_score=0.2)
        if not hits:
            return f"No knowledge found for: {query}"
        parts = []
        for entry, score in hits:
            snippet = knowledge_base.best_chunks(entry, query)
            if len(snippet) > 400:
                snippet = snippet[:400].rstrip() + "..."
            parts.append(f"[{entry.topic}] (score {score:.2f}): {snippet}")
        return "\n\n".join(parts)
    return _knowledge_search


# --------------------------------------------------------------------------
# Memory recall
# --------------------------------------------------------------------------

def _make_memory_lookup(memory_store):
    def _memory_lookup(query: str) -> str:
        if memory_store is None:
            return "No memory store available."
        parts = []
        facts = memory_store.all_facts()
        if facts:
            matching = {
                k: v for k, v in facts.items()
                if any(w in k.lower() for w in query.lower().split())
            }
            if matching:
                lines = "; ".join(f"{k}: {v}" for k, v in matching.items())
                parts.append(f"Matching facts: {lines}")
            elif len(query.split()) <= 2:
                lines = "; ".join(f"{k}: {v}" for k, v in list(facts.items())[:10])
                parts.append(f"All known facts: {lines}")
        try:
            prefs = memory_store.all_preferences()
            if prefs:
                for cat, entries in prefs.items():
                    if isinstance(entries, dict) and entries:
                        items = "; ".join(f"{k}: {v}" for k, v in entries.items())
                        parts.append(f"Preferences ({cat}): {items}")
        except (AttributeError, TypeError):
            pass
        if not parts:
            return f"No stored information found for: {query}"
        return "\n".join(parts)
    return _memory_lookup


# --------------------------------------------------------------------------
# Registry builder
# --------------------------------------------------------------------------

def build_tool_registry(
    knowledge_base=None,
    memory_store=None,
) -> ToolRegistry:
    """Build a ToolRegistry wired to the engine's live subsystems."""
    registry = ToolRegistry()

    registry.add(Tool(
        name="calculator",
        description=(
            "Evaluate a mathematical expression. Use this for any arithmetic "
            "the user asks about — addition, subtraction, multiplication, "
            "division, exponents, modulo. Pass a valid Python arithmetic "
            "expression (numbers and operators only, no variables)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "The arithmetic expression to evaluate, e.g. '(15 * 7) + 23'",
                },
            },
            "required": ["expression"],
        },
        func=_calculator,
    ))

    registry.add(Tool(
        name="get_current_time",
        description="Get the current date and time.",
        parameters={"type": "object", "properties": {}},
        func=_get_current_time,
    ))

    registry.add(Tool(
        name="knowledge_search",
        description=(
            "Search Shaggoth's knowledge base for information on a topic. "
            "Use this when the user asks about something and you want to "
            "check if there's a relevant article or research note."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query, e.g. 'photosynthesis' or 'how do rockets work'",
                },
            },
            "required": ["query"],
        },
        func=_make_knowledge_search(knowledge_base),
    ))

    registry.add(Tool(
        name="memory_lookup",
        description=(
            "Look up what Shaggoth remembers about the user — facts they've "
            "shared, preferences, projects. Use this when the user asks "
            "'what do you know about me' or references something personal."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to look up, e.g. 'name' or 'preferences' or 'projects'",
                },
            },
            "required": ["query"],
        },
        func=_make_memory_lookup(memory_store),
    ))

    return registry
