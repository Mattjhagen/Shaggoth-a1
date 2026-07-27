# Automating training

**Status:** plan, not built. Written 2026-07-27 against Shaggoth `fc761c1`.
**Read `~/AGENTS.md` first** — it has the verified state this plan assumes.

---

## 0. What "training" means here, precisely

Shaggoth is **not** a model that learns weights from feedback. Saying "train it"
imports expectations that do not hold, so this plan uses exact terms:

| Layer | What it is | Can it be trained? |
|---|---|---|
| **Corpus** | scraped pages → `data/knowledge/*.md` | Yes — grow and repair it |
| **Retrieval** | BM25 + title boost + exactness | Yes — tune against a probe set |
| **Selection** | which sentence answers the question | Yes — this is where quality lives |
| **Reasoning** | compare / causal / enumerate | Yes — intent + ranking rules |
| **Generation** | Markov chain | Retrainable, but it is not the problem |

A thumbs-down does **not** adjust weights. It marks a knowledge entry as
producing bad answers, and the entry gets re-researched. For a retrieval
system, corpus and selection quality *is* the learned behaviour. That is the
thing to automate.

> **The honest ceiling:** every improvement below makes it retrieve and select
> better. None of it makes it *fluent*. Fluency needs a real language model,
> which is a separate decision with a separate cost — see §7.

---

## 1. The actual bottleneck

The repair mechanism already exists and is wired:

```
thumbs-down → FeedbackStore.record(entries_used=[...])
            → repair_queue()
            → CuriosityScheduler._repair_one()   (runs before age-based refresh)
            → curiosity.research_topic(topic)
```

What does not exist is **judgement at scale**. Every improvement so far came
from a human noticing an answer was wrong. The loop cannot generate that
signal, so left alone it grows *broader*, never *better*.

**Automating training = automating the judgement, then closing the loop on it.**

Everything below is in dependency order. Do not skip ahead: phase 1 is a gate,
and phases 3–5 are worthless if it fails.

---

## PHASE 1 — Prove repair actually repairs (GATE)

**Why first:** re-researching an entry may fetch the same page and produce the
same passage. The counters move, the episode completes, nothing improves —
and it looks exactly like success. If this is what happens, phases 3–5 are
built on sand and the design needs rethinking, not extending.

### Build
`shaggoth/feedback/verify.py`

```python
@dataclass
class RepairOutcome:
    topic: str
    question: str
    before: str          # answer text prior to repair
    after: str           # answer text after
    changed: bool        # did the text move at all?
    improved: bool | None  # critic verdict, None if no critic yet
    words_before: int
    words_after: int
```

- Snapshot the answer **before** repair: in `_repair_one()`, re-answer
  `target.last_question` and store the text on the `RepairTarget`.
- After the episode completes (`on_episode_complete`), re-answer the same
  question and diff.
- Persist outcomes to `data/repair_outcomes.json`; expose `GET /repairs`.

### Verify
```bash
# Seed ~15 real complaints across intents, then let two cycles run.
curl -s localhost:8420/repairs | python3 -m json.tool
```

### The decision this forces
- **`changed` is mostly false** → re-research is a no-op. Go to §3.4 (source
  escalation) *before* anything else. This is the likely outcome for Wikipedia-
  sourced entries.
- **`changed` true but `improved` false** → the problem is *selection*, not the
  corpus. Prioritise phase 2's critic and §4.
- **Both true** → the loop works; proceed as written.

**Report the answer plainly either way.** A negative result here is the most
valuable thing this phase can produce.

---

## PHASE 2 — An automated critic

A cheap, honest scorer so the system can judge its own answers without a human.
Not a model — a set of checks that catch the failure modes actually observed.

### Build
`shaggoth/quality/critic.py`

```python
@dataclass
class Critique:
    score: float          # 0..1
    verdict: str          # "good" | "weak" | "bad"
    reasons: list[str]    # human-readable, e.g. "answer never mentions the subject"
```

`critique(question, answer, intent, entries_used) -> Critique`

Checks, each one derived from a real bug in the log:

| Check | Catches | Real example |
|---|---|---|
| Answer contains the question's subject | off-topic retrieval | "what is dna" → the manga *DNA²* |
| Definitional question → definitional answer | caption instead of lead | "what is an atom" → image caption |
| Causal question → causal markers **and** the focus word | adjacent-but-wrong | "why does photosynthesis need light" → bacterial membranes |
| No index/nav furniture | scraper debris | "If an internal link led you here…" |
| No orphaned parenthetical / mid-sentence start | split artefacts | "Escher) or Gravity, a 1952…" |
| Length sane for intent | stubs and walls | `python.md` at five words |
| Comparison names **both** subjects | half-answers | aeroponics/hydroponics |

Reuse what exists — do not reimplement: `_is_definitional`, `_is_list_debris`,
`_CAUSAL_MARKER`, `has_subject`, `_topic_words`.

### Wire
1. `POST /chat` optionally returns `critique` when `?critique=1` — never on by
   default, it is diagnostic weight on every reply.
2. `FeedbackStore.record(verdict="auto-bad", source="critic")` when the critic
   scores below threshold **and** no human has rated that answer. Keep auto and
   human verdicts distinguishable: a human thumbs-down must always outrank the
   critic, and the critic must never overwrite one.

### Test
`tests/test_critic.py` — one case per row above, using the *actual* bad answers
recorded in AGENTS.md so the critic is proven against real failures rather than
invented ones.

---

## PHASE 3 — A probe suite that runs itself

