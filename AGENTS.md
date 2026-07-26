# Shaggoth AI — Development Notes

## Project Overview
Shaggoth is a Python conversational AI platform (stdlib-only, no deps) with:
- Guardrails engine (hot-reloadable JSON rules)
- Memory store (SQLite: messages, facts, topic recall via TF-IDF)
- Plugin system (time, calculator, remember/recall)
- Knowledge base (file-backed .md entries with keyword index)
- Scraper engine (stdlib urllib, SQLite-backed)
- Learner pipeline (scrape → train Markov/TinyGPT)
- REST API server with SSE streaming
- Personality engine (JSON config)
- Dialogue pipeline: guardrails → knowledge → plugins → memory → generation → recall → output guardrails

## Architecture: Dialogue Pipeline (`shaggoth/dialogue/engine.py`)
```
1. guardrails  — input rules may block/refuse
2. knowledge   — retrieve relevant entries (TF-IDF keyword match)
3. plugins     — feature commands get first crack
4. memory      — extract facts; find topic overlaps
5. generation  — pattern engine, else language model
6. recall      — topic callback from past conversations
7. guardrails  — output rules (redaction, length)
8. persist     — store both sides in memory
```

## What We Just Built: Curiosity Engine (`shaggoth/curiosity/`)
New package that adds autonomous knowledge acquisition:

### Files Created
- `shaggoth/curiosity/__init__.py` — exports CuriosityEngine
- `shaggoth/curiosity/search.py` — DuckDuckGo HTML search (stdlib urllib, no API key)
- `shaggoth/curiosity/topics.py` — topic detection from user messages, gap analysis
- `shaggoth/curiosity/engine.py` — core CuriosityEngine: detect gaps → search → scrape → store
- `shaggoth/curiosity/scheduler.py` — background thread that periodically scans messages for gaps
- `tests/test_curiosity.py` — 24 tests, all passing

### Files Modified
- `shaggoth/plugins/builtin.py` — added `curiosity` plugin (responds to "research X", "look up X", "learn about X")
- `shaggoth/server.py` — added 7 new API endpoints for curiosity control

### How It Works
1. User says "what is X?" → `analyze_message()` extracts topic
2. Checks if knowledge base already covers it (keyword overlap ≥ 60%)
3. If gap detected → `search_web()` queries DuckDuckGo HTML
4. Scrapes top results via existing `ScraperEngine`
5. Chunks text into ~2000-word knowledge entries
6. Stores in KnowledgeBase via `add_entry()`

### New API Endpoints
- `GET /curiosity/status` — engine status, episode count
- `GET /curiosity/history` — past research episodes
- `GET /curiosity/scheduler` — scheduler status
- `POST /curiosity/research` — manually trigger research on a topic
- `POST /curiosity/ingest` — directly ingest text or URLs
- `POST /curiosity/scheduler/trigger` — trigger a scheduler cycle
- `POST /curiosity/message` — feed a message for gap detection

### Plugin Usage
User says: "research quantum computing" → plugin triggers background research, replies "I'm researching..."

## Key Extension Points
- **Plugins**: `shaggoth/plugins/__init__.py` → `PluginRegistry.register(name)`
- **Knowledge**: `shaggoth/knowledge/engine.py` → `KnowledgeBase.add_entry(topic, content)`
- **Memory facts**: `shaggoth/memory/store.py` → `MemoryStore.extract_and_store_facts(text)`
- **Scraper**: `shaggoth/scraper/engine.py` → `ScraperEngine.fetch_page(url)`
- **Background tasks**: use `threading.Thread(daemon=True)` pattern (see learner/pipeline.py)

## Pre-existing Test Failures (NOT from our changes)
8 failures + 4 errors in guardrails/dialogue/memory tests. Confirmed same count before and after curiosity changes. Root causes:
- SQLite schema has `user_id` column but some queries don't match ON CONFLICT clauses
- Guardrail rules not loading from default config properly in test environment

## Commands
- `python3 -m shaggoth chat` — interactive REPL
- `python3 -m shaggoth serve` — REST API + dashboard
- `python3 -m shaggoth learn --urls URL` — scrape + train
- `python3 -m shaggoth knowledge list` — show knowledge entries
- `python3 -m unittest tests.test_curiosity -v` — run curiosity tests

## Deployment
- Shaggoth repo: `github.com/Mattjhagen/Shaggoth-a1` (branch: `claude/ai-model-guardrails-platform-o6b50g`)
- Archon IDE repo: `github.com/Mattjhagen/archon-ide` (also copied to `Relay/archon-ide/`)
- Relay repo: `github.com/Mattjhagen/Relay` (gateway homepage)
- Cloudflare Pages: `docs.relayapp.pro` (Account ID: `b36aaecab5f5f0c07ef80a83a1e6c561`)
- Fly.io: `archon-ide-pacmac` → `app.relayapp.pro`, `ide.relayapp.pro`

## Cloudflare Docs Deployment
Set env vars `CF_TOKEN` and `ACCT_ID` (Account ID: `b36aaecab5f5f0c07ef80a83a1e6c561`), then:
`CLOUDFLARE_API_TOKEN=$CF_TOKEN CLOUDFLARE_ACCOUNT_ID=$ACCT_ID npx wrangler pages deploy . --project-name=archon-docs --commit-dirty=true`

## What's Next for Curiosity
- [ ] Feed conversation history into scheduler for continuous learning
- [ ] Add "curiosity level" setting (how aggressive to research)
- [ ] Add deduplication: don't re-research recently covered topics
- [ ] Add topic scoring: prioritize topics with more mentions
- [ ] Add knowledge freshness: re-research stale entries periodically
- [ ] Add "what did you learn recently?" command to surface recent knowledge
- [ ] Integrate with TinyGPT training: auto-train after curiosity episodes
- [ ] Add Wikipedia/Wikimedia API as additional source
- [ ] Add RSS feed monitoring for ongoing topic tracking
