#!/usr/bin/env python3
"""Run the Shaggoth evaluation benchmark.

Usage::

    python3 scripts/run_eval.py                          # default benchmark
    python3 scripts/run_eval.py --benchmark custom.jsonl # custom tasks
    python3 scripts/run_eval.py --output results.jsonl   # custom output path
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shaggoth.config import load_settings, DATA_DIR
from shaggoth.__main__ import build_engine
from shaggoth.eval.harness import Harness
from shaggoth.eval.scorer import score_run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Shaggoth eval benchmark")
    parser.add_argument(
        "--benchmark",
        default=None,
        help="path to benchmark JSONL (default: bundled benchmark)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="path for results JSONL (default: data/eval/runs/eval-<timestamp>.jsonl)",
    )
    args = parser.parse_args(argv)

    settings = load_settings()
    engine = build_engine(settings)

    print(f"Loading benchmark from {args.benchmark or 'bundled default'}")
    harness = Harness(engine, session_id="eval-bench")

    t0 = time.monotonic()
    results = harness.run(benchmark_path=args.benchmark)
    elapsed = time.monotonic() - t0

    if not results:
        print("No tasks found.")
        return 1

    output = args.output or str(
        DATA_DIR / "eval" / "runs" / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.jsonl"
    )
    harness.save_results(results, output)
    print(f"Results written to {output}")

    card = score_run(results)
    print(f"\n{card.summary()}")
    print(f"\nCompleted {card.total} tasks in {elapsed:.1f}s")

    return 0 if card.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
