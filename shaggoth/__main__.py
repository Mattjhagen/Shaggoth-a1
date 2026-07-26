"""Shaggoth CLI.

    python3 -m shaggoth chat                 # interactive REPL
    python3 -m shaggoth serve                # REST API server + web dashboard
    python3 -m shaggoth train --corpus F     # train the Markov model
    python3 -m shaggoth train --model tinygpt --corpus F --steps 5000
    python3 -m shaggoth learn --urls URL     # scrape + train (self-learning)
    python3 -m shaggoth guardrails list|test
    python3 -m shaggoth facts
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from .config import ensure_dirs, load_settings, DATA_DIR
from .dialogue import DialogueEngine
from .guardrails import GuardrailEngine
from .memory import MemoryStore
from .models.markov import MarkovModel


def _load_tinygpt(settings: dict):
    """Try to load TinyGPT model from disk."""
    try:
        from .models.tinygpt import TinyGPTModel, TORCH_AVAILABLE
        if not TORCH_AVAILABLE:
            return None
        model = TinyGPTModel()
        pt_path = str(DATA_DIR / "tinygpt.pt")
        if Path(pt_path).exists():
            model.load(pt_path)
            print(f"[shaggoth] Loaded TinyGPT from {pt_path}")
            return model
    except Exception:
        pass
    return None


def _load_markov(settings: dict) -> MarkovModel | None:
    model = MarkovModel()
    model_path = Path(settings["markov_model_path"])
    if model_path.exists():
        model.load(str(model_path))
    return model if model.is_trained() else None


def build_engine(settings: dict) -> DialogueEngine:
    ensure_dirs()

    model_choice = settings.get("model", "auto")
    model = None

    if model_choice in ("auto", "tinygpt"):
        model = _load_tinygpt(settings)
    if model is None and model_choice in ("auto", "markov"):
        model = _load_markov(settings)

    return DialogueEngine(
        guardrails=GuardrailEngine(settings["guardrails_path"]),
        memory=MemoryStore(settings["db_path"]),
        model=model if model.is_trained() else None,
        bot_name=settings["bot_name"],
        recall_threshold=settings["memory_recall_threshold"],
    )


def cmd_chat(settings: dict) -> int:
    engine = build_engine(settings)
    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    model_name = type(engine.model).__name__ if engine.model else "none"
    print(f"{settings['bot_name']} v0.1 — model: {model_name} — type 'quit' to exit. (session {session_id})")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"quit", "exit", "/quit"}:
            break
        if not text:
            continue
        reply = engine.respond(text, session_id=session_id)
        tag = f" [{reply.source}]" if reply.source != "pattern" else ""
        print(f"{settings['bot_name'].lower()}>{tag} {reply.text}")
    return 0


def cmd_serve(settings: dict, host: str | None, port: int | None) -> int:
    from .server import serve

    engine = build_engine(settings)
    serve(engine, host or settings["server_host"], port or settings["server_port"])
    return 0


def cmd_train(settings: dict, corpus: str, model_name: str, steps: int, out: str | None) -> int:
    text = Path(corpus).read_text(encoding="utf-8")
    if model_name == "markov":
        model = MarkovModel()
        model.train(text)
        path = out or settings["markov_model_path"]
        model.save(path)
        contexts = len(model.table)
        print(f"Trained Markov model on {len(text):,} chars ({contexts:,} contexts) → {path}")
    elif model_name == "tinygpt":
        from .models.tinygpt import TinyGPTModel

        model = TinyGPTModel()
        model.train(text, steps=steps)
        path = out or str(DATA_DIR / "tinygpt.pt")
        model.save(path)
        print(f"Trained TinyGPT for {steps} steps → {path}")
        print("Sample:", model.generate("Hello", max_tokens=120))
    else:
        print(f"unknown model: {model_name}", file=sys.stderr)
        return 2
    return 0


def cmd_learn(settings: dict, urls: list[str], depth: int, max_pages: int, steps: int) -> int:
    from .learner.pipeline import LearnerPipeline

    pipeline = LearnerPipeline()

    if urls:
        pipeline.scraper.add_seeds(urls)
        print(f"Added {len(urls)} seed URLs")

    print("Starting learning cycle...")
    session = pipeline.learn(
        urls=None,  # already added
        crawl_depth=depth,
        max_pages=max_pages,
        training_steps=steps,
        background=False,  # blocking for CLI
    )

    print(f"\nLearning complete ({session.session_id}):")
    print(f"  Pages scraped:  {session.pages_scraped}")
    print(f"  Words learned:  {session.words_learned:,}")
    print(f"  Training steps: {session.training_steps}")
    print(f"  Model saved to: {session.model_path}")
    if session.error:
        print(f"  Error: {session.error}")
    return 0 if session.status == "completed" else 1


def cmd_guardrails(settings: dict, action: str, text: str | None) -> int:
    engine = GuardrailEngine(settings["guardrails_path"])
    if action == "list":
        for rule in engine.rules():
            state = "on " if rule.get("enabled", True) else "off"
            print(f"[{state}] {rule['id']:<28} {rule['type']}")
        print(f"\nEdit {settings['guardrails_path']} to adjust (hot-reloads).")
    elif action == "test":
        if not text:
            print("usage: shaggoth guardrails test \"some message\"", file=sys.stderr)
            return 2
        verdict = engine.check_input(text)
        if verdict.allowed:
            filtered, fired = engine.filter_output(text)
            print(f"ALLOWED. Output rules that would fire: {fired or 'none'}")
        else:
            print(f"BLOCKED by rule '{verdict.rule_id}': {verdict.message}")
    return 0


def cmd_eval(settings: dict, corpus: str, model_path: str | None) -> int:
    from .models.tinygpt import TinyGPTModel, TORCH_AVAILABLE
    from .models.eval import perplexity

    if not TORCH_AVAILABLE:
        print("eval requires PyTorch: pip install torch", file=sys.stderr)
        return 2

    text = Path(corpus).read_text(encoding="utf-8")

    model = TinyGPTModel()
    path = model_path or str(DATA_DIR / "tinygpt.pt")
    if Path(path).exists():
        model.load(path)
        print(f"Loaded model from {path}")
    else:
        print(f"No model found at {path}, training on corpus...", file=sys.stderr)
        model.train(text, steps=500, log_every=200)

    result = perplexity(model.model, text, model.tokenizer, model.cfg.block_size)
    print(f"Perplexity: {result['perplexity']}")
    print(f"Loss:       {result['loss']}")
    print(f"Tokens:     {result['tokens_evaluated']:,}")
    print(f"Chunks:     {result['chunks']}")
    return 0


def cmd_facts(settings: dict) -> int:
    memory = MemoryStore(settings["db_path"])
    facts = memory.all_facts()
    if not facts:
        print("No facts stored yet.")
    for key, value in facts.items():
        print(f"{key:>12}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shaggoth", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("chat", help="interactive chat REPL")

    p_serve = sub.add_parser("serve", help="run the REST API server + web dashboard")
    p_serve.add_argument("--host", default=None)
    p_serve.add_argument("--port", type=int, default=None)

    p_train = sub.add_parser("train", help="train a language model")
    p_train.add_argument("--corpus", required=True)
    p_train.add_argument("--model", default="markov", choices=["markov", "tinygpt"])
    p_train.add_argument("--steps", type=int, default=2000)
    p_train.add_argument("--out", default=None)

    p_learn = sub.add_parser("learn", help="self-learn: scrape URLs and train")
    p_learn.add_argument("--urls", nargs="*", default=[], help="seed URLs to scrape")
    p_learn.add_argument("--depth", type=int, default=1, help="crawl depth (0-3)")
    p_learn.add_argument("--max-pages", type=int, default=20, help="max pages to scrape")
    p_learn.add_argument("--steps", type=int, default=1000, help="training steps")

    p_guard = sub.add_parser("guardrails", help="inspect and test guardrails")
    p_guard.add_argument("action", choices=["list", "test"])
    p_guard.add_argument("text", nargs="?", default=None)

    p_eval = sub.add_parser("eval", help="evaluate model perplexity on a corpus")
    p_eval.add_argument("--corpus", required=True)
    p_eval.add_argument("--model-path", default=None)

    sub.add_parser("facts", help="show remembered facts")

    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "chat":
        return cmd_chat(settings)
    if args.command == "serve":
        return cmd_serve(settings, args.host, args.port)
    if args.command == "train":
        return cmd_train(settings, args.corpus, args.model, args.steps, args.out)
    if args.command == "learn":
        return cmd_learn(settings, args.urls, args.depth, args.max_pages, args.steps)
    if args.command == "eval":
        return cmd_eval(settings, args.corpus, args.model_path)
    if args.command == "guardrails":
        return cmd_guardrails(settings, args.action, args.text)
    if args.command == "facts":
        return cmd_facts(settings)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
