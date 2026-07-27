# AGENTS.md — Shaggoth / Relay / Archon Handoff

**Purpose:** resume work after a context reset. Everything here was *verified by command*, not assumed.
**Last verified:** 2026-07-27 ~02:05 UTC

---

## 1. Where things actually run

| Layer | Host | Detail |
|---|---|---|
| **Shaggoth inference** | **r510-1** (`matt@100.103.3.35`) | 16 cores, 39 GB RAM, Ubuntu 24.04, Python 3.12.3. **This is the AI compute.** |
| Shaggoth overflow (planned) | MacBook Air `100.67.199.109` | Also runs a Shaggoth instance on :8420 |
| Rust backend + React IDE | Fly.io `archon-ide-pacmac` (ord) | Orchestration only — **no model inference** |
| Anthropic / OpenAI / Gemini | Their clouds | Only when selected as provider |
| Ollama | r510-1 | `ollama.service` active |

**Fly reaches Shaggoth over Tailscale.** Fly is a proxy, not the compute.

### Live URLs
- `https://ide.relayapp.pro` — **the real, working Archon IDE** (Fly)
- `https://archon-ide-pacmac.fly.dev` — same app, direct
- `https://r510-1.tail3f2448.ts.net` — Shaggoth HTTPS (**tailnet-only**, real LE cert)
- `https://mattys-macbook-air.tail3f2448.ts.net` — MacBook Shaggoth (tailnet-only)
- `https://docs.relayapp.pro/ide` — ⚠️ **stale prototype, not the real IDE** (see §5)

---

## 2. Access

```bash
ssh matt@100.103.3.35        # r510-1, key auth works, NO passwordless sudo
```

- `~/.ssh/config` has `Host r510` → `192.168.0.169` (LAN, currently unreachable — use the Tailscale IP)
- **sudo on r510 requires a password.** Do not ask the user for it. Work around it (see §4).
- `loginctl show-user matt` → **`Linger=yes`** — user systemd units run 24/7 without login.
- `gh` CLI auth is **broken** (invalid keyring token). Git over SSH works.

---

## 3. Shaggoth state (verified)

### Two installs, same repo, different branches
| Path | Branch | Has curiosity? |
|---|---|---|
| `~/Shaggoth-a1` | `main` @ `e033ae8` | ❌ No |
| `~/shaggotha1` | `claude/ai-model-guardrails-platform-o6b50g` @ `1cf466f` | ✅ **Yes** |

**The running process is the manual one from `~/shaggotha1`** (has curiosity).
`shaggoth.service` (`/etc/systemd/system/`) points at `~/Shaggoth-a1` and is **crash-looping**
with `OSError: [Errno 98] Address already in use` — port 8420 held by the manual process.

> ⚠️ **Reboot hazard:** as-is, a reboot boots the OLD curiosity-less code. Fixed by §4 consolidation.

### Data location
`DATA_DIR = ROOT/data` where `ROOT = $SHAGGOTH_ROOT` or the install dir.
Live data → **`/home/matt/shaggotha1/data`**. `SHAGGOTH_ROOT` env var can override.

### Curiosity engine — already built
`shaggoth/curiosity/`: `engine.py`, `scheduler.py`, `search.py`, `topics.py`,
`wikipedia.py`, `freshness.py`. Also `scraper/`, `learner/`, `knowledge/`, `memory/`.

`serve()` auto-starts the scheduler (`scheduler.start()`), and every `/chat` message is fed to
`scheduler.record_message()` → **curiosity clues come from conversation already.**

### Verified status snapshot
```
/curiosity/scheduler  → {"enabled": true, "interval_minutes": 60,
                         "buffered_messages": 4, "thread_alive": true}
/scrape/stats         → 8 pages, 161,004 words, 34 seeds (7 done/27 pending), 0 errors
/curiosity/status     → total_episodes: 0, knowledge_entries: 1
```

**Why 0 episodes:** `ScheduleConfig.min_message_count = 5`, only 4 buffered, 60-min interval.
Not broken — never triggered. Tune in `shaggoth/curiosity/scheduler.py`.

### Working API endpoints
`/health` `/chat` `/chat/stream` `/history` `/facts` `/guardrails`
`/learn/start` `/learn/status` `/scrape/url` `/scrape/stats`
`/curiosity/research|status|history|ingest|ingest-wiki|freshness|refresh-stale|scheduler`
`/wiki?q=topic`

`POST /chat` body `{"message": "...", "session_id": "..."}` → response field **`reply`**
(the Rust backend depends on this exact shape).

---

## 4. COMPLETED this session ✅

### 4a. Knowledge seeding — DONE
`~/seed_knowledge.py` ingested **104 Wikipedia topics → 692,622 words → 305 knowledge entries**,
0 failures. Corpus at `data/knowledge/*.md` (4.4 MB). Log: `~/seed_knowledge.log`.

### 4b. Markov model trained — DONE
```bash
cat data/knowledge/*.md > data/corpus/knowledge_corpus.txt   # 674k words
python3 -m shaggoth train --corpus data/corpus/knowledge_corpus.txt --model markov
# → 4,095,782 chars, 322,094 contexts → data/markov_model.json (12 MB)
```
**Before this, `data/markov_model.json` did not exist** — which is why `/chat` only ever
returned `source: "pattern"` (canned lines). Training is what unlocked `source: "model"`.

### 4c. Directory consolidation — DONE
- `~/stash/Shaggoth-a1.main-2026-07-27` ← old `main` branch (no curiosity)
- `~/Shaggoth-a1` ← **canonical**, curiosity branch + trained model + 305 entries
- `~/shaggotha1` → symlink to `~/Shaggoth-a1`

`shaggoth.service` now runs the correct code, bound to **`0.0.0.0:8420`** (so Fly can reach it
directly at `100.103.3.35:8420`), `Restart=always`, reboot-safe. **No sudo was needed.**

### 4d. Two engine bugs fixed (backups: `*.py.bak` beside each file)

**`shaggoth/dialogue/engine.py`** — knowledge-first answering.
`patterns.respond()` ran *before* knowledge, so canned lines won. Knowledge was only injected as
a *prompt* to the Markov model, which cannot follow a prompt → word salad. A hardcoded quirk
appended *"I just read something about X — want me to tell you about it?"*, so it **offered**
answers instead of giving them (the "never completes a thought" symptom).
Added `_looks_like_question()`, `_clean_sentences()`, `summarize_entry()` and a knowledge-first
branch returning `source="knowledge"`; teaser suppressed when it already answered.

**`shaggoth/knowledge/engine.py`** — BM25 ranking.
Old `query()` summed IDF once per distinct term, with **no term frequency, no length
normalization**, and tie-broke on `-word_count` (**preferring the longest doc**). Result:
"what is machine learning?" → a Swedish rock band. Replaced with Okapi BM25 (k1=1.5, b=0.75)
plus an 8.0 title-match boost, scores normalized 0..1, tie-break toward *shorter* articles.

Verified after fix: machine learning→Machine Learning, photosynthesis→Photosynthesis,
quantum mechanics→Quantum mechanics, DNA→DNA. All `source: knowledge`.

---

## 5. Pending work

