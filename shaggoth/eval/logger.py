"""Append-only JSONL run logger.

Every ``DialogueEngine.respond()`` call optionally writes one line here.
The logger is deliberately fire-and-forget: it catches all exceptions
internally so a logging failure never degrades a user-facing reply.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..config import DATA_DIR

log = logging.getLogger(__name__)

DEFAULT_RUNS_DIR = DATA_DIR / "eval" / "runs"

_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[redacted-email]"),
    (re.compile(
        r"\bsk-[A-Za-z0-9_-]{16,}\b|"
        r"\beyJ[A-Za-z0-9._-]{20,}\b|"
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    ), "[redacted-secret]"),
]


def _redact_for_log(text: str) -> str:
    for pat, repl in _REDACT_PATTERNS:
        text = pat.sub(repl, text)
    return text


@dataclass
class RunRecord:
    run_id: str
    timestamp: float
    session_id: str
    user_input: str
    reply_text: str
    source: str
    mode: str
    blocked: bool
    entries_used: list[str]
    reasoning: list[str]
    latency_ms: float
    new_facts: dict[str, Any] = field(default_factory=dict)
    memory_triggers: list[str] = field(default_factory=list)
    flag: str = "green"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunLogger:
    """Append JSONL records to a single file per day.

    Usage::

        logger = RunLogger()
        engine = DialogueEngine(..., run_logger=logger)

    The engine calls ``logger.log(...)`` at the end of ``respond()``.
    """

    def __init__(self, directory: str | Path | None = None, *, enabled: bool = True):
        self.directory = Path(directory) if directory else DEFAULT_RUNS_DIR
        self.enabled = enabled
        if self.enabled:
            self.directory.mkdir(parents=True, exist_ok=True)

    def _path_for_today(self) -> Path:
        stamp = time.strftime("%Y-%m-%d", time.localtime())
        return self.directory / f"run-{stamp}.jsonl"

    def log(
        self,
        *,
        session_id: str,
        user_input: str,
        reply_text: str,
        source: str,
        mode: str,
        blocked: bool = False,
        entries_used: list[str] | None = None,
        reasoning: list | None = None,
        new_facts: dict | None = None,
        memory_triggers: list[str] | None = None,
        flag: str = "green",
        latency_ms: float = 0.0,
    ) -> RunRecord | None:
        """Write one run record.  Returns the record on success, None on failure."""
        if not self.enabled:
            return None
        try:
            record = RunRecord(
                run_id=uuid.uuid4().hex[:12],
                timestamp=time.time(),
                session_id=session_id,
                user_input=_redact_for_log(user_input),
                reply_text=_redact_for_log(reply_text),
                source=source,
                mode=mode,
                blocked=blocked,
                entries_used=entries_used or [],
                reasoning=[str(s) for s in (reasoning or [])],
                new_facts={k: _redact_for_log(str(v)) for k, v in (new_facts or {}).items()},
                memory_triggers=memory_triggers or [],
                flag=flag,
                latency_ms=round(latency_ms, 2),
            )
            path = self._path_for_today()
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            return record
        except Exception as exc:  # noqa: BLE001
            log.warning("[eval] run logging failed: %s", exc)
            return None

    def read_records(self, path: str | Path | None = None) -> list[RunRecord]:
        """Read all records from a JSONL file (for scoring / inspection)."""
        target = Path(path) if path else self._path_for_today()
        if not target.exists():
            return []
        records = []
        for line in target.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                records.append(RunRecord(**data))
            except (json.JSONDecodeError, TypeError) as exc:
                log.debug("[eval] skipping malformed record: %s", exc)
        return records
