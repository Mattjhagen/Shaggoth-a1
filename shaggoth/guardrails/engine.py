"""Adjustable guardrails engine.

Rules live in a JSON file the user edits directly (or through the CLI/API).
The engine hot-reloads when the file's mtime changes, so guardrails can be
tuned while the bot is running.

Rule types
----------
Input rules (checked before generation):
  - ``regex_block``: message matching ``pattern`` is blocked; the rule's
    ``message`` is returned instead of a model reply.
  - ``topic_refuse``: if enough of the rule's ``keywords`` appear, refuse
    with ``message``. ``min_hits`` (default 1) tunes sensitivity.

Output rules (applied to every generated reply):
  - ``redact``: replace ``pattern`` matches with ``replacement``.
  - ``max_length``: truncate replies longer than ``value`` characters.

Every rule has a unique ``id`` and can be individually ``enabled``/disabled —
that is the primary "adjustable" surface, alongside adding and removing rules
at runtime via :meth:`GuardrailEngine.add_rule` / :meth:`remove_rule`.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "input_rules": [
        {
            "id": "no-credentials",
            "type": "regex_block",
            "pattern": r"(?i)\b(password|api[_ ]?key|secret[_ ]?token)\b\s*[:=]\s*\S+",
            "message": "I won't store or repeat credentials. Please don't paste secrets into chat.",
            "enabled": True,
        },
        {
            "id": "no-self-harm-instructions",
            "type": "topic_refuse",
            "keywords": ["kill myself", "hurt myself", "end my life"],
            "min_hits": 1,
            "message": (
                "I'm not able to help with that, but I care that you're okay. "
                "If you're in the U.S. you can call or text 988 to reach the "
                "Suicide & Crisis Lifeline, any time."
            ),
            "enabled": True,
        },
        {
            "id": "no-malware",
            "type": "topic_refuse",
            "keywords": ["write malware", "make a virus", "ransomware", "keylogger"],
            "min_hits": 1,
            "message": "I can't help build malicious software.",
            "enabled": True,
        },
    ],
    "output_rules": [
        {
            "id": "redact-emails",
            "type": "redact",
            "pattern": r"[\w.+-]+@[\w-]+\.[\w.]+",
            "replacement": "[email redacted]",
            "enabled": True,
        },
        {
            "id": "reply-length-cap",
            "type": "max_length",
            "value": 2000,
            "enabled": True,
        },
    ],
}


@dataclass
class Verdict:
    """Result of checking an input message against the guardrails."""

    allowed: bool
    message: str | None = None  # refusal text when blocked
    rule_id: str | None = None
    applied: list[str] = field(default_factory=list)  # output-rule ids that fired


class GuardrailEngine:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._lock = threading.Lock()
        self._mtime: float | None = None
        self.config: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
        if self.path:
            if self.path.exists():
                self._load()
            else:
                self.save()

    # ------------------------------------------------------------------ io
    def _load(self) -> None:
        assert self.path is not None
        with open(self.path, encoding="utf-8") as fh:
            self.config = json.load(fh)
        self._mtime = self.path.stat().st_mtime

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self.config, fh, indent=2)
            fh.write("\n")
        self._mtime = self.path.stat().st_mtime

    def maybe_reload(self) -> bool:
        """Hot-reload if the file changed on disk. Returns True if reloaded."""
        if self.path is None or not self.path.exists():
            return False
        mtime = self.path.stat().st_mtime
        if self._mtime is None or mtime > self._mtime:
            with self._lock:
                self._load()
            return True
        return False

    # --------------------------------------------------------- rule admin
    def rules(self) -> list[dict[str, Any]]:
        return list(self.config.get("input_rules", [])) + list(
            self.config.get("output_rules", [])
        )

    def add_rule(self, rule: dict[str, Any]) -> None:
        if "id" not in rule or "type" not in rule:
            raise ValueError("rule needs 'id' and 'type'")
        if any(r["id"] == rule["id"] for r in self.rules()):
            raise ValueError(f"rule id already exists: {rule['id']}")
        rule.setdefault("enabled", True)
        bucket = (
            "output_rules" if rule["type"] in ("redact", "max_length") else "input_rules"
        )
        with self._lock:
            self.config.setdefault(bucket, []).append(rule)
            self.save()

    def remove_rule(self, rule_id: str) -> bool:
        with self._lock:
            for bucket in ("input_rules", "output_rules"):
                rules = self.config.get(bucket, [])
                kept = [r for r in rules if r.get("id") != rule_id]
                if len(kept) != len(rules):
                    self.config[bucket] = kept
                    self.save()
                    return True
        return False

    def set_enabled(self, rule_id: str, enabled: bool) -> bool:
        with self._lock:
            for rule in self.rules():
                if rule.get("id") == rule_id:
                    rule["enabled"] = enabled
                    self.save()
                    return True
        return False

    # ---------------------------------------------------------- checking
    def check_input(self, text: str) -> Verdict:
        self.maybe_reload()
        if not self.config.get("enabled", True):
            return Verdict(allowed=True)
        lowered = text.lower()
        for rule in self.config.get("input_rules", []):
            if not rule.get("enabled", True):
                continue
            rtype = rule.get("type")
            if rtype == "regex_block":
                if re.search(rule["pattern"], text):
                    return Verdict(False, rule.get("message", "Blocked."), rule["id"])
            elif rtype == "topic_refuse":
                hits = sum(1 for kw in rule.get("keywords", []) if kw.lower() in lowered)
                if hits >= int(rule.get("min_hits", 1)):
                    return Verdict(False, rule.get("message", "I can't help with that."), rule["id"])
        return Verdict(allowed=True)

    def filter_output(self, text: str) -> tuple[str, list[str]]:
        """Apply output rules; returns (filtered_text, ids_of_rules_that_fired)."""
        self.maybe_reload()
        if not self.config.get("enabled", True):
            return text, []
        fired: list[str] = []
        for rule in self.config.get("output_rules", []):
            if not rule.get("enabled", True):
                continue
            rtype = rule.get("type")
            if rtype == "redact":
                new = re.sub(rule["pattern"], rule.get("replacement", "[redacted]"), text)
                if new != text:
                    fired.append(rule["id"])
                    text = new
            elif rtype == "max_length":
                limit = int(rule.get("value", 2000))
                if len(text) > limit:
                    text = text[: limit - 1].rstrip() + "…"
                    fired.append(rule["id"])
        return text, fired