| # | Task | Blocker |
|---|---|---|
| 1 | Consolidate dirs, systemd reboot-safety | Waiting on 4a |
| 2 | `docs.relayapp.pro/ide` + site chat bubble | See below |
| 3 | Shaggoth dashboard tabs | — |
| 4 | 24/7 continuous learning tuning | — |
| 5 | CPU-overflow failover to 2nd node | — |
| 6 | PWA on relayapp.pro + notifications | **Cloudflare tunnel creds** |
| 7 | News/social/Reddit scraping | — |
| 8 | Health monitoring → `r510-command-center` repo | — |

### §5.2 detail — docs site
Source = **`archon-ios` repo, `Docs` branch** (worktree already at `/tmp/docs-wt`).
- `docs/ide.html` + `docs/js/ide.js` — static prototype, hardcodes
  `"AI responses require a backend connection. This is a frontend prototype."` → should redirect to
  `https://ide.relayapp.pro`. There's a `_redirects` file (Cloudflare Pages) — cleanest lever.
- `docs/js/chat-widget.js` — canned FAQ bot. Hardcoded stale models (GPT-4o, Claude 3.5,
  Gemini 1.5, Ollama). Makes **zero** network calls.
  ⚠️ All Fly `/api/*` routes require Supabase auth, so the widget needs a **public unauthenticated
  endpoint**. Recommendation: route it to Shaggoth only (self-hosted = no API credit exposure),
  rate-limited, with graceful fallback to canned answers when Shaggoth is offline.

### §5.6 detail — public domain
**Tailscale Serve is tailnet-only.** For `shaggoth.relayapp.pro` you need a **named Cloudflare
tunnel**. The `cloudflared` on r510 is an *ephemeral quick-tunnel* (`--url http://localhost:3847`)
→ random `trycloudflare.com`, unrelated. Needs `cloudflared tunnel login` (interactive) or a
dashboard token. Cloudflare MCP available here has only D1/KV/R2/Workers — **no DNS or tunnel tools.**
PWA assets already exist: `shaggoth/static/{manifest.json,sw.js,pwa-192.png,pwa-512.png,favicon.svg}`
plus `generate-pwa-icons.py` (regenerate icons from favicon per user request).

**Open question for user:** public endpoint gated with `SHAGGOTH_API_KEY`, or open?

---

## 6. Fly.io

App `archon-ide-pacmac`, region `ord`, v48+. `flyctl` authed as `matty@purepulse.one`.

Secrets set: `ANTHROPIC_API_KEY` `OPENAI_API_KEY` `OPENROUTER_API_KEY` `SUPABASE_*`
`OPENCODE_*` `TAILSCALE_AUTHKEY` `ALLOWED_ORIGINS` `SITES_BASE_DOMAIN` `SHAGGOTH_BASE_URL`

`SHAGGOTH_BASE_URL` currently `http://100.67.199.109:8420` (**MacBook**).
→ **TODO: repoint to r510** once consolidated: `http://100.103.3.35:8420`.

> ⚠️ `start.sh` runs tailscaled with **`--accept-dns=false`** → the container **cannot resolve
> MagicDNS names**. Use raw Tailscale IPs in `SHAGGOTH_BASE_URL`, *not* `*.ts.net` hostnames,
> unless you also add an `/etc/hosts` entry in `start.sh`.

Certs: `ide.relayapp.pro` ✅ Issued · `app.relayapp.pro` ✅ Issued (added this session) ·
`vibecodes.space` ✅

Provider code (both already support `auto` + `shaggoth`):
- `archon-ide/backend/src/ai.rs` → `list_providers()`, `chat()`, `chat_shaggoth()`, `chat_auto()`
- `archon-ide/backend/src/agent/model_adapter.rs` → `call_shaggoth()` (line ~354), `call_auto()` (~417)
- Auto priority: Anthropic → OpenAI → Gemini → Ollama → Shaggoth

Deploy: `cd archon-ide && flyctl deploy -a archon-ide-pacmac` (Rust build, several minutes).

---

## 7. Storage (r510) — not a constraint

```
/dev/mapper/ubuntu--vg-ubuntu--lv   98G   37G used   57G free   40%
sda 837.3G   sdb 2T          ← ~2.7 TB unallocated
```
Shaggoth data 2.4 MB and growing slowly. Expanding the LVM into free space **requires sudo**
(`lvextend` + `resize2fs`) — optional, hand the commands to the user.

---

## 8. Hard-won gotchas

1. **`docs.relayapp.pro/ide` is NOT the real IDE.** The real one is `ide.relayapp.pro`. Don't
   debug the prototype thinking it's the app.
2. **Never send secrets/passwords through the conversation.** Give the user commands to run.
3. Fly container can't resolve MagicDNS (`--accept-dns=false`) — use Tailscale IPs.
4. Tailscale IPs are **stable across reboots** (assigned at node registration). `100.103.3.35` = r510-1,
   `100.67.199.109` = MacBook Air.
5. `tailscale serve` works **without sudo** on r510; needs root on many other setups.
6. Tailscale **Serve** = tailnet-only. **Funnel** = public but only on `*.ts.net`.
7. Shaggoth `/chat` returns **`reply`** (not `response`) — the Rust adapter depends on it.
8. Don't `git checkout` in `~/shaggotha1` while the service runs from it.
9. Heredoc + f-string + `\"` = SyntaxError. Use single quotes inside f-strings.
10. `r510` (100.105.154.91) is **offline**; the live box is **`r510-1` (100.103.3.35)**.

---

## 4e. Relevance fixes (later in the same session)

**Symptom:** asked for a story, Shaggoth replied *"Kwak'wala, sentences begin with what was
predicted by Planck's law was heavily influenced by Greek historian Dionysius of Halicarnassus"*
— five unrelated subjects in one sentence.

**Cause chain (all three linked):**
1. Markov trained on an encyclopedia cannot hold a topic; it stitches fragments from unrelated
   articles.
2. That garbage was returned as `source="model"`. **`server.py:222` only triggers curiosity
   auto-research when `source == "fallback"`** — so every incoherent answer *suppressed* the
   research that would have taught it the topic. This is why `total_episodes` was stuck at 0.
3. Normalizing BM25 scores against the best hit makes the top result **always exactly 1.0**, so
   the `top_score >= 0.35` confidence check was a silent no-op. "you tell me a story" scored the
   film *Brokeback Mountain* at 1.0 because the word "story" appears in it.

**Fixes in `dialogue/engine.py`** (backups `.bak`, `.bak2`, `.bak3`):
- `markov_is_usable()` — rejects topic-salad (>1 unrequested proper noun, >28 words, encyclopedia
  artifacts, no terminal punctuation). Rejection is deliberate: the turn degrades to `fallback`,
  which is what makes curiosity research fire.
- `knowledge_is_relevant()` — requires the article **title** to overlap the question's content
  words. A normalized score cannot express "nothing here is relevant"; title overlap can.
- `_FILLER` set so conversational filler ("tell", "me", "story", "about") cannot carry a match.
- `describe_unknown()` — relevant "I don't know X yet, researching it" instead of a random line.
- Broadened `_QUESTION_HINT` + `.search()` instead of `.match()` so "you tell me a story" counts.
- Strengthened `_NOISE` for lead-in cruft ("For other uses, see", "Not to be confused with").
- **Gotcha:** `extract_keywords` is NOT imported in `engine.py` by default — must add
  `from ..memory.store import extract_keywords` or you get a NameError and empty 500s on /chat.

