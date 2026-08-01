"""Shaggoth CLI.

    python3 -m shaggoth chat                 # interactive REPL
    python3 -m shaggoth serve                # REST API server + web dashboard
    python3 -m shaggoth train --corpus F     # train the Markov model
    python3 -m shaggoth train --model tinygpt --corpus F --steps 5000
    python3 -m shaggoth learn --urls URL     # scrape + train (self-learning)
    python3 -m shaggoth research TOPIC       # research a topic via curiosity engine
    python3 -m shaggoth wiki TOPIC           # fetch Wikipedia article
    python3 -m shaggoth guardrails list|test
    python3 -m shaggoth facts
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# Installed-mode guard: `python -m shaggoth` imports .config directly, so the
# console-script bootstrap (shaggoth._bootstrap) never runs. Without this, an
# installed package would resolve ROOT to site-packages and write user data
# (data/, config/) inside the install tree. Mirror the bootstrap's rule: when
# the package is not in a repo checkout (no LICENSE above it), default the data
# root to a per-user ~/.shaggoth.
if not os.environ.get("SHAGGOTH_ROOT") and not (Path(__file__).resolve().parent.parent / "LICENSE").exists():
    os.environ["SHAGGOTH_ROOT"] = str(Path.home() / ".shaggoth")

from .config import ensure_dirs, load_settings, DATA_DIR, CONFIG_DIR
from .dialogue import DialogueEngine
from .guardrails import GuardrailEngine
from .knowledge.engine import KnowledgeBase
from .memory import MemoryStore
from .models.markov import MarkovModel
from .personality.engine import PersonalityEngine


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

    # "auto" no longer prefers TinyGPT just because a checkpoint exists.
    #
    # A 3000-step run on this corpus reached loss 4.15 and generated non-words
    # ("symotential", "authibiiktiological") -- materially worse than the
    # Markov model, which at least emits real words. Because `auto` loaded
    # TinyGPT first, simply finishing a training run would have silently
    # downgraded every drift-mode reply on the next restart, with nothing in
    # the logs to say why.
    #
    # An unvalidated checkpoint appearing on disk is not evidence that it is
    # any good. Using it is now an explicit choice: set model = "tinygpt".
    if model_choice == "tinygpt":
        model = _load_tinygpt(settings)
    if model is None and model_choice in ("auto", "markov"):
        model = _load_markov(settings)
    if model is None and model_choice in ("cloud", "gemini", "cloudflare"):
        # Free-tier cloud backends (Gemini / Cloudflare Workers AI). No key
        # configured -> build_cloud_model returns None and the engine runs
        # knowledge/patterns only, exactly as before.
        from .models.cloud import build_cloud_model

        model = build_cloud_model(model_choice)
        if model is not None:
            print(f"[shaggoth] Using cloud model: {model.provider} ({model.model_name})")

    return DialogueEngine(
        guardrails=GuardrailEngine(settings["guardrails_path"]),
        memory=MemoryStore(settings["db_path"]),
        model=model if model and model.is_trained() else None,
        personality=PersonalityEngine(CONFIG_DIR / "personality.json"),
        knowledge=KnowledgeBase(),
        bot_name=settings["bot_name"],
        recall_threshold=settings["memory_recall_threshold"],
        mode=settings.get("dialogue_mode", "no_drift"),
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
    api_key = settings.get("api_key") or ""
    serve(engine, host or settings["server_host"], port or settings["server_port"], api_key=api_key)
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


def cmd_personality(settings: dict, action: str) -> int:
    engine = PersonalityEngine(CONFIG_DIR / "personality.json")
    if action == "show":
        data = engine.as_dict()
        print(json.dumps(data, indent=2))
    elif action == "reload":
        engine.maybe_reload()
        print("Personality reloaded.")
    return 0


def cmd_knowledge(settings: dict, action: str, **kwargs) -> int:
    kb = KnowledgeBase()
    if action == "list":
        entries = kb.list_entries()
        if not entries:
            print("No knowledge entries.")
        for e in entries:
            print(f"  {e['topic']:30s} {e['word_count']:>6} words  {e['path']}")
    elif action == "add":
        topic = kwargs.get("topic", "")
        text = kwargs.get("text") or ""
        file_path = kwargs.get("file")
        if file_path:
            text = Path(file_path).read_text(encoding="utf-8")
        if not text:
            print("Provide --text or --file", file=sys.stderr)
            return 2
        path = kb.add_entry(topic, text)
        print(f"Added knowledge entry → {path}")
    elif action == "remove":
        topic = kwargs.get("topic", "")
        if kb.remove_entry(topic):
            print(f"Removed entry: {topic}")
        else:
            print(f"No entry found: {topic}", file=sys.stderr)
            return 1
    elif action == "query":
        text = kwargs.get("text", "")
        results = kb.query(text, limit=5, min_score=0.1)
        if not results:
            print("No relevant knowledge found.")
        for entry, score in results:
            print(f"[{score:.2f}] {entry.topic}: {entry.content[:120]}...")
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


def cmd_research(settings: dict, topic: str, max_results: int, max_pages: int) -> int:
    from .curiosity.engine import CuriosityEngine

    ensure_dirs()
    engine = CuriosityEngine()
    print(f"Researching \"{topic}\"...")
    episode = engine.research_topic(topic, max_results=max_results, max_pages=max_pages, background=False)
    print(f"\nResearch complete ({episode.episode_id}):")
    print(f"  URLs found:     {episode.urls_found}")
    print(f"  Pages scraped:  {episode.pages_scraped}")
    print(f"  Words learned:  {episode.words_learned:,}")
    print(f"  Knowledge entries: {episode.knowledge_entries}")
    if episode.error:
        print(f"  Error: {episode.error}")
    return 0 if episode.status == "completed" else 1


def cmd_wiki(settings: dict, query: str) -> int:
    from .curiosity.wikipedia import fetch_article, fetch_summary, search_wikipedia

    print(f"Fetching Wikipedia article for \"{query}\"...")
    summary = fetch_summary(query)
    if summary:
        print(f"\n{summary}")
        return 0

    results = search_wikipedia(query, max_results=5)
    if not results:
        print(f"No Wikipedia results for \"{query}\".")
        return 1

    print(f"\nNo exact match. Did you mean:")
    for r in results:
        print(f"  {r['title']}: {r['snippet'][:100]}...")
    return 0


def cmd_knowledge_freshness(settings: dict) -> int:
    from .curiosity.freshness import FreshnessTracker
    from .knowledge.engine import KnowledgeBase

    tracker = FreshnessTracker(knowledge=KnowledgeBase())
    status = tracker.status()
    print(f"Knowledge freshness ({status['total_entries']} entries):")
    print(f"  Fresh: {status['fresh_count']} (updated within {status['stale_days_threshold']} days)")
    print(f"  Stale: {status['stale_count']} (older than {status['stale_days_threshold']} days)")
    if status["stale_topics"]:
        print("\n  Stale topics:")
        for t in status["stale_topics"]:
            age = f"{t['age_days']:.0f} days" if t['age_days'] is not None else "never researched"
            print(f"    {t['topic']} ({age}, {t['word_count']} words)")
    if status["fresh_topics"]:
        print("\n  Fresh topics:")
        for t in status["fresh_topics"]:
            print(f"    {t['topic']} ({t['age_days']:.0f} days old, {t['word_count']} words)")
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

    p_research = sub.add_parser("research", help="research a topic via curiosity engine")
    p_research.add_argument("topic", help="topic to research")
    p_research.add_argument("--max-results", type=int, default=5, help="max search results")
    p_research.add_argument("--max-pages", type=int, default=3, help="max pages to scrape")

    p_wiki = sub.add_parser("wiki", help="fetch a Wikipedia article")
    p_wiki.add_argument("query", help="topic to look up on Wikipedia")

    p_guard = sub.add_parser("guardrails", help="inspect and test guardrails")
    p_guard.add_argument("action", choices=["list", "test"])
    p_guard.add_argument("text", nargs="?", default=None)

    p_eval = sub.add_parser("eval", help="evaluate model perplexity on a corpus")
    p_eval.add_argument("--corpus", required=True)
    p_eval.add_argument("--model-path", default=None)

    p_personality = sub.add_parser("personality", help="view or reload personality config")
    p_personality.add_argument("action", choices=["show", "reload"], nargs="?", default="show")

    p_knowledge = sub.add_parser("knowledge", help="manage knowledge base")
    p_knowledge_sub = p_knowledge.add_subparsers(dest="action", required=True)
    p_knowledge_sub.add_parser("list", help="list knowledge entries")
    p_knowledge_add = p_knowledge_sub.add_parser("add", help="add a knowledge entry")
    p_knowledge_add.add_argument("--topic", required=True)
    p_knowledge_add.add_argument("--file", help="file to read content from")
    p_knowledge_add.add_argument("--text", help="content as text")
    p_knowledge_rm = p_knowledge_sub.add_parser("remove", help="remove a knowledge entry")
    p_knowledge_rm.add_argument("--topic", required=True)
    p_knowledge_query = p_knowledge_sub.add_parser("query", help="search knowledge base")
    p_knowledge_query.add_argument("--text", required=True)

    sub.add_parser("facts", help="show remembered facts")

    sub.add_parser("freshness", help="show knowledge freshness status")
    sub.add_parser("gui", help="launch the desktop chat window (Tkinter)")

    p_agents = sub.add_parser("agents", help="show the onboard training crew")
    p_agents.add_argument("--run", metavar="NAME", default=None, help="run one agent now and print the result")

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
    if args.command == "research":
        return cmd_research(settings, args.topic, args.max_results, args.max_pages)
    if args.command == "wiki":
        return cmd_wiki(settings, args.query)
    if args.command == "eval":
        return cmd_eval(settings, args.corpus, args.model_path)
    if args.command == "personality":
        return cmd_personality(settings, args.action)
    if args.command == "knowledge":
        kwargs = {k: getattr(args, k, None) for k in ("topic", "text", "file")}
        return cmd_knowledge(settings, args.action, **kwargs)
    if args.command == "guardrails":
        return cmd_guardrails(settings, args.action, args.text)
    if args.command == "facts":
        return cmd_facts(settings)
    if args.command == "freshness":
        return cmd_knowledge_freshness(settings)
    if args.command == "gui":
        return cmd_gui(settings)
    if args.command == "agents":
        return cmd_agents(settings, args.run)
    return 2


def cmd_gui(settings: dict) -> int:
    from .agents import agents_enabled, build_crew
    from .gui.tk import run_tk_app

    engine = build_engine(settings)

    # The desktop app runs the crew in-process when it is enabled, so the
    # local GUI is somewhere the model trains and not only somewhere it talks.
    # No curiosity scheduler or critic is built here: those belong to `serve`,
    # and the researcher and grader report a skip with the reason rather than
    # pretending to work. The curator, gatherer and trainer are fully
    # functional without a server.
    supervisor = None
    if agents_enabled(settings):
        supervisor = build_crew(engine, settings=settings)
        supervisor.start()
    try:
        return run_tk_app(engine, supervisor=supervisor)
    finally:
        if supervisor is not None:
            supervisor.stop()


def cmd_agents(settings: dict, run: str | None) -> int:
    """Show the crew, or run one agent now and print what it did."""
    from .agents import DEFAULT_AGENT_SETTINGS, agents_enabled, build_crew

    engine = build_engine(settings)
    supervisor = build_crew(engine, settings=settings)

    if not agents_enabled(settings):
        print("Agents are disabled. Enable them in config/settings.json:\n")
        print('  "agents": ' + json.dumps(DEFAULT_AGENT_SETTINGS | {"enabled": True}, indent=2))
        print("\nShowing the crew as it would be configured:\n")

    if run:
        agent = supervisor.get(run)
        if agent is None:
            print(f"No such agent: {run}")
            print("Known: " + ", ".join(a.name for a in supervisor.agents))
            return 2
        report = agent.run()
        print(json.dumps(report.as_dict(), indent=2, default=str))
        return 0

    for agent in supervisor.agents:
        state = "enabled" if agent.enabled else "disabled"
        cadence = agent.cadence_seconds / 60.0
        print(f"{agent.name:<11} {state:<9} every {cadence:g}m  {agent.role}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
