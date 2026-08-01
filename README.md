# Shaggoth

A homegrown, self-learning conversational AI that runs on **your own hardware**
with **zero required dependencies** — or, when you want a boost, on **free-tier
cloud models** with a one-line opt-in.

No wrapper around someone else's product. The dialogue engine, knowledge base,
memory, guardrails, the Markov generator, and the self-improvement loop are all
built here, from scratch, on the Python standard library. It runs identically
on a laptop, a cloud sandbox, or an old rack server.

```
$ pip install shaggoth
$ shaggoth chat
you> what is machine learning
shag> [knowledge] Machine learning (ML) is a field of study in artificial
      intelligence concerned with the development and study of statistical
      algorithms that can learn from data and generalize to unseen data.
```

## Highlights

- **No filter, by default.** Guardrails ship with the *safety floor only*
  (credentials, malware, reply length) — the voice is unfiltered, sarcastic,
  and honest. Every guardrail is a JSON rule you can edit by hand, hot-reloads
  at runtime, and can be tuned per deployment (`config/guardrails.json`).
- **Knowledge-first answering.** A BM25 knowledge base built from web research
  (Wikipedia, crawl-permissive sources) answers "what is X" with the real
  definition, attributed per entry. When it doesn't know, it says so — and
  then **goes and learns it**.
- **Onboard AI agents that train it.** A supervisor starts a crew of
  on-device agents alongside the server: a *researcher* that turns
  conversations into research topics, a *grader* that self-grades past answers
  on idle capacity, a *curator* that keeps the knowledge base clean, a
  *gatherer* that reads crawl-permissive sources, and a *trainer* that
  retrains the model behind a quality gate. All local, all free, all
  optional.
- **Persistent memory.** SQLite-backed conversation history, fact extraction
  ("my name is Matt"), topic recall, and long-context compaction.
- **Feedback → repair loop.** 👍/👎 on any reply implicates a *specific
  knowledge entry*; a repair queue re-researches it before anything age-based.
- **Hybrid inference.** Local by default (Markov, stdlib). Opt in to a
  free-tier cloud model (Gemini or Cloudflare Workers AI, plain `urllib`, no
  SDK) or a paid OpenAI backend. Swappable through one interface.
- **Web dashboard + REST API + desktop GUI.** `shaggoth serve` gives you the
  browser UI and JSON API. `shaggoth gui` gives you a Tkinter desktop app
  (stdlib, no display server required at build time).
- **Guardrails, memory, plugins, personality** all hot-reloadable, all JSON.

## Quick start

```bash
# install
pip install -e .        # or: pip install shaggoth

# interactive chat (REPL)
shaggoth chat

# desktop GUI (needs python3-tk)
shaggoth gui

# web dashboard + REST API
shaggoth serve --host 127.0.0.1 --port 8420
# open http://127.0.0.1:8420

# train the built-in Markov model on your own corpus
shaggoth train --corpus my_notes.txt --model markov

# scrape a URL and learn from it
shaggoth learn --urls https://example.org

# research a topic the knowledge-first way
shaggoth research "quantum computing"
```

Run the test suite:

```bash
PYTHONPATH=. pytest tests/ -q
```

## Hybrid inference (free or onboard)

`config/settings.json` → `"model"`:

| value | backend | cost |
|---|---|---|
| `auto` (default) | local Markov model, stdlib | free, offline |
| `markov` | same as auto | free, offline |
| `tinygpt` | local TinyGPT transformer (`pip install torch`) | free, offline |
| `gemini` | Google Gemini free tier via REST | free tier / key |
| `cloudflare` | Cloudflare Workers AI free tier via REST | free tier / token |
| `cloud` | the first of the above that has a key set | varies |

Local is always the default and always works offline. Cloud backends are
plain `urllib` (no SDKs) and fall back to the local model when no key is set:

```bash
# Gemini free tier
GEMINI_API_KEY=... shaggoth serve
# or in settings.json: "model": "gemini"

# Cloudflare Workers AI
CLOUDFLARE_ACCOUNT_ID=... CLOUDFLARE_WORKERS_AI_TOKEN=... shaggoth serve
```

## What's inside

| Component | Path | What it does |
|---|---|---|
| Dialogue engine | `shaggoth/dialogue/` | Guardrails → memory → knowledge → reasoning → generation, in character |
| Knowledge base | `shaggoth/knowledge/` | BM25 retrieval over `data/knowledge/*.md`, definition-first answers |
| Reasoning | `shaggoth/dialogue/reasoning.py` | compare / contrast / causal / enumerate from real corpus sentences |
| Memory | `shaggoth/memory/` | SQLite store; facts, recall, compaction |
| Models | `shaggoth/models/` | Markov (stdlib), TinyGPT (optional torch), cloud backends — one interface |
| Agents | `shaggoth/agents/` | Onboard crew that researches, grades, curates, gathers, trains |
| Guardrails | `shaggoth/guardrails/` | Hot-reloadable JSON rules |
| Plugins | `shaggoth/plugins/` | time, math, remember/recall, URL reading |
| API server | `shaggoth/server.py` | Stdlib HTTP JSON API + web dashboard |
| GUI | `shaggoth/gui/` | Tkinter desktop app (stdlib) |
| Curiosity | `shaggoth/curiosity/` | The self-learning loop: conversation → research → knowledge |
| Feedback | `shaggoth/feedback/` | Repair queue driven by 👍/👎 judgements |

## How it learns, 24/7

1. You chat. Every `source: fallback` reply (it didn't know) becomes a
   research topic.
2. The **researcher** agent (or the curiosity scheduler) researches the topic
   from crawl-permissive sources and writes it to the knowledge base.
3. The **grader** agent grades past answers on idle capacity (local Ollama by
   default) and files bad ones for re-research.
4. 👍/👎 on any reply implicates the exact entry it came from; a complaint
   re-queues it ahead of everything else.
5. The **curator** agent keeps the corpus clean (dedupes question-named
   duplicates, flags fragments).
6. The **trainer** agent retrains the Markov model nightly behind a quality
   gate (coherence + perplexity) — nothing bad is ever promoted to the live
   path.

## Configuration

Everything is JSON, everything hot-reloads:

- `config/guardrails.json` — the filter, rule by rule
- `config/personality.json` — voice, traits, backstory
- `config/settings.json` — model, dialogue mode, server, agent cadences
- `.env.example` → `.env` — API keys and service tokens

## Docs

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit, and the extension points
- [`docs/RESEARCH.md`](docs/RESEARCH.md) — AI history (Turing → ELIZA → GPT) and what each era taught us
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — where this is going
- [`docs/TRAINING_AUTOMATION.md`](docs/TRAINING_AUTOMATION.md) — the self-improvement loop, in depth

## License

MIT — see [LICENSE](LICENSE). Homegrown, open, yours.