Verified: story→fallback+research, machine learning→Machine Learning, photosynthesis→Photosynthesis.

## 4f. Cloudflare tunnel — UNBLOCKED

`~/.cloudflared/cert.pem` **now exists on r510** (user completed `cloudflared tunnel login`).
Named tunnel + `shaggoth.relayapp.pro` DNS route can now be created. `cloudflared` is at
`~/.local/bin/cloudflared` (**not on PATH**). Existing running instance is an unrelated ephemeral
quick-tunnel to port 3847 — leave it alone.

## 4g. Site scraping seed list

`~/seed_sites.py` — broad seed list across reference / science / health / tech / news-RSS /
Reddit-JSON. Log: `~/seed_sites.log`.
⚠️ **The scraper does NOT honour robots.txt** (`scraper/engine.py` has no robots handling). The
list is therefore weighted to crawl-permissive sources (Wikimedia, Gutenberg, US government,
open-access science) and uses RSS for news rather than crawling article pages. **Add robots.txt
support before broadening to arbitrary sites.**

## 4h. PUBLIC URL LIVE + self-learning loop verified

**`https://ai.relayapp.pro`** — public, valid cert, serving Shaggoth. Also
`https://shaggoth.relayapp.pro` (same tunnel).

- Tunnel `shaggoth` id `54251949-a47b-4a0e-a998-0b32d743a8b2`
- Config `~/.cloudflared/shaggoth-config.yml` → ingress to `127.0.0.1:8420`
- Service `~/.config/systemd/user/cloudflared-shaggoth.service` (enabled, Linger=yes → 24/7)
- `cloudflared` is at `~/.local/bin/cloudflared`, **not on PATH**

**Self-learning loop verified end-to-end:**
1. "what is aeroponic farming" → `source: fallback` (in character)
2. Curiosity auto-researched → episode `curiosity-61f07b79`, 3 queries, 2 pages, **3,253 words**
3. Same question again → `source: knowledge`. KB grew 305 → 307.

`total_episodes` went 0 → 1. **The blocker was the Markov gate**: leaked garbage was returned as
`source="model"`, and `server.py:222` only researches on `source == "fallback"`. Tightening the
gate (digit-density, min-length, and requiring ≥1 shared content word with the question) is what
made curiosity actually fire.

**Persona/voice added** (`dialogue/engine.py`): `describe_unknown()` now returns varied,
in-character "don't know yet" lines naming the subject; `compose_greeting()` + new
**`GET /greeting`** endpoint returns a fresh opening each load, citing knowledge count / most
recent topic. Voice: sarcastic, sharp, no filter.
⚠️ `KnowledgeBase` has **no `entries()` method** — use `maybe_reload()` then `._entries`.

## 4i. Shaggoth engine work COMMITTED

Commit **`62f339d`** on branch `claude/ai-model-guardrails-platform-o6b50g` in
`Mattjhagen/Shaggoth-a1` — pushed, working tree clean. Covers the BM25 ranking fix, relevance
gating, the curiosity-deadlock fix, definitional selection, and the greeting/persona work.

- 11 `.bak` files moved out of the repo to `~/stash/engine-backups/`
- `.gitignore` extended for generated artifacts (`data/knowledge/`, the corpus, curiosity history,
  freshness/learning JSON). **Regenerate with** `~/seed_knowledge.py` then
  `python3 -m shaggoth train --corpus data/corpus/knowledge_corpus.txt --model markov`
- The trained `markov_model.json` (12 MB) was already gitignored — it is **not** in the repo, so a
  fresh clone must retrain before `/chat` will return `source: model`.

## 8b. Known-remaining Shaggoth issues (next session starts here)

