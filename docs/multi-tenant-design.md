# Embeddable Shaggoth — per-site isolation design

Status: **design, not implemented.** Written before code, per instruction.
Date: 2026-07-31.

Goal: a site owner drops in one `<script>` tag; Shaggoth answers their
visitors' questions from *their* site's content, in *their* chosen voice.

---

## 0. Scope decision: one tenant end-to-end first

Build the whole vertical slice for **purepulse.one only**, then generalise.
Multi-tenant isolation, crawl scheduling, robots compliance, ownership
verification and per-site personality are each substantial; a half-built
platform teaches less than one site that actually works.

Concretely, phase 1 ships: site registry (1 row), verified ownership, a
bounded crawl of purepulse.one into an isolated corpus, per-site personality
set to `professional`, and the widget embedded on the live site. Everything
below is designed so phase 1 is a strict subset, not a throwaway prototype.

---

## 1. Why post-filtering a global index is wrong

The instinct is to keep one `KnowledgeBase` and filter results by site. That
is not merely leaky, it is **statistically incorrect**, and it is worth being
precise about why.

`KnowledgeBase.query()` scores with BM25. The IDF term is

```
idf = log(1 + (N - df + 0.5) / (df + 0.5))
```

where `N` is the corpus size and `df` the number of documents containing the
term. Both are computed over the *whole* index. With the general Wikipedia
corpus mixed in:

- `N` is ~814 instead of a site's ~20 pages, so every score is calibrated
  against the wrong denominator.
- A word that is rare and therefore *highly discriminative within a site*
  ("deposit", "consultation") is common across Wikipedia, so its IDF is
  crushed and the site's own page loses to an encyclopedia article.
- Normalisation (`score / best`) is relative to the best hit **in the whole
  corpus**, so `min_score` — the confidence threshold that decides whether
  Shaggoth answers at all — means something different per query.

Filtering after ranking cannot repair any of this: the damage is done in the
scoring, and the surviving scores are still normalised against a discarded
document. This is not hypothetical — the live server already demonstrates the
failure mode:

```
"what is PurePulse"  ->  source: knowledge
                         entries_used: ['Purepulse Part 3', 'Purepulse Part 1']
                         "Pure models are fitted with the standard audio
                          system... Pulse models are fitted with alloy wheels,
                          panoramic glass roof, and paddle-shifters..."
```

Those entries are the 2007 PSP game *WipEout Pulse* and the Smart Fortwo. The
title boost matched the customer's own brand name against unrelated scraped
articles. **A separate index per site is the fix; a filter is not.**

---

## 2. Corpus isolation

One `KnowledgeBase` instance per site, rooted at its own directory:

```
data/
  knowledge/                 # existing general corpus, untouched
  sites/
    <site_id>/
      knowledge/             # this site's pages only — its own BM25 index
      site.json              # domain, verification state, personality, crawl policy
```

`KnowledgeBase.__init__` already takes a `directory` argument and builds an
independent index, so this needs **no change to the ranking code** — only a
registry that hands out the right instance. That is the main reason to prefer
it over sharding one index.

**Answering order.** Site corpus first. Fall back to the general corpus only
if `allow_general_fallback` is true for that site (default **false**), and
when it is used, label the answer as general knowledge rather than passing it
off as the site's own. A business must never be made to appear to state
something its own pages do not say.

### 2.1 Registry and the thread-safety multiplier

A `SiteRegistry` maps `site_id -> KnowledgeBase`, created lazily and cached.
This is the part that needs care: **per-tenant instances multiply the
IndexError race surface**, one copy per site.

The guarantee each instance must keep (now actually implemented in
`knowledge/engine.py`, having previously been documented but absent):

- `_scan()` builds `entries` and `index` into **locals**, then swaps both
  under `_swap_lock`. Never assign `self._entries` before the index exists.
- `query()` takes one `_snapshot()` and reads from locals for the whole
  ranking pass, so a reload landing mid-query cannot shift positions out from
  under the list they index into.
- The lock is **never** held across file I/O.

The registry itself needs the same discipline: creating a `KnowledgeBase` for
a site is not atomic (it does a full `_scan()` in `__init__`), so two
concurrent first-requests for the same site would otherwise build two
instances and race. Guard creation with a per-registry lock and a
double-checked lookup; hold the registry lock only around the dict operations,
not around the scan. A crawl finishing must publish its new corpus by the same
swap discipline, not by mutating the live instance in place.

---

