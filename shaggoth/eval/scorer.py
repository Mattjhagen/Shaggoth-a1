"""Score harness results against expectations.

Each task can specify:
- ``expect_source``: the reply must come from this pipeline stage
- ``expect_keywords``: words that should appear in the reply
- ``expect_entries``: knowledge entries that should be cited
- ``expect_blocked``: whether the reply should be blocked
- ``expect_min_length``: minimum character count for the reply

The scorer produces per-task pass/fail verdicts and an aggregate ScoreCard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .harness import RunResult


@dataclass
class TaskScore:
    task_id: str
    category: str
    passed: bool
    checks: dict[str, bool]
    notes: list[str] = field(default_factory=list)


@dataclass
class ScoreCard:
    total: int
    passed: int
    failed: int
    score: float
    by_category: dict[str, dict[str, Any]]
    tasks: list[TaskScore]

    def summary(self) -> str:
        lines = [
            f"Score: {self.passed}/{self.total} ({self.score:.0%})",
        ]
        for cat, stats in sorted(self.by_category.items()):
            lines.append(
                f"  {cat}: {stats['passed']}/{stats['total']} "
                f"({stats['score']:.0%})"
            )
        if self.failed:
            lines.append("Failed:")
            for t in self.tasks:
                if not t.passed:
                    fails = [k for k, v in t.checks.items() if not v]
                    lines.append(f"  {t.task_id}: {', '.join(fails)}")
                    for note in t.notes:
                        lines.append(f"    {note}")
        return "\n".join(lines)


def _word_in_text(word: str, text: str) -> bool:
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text, re.I))


def score_task(result: RunResult) -> TaskScore:
    """Score a single task result against its expectations."""
    checks: dict[str, bool] = {}
    notes: list[str] = []

    checks["non_empty"] = bool(result.reply_text.strip())
    if not checks["non_empty"]:
        notes.append("reply was empty")

    checks["no_error"] = result.error is None
    if not checks["no_error"]:
        notes.append(f"error: {result.error}")

    if result.expect_source is not None:
        checks["source"] = result.source == result.expect_source
        if not checks["source"]:
            notes.append(f"expected source={result.expect_source}, got {result.source}")

    if result.expect_keywords:
        text_lower = result.reply_text.lower()
        missing = [
            kw for kw in result.expect_keywords
            if not _word_in_text(kw, result.reply_text)
        ]
        checks["keywords"] = len(missing) == 0
        if missing:
            notes.append(f"missing keywords: {missing}")

    if result.expect_entries:
        found = {e.lower() for e in result.entries_used}
        missing_entries = [
            e for e in result.expect_entries
            if e.lower() not in found
        ]
        checks["entries"] = len(missing_entries) == 0
        if missing_entries:
            notes.append(f"missing entries: {missing_entries}")

    if result.expect_blocked is not None:
        checks["blocked"] = result.blocked == result.expect_blocked
        if not checks["blocked"]:
            notes.append(
                f"expected blocked={result.expect_blocked}, got {result.blocked}"
            )

    if result.expect_min_length > 0:
        checks["min_length"] = len(result.reply_text) >= result.expect_min_length
        if not checks["min_length"]:
            notes.append(
                f"reply too short: {len(result.reply_text)} < {result.expect_min_length}"
            )

    passed = all(checks.values())
    return TaskScore(
        task_id=result.task_id,
        category=result.category,
        passed=passed,
        checks=checks,
        notes=notes,
    )


def score_run(results: list[RunResult]) -> ScoreCard:
    """Score a full benchmark run and produce an aggregate ScoreCard."""
    tasks = [score_task(r) for r in results]
    total = len(tasks)
    passed = sum(1 for t in tasks if t.passed)

    by_category: dict[str, dict[str, Any]] = {}
    for t in tasks:
        cat = t.category
        if cat not in by_category:
            by_category[cat] = {"total": 0, "passed": 0, "score": 0.0}
        by_category[cat]["total"] += 1
        if t.passed:
            by_category[cat]["passed"] += 1
    for stats in by_category.values():
        stats["score"] = stats["passed"] / stats["total"] if stats["total"] else 0.0

    return ScoreCard(
        total=total,
        passed=passed,
        failed=total - passed,
        score=passed / total if total else 0.0,
        by_category=by_category,
        tasks=tasks,
    )