1. ~~Wikipedia cruft leaks~~ **DONE — definitional selection built and verified.**
   Blacklisting was replaced with positive selection. Five fixes, each found by testing:
   a. `summarize_entry(content, topic)` now ranks sentences: definitional → mentions-topic →
      article head. Supporting sentences must stay on subject.
   b. `_is_definitional()` requires the topic to **lead** the sentence (appear before the defining
      verb, within 12 words). Without this, "Data mining **is** a related field ... unsupervised
      **learning**" qualified as a definition of *machine learning*.
   c. `_stem_match()` (4-char prefix) so `aeroponic`↔`aeroponics`, `learn`↔`learning` match.
   d. `_scrub()` **strips** citation markers instead of rejecting the sentence. Wikipedia cites its
      lead definition most heavily, so the old filter discarded the best line in every article.
   e. `_break_navboxes()` — **the decisive one.** Wikipedia's navigation sidebar is inlined as
      running text with no punctuation, welding the lead onto it:
      `"... NFT plagiarism scandal Glossary v t e Machine learning ( ML ) is a field of study ..."`
      One >400-char blob → dropped by the length filter. `v t e` (view/talk/edit) now becomes a
      sentence boundary.
   Verified 5/5: machine learning, aeroponics, photosynthesis, DNA, gravity all return their real
   definitions. Backups `engine.py.bak` … `.bak10`.
   *Residual:* trailing disambiguation debris on some entries (gravity: "Escher) or Gravity, a 1952
   mixed-media artwork by M."). `_is_list_debris()` catches album/song runs; extend for artwork and
   "All pages with titles beginning with X".
2. **Markov output is incoherent** when there is no knowledge hit. Markov cannot hold a thought.
   Options: train TinyGPT (`--model tinygpt --steps N`), or make knowledge-retrieval the primary
   path and use the model only for chit-chat.
3. ~~Greeting canned~~ **DONE** — see §4h (`/greeting` endpoint). **`static/index.html` still
   hardcodes the old line at ~line 63** — the frontend must be wired to fetch `/greeting` on load.
3b. **URLs are not understood.** User wants to paste a link and ask about it. `POST /scrape/url`
   exists and works, but `/chat` does not detect a URL in the message. Add: regex a URL out of the
   user's turn → `scraper.scrape(url)` → ingest → answer from that content in the same turn.
3c. **Reddit returns 403 Blocked.** The scraper sends a default User-Agent. Reddit's public JSON
   API requires a descriptive custom UA. Set one in `scraper/engine.py`.
4. **No thinking UI.** User wants a collapsible "thinking" dropdown + loading animation while
   processing, like mainstream assistants.
5. **No memory compaction.** User wants long-context memory with compaction.
6. **No thought queue.** User wants sequenced/queued thoughts processed when ready.
7. **Curiosity has still never run an episode** (`total_episodes: 0`). `ScheduleConfig` in
   `curiosity/scheduler.py`: `min_message_count=5`, `interval_minutes=60`. For 24/7 learning,
   lower the threshold and interval, and/or seed the topic queue directly.
8. **Only Wikipedia is scraped.** User wants news + social (Reddit JSON API).
9. **Answer quality is retrieval-only** — no synthesis across multiple entries.

## 8d. Newest user requests (not yet built)

- **Deferred/async answers.** Let Shaggoth take time to think and **come back later with the
  answer once curiosity has learned it**, rather than only answering in-turn. Needs: pending-question
  queue keyed by session, a hook on curiosity-episode completion, and a push/poll path to deliver
  the follow-up. Pairs with the "thought queue" item below.
- **Long-form responses** between answers (not just one-liners).
- **Drift toggle (`drift` / `no_drift`).** Humans can let it wander "for fun"; the IDE integration
  must NOT drift. Make it a per-request flag + a settings default, threaded from `/chat` into
  `DialogueEngine.respond()`. No-drift = knowledge/definitional answers only, Markov and tangents
  disabled. Drift = allow associative replies and topic wandering.
- **Self-awareness persona.** It should know it is an AI running on a computer (specifically: on
  the r510, learning from scraped pages) — reflected in `patterns.py` / personality traits.
- **PWA icon + polish.** User wants a *creepy Shaggoth* icon in the Archon house style (dark
  rounded square, glowing centred emblem, purple/cyan). `static/generate-pwa-icons.py` exists;
  regenerate `pwa-192.png` / `pwa-512.png` / `favicon.svg` and reference from `manifest.json`.
- **Mobile-friendly dashboard**: anchors for the tab nav, everything visible, and the on-screen
  keyboard must not cover the input (use `dvh`/`visualViewport`, not `vh`).
- **UI error seen by user:** `Error: The string did not match the expected pattern.` — a Safari/iOS
  regex or `JSON.parse` failure in `static/app.js`. Reproduce on mobile Safari; likely an
  unsupported regex construct (lookbehind) in the frontend.
- **Random thoughts + push notifications.** Shaggoth should surface unprompted thoughts through
  the day via PWA web-push to probe engagement (e.g. after a curiosity episode: "I just read about
  X, want to hear the weird part?"). Assets exist: `static/sw.js`, `manifest.json`, and the
  `Shaggoth-a1` branch has a **push register endpoint** already. Needs: VAPID keys, subscription
  storage, a scheduler for thought generation, and `sw.js` push/notificationclick handlers.
  Now feasible because the site is on a real public origin (`ai.relayapp.pro`) — web push
  requires HTTPS on a stable origin, which tailnet-only Serve could not provide.
- **Live learning counter on the r510 tty command center** — knowledge-entry / episode count
  updating in real time so the AI is visibly learning. `command_center/shaggoth.py` already
  returns everything needed (`knowledge_entries`, `total_episodes`, `pages_stored`,
  `total_words`); it just needs rendering in `app.py`/`rendering.py`.
- **Thinking dropdown + loading animation** in the chat window, like mainstream assistants.
- **Memory + memory compaction** for long context windows.
- **`ide.relayapp.pro` → repoint to Shaggoth.** User said they no longer use the IDE at that
  domain. Currently a Fly CNAME with an issued Fly cert. Repointing means
  `cloudflared tunnel route dns shaggoth ide.relayapp.pro --overwrite-dns` and adding the hostname
  to the tunnel ingress. **The Archon IDE would then only be at `app.relayapp.pro` /
  `archon-ide-pacmac.fly.dev`.** Confirm before destroying a working deployment.

## 8c. r510-command-center work (repo cloned to `/tmp/r510cc`)

**Fly module bug — root cause found.** `flyctl` IS installed at `~/.fly/bin/flyctl` and
authenticated (`matty@purepulse.one`), but **is not on `PATH`**, so `shutil.which("flyctl")`
returns `None` and `fly.py` reports "flyctl not installed". The installer edits the shell profile,
which a systemd/tty1 process never sources.
→ Added `find_flyctl_executable()` to `config.py` (mirrors the existing
`find_opencode_executable()` convention) + `flyctl_path` Config field.
**STILL TODO:** wire `fly.py:84` to use it instead of bare `shutil.which("flyctl")`.

**New module added:** `command_center/shaggoth.py` — `ShaggothState`
(LEARNING/ONLINE/STALLED/IDLE/OFFLINE/ERROR), `ShaggothStatus`, `get_status()`. Reports uptime,
curiosity scheduler liveness, episode count, knowledge entries, scraper stats. **Verified working
on r510** (returned ONLINE, 305 entries, 161,004 words). The STALLED state exists to catch
"daemon up but not actually learning".
**STILL TODO:** wire into `app.py` + `screens.py`; add `storage.py` (per-filesystem + LVM free);
add tests under `tests/`; commit and push.

Test a module on r510 with a real package dir — importlib + `from __future__ import annotations`
breaks dataclass resolution:
```bash
mkdir -p /tmp/cctest/command_center && touch /tmp/cctest/command_center/__init__.py
cp <module>.py /tmp/cctest/command_center/ && cd /tmp/cctest && python3 -c "from command_center import shaggoth; print(shaggoth.get_status())"
```

## 9. User's stated goals (verbatim intent)

- Shaggoth on **r510-1**, overflow to another compute when CPU is high
- **Always learning, 24/7**, using **curiosity clues from conversation** for context
- Needs **general knowledge** — it's a homegrown AI
- Scrape **social media + news (Reddit)**
- Make **all dashboard tabs work**, especially Learn
- **PWA** using the **favicon** as icon, with **notifications**, tied to **relayapp.pro**
- Storage meter must read so they know if more storage is needed
- Health surface in `github.com/Mattjhagen/r510-command-center`
- Keep this AGENTS.md current for context-loss recovery

---

# SESSION 2026-07-27 (03:00–05:30 UTC) — everything below verified by command

**All work in this session is committed and pushed.** Nothing is left dirty.

| Repo | Branch | HEAD |
|---|---|---|
| `~/Shaggoth-a1` | `claude/ai-model-guardrails-platform-o6b50g` | `b14f3ad` |
| `~/r510-command-center` | `main` | `6100aa9` |

Tests: Shaggoth **143 passing** (was 82/14-failing). Command center **185 passing** (was 125/7-failing).

## A. The two UI errors were ONE server-side crash — not frontend bugs

The handoff listed `Error: The string did not match the expected pattern.` as a
mobile-Safari regex/lookbehind problem in `static/app.js`. **It was not.**

`markov_is_usable()` referenced `_ARTIFACTS`, a regex constant that **was never
defined**. Every message that reached Markov generation raised `NameError`
inside the request handler; `BaseHTTPRequestHandler` then answered with its
default **HTML** error page (or dropped the connection). Both reported errors
are the same `JSON.parse` failure, worded differently by each browser:

- Chrome: `Unexpected token '<', "<!DOCTYPE"... is not valid JSON`
- Safari: `The string did not match the expected pattern.`

**Do not go looking for a lookbehind in app.js. There isn't one.**

Fixes: defined `_ARTIFACTS`; wrapped every route in `Handler._guard()` so an
unhandled exception becomes a JSON 500 instead of an HTML page. The traceback
still goes to the journal.

### Two more latent bugs of the same class, found by AST-scanning for undefined names
- `shaggoth/__main__.py` used `json.dumps` with **no `import json`** → the
  `personality` CLI subcommand crashed.
- `_NOISE` contained `\\s` / `\\b` / `\\(` inside **raw** strings (doubled by a
  heredoc during an earlier edit — gotcha #9 in §8). In a raw string that is a
  *literal backslash*, so the entire anchored lead-in group could only match a
  sentence starting with a backslash. That is why "For other uses, see …" kept
  leaking despite the filter existing.

> **Worth repeating:** `grep -rn 'r"[^"]*\\\\' shaggoth/` finds this class of bug.

## B. Drift toggle — BUILT (task 1, done first as instructed)

`shaggoth/dialogue/engine.py`: `DRIFT` / `NO_DRIFT`, `normalize_mode()`,
`DEFAULT_MODE = NO_DRIFT`. `Reply.mode` reports which mode ran.

- **NO_DRIFT** (default): knowledge + patterns only. No Markov, no "want me to
  tell you about it?" teaser, no topic callbacks. **This is what the IDE uses.**
- **DRIFT**: also allows Markov generation, the teaser, and recall callbacks.

Per request: `{"mode": "drift"|"no_drift"}` or `{"drift": true|false}`.
Instance default: `DialogueEngine(mode=...)`. Config default:
`config/settings.json` → `"dialogue_mode"`. An unrecognised mode falls back
rather than raising.

`markov_is_usable` also now rejects output starting with punctuation
(mid-sentence fragments) and **rejects outright when the prompt has no content
word** ("you", "hi", "ofjds") — there is nothing for the output to be *about*,
so relevance cannot be established.

## C. Guardrails were EMPTY on the live public endpoint

`DEFAULT_CONFIG` shipped `input_rules: []` and `output_rules: []`, and
`config/guardrails.json` on r510 matched. **ai.relayapp.pro was running with no
credential blocking, no redaction, and no length cap.** Restored a baseline:
`no-credentials`, `no-malware`, `redact-emails`, `redact-secrets`,
`reply-length-cap`. Verified live. (`max_length` also emitted `limit + 2`
characters.)

**Still open for the user:** the endpoint remains **public and
unauthenticated**. `SHAGGOTH_API_KEY` support exists and works — setting it
turns on auth *and* the rate limiter (`_rate_limit` is a no-op without a key).

## D. Fact storage was broken on every fresh database

`facts` is keyed `(key, user_id)`, but two call sites upserted with
`ON CONFLICT(key)`, which matches no constraint → `sqlite3.OperationalError`.
The **live DB had 0 rows**. Consolidated into `MemoryStore.set_fact()`; the
`remember` plugin now calls it instead of inlining the SQL. Verified live:
name extraction, `remember X is Y`, `/facts`, and recall all work.

## E. Answer quality — 13/14 definitional probes now return the real definition

Each fix was found by testing the previous one:

1. **Prefer a candidate that actually defines something.** `summarize_entry_scored()`
   reports whether the opening sentence was definitional; `respond()` does a
   first pass taking only definitional candidates. "DNA" the molecule and
   "DNA²" the manga both legitimately match "dna" — **the seeded `Dna` entry is
   the manga**; only the disambiguation gloss defines the molecule.
2. **Exact-title boost** (`_EXACT_TITLE_BOOST = 10.0`). Title overlap alone could
   not separate `Evolution` from `Evolution Sabrina Carpenter Album` — both
   matched the one query word, so the shorter-article tie-break handed the
   answer to the pop album. Same tie sent "quantum mechanics" →
   `Interpretations Of Quantum Mechanics` and "chemistry" → `Bioorganic Chemistry`.
3. **Disambiguation penalty is mild (0.75), deliberately.** Those pages carry the
   best one-line glosses in the corpus. An aggressive penalty made answers worse.
4. **Captions and infoboxes weld onto the lead** (same class as the navbox bug).
   `_DEFINITION_RESTART` splits `"...watershed A river is a natural stream..."`.
5. **Scope clauses**: `_SCOPE_PREFIX` so "In physics, gravity … is …" counts.
6. **`_is_list_debris` extended**: catalogue entries, index furniture, and
   **orphaned parentheticals** — the `"Escher) or Gravity, a 1952 …"` tail came
   from `"M. C. Escher"` splitting on `"M."`.
7. **Body-route relevance**: `knowledge_is_relevant(topic, text, content)` also
   accepts when *every* content word appears in the body and there are ≥2 of
   them. Titles alone could not reach a character discussed across six chapters.

*Residual:* `"what is an atom"` still returns a mid-article sentence.

## F. Reddit — the handoff's diagnosis was wrong

`https://www.reddit.com/robots.txt` is:

```
User-agent: *
Disallow: /
```

**Reddit forbids all crawling.** A descriptive User-Agent does not change it
(verified: still 403), and `.rss` answers 200 but is covered by the same
robots.txt. The supported route is Reddit's **OAuth API with a registered app**.
`~/seed_sites.py` now has the Reddit block renamed `reddit_json_disabled` with
this reasoning inline.

The scraper **does** now honour robots.txt (`ScraperEngine.robots_allows()`,
cached per origin for 1h, fails open on missing/unreachable, always honours a
fetched `Disallow`, logs refusals). `USER_AGENT` is descriptive and contactable.

## G. The book is ingested

`~/seed_book.py` ingested `github.com/Mattjhagen/the-gentle-conquest`:
**38 entries, 158,161 words** (prologue + 35 chapters + epilogue + README).
KB is now **~360 entries**. Verified: "what is the gentle conquest",
"tell me about the shepherd", "who is Ellie Finch" all answer from it.

## H. Frontend / PWA

- **`/greeting` is wired** (`loadGreeting()` in app.js). Fresh line every load.
- **Icons**: `favicon.ico` did not exist → 404 on every page load. `favicon.svg`
  is now the single source (creepy slit-pupil eye + tendrils, Archon dark
  plate) and `generate-pwa-icons.py` rasterises it via **cairosvg** into
  `favicon.ico` (16/32/48), `apple-touch-icon.png`, `pwa-192`, `pwa-512`, and
  `pwa-512-maskable` (padded for Android's safe zone).
  ⚠️ cairosvg does **not** resolve `<image xlink:href>` — it silently produced an
  empty 1.8 KB plate. The maskable variant inlines the SVG into a `<g transform>`.
- **Mobile**: `--app-h` tracks `visualViewport.height` (100vh does not change
  when the keyboard opens, which is why the input went behind it); `dvh`/`vh`
  fallbacks; `viewport-fit=cover` + safe-area padding; 16px inputs (or iOS
  zooms on focus); 44px tap targets; scrollable drawer.
- **Nav**: real `href="#view"` anchors + hashchange routing. Tab survives reload
  and the back button.
- **New UI**: thinking indicator, collapsible "how it got that" panel (source /
  mode / rules / facts learned), drift selector in Settings.
- `readJson()` reports *"the server returned an error page"* instead of
  surfacing a raw `JSON.parse` error.

## I. URL handling in /chat — BUILT

A message containing an `http(s)` URL is scraped, ingested, and answered in the
same turn. Stripping the link often leaves no subject ("what do you make of ?"),
so `question_for_page()` substitutes "what is <title>" when the residual has no
content word; a real question is left alone. `clean_page_title()` strips
"- Wikipedia" / "| GitHub" suffixes before they become a knowledge topic.

## J. r510-command-center — WIRED

`command_center/shaggoth.py` is rendered now. Telemetry block grew to
**13 lines** (`MIN_HEIGHT` 20 → 22):

- `SHAGGOTH <STATE>` | `TOPICS n (+n)  EPISODES n (+n)`
- `LEARNING <activity>` | `WORDS n (+n)`
- a scrolling shell-style **ingestion ticker**

`LearningCounter` baselines on the first healthy sample (offline samples are
ignored, a shrinking KB re-baselines). `LearningFeed` recovers events by
**diffing successive topic maps** — Shaggoth reports totals, not events — and
the first sample only baselines, or the ticker would replay 360 old topics.

**`[G]`** opens a full Shaggoth learning detail screen.

**Aliens**: two narrators inside the animation grid (green on Earth, purple on
the satellite, blue cameo, amber floor mess). **Both** are Shaggoth, held in
**two separate `/chat` sessions** and pointed at each other
(`command_center/conversation.py`) — every line on screen is its own words.
Two sessions because `/chat` keeps per-session memory; one session makes it
answer itself and collapse into a monologue. Seeded from the novel every
restart. Falls back to telemetry commentary when Shaggoth is unreachable.

⚠️ **Do not hand a reply to the other speaker verbatim.** It looks right and
is not: the reply retrieves the same knowledge entry, so the two sides parrot
one paragraph forever. Each speaker is prompted with a *subject* pulled from
what the other said; only the prompt is derived.

Drift quality took four passes (all tested): non-answers must not steer;
sentence-initial capitals are not names; bibliographic words ("Novel",
"Overview") are not names; clause openers are stripped; repeated answers do not
re-queue; avoidance compares by containment.

`fly.py` already used `find_flyctl_executable` — that handoff TODO was stale.

## K. No-sudo restart (important)

`shaggoth.service` is a **system** unit; `systemctl restart` needs a password.
But `Restart=always` and the process runs as `matt`, so:

```bash
kill $(systemctl show shaggoth -p MainPID --value)
for i in $(seq 1 25); do sleep 2; curl -sf -m 3 localhost:8420/health >/dev/null && break; done
```

systemd respawns it with the new code. **It takes ~10–20 s** (12 MB Markov model
+ 360 knowledge entries) — a 7 s sleep is not enough and will look like a crash.

## L. Running the tests

Neither box has pytest installed. `uv` is on r510 but **not on PATH**:

```bash
cd ~/Shaggoth-a1        && PYTHONPATH=. ~/.local/bin/uvx pytest tests/ -q
cd ~/r510-command-center && ~/.local/bin/uvx pytest tests/ -q   # editable install, no PYTHONPATH needed
```

Shaggoth has **no `tests/__init__.py`**, hence `PYTHONPATH=.`.

## M. Still open

1. **Auth on the public endpoint** — decision needed from the user.
2. **Deferred/async answers** + **PWA push notifications** (VAPID keys,
   subscription storage, `sw.js` push handlers). Not started.
3. **Self-aware persona** in `patterns.py` (knows it is an AI on the r510).
4. **Memory compaction / thought queue.** Not started.
5. **Curiosity tuning** — `ScheduleConfig(min_message_count=5, interval_minutes=60)`.
   Still only 1 episode total.
6. **`what is an atom`** returns a mid-article sentence.
7. **Markov is still incoherent** outside knowledge hits. In NO_DRIFT it never
   speaks, which is why the default is NO_DRIFT. TinyGPT needs `pip install torch`.
8. **`ide.relayapp.pro` → Shaggoth** repoint — needs user confirmation first.

---

# SESSION 2026-07-27 (later, ~14:30–15:30 UTC) — "dashboard says STALLED"

Shaggoth HEAD `b5adb06`. Command center HEAD `31ef420`. Shaggoth tests **168**.

## N. The STALLED report was correct — the scheduler had NEVER worked

`command_center` showed `SHAGGOTH STALLED — no research in 11h` with the thread
alive and 7 clues buffered. That is exactly the failure mode the STALLED state
was added to catch, and it was telling the truth.

`CuriosityScheduler._cycle()` drained the buffer **before** testing it:

```python
messages = list(self._message_buffer)
self._message_buffer.clear()          # unconditional
if len(messages) < min_message_count: # 5
    return
```

Every cycle threw away whatever had accumulated. Unless 5+ messages landed
inside a single 60-minute window, the count restarted at zero **forever**. The
scheduler had never researched anything; the one episode on record came from
the `/chat` fallback path in `server.py`.

Fixed: peek, and spend only the messages actually analysed (so anything
arriving mid-cycle survives). Two more in the same loop:
- `config.enabled` was read nowhere — disabling a live scheduler did nothing.
- An exception killed the thread. A dead thread looks identical to an idle one
  from outside, so the daemon would answer requests forever while silently
  never learning again. Cycles are guarded and logged now.

**Defaults retuned**: `interval_minutes` 60 → **15**, `min_message_count` 5 → **2**.

**Idle cycles now refresh stale knowledge** (`refresh_stale_when_idle=True`).
"Always learning" cannot depend on someone being in the chat window. There were
**114 stale topics** queued.

**Verified unattended**: the timer fired on its own after 870 s — episodes
2 → 3, entries 362 → 365, 4,774 words on a stale topic. Dashboard went
STALLED → **ONLINE**.

## O. Knowledge slugs — the filename stem IS the topic

`_scan()` derives the topic from `fpath.stem`, so a malformed slug is a
permanently malformed topic. A leading hyphen survived `.strip()` → the entry
`" Algebra"`; `"Aeroponics - Wikipedia"` → `aeroponics---wikipedia` → came back
as `"Aeroponics   Wikipedia"`. Both broke title matching in retrieval.

Consolidated into `KnowledgeBase.slug_for()`. The two affected files on disk
were repaired; `-algebra.md` turned out to be a smaller duplicate of the real
`algebra.md` and was deleted. **362 entries, 0 duplicates, 0 malformed.**

## P. THREE separate reasons a deploy could not reach a browser

Chasing "`ai.relayapp.pro/#/learn` opens the chat view" turned up a stack of
caching problems. All fixed; this is the one to remember.

1. **Router only accepted `#learn`.** `#/learn` (the router-style form people
   actually type and share) fell through to chat. Now tolerates `#learn`,
   `#/learn`, `#/learn/`, and mixed case.

2. **Cloudflare serves `/app.js` with `max-age=14400`** regardless of the
   `no-cache` this origin sends. For four hours after every deploy, visitors
   kept running the previous JavaScript — including anyone reporting a bug that
   was already fixed. `index.html` now gets `?v=<mtime>` appended to its local
   `.js`/`.css` refs as it is served (`add_cache_busters` in `server.py`),
   derived from mtime so it cannot be forgotten on a deploy.

3. **⚠️ The big one: the service worker pinned users to their first load.**
   `sw.js` was cache-first over every same-origin request, with a cache name
   that never changed and no cleanup on `activate`. Anyone who had loaded the
   site once was stuck on that copy of `index.html`/`app.js` **permanently** —
   no deploy could ever reach them. It also cached **API responses**, because
   Shaggoth's API is at the root (`/chat`, `/curiosity/status`, `/knowledge`)
   rather than under the `/api/` prefix the worker checked, so the dashboard
   could show a stale knowledge count while the daemon was healthy.

   Rewritten (`CACHE_VERSION = 'v2'`): network-first for navigations and API,
   cache-first only for `?v=`-versioned assets, stale-while-revalidate for the
   rest, versioned cache name, old caches deleted on activate. `app.js` calls
   `registration.update()` on load and reloads once on `controllerchange`.

> **When a frontend change "doesn't take", suspect the service worker first.**
> To clear by hand in devtools console:
> ```js
> (await navigator.serviceWorker.getRegistrations()).forEach(r => r.unregister());
> (await caches.keys()).forEach(n => caches.delete(n));
> ```

Verified live: `#chat`, `#/learn`, `#/guardrails/`, `#Memory` all resolve;
unknown fragments fall back to chat.

## Q. gh CLI still unauthenticated (unchanged)

`gh auth status` → *"The token in /home/matt/.config/gh/hosts.yml is invalid."*
**Git over SSH works fine** (`ssh -T git@github.com` succeeds) and is what every
push uses, so `gh` is only needed for PR/issue commands. Re-auth is interactive
and must be run by the user:

```bash
ssh matt@100.103.3.35 -t 'gh auth login --hostname github.com --git-protocol ssh --web'
```

## R. Minor, noted but not fixed

- `HEAD` requests return a 501 HTML page (`do_HEAD` is not implemented), so
  `curl -I` reports `Content-Type: text/html` for any asset. Harmless for GET
  clients; misleading when debugging headers.
- The two `[failed]` rows in the Self-Learn log are historical, from before the
  Markov fallback existed. Not re-run.

---

# SESSION 2026-07-27 (~15:00–16:00 UTC) — "what isn't working" → fixed

Shaggoth `9b243d8` (191 tests) · command center `bb12d59` (188 tests). Both clean.

## S. The IDE was talking to the wrong machine — FIXED

`SHAGGOTH_BASE_URL` was `http://100.67.199.109:8420` (**the MacBook**), which
runs old code — asked "what is gravity" it answered `source: fallback`,
*"That's interesting — go on."*, with no `mode` field. **Every fix since
2026-07-27 03:00 was invisible to `ide.relayapp.pro` / `app.relayapp.pro`.**

Verified both hosts reachable from inside the Fly machine first (no curl or
python in that image — use bash `/dev/tcp`), then:

```bash
flyctl secrets set SHAGGOTH_BASE_URL=http://100.103.3.35:8420 -a archon-ide-pacmac
```

Rolling restart succeeded; both domains 200. **To revert:** set it back to
`http://100.67.199.109:8420`.

## T. The tty1 dashboard was running 12-hour-old code — FIXED

`~/.bashrc` autostart ran a bare `command-center`, so any exit dropped tty1 to
a bash prompt and stayed there until the next login. Now wrapped in a relaunch
loop that restarts on crash but still lets **Q** exit to a shell.

**Restarting the console from SSH:**

```bash
kill -HUP $(ps -o pid=,tty=,cmd= -t tty1 | awk '$3=="-bash"{print $1}')
```

- `getty@tty1` has `--autologin matt` and `Restart=always`, so the session
  respawns and `.bashrc` starts the dashboard cleanly.
- **Use `-HUP`, not the default TERM: an interactive bash ignores SIGTERM.**
- ⚠️ **Never `pkill -f command_center` over SSH** — the pattern matches your own
  ssh command line and kills the connection.

## U. The ambient dialogue was choosing the syllabus — FIXED

Once the scheduler worked, the command center's two narrators started driving
it. They talk to `/chat` continuously, so every word they pulled out of a reply
became a research topic: entries titled **"understanding", "continental",
"geophysicists", "wavelengths"** — 14 of them in half an hour, and it would
have run all night.

`/chat` now accepts **`{"research": false}`**: answered normally, but not
buffered as a curiosity clue and no auto-research. Only an explicit `false`
opts out. The command center sets it. Junk entries removed.

Also killed a dead condition in the same branch:
`source in ("pattern","fallback") and source == "fallback"`.

## V. Also fixed this round

- **Memory tab was permanently empty.** `sessionId` was regenerated on every
  page load, so `/history?session_id=` only ever returned the current load.
  Persisted in `localStorage`, plus a "Start a new conversation" button.
- **`what is an atom`** returned an image caption. The Atom lead is
  *"An atom **consists of** a nucleus…"* and `_DEFINING_VERB` had no
  compositional forms. Added consists of / comprises / is composed of /
  is made up of. **The definitional sweep is now 8/8 clean.**
- **Self-aware persona** in `patterns.py`: what it is, where it runs, how it
  learns, and the "do you have feelings" question — in voice, every claim true
  of this deployment.
- **HEAD returned a 501 HTML page**, so `curl -I` reported `text/html` for
  every asset. Served as GET with the body suppressed.

## W. Still open (deliberately)

1. **`ai.relayapp.pro` is public and unauthenticated.** Not changed: setting
   `SHAGGOTH_API_KEY` would lock the user out of their own UI until they enter
   the key, so it needs their decision. Setting it also switches on the rate
   limiter (`_rate_limit` is a no-op without a key).
2. **Never built:** push notifications, deferred/async answers, memory
   compaction, thought queue.
3. **Markov is incoherent** outside knowledge hits, so DRIFT mode is poor.
   TinyGPT needs `pip install torch`. NO_DRIFT (the default) never calls it.
4. **Reddit** stays unscrapeable — robots.txt is `Disallow: /`. Needs their
   OAuth API with a registered app.
5. **`gh` CLI unauthenticated** — interactive, user must run it. Git over SSH
   works and is what all pushes use.

---

# SESSION 2026-07-27 (~16:00–17:00 UTC) — memory, push, deferred answers

Shaggoth `4252c2c`, **242 tests**. Command center `bb12d59`, 188 tests.

## X. It could not hold a conversation — FIXED

Reported verbatim from the UI:

```
you  > i wanted to chat
shag > Never heard of wanted chat. Annoying. I'm reading up on it right now
       [source: fallback -- curiosity research has been triggered]
```

Three faults at once: nonsense reply, the turn recorded as a knowledge gap,
and curiosity then **researched "wanted chat"**. Every reply was computed from
the current message alone, so `has it been a bit` had nothing to refer to.

- **`has_subject()`** — a turn made only of filler and pronouns is
  conversation, not a lookup. Returns `source="pattern"`, which also stops it
  being treated as a knowledge gap.
  ⚠️ **Runs *after* plugin dispatch.** `what is 6 * 7?` and
  `what do you know about me?` are made entirely of filler words but are real
  commands — the existing tests caught this immediately.
- **`is_follow_up()`** — bare (`why?`, `go on`) *and* anaphoric
  (`why does that matter`). Anaphoric questions never reach retrieval;
  `why does that matter` was being answered from an article about **matter**.
  The pattern is **anchored** and requires the pronoun to be the grammatical
  subject: an unanchored version swallowed
  `what is the thing THAT plants use to make sugar`.
- **`last_subject()`** resolves by **recency, not frequency**. Ranking session
  keywords by count answered `why?` with *"On chat?"* after a conversation
  that said "chat" three times in passing and "photosynthesis" once on
  purpose. Fact statements (`my name is Matt`) are skipped — they are facts,
  not what the conversation is about.

## Y. Memory compaction — BUILT

`MemoryStore.conversation_context(session_id)` → recent turns verbatim, a
compacted summary of everything older, session topics, last user message.
`compact_session()` folds older turns into `session_summaries` once a session
passes 40 messages, keeping the last 8 turns intact. Idempotent; extends as
the conversation grows.

**The summary is extractive on purpose** — subjects raised, questions asked,
facts learned. There is no model here that could paraphrase honestly, and an
invented paraphrase in long-term memory is worse than a plain list.

## Z. Push notifications + deferred answers — BUILT

`shaggoth/notify/`: `push.py`, `deferred.py`.

- **VAPID keys at `config/vapid.json`** — gitignored, mode 0600. Public key is
  served from `GET /push/status`. **Regenerating them invalidates every
  existing subscription.**
- `pip install --user --break-system-packages pywebpush` (PEP 668 blocks a
  plain `--user` install on this box; it lands in `~/.local`, which the system
  python3 running the service picks up).
- **Rate-limited to one notification an hour per subscriber** — research runs
  every 15 minutes and would otherwise buzz a phone all night.
- A subscription returning **404/410 is dead and is dropped**; anything else is
  transient and kept.
- **Nothing in `notify/` may raise into a caller.** Sends fire from the request
  handler *and* the scheduler thread; a dead phone must not take down a chat
  reply or the learning loop.
- `CuriosityEngine.on_episode_complete(cb)` is the hook. `serve()` registers
  two: deliver deferred answers, and announce anything over 500 words.
- **`GET /deferred` works without push**, and the frontend polls it — so
  notifications are an accelerant, not a requirement.
- Endpoints: `POST /push/subscribe|unsubscribe|test`, `GET /push/status`,
  `GET /deferred`. Settings has enable/disable/test.

## AA. Rate limiter was off exactly when it mattered — FIXED

`_rate_limit` returned `True` immediately when no API key was set. The endpoint
is public and every chat message feeds the curiosity loop, so an open endpoint
with no limiter let anyone decide what Shaggoth reads overnight. Now 60/IP/min
regardless of auth, with idle buckets pruned (the map was an unbounded leak on
a public endpoint). Verified: 60 through, then 429, recovering after the window.

**Auth is still unset and still the user's decision.** This is the floor, not
a substitute.

## BB. TinyGPT

`torch 2.13.0+cpu` installed (`--user --break-system-packages`). Training on a
1,033,094-word corpus rebuilt from `data/knowledge/`. numpy is absent — torch
warns but works.

```bash
cd ~/Shaggoth-a1 && PYTHONPATH=. python3 -m shaggoth train \
  --corpus data/corpus/knowledge_corpus.txt --model tinygpt --steps 3000
```

Writes `data/tinygpt.pt`; `build_engine()` prefers it over Markov
automatically. **Only affects DRIFT mode** — NO_DRIFT never calls a model.

## CC. Thought queue — deliberately not a third queue

Two queues already exist and are wired: `DeferredQuestions` (things someone
asked) and `CuriosityScheduler`'s topic queue (things to go read). A third
abstraction would duplicate both. If a distinct behaviour is wanted, name it.

## DD. Still open

1. **Auth on the public endpoint** — user's call. Rate limiting is now on.
2. **Reddit** — robots.txt `Disallow: /`; needs their OAuth app.
3. **`gh` CLI** — interactive, user must run it.
4. **`ide.relayapp.pro` → Shaggoth repoint** — needs confirmation; it would
   leave the Archon IDE only on `app.relayapp.pro`.

---

# SESSION 2026-07-27 (evening) — reasoning + the feedback loop

Shaggoth `f8459e0`, **297 tests**. Command center `bb12d59`, 188 tests. All clean.

## EE. Reasoning — BUILT (`shaggoth/dialogue/reasoning.py`)

Retrieval could only answer "what is X". Asked *"what is the difference between
aeroponics and hydroponics"* it returned the hydroponics article and never
mentioned aeroponics.

`Reasoner` classifies intent and gathers the several pieces needed:
`compare` · `contrast` · `causal` · `enumerate`. Plain definitions are declined
and left to retrieval.

Every reply now carries **`reasoning`** (the trace) and **`entries_used`**,
shown in the "how it got that" panel. That trace is what makes a wrong answer
attributable to a specific entry — and it is what the feedback loop below
depends on.

**It is not a language model reasoning in free text.** Nothing here can do
that. Every sentence emitted exists in the corpus; the reasoning is in *which*
sentences are selected. When only one side of a comparison is known it says
so rather than passing off half an answer.

Three bugs found building it:
- An unbounded `why\b` in `_FOLLOW_UP` matched *every* why-question, so
  "why does photosynthesis need light" got "ask me something specific".
  ⚠️ The `$`-anchored alternatives must not sit inside a group ending in `\b` —
  a word boundary after `why?` can never match.
- Every group of the comparison lead-in was optional → matched the empty
  string at position 0 → the `how are …` branch was unreachable.
- Requiring the literal topic word in every selected sentence discarded most
  real explanations ("**It** requires light because …").

Causal is still the weakest intent. Ranking by question focus fixed gravity;
photosynthesis still returns adjacent-but-wrong sentences.

## FF. Feedback → repair queue — BUILT (`shaggoth/feedback/`)

**This is the answer to "does refinement come from chatting?" — now it does.**

Breadth came from the curiosity loop; refinement came from whoever read the
code. Nothing recorded that an answer was bad, so the loop would re-fetch the
same bad entry a month later for being stale.

`POST /feedback` records question, verdict, note, source, `entries_used`,
reasoning. Because a reply names its entries, a thumbs-down implicates a
**specific knowledge entry**. Those form a **repair queue the scheduler drains
before any age-based refresh**.

- Praise offsets complaints; only net-negative entries queue.
- Repair sets a 6h cooldown, **marked before researching** — if research
  throws, the cooldown still applies and one broken topic cannot capture every
  cycle.
- A fresh complaint **reopens** a repaired entry: the repair didn't work.
- 👍/👎 on every reply; a 👎 prompts for an optional note.
- `GET /feedback` returns the queue and recent judgements.

⚠️ Bug worth remembering: `repair_queue` defaulted a never-repaired entry's
repair time to `0.0` and subtracted, so it looked repaired-at-the-epoch and
**every first-time complaint was filtered out**. The queue would have been
permanently empty. Never-repaired must mean *always eligible*.

## GG. Answers to two questions asked this session

- **Does refinement come from chatting?** It didn't; it does now, via FF.
  The loop supplies breadth, your judgement supplies quality.
- **Can it scrape Quora?** **No.** `robots.txt` explicitly prohibits using
  Quora content to train AI systems absent a contract, and it returns **403**
  regardless. Same shape as Reddit. Crawl-permissive alternatives with real
  Q&A depth: **Stack Exchange data dumps (CC-BY-SA)**, Wikipedia,
  open-access science.

## HH. TinyGPT — trained, rejected, parked

3000 steps, **loss 4.15**, emits non-words (`symotential`,
`authibiiktiological`) — worse than Markov, which at least emits real words.

⚠️ `build_engine` loaded TinyGPT first whenever the file existed, so simply
*finishing a training run* would have silently downgraded every drift reply on
the next restart. **`auto` now means Markov**; TinyGPT requires
`model = "tinygpt"` explicitly. Checkpoint parked at
`data/parked/tinygpt-3000steps-loss4.15.pt`.

Recommendation: **do not spend more CPU on it.** Retrieval is the strong path.
