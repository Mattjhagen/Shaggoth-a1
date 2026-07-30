"""Tests for built-in plugins (plugins/builtin.py)."""
from __future__ import annotations

import re
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from shaggoth.plugins.builtin import _safe_eval, build_registry
from shaggoth.plugins import PluginRegistry


# ---------------------------------------------------------------------------
# _safe_eval
# ---------------------------------------------------------------------------

class TestSafeEval:
    def test_addition(self):
        assert _safe_eval("2 + 3") == 5

    def test_subtraction(self):
        assert _safe_eval("10 - 4") == 6

    def test_multiplication(self):
        assert _safe_eval("3 * 4") == 12

    def test_division(self):
        assert _safe_eval("10 / 4") == 2.5

    def test_modulo(self):
        assert _safe_eval("10 % 3") == 1

    def test_power(self):
        assert _safe_eval("2 ** 8") == 256

    def test_unary_minus(self):
        assert _safe_eval("-5") == -5

    def test_nested_expression(self):
        assert _safe_eval("(2 + 3) * 4") == 20

    def test_float_result(self):
        assert abs(_safe_eval("1 / 3") - 0.333) < 0.01

    def test_rejects_names(self):
        with pytest.raises(ValueError):
            _safe_eval("x + 1")

    def test_rejects_function_calls(self):
        with pytest.raises((ValueError, SyntaxError)):
            _safe_eval("__import__('os')")

    def test_rejects_attribute_access(self):
        with pytest.raises((ValueError, SyntaxError)):
            _safe_eval("os.system")

    def test_division_by_zero_raises(self):
        with pytest.raises(ZeroDivisionError):
            _safe_eval("1 / 0")


# ---------------------------------------------------------------------------
# PluginRegistry
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    def setup_method(self):
        self.reg = build_registry()

    # -- time plugin ----------------------------------------------------------

    def test_time_plugin_matches_what_time(self):
        result = self.reg.dispatch("what time is it")
        assert result is not None
        assert ":" in result  # HH:MM

    def test_time_plugin_matches_current_time(self):
        result = self.reg.dispatch("current time please")
        assert result is not None

    def test_time_plugin_matches_todays_date(self):
        result = self.reg.dispatch("today's date")
        assert result is not None

    def test_time_plugin_case_insensitive(self):
        assert self.reg.dispatch("WHAT TIME IS IT") is not None

    def test_time_plugin_response_has_date(self):
        result = self.reg.dispatch("what time is it")
        current_year = str(datetime.now().year)
        assert current_year in result

    # -- calculator plugin ----------------------------------------------------

    def test_calc_simple_addition(self):
        result = self.reg.dispatch("2 + 3")
        assert result is not None
        assert "5" in result

    def test_calc_what_is_prefix(self):
        result = self.reg.dispatch("what is 2 + 3")
        assert result is not None
        assert "5" in result

    def test_calc_whats_prefix(self):
        result = self.reg.dispatch("what's 2 + 3?")
        assert result is not None
        assert "5" in result

    def test_calc_multiplication(self):
        result = self.reg.dispatch("4 * 5")
        assert result is not None
        assert "20" in result

    def test_calc_division(self):
        result = self.reg.dispatch("10 / 4")
        assert result is not None
        assert "2.5" in result

    def test_calc_power(self):
        result = self.reg.dispatch("2 ** 10")
        assert result is not None
        assert "1024" in result

    def test_calc_integer_result_shows_no_decimal(self):
        result = self.reg.dispatch("3 + 3")
        assert result is not None
        assert "6" in result
        assert "6.0" not in result

    def test_calc_bare_number_not_matched(self):
        # Single number without an operator should not match
        assert self.reg.dispatch("42") is None

    def test_calc_returns_none_for_non_math(self):
        assert self.reg.dispatch("hello world") is None

    # -- remember plugin -------------------------------------------------------

    def test_remember_stores_fact(self):
        memory = MagicMock()
        result = self.reg.dispatch("remember that favorite_color is blue", memory=memory)
        assert result is not None
        memory.set_fact.assert_called_once()

    def test_remember_with_equals(self):
        memory = MagicMock()
        result = self.reg.dispatch("remember name = Alice", memory=memory)
        assert result is not None
        memory.set_fact.assert_called_once()

    def test_remember_without_memory_returns_none(self):
        result = self.reg.dispatch("remember test = value")
        assert result is None

    def test_remember_response_echoes_value(self):
        memory = MagicMock()
        result = self.reg.dispatch("remember hobby is coding", memory=memory)
        assert "coding" in result

    def test_remember_case_insensitive(self):
        memory = MagicMock()
        result = self.reg.dispatch("REMEMBER name is Bob", memory=memory)
        assert result is not None

    # -- recall_facts plugin ---------------------------------------------------

    def test_recall_with_facts(self):
        memory = MagicMock()
        memory.all_facts.return_value = {"name": "Alice", "hobby": "hiking"}
        result = self.reg.dispatch("what do you know about me", memory=memory)
        assert result is not None
        assert "Alice" in result
        assert "hiking" in result

    def test_recall_empty_facts(self):
        memory = MagicMock()
        memory.all_facts.return_value = {}
        result = self.reg.dispatch("what do you remember about me", memory=memory)
        assert result is not None
        assert "Nothing" in result or "nothing" in result.lower()

    def test_recall_without_memory_returns_none(self):
        # "remember" only matches recall_facts, not what_i_learned
        result = self.reg.dispatch("what do you remember about me")
        assert result is None

    def test_recall_non_matching_text_returns_none(self):
        memory = MagicMock()
        result = self.reg.dispatch("hello there", memory=memory)
        assert result is None

    # -- plugin isolation -----------------------------------------------------

    def test_first_matching_plugin_wins(self):
        # 'what time is it' should match time, not calculator
        result = self.reg.dispatch("what time is it")
        assert result is not None
        # Should have a time format, not arithmetic
        assert re.search(r"\d{1,2}:\d{2}", result)

    def test_no_match_returns_none(self):
        assert self.reg.dispatch("xyzzy frobnicator") is None

    # -- curiosity plugin -------------------------------------------------------

    def test_curiosity_matches_imperative_command(self):
        result = self.reg.dispatch("research quantum computing")
        assert result is not None
        assert "quantum computing" in result

    def test_curiosity_does_not_match_embedded_learn_about(self):
        """'how do plants learn about ...' is a question, not a command."""
        assert self.reg.dispatch("how do plants learn about their environment") is None

    def test_curiosity_does_not_match_embedded_look_up(self):
        """'why do people look up at the sky' is a question, not a command."""
        assert self.reg.dispatch("why do people look up at the sky") is None

    # -- what_i_learned plugin --------------------------------------------------

    def test_what_i_learned_matches_bare_form(self):
        result = self.reg.dispatch("what do you know")
        assert result is not None

    def test_what_i_learned_does_not_intercept_know_about(self):
        """'what do you know about X' must reach know_about, not what_i_learned."""
        result = self.reg.dispatch("what do you know about photosynthesis")
        # If know_about fires, it tries the KB and returns "I don't know much"
        # or a KB result. If what_i_learned fires, it returns a topics listing.
        # Either way it should not be the generic listing.
        if result is not None:
            assert "topics so far" not in result
