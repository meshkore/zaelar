---
title: Overview
updated: 2026-09-14
status: stable
---

# Zaelar — overview

Zaelar is a **voice-first personal-life assistant**: warm, remembers you, helps run your day. It speaks by voice, shows **graphical widgets** on a canvas when useful, and runs on its **OWN brain** — the `nucleo/` module («Colmena»): a two-speed brain (**FlashBrain** for the sub-second voice turn + **SlowBrain** async agents) with its **own central memory** (`memory/`, SQLite) and cron/proactivity. No external agent.

**Status**: voice round-trip works (STT → nucleo → TTS, streaming); memory persists across sessions; widgets (agenda, weather/search, browser) work on a drag-and-drop desktop; speaker-gate v1 filters other voices. Runs locally at `http://localhost:43917` (`make run`). Pending: more importers/connectors, wake-word, SpeakerGate v2.

**Source of truth**: `docs/product/zaelar-product.md` (onboarding) + `docs/architecture/zaelar-architecture.md` (mental model) + `EPIC-v2-colmena` (roadmap). The `/architecture` route this file used to point at was retired on 2026-07-24; the curated public diagrams live in the `web/` repo under `/technology`, and `docs/architecture/` is the detailed source.
