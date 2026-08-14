"""Tests for the M4 tool-use loop: ToolRegistry, built-in tools, and
the generate_with_tools integration with OpenAIModel and DialogueEngine."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from shaggoth.tools import Tool, ToolRegistry, ToolResult
from shaggoth.tools.builtin import (
    _calculator,
    _get_current_time,
    _make_knowledge_search,
    _make_memory_lookup,
    build_tool_registry,
)


# ---------------------------------------------------------------------------
# ToolRegistry unit tests
# ---------------------------------------------------------------------------

class TestToolRegistry:
    def test_add_and_get(self):
        reg = ToolRegistry()
        tool = Tool(name="echo", description="echo", parameters={}, func=lambda: "hi")
        reg.add(tool)
        assert reg.get("echo") is tool
        assert reg.get("missing") is None

    def test_names(self):
        reg = ToolRegistry()
        reg.add(Tool(name="a", description="", parameters={}, func=lambda: ""))
        reg.add(Tool(name="b", description="", parameters={}, func=lambda: ""))
        assert reg.names() == ["a", "b"]

    def test_len(self):
        reg = ToolRegistry()
        assert len(reg) == 0
        reg.add(Tool(name="x", description="", parameters={}, func=lambda: ""))
        assert len(reg) == 1

    def test_to_openai_tools_format(self):
        reg = ToolRegistry()
        reg.add(Tool(
            name="calc",
            description="Calculate",
            parameters={"type": "object", "properties": {"expr": {"type": "string"}}},
            func=lambda expr: str(eval(expr)),
        ))
        result = reg.to_openai_tools()
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "calc"
        assert "properties" in result[0]["function"]["parameters"]

    def test_execute_known_tool(self):
        reg = ToolRegistry()
        reg.add(Tool(name="greet", description="", parameters={},
                      func=lambda name: f"Hello {name}!"))
        result = reg.execute("greet", {"name": "Matt"})
        assert result.output == "Hello Matt!"
        assert result.error is None

    def test_execute_unknown_tool(self):
        reg = ToolRegistry()
        result = reg.execute("missing", {})
        assert result.error is not None
        assert "Unknown" in result.error

    def test_execute_handles_exception(self):
        def bad(**_):
            raise ValueError("boom")
        reg = ToolRegistry()
        reg.add(Tool(name="bad", description="", parameters={}, func=bad))
        result = reg.execute("bad", {})
        assert result.error is not None
        assert "boom" in result.error

    def test_execute_tool_calls_batch(self):
        reg = ToolRegistry()
        reg.add(Tool(name="add", description="", parameters={},
                      func=lambda a, b: str(int(a) + int(b))))
        calls = [
            {"function": {"name": "add", "arguments": '{"a": "3", "b": "4"}'}},
            {"function": {"name": "add", "arguments": '{"a": "10", "b": "20"}'}},
        ]
        results = reg.execute_tool_calls(calls)
        assert len(results) == 2
        assert results[0].output == "7"
        assert results[1].output == "30"

    def test_execute_tool_calls_malformed_json(self):
        reg = ToolRegistry()
        reg.add(Tool(name="noop", description="", parameters={}, func=lambda: "ok"))
        calls = [{"function": {"name": "noop", "arguments": "not json"}}]
        results = reg.execute_tool_calls(calls)
        assert len(results) == 1
        assert results[0].output == "ok"


# ---------------------------------------------------------------------------
# Built-in tool unit tests
# ---------------------------------------------------------------------------

class TestBuiltinTools:
    def test_calculator_basic_arithmetic(self):
        assert _calculator("2 + 3") == "5"
        assert _calculator("10 * 5") == "50"
        assert _calculator("100 / 4") == "25"

    def test_calculator_complex_expression(self):
        assert _calculator("(15 * 7) + 23") == "128"

    def test_calculator_rejects_non_arithmetic(self):
        with pytest.raises((ValueError, SyntaxError)):
            _calculator("import os")

    def test_get_current_time_returns_string(self):
        result = _get_current_time()
        assert isinstance(result, str)
        assert len(result) > 10

    def test_knowledge_search_no_kb(self):
        func = _make_knowledge_search(None)
        assert "No knowledge base" in func(query="anything")

    def test_knowledge_search_with_kb(self):
        from shaggoth.knowledge.engine import KnowledgeBase
        with tempfile.TemporaryDirectory() as td:
            kb = KnowledgeBase(td)
            kb.add_entry("Photosynthesis",
                         "Photosynthesis is how plants convert light into energy. " * 10)
            func = _make_knowledge_search(kb)
            result = func(query="photosynthesis")
            assert "Photosynthesis" in result

    def test_knowledge_search_no_results(self):
        from shaggoth.knowledge.engine import KnowledgeBase
        with tempfile.TemporaryDirectory() as td:
            kb = KnowledgeBase(td)
            func = _make_knowledge_search(kb)
            result = func(query="xyznonexistent")
            assert "No knowledge found" in result

    def test_memory_lookup_no_store(self):
        func = _make_memory_lookup(None)
        assert "No memory store" in func(query="anything")

    def test_memory_lookup_with_facts(self):
        from shaggoth.memory import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            ms = MemoryStore(str(Path(td) / "m.db"))
            ms.set_fact("name", "Matt", confidence=1.0, source="user")
            func = _make_memory_lookup(ms)
            result = func(query="name")
            assert "Matt" in result

    def test_memory_lookup_all_facts(self):
        from shaggoth.memory import MemoryStore
        with tempfile.TemporaryDirectory() as td:
            ms = MemoryStore(str(Path(td) / "m.db"))
            ms.set_fact("city", "Portland", confidence=0.8, source="pattern")
            func = _make_memory_lookup(ms)
            result = func(query="info")
            assert "Portland" in result

    def test_build_tool_registry_returns_registry(self):
        reg = build_tool_registry()
        assert isinstance(reg, ToolRegistry)
        assert len(reg) >= 4
        assert "calculator" in reg.names()
        assert "get_current_time" in reg.names()
        assert "knowledge_search" in reg.names()
        assert "memory_lookup" in reg.names()


# ---------------------------------------------------------------------------
# ToolLoopResult
# ---------------------------------------------------------------------------

class TestToolLoopResult:
    def test_dataclass_fields(self):
        from shaggoth.models.openai_model import ToolLoopResult
        r = ToolLoopResult(text="answer", tool_calls=[], iterations=2)
        assert r.text == "answer"
        assert r.iterations == 2

    def test_defaults(self):
        from shaggoth.models.openai_model import ToolLoopResult
        r = ToolLoopResult(text="x")
        assert r.tool_calls == []
        assert r.iterations == 1


# ---------------------------------------------------------------------------
# generate_with_tools (mocked OpenAI client)
# ---------------------------------------------------------------------------

class TestGenerateWithTools:
    def _make_model(self):
        from shaggoth.models.openai_model import OpenAIModel
        model = OpenAIModel(api_key="test-key")
        return model

    def test_no_tools_falls_back_to_generate_chat(self):
        model = self._make_model()
        with patch.object(model, "generate_chat", return_value="plain answer") as mock_gc:
            result = model.generate_with_tools(
                user_message="hello",
                tools=None,
            )
        assert result.text == "plain answer"
        assert result.tool_calls == []
        mock_gc.assert_called_once()

    def test_empty_registry_falls_back_to_generate_chat(self):
        model = self._make_model()
        empty_reg = ToolRegistry()
        with patch.object(model, "generate_chat", return_value="plain") as mock_gc:
            result = model.generate_with_tools(
                user_message="hello",
                tools=empty_reg,
            )
        assert result.text == "plain"
        mock_gc.assert_called_once()

    def test_tool_loop_single_call(self):
        model = self._make_model()

        reg = ToolRegistry()
        reg.add(Tool(name="calculator", description="calc", parameters={},
                      func=lambda expression: "42"))

        tc_obj = MagicMock()
        tc_obj.id = "call_1"
        tc_obj.function.name = "calculator"
        tc_obj.function.arguments = '{"expression": "6 * 7"}'

        tool_response = MagicMock()
        tool_response.choices = [MagicMock()]
        tool_response.choices[0].finish_reason = "tool_calls"
        tool_response.choices[0].message.tool_calls = [tc_obj]
        tool_response.choices[0].message.content = None

        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].finish_reason = "stop"
        final_response.choices[0].message.tool_calls = None
        final_response.choices[0].message.content = "6 times 7 is 42."

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [tool_response, final_response]
        model._client = mock_client

        result = model.generate_with_tools(
            user_message="what is 6 times 7?",
            tools=reg,
        )
        assert result.text == "6 times 7 is 42."
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "calculator"
        assert result.tool_calls[0].output == "42"
        assert result.iterations == 2

    def test_tool_loop_no_tool_calls(self):
        model = self._make_model()
        reg = ToolRegistry()
        reg.add(Tool(name="calc", description="", parameters={}, func=lambda: ""))

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].finish_reason = "stop"
        response.choices[0].message.tool_calls = None
        response.choices[0].message.content = "Direct answer."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = response
        model._client = mock_client

        result = model.generate_with_tools(
            user_message="hello",
            tools=reg,
        )
        assert result.text == "Direct answer."
        assert len(result.tool_calls) == 0
        assert result.iterations == 1

    def test_tool_loop_respects_max_iterations(self):
        model = self._make_model()
        reg = ToolRegistry()
        reg.add(Tool(name="loop", description="", parameters={}, func=lambda: "result"))

        tc_obj = MagicMock()
        tc_obj.id = "call_loop"
        tc_obj.function.name = "loop"
        tc_obj.function.arguments = "{}"

        loop_response = MagicMock()
        loop_response.choices = [MagicMock()]
        loop_response.choices[0].finish_reason = "tool_calls"
        loop_response.choices[0].message.tool_calls = [tc_obj]
        loop_response.choices[0].message.content = None

        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.content = "Finally done."

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            loop_response, loop_response, final_response,
        ]
        model._client = mock_client

        result = model.generate_with_tools(
            user_message="loop",
            tools=reg,
            max_iterations=2,
        )
        assert result.iterations == 2
        assert len(result.tool_calls) == 2


# ---------------------------------------------------------------------------
# DialogueEngine integration with tools
# ---------------------------------------------------------------------------

class TestDialogueEngineToolIntegration:
    def test_engine_creates_default_tool_registry(self):
        from shaggoth.dialogue.engine import DialogueEngine
        engine = DialogueEngine()
        assert isinstance(engine.tools, ToolRegistry)
        assert len(engine.tools) >= 4

    def test_engine_accepts_custom_tool_registry(self):
        from shaggoth.dialogue.engine import DialogueEngine
        custom = ToolRegistry()
        custom.add(Tool(name="custom", description="", parameters={}, func=lambda: "ok"))
        engine = DialogueEngine(tools=custom)
        assert engine.tools is custom
        assert "custom" in engine.tools.names()

    def test_reply_has_tools_used_field(self):
        from shaggoth.dialogue.engine import Reply
        r = Reply(text="test", source="model")
        assert hasattr(r, "tools_used")
        assert r.tools_used == []

    def test_respond_uses_tools_when_gpt_configured(self):
        from shaggoth.dialogue.engine import DialogueEngine
        from shaggoth.memory import MemoryStore
        from shaggoth.models.openai_model import OpenAIModel, ToolLoopResult

        mock_model = MagicMock(spec=OpenAIModel)
        mock_model.configured = True
        mock_model.is_trained.return_value = True
        mock_model.generate_chat.return_value = "Direct answer."
        mock_model.generate_with_tools.return_value = ToolLoopResult(
            text="Calculated: 42",
            tool_calls=[ToolResult(
                tool_name="calculator",
                arguments={"expression": "6*7"},
                output="42",
            )],
            iterations=2,
        )

        with tempfile.TemporaryDirectory() as td:
            engine = DialogueEngine(
                memory=MemoryStore(str(Path(td) / "m.db")),
                model=mock_model,
                seed=1,
            )
            reply = engine.respond("what is 6 times 7", session_id="s1")
            assert reply.source in ("model", "fallback")
            mock_model.generate_with_tools.assert_called()
            assert "tool: calculator" in str(reply.reasoning)


# ---------------------------------------------------------------------------
# OpenAI tool serialization
# ---------------------------------------------------------------------------

class TestOpenAIToolSerialization:
    def test_full_registry_serializes(self):
        reg = build_tool_registry()
        tools = reg.to_openai_tools()
        assert len(tools) >= 4
        names = {t["function"]["name"] for t in tools}
        assert "calculator" in names
        assert "get_current_time" in names
        assert "knowledge_search" in names
        assert "memory_lookup" in names
        for t in tools:
            assert t["type"] == "function"
            assert "description" in t["function"]
            assert "parameters" in t["function"]
