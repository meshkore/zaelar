---
title: Glossary
updated: 2026-09-14
status: stable
---

# Glossary — one line per term

- **Colmena**: the two-speed brain design (Flash + Slow); implemented by `nucleo/`.
- **FlashBrain** (`nucleo/flash/`): sub-second voice layer, non-reasoning model chosen per invocation.
- **SlowBrain** (`nucleo/dispatch.py` + `memory_agent.py` + `agentes/`): async CodeAgent reasoning off the voice path.
- **escalate_to_slowbrain**: the Flash→Slow handoff call for memory/tools/reasoning.
- **memory/**: central SQLite memory (`zaelar.db`: vec + FTS5 + graph + forgetting + episodic layer).
- **bus/**: in-process pub/sub event bus + durable log + SSE bridge.
- **sparks** (`nucleo/sparks.py`): proactivity source feeding the loop/cron.
- **homeostasis** (`nucleo/homeostasis.py`): deterministic, model-free machine-health layer beside the brain.
- **SpeakerGate** (`frontend/app/lib/speaker-gate.js`): learns the owner's voice, filters other voices.
- **Widget** (`widgets/<id>/` + desktop.js): isolated visual unit (manifest + widget.js + data.py), voice-driven via silent tags.
- **EPIC-v2-colmena**: design source of truth in `.meshkore/roadmap/`.
- **/debug**: diagnostics surface (AudioProbe RMS, mic meter, client logs via `/api/client-log`).
