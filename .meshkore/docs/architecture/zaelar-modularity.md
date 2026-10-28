# zaelar — Modularity and coupling contracts

> Canonical doc for the **map of pieces**: how modules connect, which contracts exist (event / facade call /
> DB), the kill-switch inventory and the rules for adding new pieces. Keep it aligned whenever the topology
> changes (it is part of docs-sync).

## 1 · Guiding principle

zaelar is **a single process** with isolated modules that connect ONLY through three kinds of seam:

1. **EVENTS** — the bus (`bus/`, fnmatch pub/sub + loop-agnostic `emit_sync`) for async/fan-out work; the
   observer (`voice/observer.py::emit`) for turn telemetry, BRIDGED to the bus as the `observer` topic.
2. **Facade CALLS** — each domain exposes a public surface; the hot voice path uses direct calls (never wait on
   an event inside the turn).
3. **DB** — a single SQLite `zaelar.db` with a **single writer** (queue `memory/queue.py` → `writer.py`);
   concurrent WAL reads.

**Golden rule:** a new piece is mounted in the lifespan (`server/__init__.py`) behind a config/env gate, exposes
idempotent `start()`/`stop()`, subscribes to the bus (it does not import other domains' internals), and its
failure NEVER takes voice down (try/except "voice/chat unaffected").

## 2 · Per-domain facades (the public surface)

| Domain | Facade | Notes |
|---|---|---|
| `memory/` | **`memory/api.py`** (imported as `from memory import api as memory`) + `memory/journal.py` (task continuity) | `__all__` declared in `api.py`. Writes go through the queue; `set_state`/`forget`/user-rules are direct (RLock, by design: immediate effect) |
| `bus/` | `bus.publish/emit_sync/subscribe/add_sink` + `bus.log.recent/count` | `bus/log.py` is a **sink that persists EVERY bus event** (table `events`) — the durable audit substrate |
| `widgets/` | `widgets.dispatch_tag` + `widgets/server_api.py` (HTTP + `brain_action` + `run_widget_action`) + `runtime.catalog/identify/get` + `generator` | The `_run_widget` pool (4 threads + 8 s timeout) isolates every `data.py` |
| `voice/` (brain contract) | `observer.emit/turn_detail`, `brain_notes.push/drain`, `proactive.notify`, `trace.begin/adopt/scope`, `attention`, `speech`, `tag_protocol` | Transport-agnostic upper level; `voice/engine/` is the MOTOR (LiveKit) and its internals are not a facade |
| `nucleo/` | provider `voice/engine/llm/providers/nucleo.py` (edge with voice) + `dispatch` (sessions facade: `active_sessions/has_active/resolve_sessions/inject_soon/cancel_soon`) + `escalate` + `memory_agent` | The `dispatch._SESSIONS` registry is private RAM; it is read ONLY through its facade |
| `connectors/` | `connectors/<x>/service.py` per connector + `connectors/messaging/ingest.py` (topics) | |
| `config/` | one owner module per store (`settings.py`/`connectors.py`/`v2.py`) with a redacted public view | |

## 3 · EVENT contracts (bus topics)

Every topic is ALSO persisted in `zaelar.db·events` by `bus/log.py` (when `ZAELAR_BUS_LOG=1`).

| Topic | Emitter | Subscriber(s) | Key payload |
|---|---|---|---|
| `observer` | `voice/observer.emit` (bridge `bus/sse.py`) — EVERY timeline event | SSE `GET /events`, viewer, tester judge, **Susurro** | `{kind,label,text,role,extra,trace,span}` |
| **`turn.completed`** | `voice/observer.turn_detail` (called by BOTH paths: voice provider and probe) | **Susurro** | full turn: `{user, reply, system_prompt, window, tools, decision, engine, trace}` |
| `memory.updated` | `memory/queue`, `api._emit`, prompt(query) | SSE bridge (coalesced), `memory_cache` (sink) | `{op, ids}` |
| `escalate.requested` / `escalate.done` | `nucleo/flash/escalate` | `nucleo/dispatch` (sole consumer) | `{id, request, context{trace}}` |
| `worker.spawned/phase/result/say/done/error/cancelled` | `nucleo/workers/session` | log/UI | per session |
| `worker.ask` / `worker.say` | `nucleo/cli/worker_api` | log/loop | `{id, question, corr_id}` |
| `worker.stuck` / `worker.budget_nudge` / `worker.budget_kill` | `nucleo/pulse/loop` (supervisor) | log, **Susurro (friction)** | `{id, age_s}` |
| `loop.tick` / `loop.scheduled_fired` / `loop.spark` / `loop.consolidated` | `nucleo/pulse/loop` | pulse SSE / log | |
| `connector.msg` / `connector.status` / `msg.mark_read` / `msg.reply` | `connectors/messaging/ingest` | owner of `mensajeria`, consumers | |
| `susurro.finding` | `nucleo/susurro` | dev-loop (test→fix cron) | structured finding |

**Relevant observer events by `kind`** (all with `trace`/`span` stamped automatically by `emit()`):
`transcript` (🗣 user / zaelar), `brain` (prompt/reply/notes/escalation/promise-without-action), `perf`
(forensic turn_detail: system+window+tools+**decision**), `widget`/`backed`/`background`, `music`, `search`,
`task` (phase/dedup/resume), `rail` (incl. `fail` → `sin_resolver`), `vad` (barge-in/false interruption),
`alert`+`error` (degraded turn), `ambient`, `memory`, `timing`, `trace` (root), `susurro`, `homeostasis`
(the autonomous MACHINE-health layer, `nucleo/pulse/homeostasis.py`; labels
`start`/`degraded`/`recycle`/`rotate`/`evict`/`alert`).

**Agent-to-agent conversation pact.** The cluster bridge (`connectors/meshkore/bridge.py`) emits channel observer
events with a **`pact`** field in the **`🤝 pact updated`** event when a per-peer pact is sealed (negotiated
cadence / medium / scope). The `cluster.pact` tag is **allowed from a cluster turn** — it is on the cluster-turn
tag allowlist next to `cluster.send`/`cluster.done` (the operator's other capability tags stay blocked from a
peer turn). The pact is the THIRD level of rules (system/hard > operator > pact), lives in the per-peer capsule
(`capsule.pact`), only RESTRICTS our behaviour (it never grants capabilities, closed vocabulary) and its cadence
is enforced for real by a throttle in `cluster.send` (`capsule.cadence_wait`). Details in
`.meshkore/docs/security/zaelar-security.md`.

## 4 · Kill-switches (inventory)

**Startup gates** (lifespan; pattern `active_brain()=="nucleo" and os.getenv(X,"1")=="1"`):
`ZAELAR_MEMORY` · `ZAELAR_LOOP` · `ZAELAR_SLOWBRAIN` · `ZAELAR_BUS_LOG` (default 0) · `MESHKORE_AUTORECONNECT` ·
**`ZAELAR_SUSURRO` + config `susurro.enabled`** · **`ZAELAR_HOMEOSTASIS`** (the autonomous machine-health
layer, `nucleo/pulse/homeostasis.py`).

**Per piece:** `MEM_PROCESSOR` (the HEART) · `BROWSER_SEARCH` · `MESHKORE_MEMORY` · `ZAELAR_LOG_PROMPTS`
(forensic turn_detail capture; ⚠️ the Susurro needs it — with it off, the Susurro degrades to loose signals) ·
`MEM_SEMANTIC_DEDUP` · `MEMORY_RERANK*` · `WIDGETS_BACKED_MAX_FAILS` · config flags `flags.brain`,
`memory.rerank_provider='off'`, `attention_mode`.

**Extension points:** a global kill-switch for the widget system, a per-widget background disable, and a
read-only (dry-run) memory mode would all slot into the same lifespan-gate pattern.

## 5 · Documented coupling exceptions

These cross-domain dependencies are known, deliberate and bounded; new code does not extend them.

| # | Coupling | Rule |
|---|---|---|
| 1 | `voice.engine.core.langs` imported from nucleo/dispatch/prompt/probe — a language utility that lives inside the motor | Frozen by the dependency-direction ratchet (§7); new code adds no sites; the target is a home in a neutral low layer |
| 2 | `widgets.navegador.tasks/owner` and `widgets.mensajeria.data` imported from the provider/nucleo (the core knows these widgets by name) | Accepted for the two first-class backed widgets; the pattern is not extended |
| 3 | Lazy inverse coupling `memory/server_api.py` → `nucleo.memory_agent` | It is how the single-writer rule is enforced over HTTP |

Facade rules that are already in force: `widgets.server_api.run_widget_action()` is the public entry for running
a widget action (no private `_run_widget` imports), `memory/api.py` declares `__all__`, cross-domain imports at
module level are lazy, `turn.completed` is emitted from the single `observer.turn_detail` point both voice and
probe call, and the probe drains `brain_notes` exactly like the voice provider.

## 6 · Rules for a new piece (checklist)

1. Own module declared in `cluster.yaml`; idempotent `start()`/`stop()`; mounted in the lifespan behind a gate
   (config store wins, env fallback) and an isolating try/except.
2. Connects through the **bus** (subscribe) and **facades** — never deep imports into another domain nor private
   `_x` names.
3. Memory writes through `memory.api` (queue/gates); NEVER the DB directly.
4. Telemetry through `observer.emit` with its own kind (the trace is stamped automatically); domain events
   through `bus.emit_sync` with a `domain.event` topic.
5. Fail-open: its failure does not affect voice; no locks shared with the turn; I/O outside the turn's event
   loop.
6. Minimal mutable global state, with `reset()` for tests.
7. Docs-sync: entry in CLAUDE.md + category doc + `/architecture` diagram + this doc if the topology changes.

## 7 · Dependency directions — frozen and guarded

A rule each caller has to remember is not a rule, so dependency directions are enforced by a ratchet, like the
size table: `tests/infrastructure/unit/test_dependency_directions_only_improve.py` (testmap **7.32**, sibling
of 7.22).

What it freezes, from a full AST measurement of the tree:

- **The (file → module) pairs that reach `voice.engine.*` from outside `voice/`** — the boundary §2 already
  declares («the motor's internals are not a facade»). The inventory can only shrink; a NEW pair is red with the
  fix in the message: use the facade, or extract the shared thing to a lower layer. `voice.observer` /
  `proactive` / `tag_protocol` are the blessed brain-contract surface and are NOT in scope.
- **Private (`_x`) names that cross a domain boundary** — an explicit allowlist
  (`nucleo/workers/findings.py` → `widgets.navegador.act_api._HANDED`). Keeping that list tiny is what makes the
  guard cheap: any new offender is a decision, not noise.

`voice/engine/core/langs.py` is a shared language utility that happens to live inside the motor and accounts
for most of the frozen pairs, almost all imported lazily. Its destination is a home in a low layer with a
re-export shim at the old path (the `text_norm.py` / `errors.brief` precedent); meanwhile the frozen inventory
holds the line.

**Growth doctrine, in one paragraph:** as the tree grows, prefer a thousand small pieces over one giant one —
the size ratchet (7.22) enforces the *pieces*, this one enforces the *joints*. A file that outgrows its ceiling
pays by extracting a cohesive concern behind aliases, never by raising the ceiling; a module that needs another
domain goes through §2's facade, never through its internals; anything two domains both need gets extracted
DOWN, not imported ACROSS.