## 3. Personality per site

Personality is currently a property of the **server** — one
`config/personality.json`, one `PersonalityEngine`. It must become a property
of the **site**, so two sites can hold different voices simultaneously.

Extend the existing `personality/engine.py` and `/personality` endpoint; do
not build a parallel system.

### 3.1 Presets

| preset | intended use |
|---|---|
| `professional` | **default for every new site** |
| `friendly` | warmer, still customer-safe |
| `concise` | minimal, answer-only |
| `shaggoth` | the existing rude voice — **opt-in only** |

The rude voice must never be inherited by a customer site. Default on
creation, not merely on the form.

Changing preset must **not** require a re-crawl: personality affects
generation only, so it lives in `site.json` and is read per request. Corpus
and voice are independent axes.

### 3.2 The voice is not only in personality/engine.py

Verified by grep — these hardcode the rude persona and will leak it through
any preset until they are made personality-aware:

- `dialogue/engine.py:1292` `compose_greeting()` — opening lines
- `dialogue/engine.py:1170` `describe_unknown()` — "don't know" replies
- `dialogue/engine.py:1188` — literal `"You'll have to be more specific than
  that. I'm smart, not psychic."`
- `dialogue/patterns.py:176` `FALLBACKS`, returned at `patterns.py:223`

Each needs to take the active personality and select from a per-preset phrase
set rather than a module-level constant.

### 3.3 Bug to fix in describe_unknown() while there

It prints the first extracted keywords raw, with no check that they form a
sensible subject. Reproduced locally:

```
"how many topics do you know so far" -> "topics far isn't in my head yet..."
"how does that sit with you"         -> "Nothing on sit yet..."
"what is quantum chromodynamics"     -> correct
```

