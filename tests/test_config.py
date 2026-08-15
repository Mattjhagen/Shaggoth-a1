"""Tests for shaggoth/config.py — load_settings() resilience."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from shaggoth.config import DEFAULT_SETTINGS, load_settings


class TestLoadSettings:
    def test_returns_defaults_when_no_file(self, tmp_path):
        result = load_settings(tmp_path / "nonexistent.json")
        assert result["bot_name"] == DEFAULT_SETTINGS["bot_name"]
        assert result["server_port"] == DEFAULT_SETTINGS["server_port"]

    def test_overrides_defaults_from_valid_file(self, tmp_path):
        cfg = tmp_path / "settings.json"
        cfg.write_text(json.dumps({"bot_name": "MyBot", "server_port": 9999}))
        result = load_settings(cfg)
        assert result["bot_name"] == "MyBot"
        assert result["server_port"] == 9999
        # Other defaults still present
        assert "db_path" in result

    def test_corrupt_json_falls_back_to_defaults(self, tmp_path):
        cfg = tmp_path / "settings.json"
        cfg.write_text("{bad json")
        result = load_settings(cfg)
        # Must not raise; must return defaults
        assert result["bot_name"] == DEFAULT_SETTINGS["bot_name"]

    def test_empty_file_falls_back_to_defaults(self, tmp_path):
        cfg = tmp_path / "settings.json"
        cfg.write_text("")
        result = load_settings(cfg)
        assert result["bot_name"] == DEFAULT_SETTINGS["bot_name"]

    def test_partial_override_keeps_other_defaults(self, tmp_path):
        cfg = tmp_path / "settings.json"
        cfg.write_text(json.dumps({"bot_name": "Partial"}))
        result = load_settings(cfg)
        assert result["bot_name"] == "Partial"
        assert result["server_port"] == DEFAULT_SETTINGS["server_port"]

    def test_deep_copy_of_defaults(self, tmp_path):
        """Mutating the returned dict must not affect a second call."""
        r1 = load_settings(tmp_path / "missing.json")
        r1["bot_name"] = "mutated"
        r2 = load_settings(tmp_path / "missing.json")
        assert r2["bot_name"] == DEFAULT_SETTINGS["bot_name"]
