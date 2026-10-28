---
title: Zaelar Memory Change Workflow
category: ops
updated: 2026-07-14
owner: ricart
status: current
---

# MEMORY change workflow — "run the memory workflow"

**Trigger:** when the operator says **"run the memory workflow"** («pasa el workflow de memoria», or "review/close
the memory change"), or when YOU have just touched something STRUCTURAL in memory and are about to call it done —
run this checklist before saying you are finished.

It exists because a memory change **radiates**: the substrate is written and read by many pieces (FlashBrain,
memory agent, widgets, connectors, reset, episodic layer, viewer). Whenever the schema, the write HEART, the
retriever or the read speeds change, you must verify that **all those interactions — on write AND on read — stay
aligned**, document it in several places, test and commit. This workflow captures that once, so nobody has to
re-investigate "who does this affect" every time.

> It is the `memory/` specialization of [[zaelar-change-protocol]] / [[zaelar-docs-sync]] /
> [[zaelar-alignment-review]]. Current state of the subsystem: [[zaelar-memory]] (source of truth for the
> design).

---

## 0. Does this workflow apply? (scope filter)

It applies if the change alters something that **any memory writer or reader has to respect**. Yes to any of
these → full workflow:

- **Schema / pill** — columns of `memories` (`slot`/`meta`/…), `state`, `edges`, `episodic`, `journal`;
  `memory/schema.py` + migration in `memory/db.py` (`SCHEMA_VERSION`).
- **The write HEART** — `nucleo/memory_agent/processor/distill.py` (LLM processor: prompt, model, pill output) or
  `nucleo/memory_agent.py` (`classify`/`ingest_utterance`/`remember`/`_write_atom`/`compose_context`).
- **Writer / queue / slots** — `memory/writer.py` (insert, supersede/dedup by slot, reinforce, delete),
  `memory/queue.py`, and the **canonical registry `memory/slots.py`** (adding/renaming a slot or an alias affects
  writer + memory_agent + the processor prompt AT ONCE — that is the point: one single place).
- **Retriever / scoring** — `memory/retriever.py` (vec/FTS/RRF, weights α/β/γ/δ, graph_expand),
  `memory/embeddings/`.
- **Read speeds** — `memory.state()`, `memory.recent_short()`, `memory.query()`; and the FlashBrain cache
  `nucleo/flash/memory_cache.py` + `nucleo/flash/prompt.py` (`needs_recall`/`compose_recall`).
- **Consolidator / forgetting** — `memory/consolidator.py` (promote/dedup/decay/evict) and its trigger from
  `nucleo/pulse/loop.py`.
- **Observability / viewer** — `memory/viewer.py` + `GET /api/memory/viewer/*` (`server/memory_viewer_api.py`),
  the bounded `memory/api.py::map`, the `memory.updated` SSE bridge in `server/__init__.py`,
  `frontend/app/components/MemoryMap.js` + `components/memory/`, `kind=memory` rows in `DebugPanel.js`.

**It is NOT triggered by**: a comment, an internal rename, a tweak that touches neither the data contract nor
any of the interactions above. Carry on as usual.

---

## 1. Impact map — "if you touched this, review/update that"

### 1a. Memory WRITERS (all through the `memory/api.py` facade, async — never the DB directly)

| Writer | Where | What to review after a change |
|---|---|---|
| **HEART — operator turn** | `nucleo/memory_agent.ingest_utterance` → `mem_processor.process` (LLM) / `classify` (fail-open) → `remember`/`_write_atom` | New pills respect the schema (`slot`/`meta`/`ttl`); fail-open still works without Ollama; wiring in `voice/engine/llm/providers/nucleo.py` (fire-and-forget). |
| **SHORT conversational buffer** | `voice/engine/llm/providers/nucleo.py` (`memory.write(kind='conv', level='short', ttl_days=…)`) | It stays EPHEMERAL (TTL), NOT durable; it feeds `recent_short`; it does not re-inflate memory with raw writes. |
| **SlowBrain / agents** | `nucleo/memory_agent.remember({text,kind[,slot,meta]})` (the only sanctioned SlowBrain writer); `nucleo/dispatch/` | It passes `slot` for singular facts; it does not block. |
| **Brain Workers (EXTERNAL)** | `hbmem remember` (`nucleo/cli/mem.py`) → `POST /api/memory/remember` (`memory/server_api.py`) → `memory_agent.remember_external` | It requires the per-task token (mem_cli headers); it applies the P0a gates + identity-slot veto + `meta.source="worker:<id>"`; it NEVER touches `state`; the worker's Bash stays limited to the CLIs (`dispatch._tools_for` without bare "Bash"). Session result: only if `ok` (`workers/session._deliver`). |
| **Worker context at START** | `nucleo/dispatch._compose_context` → `memory_agent.compose_context` | The «CONTEXTO DE MEMORIA» block of the worker prompt is NOT empty (guard in `tests/agent_headless/unit/test_dispatch.py`). |
| **Hard reset** | `nucleo/reset.py` (`set_state({trabajo_interrumpido})` + `memory.write(level='short')`) | Freezing to STATE + logging to SHORT stay valid with the new schema. |
| **Live UI context → STATE** | Canvas (authoritative frontend): `POST /api/canvas/state` (`server/canvas_api.py`) → `set_state({open_widgets})`; running tasks: `nucleo/dispatch/::_emit_activity` → `set_state({activity})` | The report normalizes instance ids and dedups; `set_state` does NOT overwrite other fields (shallow patch); it fires `memory.updated` to refresh prompt+map. |
| **Widgets / lifecycle** | `widgets/lifecycle.py` (`record_created`/deletion tombstone) | Creation/removal traces are written through the facade; golden rule "history is never deleted". |
| **Connectors / messaging** | `connectors/messaging/store.py` (`memory.write(kind='msg', level='short')`) | The dump still goes through the facade; `slot` if the datum is singular. |
| **Episodic (paste/drop)** | `memory/episodic.py` ← `memory/server_api.py` (`write_episode`) | The searchable summary is still indexed in `memories` (vec/fts). |
| **Spoken rules** | NOT memory since V2-806: `nucleo/flash/style_directive.py` (both channels) → `rules.shape.write` → rows of the rules table (`rules/`) | That memory composes no rule; that each surface reads `rules.notes.for_surface` / `rules.prompt.voice_block`; that the event carries the scope. Nodes 2.172, 2.204, 2.811. |
| **Request rows** | `nucleo/request_row.py` (inline ops) + `nucleo/tasks.py` (worker sessions) + `nucleo/batch/runner.py` (list steps) → `memory/tasks_store.task_put`/`task_patch`; the end state as the `spec` artifact (`artifact_put`), the verdict from `nucleo/circuit.py` | One row per request; a later op never improves a failed row; schema v9 `verdict`; the prompt's `task_block.recent_lines` still reads it. Nodes 2.194, 2.196, 2.198. |
| **Workflow table** | `memory/workflows_store.workflow_upsert` / `workflow_hit` / `workflow_forget` (re-exported by `memory.api`) | That a channel that stopped serving is demoted, not kept as the first answer. |

### 1b. Memory READERS (direct, NO LLM on the path — golden rule)

| Reader | Where | What to review |
|---|---|---|
| **STATE (µs, always in the prompt)** | `memory.state()` → `nucleo/flash/memory_cache._compose` (incl. live UI context: `open_widgets`/`activity`) | `_compose` renders the new fields (lists included); invalidation by `memory.updated` intact. |
| **SHORT (µs, whole working set)** | `memory.recent_short()` → `memory_cache._compose` ("Conversación reciente" block) | It still reads directly (no embeddings) and bounded (limit/max_chars). |
| **LONG (ms, on demand, off-loop)** | `nucleo/flash/prompt.compose_recall` → `memory.query` → `retriever.search` → **reranker** (`memory/rerank.py`, fail-open); `asyncio.to_thread` + `needs_recall` | It NEVER enters the event loop; scoring stays coherent; the reranker stays fail-open. |
| **Brain Workers (serial read)** | `hbmem recall` → `POST /api/memory/recall` → `memapi.query()` | It stays read-only and filters `untrusted` (the retriever does it); it never opens the DB. |
| **SlowBrain (off-hot-path, may use an LLM)** | `nucleo/memory_agent.compose_context` | The only face that may use a recall LLM — verify it stays off-hot-path. |
| **Viewer / diagnostics** | `memory/viewer.py` → `GET /api/memory/viewer/*` → `MemoryMap.js` + `components/memory/` | No stored row leaves the viewer and every total is a COUNT (node 1.11); a new kind that is not his own fact is kept out of `_OWN_KINDS_SQL`. |

> **Golden latency rule (repeated because it is easy to break):** **LLM on WRITE (off-hot-path), DIRECT queries
> on READ.** No change may put an LLM or SYNCHRONOUS memory I/O into the voice turn.

---

## 2. Schema migration (if you touched columns/tables)

- Bump `SCHEMA_VERSION` in `memory/schema.py` and add an **idempotent, NON-destructive ALTER** migration in
  `memory/db.py::_migrate` (SQLite has no `ADD COLUMN IF NOT EXISTS` → check `PRAGMA table_info` first).
- Indexes that depend on new columns are created **after** the ALTER (never in `BASE_DDL`, which runs before).
- **Verify both paths**: a new DB (from `BASE_DDL`) and an existing old DB (v_previous → v_new) — it migrates and
  **loses no data**. Test with a simulated DB of the previous version.

---

## 3. Document — the golden rule is ALWAYS all three places, never two out of three

1. **`zaelar-memory.md`** (source of truth): §Schema, §The write HEART, §Reading at THREE speeds, §How the rest of
   the system USES it, §Observability — whatever you touched.
   - **If you changed a memory MODEL** (distiller or REM synthesis), the place is **§Memory models**: the table
     of the two tasks, why the criterion differs for each (price in the HEART because it runs every turn; quality
     in REM because it is one call per day with bounded input), the VETOES with their reason, and the fallback
     chains. Also: **save the raw report** of the run in `tests/memory/e2e/bot/resultados/` and add its row to
     that folder's `README.md`. The rule is that nobody should have to RE-RUN a benchmark to know why we use a
     model — explanations come from the doc, not from the memory of whoever ran it. Dense verdicts go to
     `zaelar-model-benchmarks.md §12.x` and the curated summary the operator sees to
     `config/model_benchmarks.py` (all three, or they drift apart silently).
2. **`CLAUDE.md`**: the "Central memory" key decision + the `memory/`/`nucleo/` module bullet + (if it is a new
   invariant) its hard rule. **Explain how memory is used from other modules** — keeping it current is mandatory
   (write AND read).
3. **Public diagram** `/technology/memory`, maintained outside this repo (a MANUAL step — no workflow syncs it
   automatically): pieces + **models in use** (the write processor's model, embeddings, etc.) + cost (local/free vs
   cloud), only if the change is significant from the outside.

---

## 4. Tests — not just code review

- `.venv/bin/pytest memory/ nucleo/ -q` (with `ZAELAR_EMBED_BACKEND=hash` so it does not depend on Ollama).
- Add/adjust tests for what you changed: schema/migration (`memory/test_pill_slot.py`), heart
  (`tests/memory/integration/test_memory_agent.py`), writer/retriever/consolidator.
- **Determinism**: the LLM processor is turned off in tests with `MEM_PROCESSOR=0` (heuristic path); to exercise
  the LLM, mock `mem_processor.process`.
- If you touched writers outside `memory/` (messaging, widgets, reset), run THEIR suite too.

---

## 5. Restart and verify live (if you touched `.py`)

- `make run` and check in the **🧠 viewer** (the orb's bowl) + the **◷ column** that memory forms as expected
  (curated pills, STATE populated, no raw junk). The `kind=memory` event stream must reflect the change.

---

## 6. Commit / push

- Commit with a pathspec (`git commit -- <paths>`) after checking that `git diff --cached --name-only` is empty,
  with a message that names the change; then push, as described in `CLAUDE.md`.

---

## 7. Close with the alignment review

Run [[zaelar-alignment-review]]: **code ↔ CLAUDE.md ↔ zaelar-memory.md ↔ the Memory diagram on `/technology` ↔
tests** must tell the SAME story (current state, no dirty/legacy). It is the final quality gate.

---

## Summary for the operator (when done)

Report in 4 lines: **(1) what changed** in memory; **(2) which writers/readers I reviewed** and whether they stay
aligned; **(3) migration + tests** (green/red); **(4) docs + diagram** updated and alignment passed. If anything
was left open (calibration, a consumer still to migrate), say so explicitly.
