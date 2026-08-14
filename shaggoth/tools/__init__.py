"""Tool system — model-selected actions during generation.

Unlike plugins (checked before generation, first-match-wins), tools are
offered to the language model as callable functions.  The model decides
which tool to invoke, the harness executes it, and the result is fed
back so the model can incorporate it into its reply.

A tool is a function with a JSON-schema description.  The registry
collects them and serialises the catalogue for the OpenAI
function-calling API.

    from shaggoth.tools import ToolRegistry, Tool

    registry = ToolRegistry()
    registry.add(Tool(
        name="calculator",
        description="Evaluate an arithmetic expression.",
        parameters={
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
        func=lambda expression: str(eval_safe(expression)),
    ))
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)

_MAX_ITERATIONS = 5


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    func: Callable[..., str]


@dataclass
class ToolResult:
    tool_name: str
    arguments: dict[str, Any]
    output: str
    error: str | None = None


class ToolRegistry:
    """Collect tools and convert them to OpenAI function-calling format."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)

    def to_openai_tools(self) -> list[dict[str, Any]]:
        """Serialise every tool as an OpenAI ``tools`` entry."""
        out = []
        for tool in self._tools.values():
            out.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return out

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Run a tool by name and return a structured result."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_name=name,
                arguments=arguments,
                output="",
                error=f"Unknown tool: {name}",
            )
        try:
            output = tool.func(**arguments)
            return ToolResult(tool_name=name, arguments=arguments, output=str(output))
        except Exception as exc:  # noqa: BLE001
            log.warning("[tools] %s failed: %s", name, exc)
            return ToolResult(
                tool_name=name,
                arguments=arguments,
                output="",
                error=str(exc),
            )

    def execute_tool_calls(
        self, tool_calls: list[dict[str, Any]],
    ) -> list[ToolResult]:
        """Execute a batch of tool calls returned by the model."""
        results = []
        for call in tool_calls:
            func_info = call.get("function", {})
            name = func_info.get("name", "")
            raw_args = func_info.get("arguments", "{}")
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                arguments = {}
            results.append(self.execute(name, arguments))
        return results


__all__ = ["Tool", "ToolRegistry", "ToolResult"]
