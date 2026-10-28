---
title: Glossary
updated: 2026-10-26
status: stable
---

# Glossary — one line per term

- **Colmena**: the two-speed brain design (Flash + Slow); implemented by `nucleo/`.
- **FlashBrain** (`nucleo/flash/`): sub-second voice layer, non-reasoning model chosen per invocation.
- **SlowBrain** (`nucleo/dispatch/` + `memory_agent.py` + `agentes/`): async CodeAgent reasoning off the voice path.
- **Slow lane / slow-process model** (`services.slow_process`, V2-811): a cheaper, slower model seat for background work that can wait (classify, extract, summarise, paraphrase); off by default; the route is decided once per rule or task and stored. Not the SlowBrain.
- **escalate_to_slowbrain**: the Flash→Slow handoff call for memory/tools/reasoning.
- **memory/**: central SQLite memory (`zaelar.db`: vec + FTS5 + graph + forgetting + episodic layer).
- **bus/**: in-process pub/sub event bus + durable log + SSE bridge.
- **sparks** (`nucleo/sparks.py`): proactivity source feeding the loop/cron.
- **homeostasis** (`nucleo/homeostasis.py`): deterministic, model-free machine-health layer beside the brain.
- **SpeakerGate** (`frontend/app/lib/speaker-gate.js`): learns the owner's voice, filters other voices.
- **Widget** (`widgets/<id>/` + desktop.js): isolated visual unit (manifest + widget.js + data.py), voice-driven via silent tags.
- **Screens** (V2-792): the computer and the phone open on the same agent at once. A request's cards open on the screen that asked (`origin_dev`), the other screen gets a chip; the voice lives on one screen. A widget's manifest `"screens"` says whether it is `shared` (a reflection, open anywhere) or `single` (sound or picture: one screen, it moves).
- **/debug**: diagnostics surface (AudioProbe RMS, mic meter, client logs via `/api/client-log`).
- **Personal Operating System**: the public positioning (zaelar.com) — one voice agent + a canvas of apps (widgets).
- **Apps**: where generated widgets are kept; «describe it and it writes the widget» (beta).
- **MeshKore network**: an open agent network Zaelar orchestrates; it finds external live agents (bookings, searches and many other services) through the **Oracle** (`nucleo/mesh_agents.py`) and talks to peers over **clusters** (`connectors/meshkore/`).
- **Self-hosted / hosted**: the same engine run locally (`make run`, free, fair-code) or as the hosted version (see zaelar.com).
- **PWA** (`frontend/mobile/`): the phone shell, installed from the browser; the voice lives on one device at a time.
