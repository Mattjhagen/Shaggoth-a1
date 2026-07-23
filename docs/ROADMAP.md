# Roadmap

## Phase 0 — Core platform ✅ (this PR)

- [x] Dialogue engine with 7-stage pipeline (guardrails → plugins → memory →
      generation → recall → output filter → persist)
- [x] Adjustable, hot-reloadable guardrails (JSON + CLI + HTTP)
- [x] SQLite memory: transcripts, fact extraction, cross-session topic recall
- [x] Trainable Markov language model (stdlib)
- [x] TinyGPT: from-scratch GPT-style transformer (optional torch), ready to
      train on the R510
- [x] Plugin system + built-ins (time, calculator, remember/recall)
- [x] REST API server (stdlib, CORS) — the mobile-app contract
- [x] Test suite (31 tests), research + architecture docs

## Phase 1 — Make the model real (on the R510)

- [ ] Train TinyGPT on a real corpus (project docs, public-domain books,
      exported chat logs) — see `docs/R510_SETUP.md`
- [ ] Word/BPE tokenizer to replace char-level (better sample quality)
- [ ] `settings.json` switch: `"model": "markov" | "tinygpt"`
- [ ] Overnight training routine on the R510 (systemd timer)
- [ ] Perplexity eval script so model upgrades are measurable

## Phase 2 — Platform hardening (pre-mobile)

- [ ] API auth (bearer tokens), rate limiting as a guardrail rule type
- [ ] Streaming responses (chunked/SSE) for typing-indicator UX
- [ ] Multi-user: per-user fact namespaces and session ownership
- [ ] Embedding-based memory recall behind the existing `Recall` interface
- [ ] Structured logging + `/metrics`
- [ ] TLS via reverse proxy (caddy/nginx) or Tailscale Serve — the API stays
      Tailnet-only; phones reach it through Tailscale

## Phase 3 — Mobile apps (iOS + Android)

Goal: a beautiful, Grok/Claude/ChatGPT-class chat client backed by the
Shaggoth API on the R510 over Tailscale.

**Recommended stack: React Native + Expo.** One codebase, genuinely native
feel, first-class chat libraries, over-the-air updates, and Expo Application
Services handles both App Store and Play Store builds. (Fully-native
Swift/SwiftUI + Kotlin/Compose is the fallback if we later need per-platform
polish the RN layer can't reach.)

- [ ] App scaffold (Expo + TypeScript), dark/light themes
- [ ] Chat screen: streaming bubbles, markdown rendering, haptics
- [ ] Sessions drawer (maps to `session_id`), local cache with offline replay
- [ ] Memory screen: view/edit facts (`GET /facts` + a future `PUT`)
- [ ] Guardrails screen: toggle rules from the phone (the "adjustable" promise,
      in your pocket)
- [ ] Tailscale on-device so the phone reaches the R510 anywhere
- [ ] Push notifications (Phase 2 server events)
- [ ] TestFlight + Play internal track, then store listings

## Phase 4 — Base-platform maturity

- [ ] Plugin marketplace layout (`shaggoth_plugins/` namespace packages)
- [ ] Voice in/out (on-device STT/TTS in the apps)
- [ ] Optional bridge plugin to external LLM APIs — the homegrown model stays
      primary; the bridge is just another swappable `LanguageModel`
- [ ] Multi-agent: several Shaggoth instances with different guardrail
      profiles talking to each other (PARRY-meets-ELIZA, 60 years later)
- [ ] Fine-tuning loop: nightly retrain on accumulated (consented)
      conversation logs
