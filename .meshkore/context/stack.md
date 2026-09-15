---
title: Stack
updated: 2026-09-14
status: stable
---

# Stack — blindado (do not change without operator sign-off)

| Layer | Choice | Why locked |
|---|---|---|
| Voice engine | LiveKit Agents (Python) + Silero VAD | Turn-taking/VAD/barge-in governed, no custom watchdog on the critical path |
| STT default | Local Whisper (MLX on Apple Silicon, faster-whisper elsewhere) | Free, private; cloud STT (Deepgram/AIMLAPI) is explicit opt-in |
| TTS default | Deepgram Aura-2 (es+en); Kokoro local = free option | Voice quality; local fallback unlimited + private |
| Brain | Own `nucleo/` (Colmena): Flash non-reasoning + Slow CodeAgent | Sub-second voice turn; reasoning stays off the voice path |
| Memory | SQLite `zaelar.db` (sqlite-vec + FTS5 + RRF + graph) | Single-file, local, queryable; no external DB |
| Server | FastAPI (`python -m server`), WebRTC audio + HTTP + SSE | Composition root: serves frontend, ICE, events, widgets API, wizard |
| Frontend | Vanilla ES modules, no build; `--hb-*` CSS tokens, dark default | Thin shell; SVG icon language from `lib/icons.js` only |
| Runtime | Python 3.11+, async-first; `http://localhost:43917` | Matches LiveKit Agents + MLX ecosystem |
