"""Configuration loading and project paths.

All configuration is plain JSON so the platform stays dependency-free and the
files stay hand-editable. Paths resolve relative to the repository root by
default but every component accepts explicit paths, so the package also works
embedded inside another project (its role as a base platform).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Repo root = parent of the package directory. Overridable for embedding.
ROOT = Path(os.environ.get("SHAGGOTH_ROOT", Path(__file__).resolve().parent.parent))

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

DEFAULT_SETTINGS: dict[str, Any] = {
    "bot_name": "Shaggoth",
    "model": "auto",
    "api_key": "",
    "db_path": str(DATA_DIR / "shaggoth.db"),
    "guardrails_path": str(CONFIG_DIR / "guardrails.json"),
    "markov_model_path": str(DATA_DIR / "markov_model.json"),
    "memory_recall_threshold": 0.35,
    # Default dialogue mode: "no_drift" (knowledge and patterns only) or
    # "drift" (also allows Markov generation, topic callbacks, and tangents).
    # Individual /chat requests may override this per message.
    "dialogue_mode": "no_drift",
    "server_host": "127.0.0.1",
    "server_port": 8420,
    # Onboard training agents. Off by default: they consume the same CPU that
    # answers chat, so an existing deployment that picks up this key keeps
    # behaving exactly as it did. See shaggoth/agents/__init__.py for the
    # per-agent cadences this expands to.
    "agents": {"enabled": False},
}


def load_settings(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load settings.json, falling back to defaults for missing keys."""
    settings = dict(DEFAULT_SETTINGS)
    candidate = Path(path) if path else CONFIG_DIR / "settings.json"
    if candidate.exists():
        with open(candidate, encoding="utf-8") as fh:
            settings.update(json.load(fh))
    return settings


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
