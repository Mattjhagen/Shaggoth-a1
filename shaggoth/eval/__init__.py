"""Eval harness: run logging and benchmark scoring.

Provides two orthogonal capabilities:

1. **RunLogger** — append-only JSONL recording of every ``respond()`` call,
   for offline analysis and regression detection.  Wired into the dialogue
   engine as an optional hook; never crashes the agent.

2. **Harness / Scorer** — drive a benchmark task-list through an engine and
   score the results against expectations.
"""

from .logger import RunLogger
from .harness import Harness, BenchmarkTask, RunResult
from .scorer import score_run, ScoreCard

__all__ = [
    "RunLogger",
    "Harness",
    "BenchmarkTask",
    "RunResult",
    "score_run",
    "ScoreCard",
]