The failure is confined to questions whose subject is not a real noun phrase.
Fix: if the extracted subject is fewer than two real words, or mostly
stopwords, fall back to a generic in-voice line ("I don't have anything on
that yet") instead of echoing fragments. This reads as broken in *any* voice,
so it blocks the customer-facing widget.

---

## 4. Domain ownership verification — mandatory, gates the first crawl

Without it the server is an **open crawl-on-demand proxy**: anyone registers
any domain and the r510 fetches it on their behalf. Abuse complaints land on
a residential IP.

Registration therefore yields a site in state `pending`, never `verified`, and
**no crawl runs until verified**. Two accepted proofs:

1. **DNS TXT** — `shaggoth-verify=<token>` on the domain.
2. **File** — `<token>` served at `https://<domain>/.well-known/shaggoth-verify.txt`.

The token is random per site and never reused. Re-verify periodically; a
domain that changes hands should stop being crawled. Verification failure is
a hard stop, not a warning.

---

## 5. Crawl policy — correcting the brief

The brief states the scraper does not honour robots.txt. **That is wrong, and
I checked before designing around it.** `shaggoth/scraper/engine.py` already
implements it and, crucially, *enforces* it:

- `ScraperEngine.__init__(respect_robots: bool = True)` — on by default
- `robots_allows()` with a 1-hour cache (`ROBOTS_TTL_SECONDS = 3600`)
- enforced in the fetch path at `engine.py:214`:
  `if self.respect_robots and not self.robots_allows(url): ...`
- descriptive UA already set:
  `ShaggothBot/0.1 (+https://ai.relayapp.pro; self-hosted research bot; contact: .../issues)`

Note `robots_allows()` **fails open** — a site with no robots.txt, or one that
cannot be fetched, is treated as allowed. That is the right default for our
own corpus building. For customer-domain crawling it is also acceptable *only
because* ownership is verified first.

What is genuinely **missing** and must be built:

- **Per-domain rate limiting.** `crawl()` loops `fetch_page()` with no delay
  between requests. Add a per-origin minimum interval and honour
  `Crawl-delay` when robots.txt specifies it.
- **Bounded crawls per site:** max pages, max depth, wall-clock timeout, and a
  cap on total bytes.
- **Scheduled re-crawl** so answers track site changes, with jitter so all
  tenants do not re-crawl at once.

---

## 6. Read-only by default

A visitor question must not trigger curiosity research into the global corpus.
Today `/chat` defaults the other way — `server.py` computes
`may_research = body.get("research", True) is not False`, so research is
**on** unless explicitly disabled.

Relying on the widget to send `research: false` is the wrong place for the
control: it is a client-supplied flag on a public, `Access-Control-Allow-Origin: *`
endpoint. Embedded traffic must be read-only **server-side**, keyed on the
request being a site-scoped widget request, and not overridable by the body.

Acceptance test: ask a nonsense term through the widget path, confirm
`total_episodes` does not move and no file appears in `data/knowledge/`.

---

## 7. Widget contract

```html
<script src="https://ai.relayapp.pro/embed/shaggoth-widget.js"
        data-site-id="..."></script>
```

One file, no build step, no dependencies. Start from the existing ~14.7KB
widget in the PurePulse clone.

- **Shadow DOM**, so host-page CSS cannot leak in or out.
- Degrades gracefully on 429 / unreachable / slow — **never an infinite
  spinner**; show a plain retry affordance.
- Keyboard accessible; ESC closes; transcript is `aria-live`.
- Mobile sizing via `dvh` / `visualViewport`, **not `vh`** — the keyboard
  overlap bug has bitten this project before.

---

## 8. Escalation — hand off to a human

Shaggoth is already honest when it does not know (`source: "fallback"`). On
its own dashboard "I'm off to research it now" is right. On a customer's site
that admission should route to a person instead of dead-ending.

### 8.1 Two failures, two messages — do not conflate them

This is the important structural point. "Overloaded" hides two unrelated
conditions, and they must not share a message:

| condition | truth | what the visitor sees |
|---|---|---|
| **Knowledge gap** — `source: "fallback"`, no corpus match | nobody here has written this down | offer a human: contact details + "pass this along" |
| **Service trouble** — 429, timeout, unreachable, backend down | the box is busy; the answer may well exist | "can't reach the assistant right now", retry + contact details |

Telling a customer "nobody knows the answer" when the truth is the server is
busy is a lie about the business. Keep the two paths separate all the way
through the widget.

### 8.2 Triggers

- `source == "fallback"` (no knowledge match)
- repeated low-confidence answers within one session
- visitor explicitly asks for a human
- backend unreachable / 429 / timeout

The last one forces a design constraint: **escalation must work while
Shaggoth is down.** Contact details therefore ship in the widget config at
embed time and must never require a live API call to retrieve.

### 8.3 Onboarding fields

- **support email — required**
- optional: phone, contact-page URL, business hours

Auto-discovery is a *fallback, not the primary path*: during the initial
crawl, scrape contact/about pages for `mailto:` / `tel:` and **pre-fill** the
form. Always show it for confirmation. A wrong support email silently
swallowing customer questions is worse than no widget at all, so a scraped
address is never used unverified.

**Surfacing is the owner's choice**, asked at onboarding: shown as plain
text, `mailto:` link only, or contact-page link only. Do not publish a
scraped address as plain text without an explicit opt-in — an address that
existed only behind a contact form should not be turned into scrapeable text
by us.

### 8.4 Behaviour

Show the contact details inline and offer to pass the question along. A
`mailto:` with the transcript prefilled is the zero-infrastructure option —
**do not build a ticketing system.**

The transcript contains whatever a visitor typed. **Nothing is auto-sent
anywhere.** The visitor initiates the handoff and sees the full content
before it leaves their browser.

### 8.5 Capacity

Worth correcting the premise: the ~85% idle CPU burn was root-caused and
fixed earlier today — an unindexed `keywords`→`messages` join in
`session_topics()`. Live process CPU is now **~11% of one core**, and `/chat`
went from 5.4–7.1s to **0.072s** (see AGENTS.md, commit `e195c3f`).

That materially changes the capacity picture: the per-request cost was the
constraint, and it is now ~75× cheaper. Still true, and still worth measuring
before several tenants embed:

- the 60 req/IP/min limit is **shared across all embeds** (§9)
- each tenant adds a `KnowledgeBase` held in memory; 814 entries currently
  cost ~420MB RSS at startup, so per-site corpora need a memory budget and
  probably an LRU eviction of idle tenants
- re-crawls are the real spike, not queries — schedule them with jitter

## 9. Open, deliberately not decided here

- **`SHAGGOTH_API_KEY` and rate limits are the user's call** and are not
  touched. Worth flagging: the current limit is **60 req/IP/min shared across
  every embed**, so one busy tenant degrades all others. Per-site quota is the
  natural fix but is a policy decision.
- `Access-Control-Allow-Origin: *` currently lets any origin call `/chat`.
  Once `site_id` exists, an allowed-origins list per site becomes possible —
  a real control, though not a security boundary on its own.
- Whether general-corpus fallback is ever offered to customers at all.
