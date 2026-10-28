---
title: Stack
updated: 2026-10-28
status: stable
---

# Stack — locked shape (do not change a layer without the operator's sign-off)

The MODELS are not listed here: `config/models.default.json` is their one public source (V2-500), with the reason
each provider was retired. This page is the SHAPE — which layer exists and why it is locked.

| Layer | Choice | Why locked |
|---|---|---|
| Voice engine | LiveKit Agents (Python) + Silero VAD | Turn-taking/VAD/barge-in governed; no custom watchdog on the critical path |
| STT / TTS | Hosted providers from the model table (today Deepgram STT, Inworld TTS), chosen per invocation | Latency and quality measured; the table decides, never a global env |
| Brain | Own `nucleo/` («Colmena»): FlashBrain non-reasoning for the turn + Brain Workers (Claude Code / Codex agents) off the voice path; a decision model (Jev) answers closed questions the turn pays once | Sub-second voice turn; reasoning stays off the voice path; verdicts over text guards |
| Memory | One SQLite `zaelar.db` (sqlite-vec + FTS5 + RRF + graph), embeddings from the table (OpenAI direct; never a relay) | Single-file, local, queryable; no external DB |
| Search | `search/` service: one door (`find()`), providers declared once with a health probe | A fact is answered in the turn; a search never leaves the service |
| Rules | `rules/` one scoped table (global → domain → widget → item) | Preferences are data the engine reads, never constants |
| Server | FastAPI (`python -m server`): WebRTC audio + HTTP + SSE; LiveKit worker embedded | Composition root: frontend, ICE, events, widgets API, wizard |
| Frontend | Vanilla ES modules, no build; design-system tokens (`frontend/app/core/palette.css`, `components.css`, the elevation ladder, V2-689) | Thin shell; one visual language for native, generated and user widgets |
| Runtime | Python 3.12, async-first; `http://localhost:43917`; LiveKit native binary, no Docker in the core | Matches LiveKit Agents; self-host in one command |