The regression net. I ran this by hand every session ("definitional sweep 14/14")
and it caught every regression I introduced. Automate it.

### Build
`tests/probes/probes.yaml` — question + expected *properties*, never exact text:

```yaml
- question: what is an atom
  intent: define
  must_contain_any: [nucleus, protons, electrons]
  must_not_contain: ["black bar", angstrom]
  min_words: 15
- question: what is the difference between aeroponics and hydroponics
  intent: compare
  must_mention_all: [aeroponics, hydroponics]
- question: i wanted to chat
  expect_source: pattern     # must NOT be a knowledge gap
```

`shaggoth/quality/probes.py` → `run_probes(engine) -> ProbeReport`

### Wire
- CLI: `python3 -m shaggoth probe` → table + non-zero exit on regression.
- Scheduled: a cycle every N hours writes `data/probe_history.json`.
- `GET /probes` → latest report, pass rate, and **what changed since last run**.
- Command center: surface pass rate next to the learning counter. A falling
  score is the single most useful number on that screen.

### Why this matters most
Fixing the scheduler is what set the runaway `Part 1 Part 1` entries growing,
and what let the dashboard hijack the syllabus. **On this project, fixes
routinely create the next bug.** A probe suite running on a timer is the only
thing that catches that without a human watching.

---

## PHASE 4 — Close the loop: repair → verify → escalate

With §1 measuring, §2 judging, and §3 detecting regressions, make repair
self-correcting.

```
critic or human marks answer bad
        ↓
entry → repair queue
        ↓
re-research (existing)
        ↓
re-answer + critique  ← PHASE 1 + 2
        ↓
   improved? ──yes──→ clear marks, record outcome
        │
        no
        ↓
   escalate: try a DIFFERENT source, not the same page again
        ↓
   still bad after N attempts → quarantine the entry, stop burning cycles
```

### Build
- `CuriosityEngine.research_topic(..., exclude_sources=[...])` so a retry does
  not fetch the page that already failed.
- Source ladder: Wikipedia → Stack Exchange dump → open-access science →
  general web. Each step needs a robots.txt check (`ScraperEngine.robots_allows`
  already exists — **use it, do not bypass it**).
- `data/quarantine/` for entries that resist repair, excluded from retrieval
  with the reason recorded. Do not delete — a quarantined entry is evidence.

### Guard rails (learned the hard way)
- Cap repairs per cycle. One stubborn topic must not monopolise the loop.
- Mark the cooldown **before** researching, not after — if research throws, the
  cooldown must still apply. This is already the behaviour; keep it.
- Never let repair write an entry whose topic is a chunk name (`X Part 2`).
  `base_topic()` guards this; it is why the KB stopped growing garbage.

---

## PHASE 5 — Corpus hygiene, automatically

The KB is ~480 entries and grows unattended. Junk accumulates silently.

### Build
`shaggoth/quality/audit.py` → `audit_knowledge() -> AuditReport`

Detect and act:
- stacked chunk suffixes (`part-N-part-M`) → **delete**
- duplicate topics → keep the longest, delete the rest
- stubs under ~60 words → quarantine (they can win an exact-title match and
  shadow the real article — `python.md` did exactly this)
- disambiguation-only entries with no real prose → quarantine
- entries no query has ever matched → flag as dead weight

Run on a timer; expose `GET /audit`; log every action. **Never silently delete
without recording what and why.**

### Verify
```bash
ls ~/Shaggoth-a1/data/knowledge | grep -cE "part-[0-9]+-part"   # must be 0
curl -s localhost:8420/audit | python3 -m json.tool
```

---

## PHASE 6 — Retraining the generator, automatically

Only worth it once §1–§5 hold. The generator is not the bottleneck.

- **Markov:** cheap. Retrain whenever the corpus grows >10% since the last
  train. `LearnerPipeline` already falls back to Markov correctly.
- **TinyGPT:** **do not, without new evidence.** A 3000-step run reached loss
  4.15 and emitted non-words (`symotential`, `authibiiktiological`) — worse than
  Markov. Checkpoint parked at `data/parked/`. Reaching usefulness needs
  ~10–100× the steps: days of CPU for a mode that is not the default.
  ⚠️ `build_engine` used to prefer TinyGPT whenever the file existed, so merely
  *finishing a run* silently downgraded every drift reply. `auto` now means
  Markov; TinyGPT requires `model = "tinygpt"` explicitly. **Do not undo that.**

---

## 7. What this does not solve

Say this to the user rather than letting them discover it:

1. **Fluency.** Every answer is a sentence lifted from a scraped page. It will
   never *phrase* things well, only *select* well. Fixing that means a real
   language model behind the same interface (`DialogueEngine.respond`), which is
   a cost and privacy decision, not an engineering one.
2. **Synthesis across many entries.** Reasoning compares two things. "Summarise
   what you know about X across everything you've read" is out of reach without
   a generator.
3. **Judgement about correctness.** The critic checks *shape* — on-topic,
   definitional, not debris. It cannot tell a true statement from a false one.
   Only the corpus can, which is why source quality matters more than any rule.

---

## Suggested order and rough size

| Phase | Size | Gate? |
|---|---|---|
| 1 — prove repair | small | **yes — stop if it fails** |
| 2 — critic | medium | feeds 3 and 4 |
| 3 — probe suite | medium | highest ongoing value |
| 4 — escalation | large | needs 1 + 2 |
| 5 — audit | medium | independent, safe anytime |
| 6 — retraining | small | last |

**Start with phase 1 and report the result before building anything else.**
