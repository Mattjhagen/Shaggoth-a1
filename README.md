# Shaggoth

A homegrown, from-scratch conversational AI platform with **adjustable guardrails**,
**persistent memory**, and a **plugin system** — designed as a base platform for other
projects, and as the backend for future native iOS/Android apps.

Zero required dependencies: everything in Phase 1 runs on the Python 3.10+ standard
library, so it works identically on a laptop, a cloud sandbox, or the Dell R510.

## Quick start

```bash
# Interactive chat (REPL)
python3 -m shaggoth chat

# Start the REST API server (for apps / curl)
python3 -m shaggoth serve --port 8420

# Train the built-in Markov language model on a corpus
python3 -m shaggoth train --corpus data/corpus/starter.txt

# Inspect / test guardrails
python3 -m shaggoth guardrails list
python3 -m shaggoth guardrails test "some message to check"

# See what Shaggoth remembers about you
python3 -m shaggoth facts
```

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

## What's inside

| Component | Path | What it does |
|---|---|---|
| Dialogue engine | `shaggoth/dialogue/` | Orchestrates guardrails → plugins → memory → generation |
| Guardrails | `shaggoth/guardrails/` | Hot-reloadable JSON rules: block, refuse, redact, limit |
| Memory | `shaggoth/memory/` | SQLite store; extracts facts, recalls past topics to trigger callbacks |
| Models | `shaggoth/models/` | Trainable Markov generator (stdlib) + from-scratch TinyGPT transformer (optional PyTorch, for the R510) |
| Plugins | `shaggoth/plugins/` | Add features: built-ins include time, math, remember/recall |
| API server | `shaggoth/server.py` | Stdlib HTTP JSON API with CORS — the mobile-app backend |

## Adjusting guardrails

Edit `config/guardrails.json` — the engine hot-reloads on file change. Each rule has an
`id`, a `type` (`regex_block`, `topic_refuse`, `redact`, `max_length`), and an `action`
message you control. Rules can also be listed/tested from the CLI and managed over the
HTTP API (`GET /guardrails`, `POST /guardrails/rules`, `DELETE /guardrails/rules/<id>`).

## Memory that triggers topics

Every conversation is stored in SQLite (`data/shaggoth.db`). Shaggoth extracts facts
("my name is Matt", "I like synthwave") and keyword-indexes every message. When a new
message overlaps strongly with an *earlier* conversation, the reply weaves in a callback:
*"By the way — last time we talked about your homelab…"*.

## Docs

- [`docs/RESEARCH.md`](docs/RESEARCH.md) — AI history: Turing (1950) → ELIZA (1966) → GPT/OpenAI, and what each era taught us that shaped this design
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how the pieces fit, and the extension points
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — Phases 0–4, including the native iOS/Android apps
- [`docs/R510_SETUP.md`](docs/R510_SETUP.md) — Tailscale SSH to the R510, running opencode + Big Pickle, training TinyGPT

## License

MIT
