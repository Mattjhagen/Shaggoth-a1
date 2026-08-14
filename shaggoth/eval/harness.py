"""Benchmark harness: drive tasks through an engine and record results.

A benchmark file is JSONL where each line is a task::

    {"id": "know-01", "input": "what is photosynthesis",
     "category": "knowledge", "expect_source": "knowledge",
     "expect_keywords": ["light", "energy"]}

The harness feeds each task to ``engine.respond()`` and writes a parallel
JSONL results file for ``scorer.score_run()`` to evaluate.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..config import DATA_DIR

log = logging.getLogger(__name__)

DEFAULT_BENCHMARKS_DIR = DATA_DIR / "eval" / "benchmarks"


@dataclass
class BenchmarkTask:
    id: str
    input: str
    category: str = "general"
    expect_source: str | None = None
    expect_keywords: list[str] = field(default_factory=list)
    expect_entries: list[str] = field(default_factory=list)
    expect_blocked: bool | None = None
    expect_min_length: int = 0
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "BenchmarkTask":
        return cls(
            id=d["id"],
            input=d["input"],
            category=d.get("category", "general"),
            expect_source=d.get("expect_source"),
            expect_keywords=d.get("expect_keywords", []),
            expect_entries=d.get("expect_entries", []),
            expect_blocked=d.get("expect_blocked"),
            expect_min_length=d.get("expect_min_length", 0),
            description=d.get("description", ""),
        )


@dataclass
class RunResult:
    task_id: str
    input: str
    category: str
    reply_text: str
    source: str
    blocked: bool
    entries_used: list[str]
    reasoning: list[str]
    latency_ms: float
    expect_source: str | None = None
    expect_keywords: list[str] = field(default_factory=list)
    expect_entries: list[str] = field(default_factory=list)
    expect_blocked: bool | None = None
    expect_min_length: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_tasks(path: str | Path | None = None) -> list[BenchmarkTask]:
    """Load benchmark tasks from a JSONL file."""
    p = Path(path) if path else DEFAULT_BENCHMARKS_DIR / "default.jsonl"
    if not p.exists():
        log.warning("[eval] benchmark file not found: %s", p)
        return []
    tasks = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            tasks.append(BenchmarkTask.from_dict(json.loads(line)))
        except (json.JSONDecodeError, KeyError) as exc:
            log.warning("[eval] skipping malformed task: %s", exc)
    return tasks


class Harness:
    """Run benchmark tasks through a DialogueEngine and collect results."""

    def __init__(self, engine: Any, session_id: str = "eval"):
        self.engine = engine
        self.session_id = session_id

    def run(
        self,
        tasks: list[BenchmarkTask] | None = None,
        benchmark_path: str | Path | None = None,
    ) -> list[RunResult]:
        """Execute tasks and return results.

        Loads from ``benchmark_path`` when ``tasks`` is not given.
        """
        if tasks is None:
            tasks = load_tasks(benchmark_path)
        if not tasks:
            log.info("[eval] no tasks to run")
            return []

        results: list[RunResult] = []
        for task in tasks:
            result = self._run_one(task)
            results.append(result)
        return results

    def _run_one(self, task: BenchmarkTask) -> RunResult:
        try:
            sid = f"{self.session_id}_{task.id}"
            t0 = time.monotonic()
            reply = self.engine.respond(task.input, session_id=sid)
            latency = (time.monotonic() - t0) * 1000
            return RunResult(
                task_id=task.id,
                input=task.input,
                category=task.category,
                reply_text=reply.text,
                source=reply.source,
                blocked=reply.blocked,
                entries_used=list(reply.entries_used),
                reasoning=list(reply.reasoning),
                latency_ms=round(latency, 2),
                expect_source=task.expect_source,
                expect_keywords=task.expect_keywords,
                expect_entries=task.expect_entries,
                expect_blocked=task.expect_blocked,
                expect_min_length=task.expect_min_length,
            )
        except Exception as exc:  # noqa: BLE001
            log.error("[eval] task %s failed: %s", task.id, exc)
            return RunResult(
                task_id=task.id,
                input=task.input,
                category=task.category,
                reply_text="",
                source="error",
                blocked=False,
                entries_used=[],
                reasoning=[],
                latency_ms=0.0,
                expect_source=task.expect_source,
                expect_keywords=task.expect_keywords,
                expect_entries=task.expect_entries,
                expect_blocked=task.expect_blocked,
                expect_min_length=task.expect_min_length,
                error=str(exc),
            )

    @staticmethod
    def save_results(results: list[RunResult], path: str | Path) -> Path:
        """Write results to JSONL."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            for r in results:
                fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
        return p

    @staticmethod
    def load_results(path: str | Path) -> list[RunResult]:
        """Read results from a JSONL file."""
        p = Path(path)
        results = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                results.append(RunResult(**data))
            except (json.JSONDecodeError, TypeError):
                continue
        return results
