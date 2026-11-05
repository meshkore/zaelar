---
title: Glossary
updated: 2026-10-26
status: stable
---

# Glossary — one line per term

- **Colmena**: the two-speed brain design (Flash + Brain Workers); implemented by `nucleo/`.
- **FlashBrain** (`nucleo/flash/` + `nucleo/turn/`): the conversation, the reflexes, the router, the mouth and the screen; one turn pipeline for voice and text, one non-reasoning model call chosen per invocation.
- **Router** (`nucleo/turn/flow_of.route`): the one door every request — and every event — goes through before anything is opened.
- **Task**: a request that is work. One row, one Brain Worker, one writer of its ending (`circuit.settle`).
- **Task row** (`tasks`, `nucleo/circuit/ledger.py`): the task's state — `state`, `waiting_for`, `waiting_since`, `deadline`, `ask_id`/`ask`, `session_id`, `cwd`, `playbook`, trace, artefacts. The row is the truth; the worker session is a cache.
- **Session id**: the harness's resumable id of a worker session, kept on the row with its cwd; an answer or an event resumes that session by id, re-briefed from the row.
- **Playbook** (`nucleo/workers/prompts/playbook.py`): the worker's method — nine checkpoints (understand, record, resolve the facts, choose channel and UI, compose, confirm, act, verify, report). The WORKER chooses one of `errand`, `message`, `document`, `lista` from the catalogue in its brief (the engine only suggests); Flash never picks one.
- **Checkpoint 1**: closed by `report playbook` + a readable `report goal` (the row's `playbook` and `done_when`); the harness (`nucleo/workers/exit_gate.py`) refuses any act that leaves the machine until it is closed.
- **Invariants I1–I8**: one identity per task (the row); the end state is the request's, never a card's presence; one writer of an ending, three causes, no clock; the mouth speaks the row; what leaves passes the leave door; his text never opens the voice; the screen paints the record; health and observability. See `docs/architecture/zaelar-architecture.md` §5h.
- **Directory** (`widgets/directory.py`): who a name is — one ranking of match strength (phonetic by default, literal in quotes) × closeness (recent conversation, then favorites → family → friends → colleagues → the rest); unclassified contacts are never send targets.
- **Contact pill** (`nucleo/memory_agent/contacts.py`): one structured memory line per managed contact, in its own lane; `who(description)` returns contact ids with evidence. REM links one person's records, never deletes them.
- **The asker** (`nucleo/circuit/asker.py`): the one function a question for him goes through, whoever asks; the row waits with an `ask_id`, the question goes on screen, the answer is bound by id (screen) or by the brief's verdict (voice).
- **Internal API**: the worker's hands — the agent's own doors reached through the bridge (`nucleo/cli/bridge.py` → `/api/worker/act`, per-task token), with consent inside each door.
- **Taint** (`nucleo/untrusted.py`, `nucleo/workers/taint.py`): the mark a worker session gets when it reads a stranger's text; afterwards an exit that leaves the machine carrying his data asks him (a bare query with nothing of his still runs).
- **Stream worker** (`nucleo/events/stream.py`): one always-on worker session per stream (mail, messages) serving the rules subscribed to it, resumed by id per item.
- **Mouth**: one function, two entries — in a turn the reply (`nucleo/turn/reply.py`), out of a turn `nucleo/pulse/notices.notify` (with a task id or a notice key).
- **Brain Worker** (`nucleo/workers/` + `nucleo/dispatch/` + `agentes/`): one headless agent session per task (Claude Code / Codex), off the voice path. «SlowBrain» is its older name.
- **Slow lane / slow-process model** (`services.slow_process`, V2-811): a cheaper, slower model seat for background work that can wait (classify, extract, summarise, paraphrase); off by default; the route is decided once per rule or task and stored. Not the Brain Worker.
- **escalate_to_slowbrain**: the model's call that makes a request a task (legacy name); a sure `escalate` verdict of the turn's brief routes it too.
- **memory/**: central SQLite memory (`zaelar.db`: vec + FTS5 + graph + forgetting + episodic layer).
- **bus/**: in-process pub/sub event bus + durable log + SSE bridge.
- **sparks** (`nucleo/pulse/sparks.py`): proactivity source feeding the loop/cron.
- **homeostasis** (`nucleo/pulse/homeostasis.py`): deterministic, model-free machine-health layer beside the brain.
- **SpeakerGate** (`frontend/app/lib/speaker-gate.js`): learns the owner's voice, filters other voices.
- **Widget** (`widgets/<id>/` + desktop.js): isolated visual unit (manifest + widget.js + data.py), voice-driven via silent tags.
- **Screens** (V2-792): the computer and the phone open on the same agent at once. A request's cards open on the screen that asked (`origin_dev`), the other screen gets a chip; the voice lives on one screen. A widget's manifest `"screens"` says whether it is `shared` (a reflection, open anywhere) or `single` (sound or picture: one screen, it moves).
- **/debug**: diagnostics surface (AudioProbe RMS, mic meter, client logs via `/api/client-log`).
- **Personal Operating System**: the public positioning (zaelar.com) — one voice agent + a canvas of apps (widgets).
- **Apps**: where generated widgets are kept; «describe it and it writes the widget» (beta).
- **MeshKore network**: an open agent network Zaelar orchestrates; it finds external live agents (bookings, searches and many other services) through the **Oracle** (`nucleo/mesh_agents.py`) and talks to peers over **clusters** (`connectors/meshkore/`).
- **Self-hosted / hosted**: the same engine run locally (`make run`, free, fair-code) or as the hosted version (see zaelar.com).
- **PWA** (`frontend/mobile/`): the phone shell, installed from the browser; the voice lives on one device at a time.
