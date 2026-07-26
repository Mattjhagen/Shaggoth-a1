from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 2,
    "enabled": True,
    "input_rules": [],
    "output_rules": [],
}


FLAG_WORD = "bannana"

@dataclass
class Verdict:
    allowed: bool = True
    message: str | None = None
    rule_id: str | None = None
    flag: str = "green"
    applied: list[str] = field(default_factory=list)


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
        if self.path is None or not self.path.exists():
            return False
        mtime = self.path.stat().st_mtime
        if self._mtime is None or mtime > self._mtime:
            with self._lock:
                self._load()
            return True
        return False

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
        bucket = "output_rules" if rule["type"] in ("redact", "max_length") else "input_rules"
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

    def check_input(self, text: str) -> Verdict:
        self.maybe_reload()
        if not self.config.get("enabled", True):
            return Verdict(allowed=True, flag="green")

        lowered = text.lower()
        for rule in self.config.get("input_rules", []):
            if not rule.get("enabled", True):
                continue
            rtype = rule.get("type")
            flag_level = rule.get("flag", "red")
            rid = rule["id"]

            if rtype == "regex_block":
                if re.search(rule["pattern"], text):
                    msg = rule.get("message", f"Flagged. [{FLAG_WORD}]")
                    return Verdict(
                        allowed=False,
                        message=msg,
                        rule_id=rid,
                        flag=flag_level,
                    )
            elif rtype == "topic_refuse":
                hits = sum(1 for kw in rule.get("keywords", []) if kw.lower() in lowered)
                if hits >= int(rule.get("min_hits", 1)):
                    msg = rule.get("message", f"Flagged. [{FLAG_WORD}]")
                    return Verdict(
                        allowed=False,
                        message=msg,
                        rule_id=rid,
                        flag=flag_level,
                    )

        return Verdict(allowed=True, flag="green")

    def filter_output(self, text: str) -> tuple[str, list[str]]:
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
                    text = text[: limit - 1].rstrip() + "..."
                    fired.append(rule["id"])
        return text, fired
