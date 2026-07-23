# Architecture

Shaggoth is a **base platform**: a small, readable core with hard extension
points. Every subsystem is swappable by constructor injection — nothing
reaches into globals.

## The message pipeline

```
user message
   │
   ▼
┌───────────────┐  blocked → refusal reply (rule's own message)
│ 1. Guardrails │──────────────────────────────┐
│    (input)    │                              │
└──────┬────────┘                              │
       ▼                                       │
┌───────────────┐  handled → plugin reply      │
│ 2. Plugins    │──────────────────────────┐   │
└──────┬────────┘                          │   │
       ▼                                   │   │
┌───────────────┐                          │   │
│ 3. Memory     │ extract facts,           │   │
│               │ find topic overlaps      │   │
└──────┬────────┘                          │   │
       ▼                                   │   │
┌───────────────┐ pattern engine first,    │   │
│ 4. Generation │ language model second,   │   │
│               │ fallback last            │   │
└──────┬────────┘                          │   │
       ▼                                   │   │
┌───────────────┐ "last time you           │   │
│ 5. Recall     │  mentioned …"            │   │
└──────┬────────┘                          │   │
       ▼                                   ▼   │
┌───────────────┐                              │
│ 6. Guardrails │ redact / truncate            │
│    (output)   │◄─────────────────────────────┘
└──────┬────────┘
       ▼
┌───────────────┐
│ 7. Persist    │ both turns → SQLite
└──────┬────────┘
       ▼
    reply (+ metadata: source, rules fired, memory triggers, new facts)
```

Implementation: `shaggoth/dialogue/engine.py` (`DialogueEngine.respond`).
Every reply carries metadata about *why* it is what it is — which guardrail
fired, which plugin answered, what memory was recalled. Observability is a
feature of the platform, not a debug afterthought.

## Subsystems

### Guardrails (`shaggoth/guardrails/engine.py`)
JSON rules in `config/guardrails.json`; hot-reloaded on mtime change.
Input rules (`regex_block`, `topic_refuse`) run before anything else and
short-circuit the pipeline. Output rules (`redact`, `max_length`) run on every
reply — including plugin and pattern replies. Rules are added/removed/toggled
at runtime via Python API, CLI, or HTTP.

Adding a rule *type* = one `elif` in `check_input`/`filter_output`. Planned
types live in ROADMAP (rate limits, per-session overrides, classifier hooks).

### Memory (`shaggoth/memory/store.py`)
Single SQLite file, three tables: `messages` (full transcript, per session),
`keywords` (inverted index), `facts` (key → value). Fact extraction is
regex-based information extraction; topic recall is TF-IDF-weighted keyword
overlap restricted to *other* sessions, so callbacks reference genuinely past
conversations. The `Recall` dataclass is the interface — an embedding-based
recaller can replace the keyword one without the dialogue engine noticing.

### Models (`shaggoth/models/`)
`LanguageModel` ABC: `train / generate / save / load / is_trained`.
- `MarkovModel` — Shannon-style word n-gram; stdlib; trains in milliseconds.
- `TinyGPTModel` — decoder-only transformer (char-level), optional PyTorch;
  the model you train on the R510. Same interface, so `build_engine` can swap
  it in via config once a checkpoint exists.

### Plugins (`shaggoth/plugins/`)
Ordered registry of `f(text, **context) -> str | None`. First non-None wins.
Built-ins (time, safe AST calculator, `remember X is Y`, "what do you know
about me") double as examples. This is the seam where future tools —
weather, home-automation, search — attach without touching the core.

### API server (`shaggoth/server.py`)
Stdlib `ThreadingHTTPServer`, JSON + CORS. One `DialogueEngine` instance
serves all sessions; SQLite connection uses `check_same_thread=False` and
the guardrail engine locks around mutation. This is the contract the mobile
apps build against (`POST /chat`, `GET /history`, `GET /facts`,
`GET|POST|DELETE /guardrails…`).

## Design rules for contributors (including future us)

1. **Stdlib by default.** New required dependencies need a reason written in
   the PR. Optional heavyweights (torch) stay behind import guards.
2. **Everything injectable.** New subsystems take their collaborators as
   constructor arguments and provide an in-memory default for tests.
3. **Metadata over magic.** If a stage changes a reply, it must say so in the
   `Reply` metadata.
4. **Tests are the spec.** `tests/` runs with `python3 -m unittest discover
   -s tests` in under two seconds, no network, no GPU.
