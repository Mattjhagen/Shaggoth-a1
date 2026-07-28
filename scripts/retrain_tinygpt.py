#!/usr/bin/env python3
"""Continuous-retraining orchestrator for TinyGPT.

Run from the repo root (needs ``PYTHONPATH=.`` and the system python3 that can
see torch -- NOT uvx, which can't; see AGENTS.md gotchas).

What it does, in order:

  1. Rebuild the corpus from the CURRENT state of data/knowledge/ (which grows
     via curiosity research + feedback repair).
  2. Train a fresh TinyGPT to a STAGING path (data/tinygpt.pt.new), never
     touching the live checkpoint.
  3. Evaluate the staging checkpoint: perplexity + a coherence check
     (fraction of generated words that are real corpus words).
  4. Compare against the currently-live checkpoint (data/tinygpt.pt). Promote
     ONLY if coherent AND perplexity did not regress. Otherwise keep live
     untouched and park the rejected candidate.
  5. Append the decision (either way) to data/retrain_log.jsonl.

IMPORTANT -- this is NOT fine-tuning. TinyGPTModel.train() re-derives the BPE
tokenizer and re-initialises all weights from scratch every run, so this is a
full from-scratch retrain on the current corpus, not warm-start and not a
weight-preserving / LoRA fine-tune. It cannot be warm-started cheaply because a
growing corpus changes the BPE vocab and therefore the embedding shapes.

Promotion writes data/tinygpt.pt but does NOT wire the model into serve. serve
only loads TinyGPT when config/settings.json has "model": "tinygpt"; with the
default "auto" it stays on Markov regardless of what is on disk. Two
independent gates on purpose (see shaggoth/models/promote.py header).
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
import time
from pathlib import Path


def _ts() -> float:
    return time.time()


def _sidecars(pt: str) -> list[str]:
    """The files that travel with a checkpoint."""
    return [pt, pt + ".tok.json", pt + ".json"]


def _copy_set(src_pt: str, dst_pt: str) -> None:
    for s in _sidecars(src_pt):
        if os.path.exists(s):
            shutil.copy2(s, dst_pt + s[len(src_pt):])


def _move_set(src_pt: str, dst_pt: str) -> None:
    for s in _sidecars(src_pt):
        if os.path.exists(s):
            os.replace(s, dst_pt + s[len(src_pt):])


def rebuild_corpus(knowledge_dir: Path, corpus_path: Path) -> int:
    files = sorted(glob.glob(str(knowledge_dir / "*.md")))
    corpus_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(corpus_path, "w", encoding="utf-8") as out:
        for f in files:
            try:
                out.write(Path(f).read_text(encoding="utf-8"))
                out.write("\n")
                n += 1
            except Exception:
                continue
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Retrain + gate + promote TinyGPT")
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--dry-run", action="store_true",
                    help="run gate but never promote (still logs)")
    # Small-by-default config so a full run finishes in minutes on r510-1's
    # pre-AVX Xeon (see AGENTS.md section SS). The full default config
    # (vocab 2048, block 256, 4 layer) is ~4.3 s/step -> ~6h and has SIGILL'd
    # on this box; these dims train in ~10-15 min. Override for a beefier box.
    ap.add_argument("--vocab", type=int, default=1024)
    ap.add_argument("--block", type=int, default=96)
    ap.add_argument("--layers", type=int, default=2)
    ap.add_argument("--heads", type=int, default=3)
    ap.add_argument("--embd", type=int, default=96)
    args = ap.parse_args()

    data = Path(args.data_dir)
    knowledge_dir = data / "knowledge"
    corpus_path = data / "corpus" / "knowledge_corpus.txt"
    live_pt = str(data / "tinygpt.pt")
    staging_pt = str(data / "tinygpt.pt.new")
    prev_pt = str(data / "tinygpt.pt.prev")      # rollback target
    rejected_pt = str(data / "tinygpt.pt.rejected")
    log_path = data / "retrain_log.jsonl"

    record: dict = {"started_at": _ts(), "steps": args.steps}

    # torch import is deferred so a torch-less environment fails loudly here
    # rather than half way through.
    try:
        from shaggoth.models.tinygpt import TinyGPTModel, GPTConfig, TORCH_AVAILABLE
        from shaggoth.models.eval import perplexity
        from shaggoth.models import promote as gate
    except Exception as exc:
        print(f"[retrain] import failed: {exc}", file=sys.stderr)
        return 2
    if not TORCH_AVAILABLE:
        print("[retrain] torch unavailable -- use system python3, not uvx",
              file=sys.stderr)
        return 2

    # This runs alongside the live Shaggoth service on a shared 16-core box.
    # Cap torch threads so a retrain cannot saturate every core and spike chat
    # latency. Overridable via OMP_NUM_THREADS in the systemd unit.
    try:
        import torch
        n = int(os.environ.get("OMP_NUM_THREADS", "4"))
        torch.set_num_threads(max(1, n))
    except Exception:
        pass

    # 1. rebuild corpus
    n_entries = rebuild_corpus(knowledge_dir, corpus_path)
    text = corpus_path.read_text(encoding="utf-8")
    record["corpus_entries"] = n_entries
    record["corpus_chars"] = len(text)
    print(f"[retrain] corpus: {n_entries} entries, {len(text):,} chars")

    # 2. train to STAGING (never touch live)
    for s in _sidecars(staging_pt):
        if os.path.exists(s):
            os.remove(s)
    t0 = _ts()
    cfg = GPTConfig(vocab_size=args.vocab, block_size=args.block,
                    n_layer=args.layers, n_head=args.heads, n_embd=args.embd)
    print(f"[retrain] config: {cfg}")
    model = TinyGPTModel(cfg)
    model.train(text, steps=args.steps, log_every=max(args.steps // 10, 1))
    model.save(staging_pt)
    train_secs = _ts() - t0
    record["train_seconds"] = round(train_secs, 1)
    print(f"[retrain] trained {args.steps} steps in {train_secs/60:.1f} min "
          f"-> {staging_pt}")

    # 3. eval staging. Perplexity strides over the corpus one window at a
    # time, so scoring the full ~10 MB would take longer than training. A
    # representative slice is enough for a promote/reject comparison; both the
    # candidate and the live checkpoint are scored on the SAME slice so the
    # comparison is fair. Coherence vocab still uses the FULL corpus (it must
    # know every real word).
    EVAL_CHARS = 400_000
    eval_text = text[:EVAL_CHARS]
    cand = perplexity(model.model, eval_text, model.tokenizer, model.cfg.block_size)
    cand_ppl = float(cand["perplexity"])
    vocab = gate.corpus_vocabulary(text)
    coh = gate.coherence_report(model, vocab)
    record["candidate_perplexity"] = cand_ppl
    record["candidate_loss"] = cand.get("loss")
    print(f"[retrain] candidate perplexity={cand_ppl} "
          f"coherence_ratio={coh.known_word_ratio} passed={coh.passed}")
    for s in coh.samples:
        print(f"    {s['probe']!r} -> {s.get('output','')!r}")

    # perplexity of the currently-live checkpoint, if any, for comparison
    live_ppl = None
    if os.path.exists(live_pt):
        try:
            live_model = TinyGPTModel()
            live_model.load(live_pt)
            live_eval = perplexity(live_model.model, eval_text,
                                   live_model.tokenizer, live_model.cfg.block_size)
            live_ppl = float(live_eval["perplexity"])
        except Exception as exc:
            print(f"[retrain] warning: could not eval live checkpoint: {exc}")
            live_ppl = None
    record["live_perplexity"] = live_ppl

    # 4. decide
    decision = gate.decide(cand_ppl, coh, live_ppl)
    record["decision"] = decision.as_dict()
    record["finished_at"] = _ts()
    print(f"[retrain] {decision.reason}")

    promoted = False
    if decision.promote and not args.dry_run:
        # keep the outgoing live checkpoint for rollback, then swap staging in
        if os.path.exists(live_pt):
            _copy_set(live_pt, prev_pt)
        _move_set(staging_pt, live_pt)
        promoted = True
        print(f"[retrain] PROMOTED -> {live_pt} (previous kept at {prev_pt})")
    else:
        # park the rejected candidate for inspection; do NOT touch live
        for s in _sidecars(rejected_pt):
            if os.path.exists(s):
                os.remove(s)
        _move_set(staging_pt, rejected_pt)
        if args.dry_run and decision.promote:
            print(f"[retrain] dry-run: would have promoted; live untouched")
        else:
            print(f"[retrain] NOT promoted; live untouched, "
                  f"candidate parked at {rejected_pt}")
    record["promoted"] = promoted

    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"[retrain] logged decision to {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
