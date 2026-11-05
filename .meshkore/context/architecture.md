---
title: Architecture
updated: 2026-11-05
status: stable
---

# Architecture — mental model

**Three layers, decoupled** (full model: `docs/architecture/zaelar-architecture.md`):

1. **Voice + canvas** — the ONLY user surface (`:43917`). Mic → STT → brain → TTS; widget desktop driven BY VOICE via silent tags over SSE. `frontend/` is a thin ES-module shell (no build), no business logic.
2. **Brain («Colmena» = `nucleo/`)** — decides + acts. **Flash is the interface and the life; the Worker does the work; the agent's memory is the state.**
   - **FlashBrain** owns the conversation, the reflexes (one declared action, one call), the router, the mouth and the screen. Every turn — voice or text — runs ONE pipeline (`nucleo/turn/pipeline.py`) with ONE model call (non-reasoning, per invocation); nothing runs the model after the main stream.
   - **The router** (`nucleo/turn/flow_of.route`) decides, before anything is opened, where a request goes: conversation, a reflex, an open flow, or a new **task**. Events (an inbound message or mail, a due job, a worker that ended or asked) go through the same door.
   - **A task** = one row of `tasks` + one Brain Worker session per request (Claude Code / Codex), resumable by id, following a **playbook**. The row is the truth (what it waits for, its open question, its session id); the session is a cache, re-briefed from the row. The worker asks him through Flash and ends; his answer resumes that session.
   - **The circuit** verifies against the task's end state and is the only writer of its ending. **One mouth** in a turn (the reply) and one out of it (`nucleo/pulse/notices`).
   - **The internal API**: the worker's hands are the agent's doors, reached through the bridge (`nucleo/cli/`) with a per-task token; consent lives in each door, and a session that read a stranger's text is tainted — its exits ask.
   - The pulse (~1 Hz) + own cron + sparks own proactivity. Drives the canvas through a thin tag contract.
3. **Compute** — one atomic headless agent per widget task: born → builds `widgets/<id>/` → exits. File tools only, scoped, hard timeout, output validated.

**Ownership**: `memory/` (SQLite `zaelar.db`: vec + FTS5 + graph + forgetting) is the central memory; `bus/` is the in-process event bus; `server/` (FastAPI) is transport + composition root; `config/v2.py` owns model routing. Layers are independent — widgets never touch the voice core. Beside the brain sits a deterministic autonomic homeostasis layer (`nucleo/pulse/homeostasis.py`, no model) for machine health.

**The slow lane** (`context/slow-lane.md`, V2-811): a second model seat for background work that can wait — off by default, adopted call site by call site, the route decided once and stored, never per item.
