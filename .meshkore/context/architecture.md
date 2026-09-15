---
title: Architecture
updated: 2026-09-14
status: stable
---

# Architecture — mental model

**Three layers, decoupled** (full model: `docs/architecture/zaelar-architecture.md`):

1. **Voice + canvas** — the ONLY user surface (`:43917`). Mic → STT → brain → TTS; widget desktop driven BY VOICE via silent tags over SSE. `frontend/` is a thin ES-module shell (no build), no business logic.
2. **Brain («Colmena» = `nucleo/`)** — decides + acts. **FlashBrain** owns the sub-second voice turn (non-reasoning model, per-invocation); **SlowBrain** runs async Claude Code / Codex agents off the voice path (`escalate_to_slowbrain`). Loop (~1 Hz) + own cron + sparks own proactivity. Drives the canvas through a thin tag contract.
3. **Compute** — one atomic headless agent per widget task: born → builds `widgets/<id>/` → exits. File tools only, scoped, hard timeout, output validated.

**Ownership**: `memory/` (SQLite `zaelar.db`: vec + FTS5 + graph + forgetting) is the central memory; `bus/` is the in-process event bus; `server/` (FastAPI) is transport + composition root; `config/v2.py` owns model routing. Layers are independent — widgets never touch the voice core. Beside the brain sits a deterministic autonomic homeostasis layer (`nucleo/homeostasis.py`, no model) for machine health.
