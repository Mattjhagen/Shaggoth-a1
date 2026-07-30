"""Tests for PersonalityEngine (personality/engine.py)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from shaggoth.personality.engine import DEFAULT_PERSONALITY, PersonalityEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _engine(tmp_path: Path) -> PersonalityEngine:
    p = tmp_path / "personality.json"
    return PersonalityEngine(path=p)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_file_when_missing(self, tmp_path):
        p = tmp_path / "personality.json"
        PersonalityEngine(path=p)
        assert p.exists()

    def test_defaults_applied_when_no_file(self, tmp_path):
        eng = _engine(tmp_path)
        assert eng.config["version"] == 1
        assert "traits" in eng.config

    def test_loads_existing_file(self, tmp_path):
        p = tmp_path / "personality.json"
        p.write_text(json.dumps({"traits": ["sneaky", "clever"]}))
        eng = PersonalityEngine(path=p)
        assert "sneaky" in eng.config["traits"]

    def test_missing_keys_filled_with_defaults(self, tmp_path):
        p = tmp_path / "personality.json"
        p.write_text(json.dumps({"traits": ["brave"]}))
        eng = PersonalityEngine(path=p)
        # 'backstory' not in file, but should be pulled from defaults
        assert "backstory" in eng.config


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

class TestProperties:
    def test_greeting_returns_configured_value(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"greeting": "Sup."}))
        eng = PersonalityEngine(path=p)
        assert eng.greeting == "Sup."

    def test_greeting_falls_back_to_default(self, tmp_path):
        eng = _engine(tmp_path)
        assert eng.greeting == DEFAULT_PERSONALITY["greeting"]

    def test_backstory_returns_configured_value(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"backstory": "I was born in a server rack."}))
        eng = PersonalityEngine(path=p)
        assert "server rack" in eng.backstory


# ---------------------------------------------------------------------------
# trait_prompt
# ---------------------------------------------------------------------------

class TestTraitPrompt:
    def test_includes_traits(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"traits": ["brilliant", "impatient"]}))
        eng = PersonalityEngine(path=p)
        prompt = eng.trait_prompt()
        assert "brilliant" in prompt
        assert "impatient" in prompt

    def test_includes_speaking_style(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"speaking_style": "extremely terse"}))
        eng = PersonalityEngine(path=p)
        assert "extremely terse" in eng.trait_prompt()

    def test_includes_mood(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"mood": "irritable"}))
        eng = PersonalityEngine(path=p)
        assert "irritable" in eng.trait_prompt()

    def test_empty_traits_produces_minimal_prompt(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"traits": [], "speaking_style": "", "mood": ""}))
        eng = PersonalityEngine(path=p)
        prompt = eng.trait_prompt()
        assert isinstance(prompt, str)

    def test_returns_string(self, tmp_path):
        eng = _engine(tmp_path)
        assert isinstance(eng.trait_prompt(), str)

    def test_includes_backstory(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"backstory": "I run on a toaster."}))
        eng = PersonalityEngine(path=p)
        assert "toaster" in eng.trait_prompt()

    def test_includes_interests(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"interests": ["chess", "rockets"]}))
        eng = PersonalityEngine(path=p)
        prompt = eng.trait_prompt()
        assert "chess" in prompt
        assert "rockets" in prompt

    def test_includes_values(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"values": ["honesty", "growth"]}))
        eng = PersonalityEngine(path=p)
        prompt = eng.trait_prompt()
        assert "honesty" in prompt

    def test_exclude_backstory(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"backstory": "I run on a toaster.", "traits": ["fast"]}))
        eng = PersonalityEngine(path=p)
        prompt = eng.trait_prompt(include_backstory=False)
        assert "toaster" not in prompt
        assert "fast" in prompt


# ---------------------------------------------------------------------------
# random_quirk
# ---------------------------------------------------------------------------

class TestRandomQuirk:
    def test_none_when_no_quirks(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"quirks": []}))
        eng = PersonalityEngine(path=p)
        assert eng.random_quirk() is None

    def test_returns_quirk_string(self, tmp_path):
        p = tmp_path / "p.json"
        p.write_text(json.dumps({"quirks": ["hates small talk", "loves recursion"]}))
        eng = PersonalityEngine(path=p)
        quirk = eng.random_quirk()
        assert quirk in ("hates small talk", "loves recursion")

    def test_default_engine_has_no_quirks(self, tmp_path):
        # Default config has empty quirks list
        eng = _engine(tmp_path)
        assert eng.random_quirk() is None


# ---------------------------------------------------------------------------
# save / reload
# ---------------------------------------------------------------------------

class TestSaveReload:
    def test_save_writes_json(self, tmp_path):
        eng = _engine(tmp_path)
        eng.config["mood"] = "ecstatic"
        eng.save()
        loaded = json.loads((tmp_path / "personality.json").read_text())
        assert loaded["mood"] == "ecstatic"

    def test_maybe_reload_returns_false_when_no_change(self, tmp_path):
        eng = _engine(tmp_path)
        assert not eng.maybe_reload()

    def test_maybe_reload_returns_true_after_file_change(self, tmp_path):
        p = tmp_path / "personality.json"
        eng = PersonalityEngine(path=p)
        # Write a modified file with a different mtime
        time.sleep(0.01)
        p.write_text(json.dumps({"traits": ["grumpy"]}))
        import os
        os.utime(p, (time.time() + 1, time.time() + 1))
        assert eng.maybe_reload()

    def test_maybe_reload_updates_config(self, tmp_path):
        p = tmp_path / "personality.json"
        eng = PersonalityEngine(path=p)
        import os
        p.write_text(json.dumps({"mood": "melancholy"}))
        os.utime(p, (time.time() + 1, time.time() + 1))
        eng.maybe_reload()
        assert eng.config["mood"] == "melancholy"

    def test_maybe_reload_false_when_file_missing(self, tmp_path):
        p = tmp_path / "personality.json"
        eng = PersonalityEngine(path=p)
        p.unlink()
        assert not eng.maybe_reload()


# ---------------------------------------------------------------------------
# as_dict
# ---------------------------------------------------------------------------

class TestAsDict:
    def test_as_dict_returns_dict(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.as_dict()
        assert isinstance(d, dict)

    def test_as_dict_is_copy(self, tmp_path):
        eng = _engine(tmp_path)
        d = eng.as_dict()
        d["mood"] = "modified"
        assert eng.config.get("mood") != "modified"
