"""Feedback on answers, and the repair queue it produces.

Until now, breadth came from the 15-minute curiosity loop and *refinement*
came from whoever happened to be reading the code. If an answer was thin,
off-target, or quoted an image caption instead of a definition, nothing
recorded that. The loop would cheerfully re-fetch the same bad entry a month
later on the grounds that it was stale.

The judgement that an answer was bad is the single most valuable signal this
system can get, and it was being thrown away.

So: a reply carries the entries it was built from (``entries_used``, added
with the reasoning work). Marking that reply bad therefore implicates a
specific knowledge entry, not just a question. Those entries become a
**repair queue**, which the scheduler drains *before* it refreshes anything
merely old -- an entry known to have produced a bad answer is a better use of
a research cycle than the oldest entry on file.

Repairing an entry clears its marks. If the repair does not help, the next
thumbs-down puts it straight back, so a genuinely difficult topic keeps
getting attention instead of being permanently "done".
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ..config import DATA_DIR

FEEDBACK_PATH = DATA_DIR / "feedback.json"

GOOD = "good"
BAD = "bad"
VERDICTS = (GOOD, BAD)

#: Keep the log bounded; the repair queue only needs recent judgement.
MAX_ENTRIES = 2000

#: A repaired entry is not eligible again for this long, so one persistent
#: complaint cannot monopolise every research cycle.
REPAIR_COOLDOWN_SECONDS = 6 * 3600


@dataclass
class Feedback:
    """One judgement about one answer."""

    question: str
    verdict: str
    answer: str = ""
    source: str = ""
    entries_used: list = field(default_factory=list)
    reasoning: list = field(default_factory=list)
    note: str = ""
    session_id: str = "default"
    ts: float = 0.0


@dataclass
class RepairTarget:
    """A knowledge entry that answers badly, and how badly."""

    topic: str
    bad: int
    good: int
    last_note: str = ""
    last_question: str = ""

    @property
    def score(self) -> int:
        """Net complaints. Positive means it is doing more harm than good."""
        return self.bad - self.good


def normalize_verdict(value) -> str:
    """Coerce whatever a client sent into ``good``/``bad``, or ``""``."""
    if isinstance(value, bool):
        return GOOD if value else BAD
    text = str(value or "").strip().lower()
    if text in VERDICTS:
        return text
    if text in ("up", "yes", "1", "true", "helpful", "correct", "👍"):
        return GOOD
    if text in ("down", "no", "0", "false", "unhelpful", "wrong", "👎"):
        return BAD
    return ""


class FeedbackStore:
    """Persisted feedback, and the repair queue derived from it."""

    def __init__(self, path: Optional[Path] = None,
                 cooldown: float = REPAIR_COOLDOWN_SECONDS) -> None:
        self.path = Path(path) if path else FEEDBACK_PATH
        self.cooldown = cooldown
        self._lock = threading.Lock()
        self._items: list = []
        self._repaired: dict = {}
        self._load()

    # -- persistence ------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            self._repaired = {
                str(k): float(v) for k, v in (raw.get("repaired") or {}).items()
            }
            raw = raw.get("feedback") or []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict) and item.get("question"):
                self._items.append(Feedback(**{
                    k: v for k, v in item.items()
                    if k in Feedback.__dataclass_fields__
                }))

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(
                    {
                        "feedback": [asdict(i) for i in self._items],
                        "repaired": self._repaired,
                    },
                    indent=2,
                ) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass

    # -- recording --------------------------------------------------------

    def record(
        self,
        question: str,
        verdict: str,
        answer: str = "",
        source: str = "",
        entries_used: Optional[list] = None,
        reasoning: Optional[list] = None,
        note: str = "",
        session_id: str = "default",
        now: Optional[float] = None,
    ) -> Optional[Feedback]:
        """Record a judgement. Returns ``None`` if it is unusable."""
        question = (question or "").strip()
        verdict = normalize_verdict(verdict)
        if not question or not verdict:
            return None

        item = Feedback(
            question=question,
            verdict=verdict,
            answer=(answer or "")[:2000],
            source=source or "",
            entries_used=list(entries_used or []),
            reasoning=list(reasoning or []),
            note=(note or "").strip()[:500],
            session_id=session_id or "default",
            ts=time.time() if now is None else now,
        )
        with self._lock:
            self._items.append(item)
            if len(self._items) > MAX_ENTRIES:
                del self._items[: len(self._items) - MAX_ENTRIES]
            if verdict == BAD:
                # A complaint re-opens every entry the answer was built from,
                # even one repaired recently -- the repair evidently did not
                # work, and pretending otherwise is how a bad entry becomes
                # permanent.
                for topic in item.entries_used:
                    self._repaired.pop(topic, None)
            self._save()
        return item

    # -- the repair queue -------------------------------------------------

    def repair_queue(self, now: Optional[float] = None) -> list:
        """Entries that answer badly, worst first.

        Only entries with more complaints than praise, and not repaired
        within the cooldown.
        """
        now = time.time() if now is None else now
        tally: dict = {}
        with self._lock:
            items = list(self._items)
            repaired = dict(self._repaired)

        for item in items:
            for topic in item.entries_used:
                target = tally.setdefault(topic, RepairTarget(topic=topic, bad=0, good=0))
                if item.verdict == BAD:
                    target.bad += 1
                    target.last_note = item.note or target.last_note
                    target.last_question = item.question
                else:
                    target.good += 1

        def off_cooldown(topic: str) -> bool:
            # An entry that has never been repaired is always eligible.
            # Defaulting its repair time to 0.0 and subtracting made it look
            # like it had just been repaired at the epoch, which excluded
            # every first-time complaint.
            if topic not in repaired:
                return True
            return (now - repaired[topic]) >= self.cooldown

        out = [t for t in tally.values() if t.score > 0 and off_cooldown(t.topic)]
        out.sort(key=lambda t: (-t.score, t.topic))
        return out

    def next_repair(self, now: Optional[float] = None) -> Optional[RepairTarget]:
        queue = self.repair_queue(now)
        return queue[0] if queue else None

    def mark_repaired(self, topic: str, now: Optional[float] = None) -> None:
        """Note that ``topic`` has been re-researched."""
        with self._lock:
            self._repaired[topic] = time.time() if now is None else now
            self._save()

    # -- reading ----------------------------------------------------------

    def status(self) -> dict:
        with self._lock:
            good = sum(1 for i in self._items if i.verdict == GOOD)
            bad = sum(1 for i in self._items if i.verdict == BAD)
        return {
            "total": good + bad,
            "good": good,
            "bad": bad,
            "repair_queue": len(self.repair_queue()),
        }

    def recent(self, limit: int = 20) -> list:
        with self._lock:
            return [asdict(i) for i in self._items[-limit:]]
