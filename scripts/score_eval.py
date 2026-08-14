#!/usr/bin/env python3
"""Score an existing eval results file.

Usage::

    python3 scripts/score_eval.py data/eval/runs/eval-20260814-120000.jsonl
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shaggoth.eval.harness import Harness
from shaggoth.eval.scorer import score_run


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: score_eval.py <results.jsonl>", file=sys.stderr)
        return 2

    path = Path(args[0])
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        return 1

    results = Harness.load_results(path)
    if not results:
        print("No results found in file.")
        return 1

    card = score_run(results)
    print(card.summary())
    return 0 if card.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
