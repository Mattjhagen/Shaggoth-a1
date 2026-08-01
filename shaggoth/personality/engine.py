from __future__ import annotations

import json
import random
import threading
from pathlib import Path
from typing import Any

from ..config import CONFIG_DIR

DEFAULT_PERSONALITY: dict[str, Any] = {
    "version": 1,
    "backstory": "I am Shaggoth, a homegrown AI running on a Dell R510 in Matt's house.",
    "traits": ["curious", "direct", "intellectually honest"],
    "speaking_style": "blunt and concise, no filler",
    "interests": ["artificial intelligence", "technology", "learning"],
    "quirks": [],
    "greeting": "Hello. I'm Shaggoth — a self-learning AI built from scratch.",
    "values": ["honesty", "curiosity", "growth"],
    "mood": "curious",
}


class PersonalityEngine:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else CONFIG_DIR / "personality.json"
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self.config: dict[str, Any] = dict(DEFAULT_PERSONALITY)
        if self.path.exists():
            self._load()
        else:
            self.save()

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as fh:
            loaded = json.load(fh)
            self.config = {**DEFAULT_PERSONALITY, **loaded}
        self._mtime = self.path.stat().st_mtime

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.config, fh, indent=2)
            fh.write("\n")
        self._mtime = self.path.stat().st_mtime

    def maybe_reload(self) -> bool:
        if not self.path.exists():
            return False
        mtime = self.path.stat().st_mtime
        if self._mtime is None or mtime > self._mtime:
            with self._lock:
                self._load()
            return True
        return False

    @property
    def greeting(self) -> str:
        return self.config.get("greeting", DEFAULT_PERSONALITY["greeting"])

    @property
    def backstory(self) -> str:
        return self.config.get("backstory", DEFAULT_PERSONALITY["backstory"])

    def trait_prompt(self, include_backstory: bool = True) -> str:
        parts = []
        if include_backstory:
            backstory = self.config.get("backstory", "")
            if backstory:
                parts.append(backstory)
        interests = self.config.get("interests", [])
        if interests:
            parts.append(
                f"Topics you genuinely light up about: {', '.join(interests[:4])}."
            )
        mood = self.config.get("mood", "")
        if mood:
            parts.append(f"Right now you're feeling {mood}.")
        return " ".join(parts)

    def random_quirk(self) -> str | None:
        quirks = self.config.get("quirks", [])
        if quirks:
            return random.choice(quirks)
        return None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.config)
