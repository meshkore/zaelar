# Module map — what lives inside each module

**What this is.** The DENSE inventory: for every module declared in `.meshkore/public/cluster.yaml`, which pieces
make it up, what each one decides and why it lives where it does. `CLAUDE.md` holds rules and pointers; this is
architecture documentation.

The SHORT map (one line per module, for orientation) is in `CLAUDE.md`. The architecture with its diagrams is in
`.meshkore/docs/architecture/zaelar-architecture.md`; the per-module detail, in
`.meshkore/docs/modules/zaelar-modules.md`. The rules the engine follows today are in
`.meshkore/docs/criteria.md`.

## Declared modules (`.meshkore/public/cluster.yaml`)

Before creating a new module, declare it in `.meshkore/public/cluster.yaml`. No loose `.py`/`.html` at the root;
start with `make run` → `python -m server`.

- `voice/` — **LiveKit engine** in `voice/engine/`: `AgentSession` (streaming, turns, VAD, barge-in,
  preemptive generation) + provider registry + remote/local profiles (`core/`, `speech/`, `llm/`,
  `pipeline/agent.py` with an embeddable `make_server()`, `speech/voices.py`). Turn-taking/VAD/barge-in are governed
  by LiveKit (Silero VAD + `MultilingualModel` turn detector + `allow_interruptions`). The layer above is the brain
  contract, **pure and transport-agnostic**: `tag_protocol.py`, `speech.py`, `brain_notes.py`, `proactive.py`,
  `prompt.py`, `health_state.py`, `llm_health.py`, `observer.py` (SSE), `attention.py` (the attention gate — decides
  which turn is addressed to zaelar; ambient vs attending).
- `nucleo/` — **the engine's own brain, «Colmena»**: an ORCHESTRATING FlashBrain + Claude Code workers. It is exposed
  to the engine as a `livekit.agents.llm.LLM` provider (`voice/engine/llm/providers/nucleo.py`, `BRAIN=nucleo` =
  default). `nucleo/flash/` = **FlashBrain**, the sub-second reflex (`router.py` classifies the input +
  `fast_client.py` fast non-reasoning model client **per invocation** + `frontend.py` frontend/widget manager +
  `procs.py` process launcher + `escalate.py` escalation + `prompt.py` [assembles the turn prompt: composed STATE +
  a TERSE resources layer, ~30 lines] + `memory_cache.py` [caches `memory.compose_state()` outside the turn + seeds
  the mission] + `prewarm.py` [warms FlashBrain + browser at startup] + `dialog.py` [conversational stability:
  break-loop + history pruning + anti-degeneration, SHARED by voice and probe] + `probe.py` [headless TEST channel,
  the third way of testing: `POST /api/flash/say`]). **Search** lives in its own `search/` package (`web.py` = the
  chain shared by both brains; `browser.py` = Google via a persistent Chromium; `nucleo.websearch` /
  `nucleo.browser_search` are aliases) — map in `zaelar-search.md`. **Latency — memory is NOT in the synchronous
  turn**: the STATE block (name/register/topics) comes from `memory_cache` (session cache, TTL + async refresh +
  invalidation on `memory.updated`), and semantic recall (`prompt.compose_recall`) is **on demand**
  (`prompt.needs_recall`) and **off the event loop** (`asyncio.to_thread`) — a chit-chat turn never triggers the
  retriever. `nucleo/loop.py` (~1 Hz) + `nucleo/scheduler.py` (**the engine's OWN cron**, backed by
  `memory.journal`) + `nucleo/cron_api.py` (`/api/cron`, the ⏰ panel) + `nucleo/sparks.py` (double-gated sparks) =
  the **orchestrator loop** (scheduled tasks + proactivity + triggers the memory consolidator off the hot path +
  reports by voice and UI; mounted in the lifespan with `BRAIN=nucleo`). `nucleo/dispatch.py` (dispatcher: composes
  the prompt [context + task] → CodeAgent with a per-invocation model, consumes `escalate.requested` from the bus,
  delivers by voice and UI) + `nucleo/memory_agent.py` ★ (the MEMORY agent, the single writer to `memory/`; its
  `compose_context` is the worker's **multi-axis dossier**: profile without mission + rules + ⚠️ critical items
  ALWAYS + recall + `by_concepts` + agenda, durables only, `to_thread`) + `nucleo/mem_processor.py` ★ (the WRITE
  heart: a fast non-reasoning model configured under `§memory` — default `deepseek/deepseek-v4-flash`, chosen by the
  distiller benchmark in `zaelar-model-benchmarks.md` §12.3 for matching completeness and precision at a lower cost;
  `gpt-4o-mini` is excluded because it writes facts in the wrong language into identity slots. Key PER ENDPOINT +
  health tracking with an alert on a streak of failures, so a dead writer never goes unnoticed; writing may be slow,
  it prioritises writing WELL — it DISTILLS every turn into curated pills — datum + metadata, decides
  DISCARD/STATE/SHORT/LONG + importance + `slot`; off the hot path, fail-open to the heuristic [which degrades to
  short + TTL rather than polluting]; **deterministic PRECISION gates**: discards reified requests/questions/acks,
  never lets an STT-garbled name overwrite the identity in `state` — quarantine — and never makes an ephemeral
  preference durable) + **`nucleo/workers/`** (**Brain Workers** — an AGNOSTIC substrate: `base.py`
  [`WorkerBackend`/`WorkerEvent`/`WorkerSpec`], `claude_session.py` [live stream-json], `generator_session.py`
  [widgets, wraps the killable generator], `codex_session.py` [Codex CLI, `exec --json`], **`grok_session.py`**
  [Grok Build; INHERITS from `claude_session` because its wire format is the SAME], `registry.py` [`get_backend` by
  config, mixable], `session.py` [`WorkerSession` + `SessionRecord`], **`providers.py`** [a CHAIN of
  Anthropic-compatible endpoints + hand-over when a quota is exhausted]) = the INTERACTIVE async work layer.
  `nucleo/agentes/` (the one-shot `CodeAgent` interface — `worker/web/web_cc/otros.py` are **parked**; only their
  widget-detection helpers are reused). **Worker bridges**: `nucleo/mem_cli.py` (`hbmem` — serial memory,
  recall/remember over HTTP) · `nucleo/agent_report.py` + `nucleo/agent_api.py` (`hbnote` — phase report to the bus)
  · **`nucleo/worker_bridge.py` + `nucleo/worker_api.py`** (`hbask`/`hbact`/`hbsay` — ask / request a tool / speak
  to the user, a request/response plane, `/api/worker/act`, policy + piggyback + token) ·
  `nucleo/nav_cli.py` + `widgets/navegador/act_api.py` (`hbweb` — drive the browser) · **`nucleo/widget_cli.py`**
  (`hbwidget` — READ/OPERATE a canvas widget: `read`/`data`/`show`/`close`, the `widget_data` action of
  `/api/worker/act` gated by the canonical catalog + worker provenance; the BRIDGE that reflects in the widgets what
  was done in the real world). `nucleo/danger.py` = the gate for irreversible actions. **`nucleo/susurro/`** =
  **conversational self-audit «Susurro»** — plugged in ONLY through the bus (topic `turn.completed` + friction), a
  configurable stronger model under `§susurro`, closed-catalog corrections. **`nucleo/homeostasis.py`** = the
  **AUTONOMOUS HEARTBEAT** — the third level, a SIBLING of the brain (not part of it): keeps the MACHINE healthy
  (recycles a degraded LiveKit engine when safe, rotates logs, evicts dead capsules), deterministic and with NO LLM,
  `start()/stop()` in the lifespan like the other supervisors.
- `memory/` — **central, human-like memory**, a 100% local SUBSTRATE (the write-side LLMs go through an API), one
  SQLite file `zaelar.db` (WAL, in `memory/_data/`): a shared substrate written by the FlashBrain, the memory agent
  and the widgets, and read by the retriever on the hot path (ms). **`memory.compose_state()`** composes the
  **SHARED STATE** both brains see — mission (`state.mission`) + situational + synthesized recent conversation — as
  a DIRECT read (µs, no LLM, no retriever); `nucleo/flash/memory_cache` caches it outside the turn. Every memory is
  a **PILL**: canonical datum (`text`) + metadata (`slot`/`meta`, schema v2). **`slot`** = the canonical key of a
  singular fact (`operator.name`, `goal.current`…) → the writer does **EXACT supersede/dedup with no LLM** ("the most
  recent one WINS": same datum = reinforce; changed datum = invalidate ALL current ones — self-healing). The **slot
  vocabulary lives in the SINGLE REGISTRY `memory/slots.py`**: aliases + `state` field + identity flag, consumed by
  the writer (`canon_slot`), the memory agent (gate P0b) and the processor prompt (GENERATED catalog) — the three
  layers cannot diverge; the consolidator adds `heal_slots()` (normalizes legacy slots + collapses multiple current
  rows on every sleep). The **atom contract v2** adds `value` (→ a `state_patch` synthesized MECHANICALLY from the
  registry) and `change: none|update|correction` (a change signal from the multilingual processor ITSELF → the
  anti-garble gate consumes it; the es/en regexes remain a backstop, not the only mechanism). Tables
  `state·memories·vec_memories·fts_memories·edges·episodic·journal` · queue + writer (single writer, embeddings on
  insert) · embeddings (OpenAI `text-embedding-3-small` 768 titular, `embeddinggemma` via Ollama as the local
  option, no cross-model failover; provider configurable via `memory.embed_*`, a change is a migration through
  `memory/reembed.py::migrate` with a model signature; dedup thresholds per model in `memory/dedup_thresholds.py`) · retriever (sqlite-vec + FTS5 → RRF k=60 → score
  α·rel+β·rec+γ·imp+δ·use → local cross-encoder **reranker** `memory/rerank.py` → graph_expand) · graph ·
  consolidator (LIGHT sleep: Ebbinghaus decay PER WINDOW + dedup + prune_invalid + eviction by weight, pinned rows
  untouchable) · **`memory/rem.py`** (DEEP sleep, the daily «REM phase» — repairs `embed_pending` vectors + SEMANTIC
  dedup by cosine + INSIGHTS per concept [`slot=insight:<c>`, an LLM hook injected from `nucleo/memllm.py`,
  configurable model — benchmarks §12.4] + hygiene with an alert; kill-switch `ZAELAR_REM`) · **episodic** layer
  (it absorbed the old `files/`: paste/drop → `memory/server_api.py` → `memory.write_episode`, binary + searchable
  summary, lazy load) · facade + `memory.updated` signal on the bus.
  **`memory/vault.py`** ★ (the operator's ENCRYPTED secrets VAULT — asymmetric sealed-box crypto via PyNaCl + an
  Argon2id passphrase envelope + WebAuthn PRF passkeys; tables `vault_meta`/`vault_secrets`), **`memory/secrets.py`**
  (FAIL-CLOSED detection + redaction) and **`memory/vault_api.py`** (`/api/vault/*`, loopback). Design in
  `zaelar-memory.md`.
- `observability/` — **WHO · WHEN · in which FLOW**. It completes the event log (which already recorded WHAT
  happens) with the axes to ANALYZE it: `identity.py` (a stable **`user_id`** per installation — a random UUID4 in
  the gitignored `config/identity.json`, created and logged **explicitly in the server lifespan** at startup;
  `ZAELAR_USER_ID`, when set, wins over the file — and a **`session_id`** per operator WORK SESSION: it starts on
  connect, closes with ⏻ or when the tab closes, and a reconnection does NOT split it in two) · `flows.py` (reading
  by **CORRELATION ID**: flows with their real end-to-end duration, families, actors, tokens and errors;
  chronological detail; sessions; coverage) · `api.py` (`/api/observability/*`). **The correlation id is NOT a new
  id: it is the turn's `trace` PROMOTED** from a JSON field to an indexed column (`events.corr_id`) — a second,
  parallel id would drift from the first at the first unstitched cross-loop seam. A new flow is born with every
  operator request; whatever continues a live flow inherits its id.
  **A correction spoken while a task is still live MERGES into that task's `corr_id`** instead of opening a new
  one: `send_to_worker`'s handler (`nucleo.py::_on_tool_call`) already resolves its target via
  `dispatch.resolve_sessions()`; when that resolves to exactly one live session, this turn adopts its `trace_id`
  (`dispatch.trace_of` + `trace.adopt`) instead of keeping the fresh one `trace.begin()` opened at turn start. With
  several live sessions and no unambiguous match, nothing merges — an extra flow beats guessing which task a
  correction belongs to. A flow's end is EXPLICIT (`kind="flow"`, emitted where the worker session that spawned it
  finishes), not inferred from silence.
  **A single utterance split across several LiveKit turns also merges:** LiveKit closes one turn per STT-final
  segment, so `_begin_or_adopt_trace()` (`nucleo.py`) checks the fragment accumulator's `pending()`: while a
  fragment chain is open, the next turn ADOPTS its trace rather than opening one, cleared once the chain resolves.
  If the accumulator judges a sentence complete and the operator keeps talking about the same thing, that opens a
  new chain/trace — the design favours one flow per sentence chain.
  **A pending confirmation's answer also merges into the turn that asked** (`widgets/confirm.py::request()`
  captures `trace.current()`, `_resolve_confirm()` adopts it before executing/cancelling) — the ask/answer/action of
  an irreversible confirm-gate reads as one flow even across a barge-in-cancelled reply attempt in between.
  `flows()`'s SQL exposes `origin` (the `trace.begin(origin=...)` argument: `turno`/`kickoff`/`ui`/`cron`/
  `proactivo`/`cluster`/`probe`) and `title` (that root event's text) per flow — what a flow viewer uses to tell a
  real task apart from session initialization (kickoff greeting, canvas-restore reconciliation within the session's
  first ~10 s) and to label each column/rail item with more than a bare corr_id.
  **A plain conversational flow closes EXPLICITLY too**, so a viewer never has to guess liveness from recency:
  `_run`'s success path (never the `CancelledError` branch — a barge-in cancellation may still get continued by the
  next fragment) calls `_maybe_close_flow()`, which closes the current trace UNLESS the fragment accumulator still
  expects more on it, a confirmation asked on it is still pending, or a worker is still running on it
  (`dispatch.has_live_trace`, the reverse of `trace_of`) — that worker owns the close instead.
  **A confirmation's "sí"/"no" is resolved BEFORE any slow work**: a clear yes/no is resolved right after the
  hard-interrupt check, before the model is even called, so a turn cancelled by barge-in can never lose the answer
  and leave the confirmation pending; ambiguous replies fall through to the late-stage deterministic backstop
  (`classify_reply` + resolve) after the model's response.
  **A widget can opt out of the visual Sí/No overlay** (`"confirm_ui": false` in its manifest,
  `nucleo.py::_confirm_ui_paints`; e.g. `widgets/agenda/manifest.json`, a voice-only card): the confirmation
  itself, and voice resolution, are unchanged — only the SSE emit that paints the card overlay is skipped.
  READ-ONLY: the only writer of `events` is still the bus sink.
- `bus/` — **the nervous system**: in-process signal pub/sub (asyncio, fnmatch patterns + a loop-agnostic
  `emit_sync` via `call_soon_threadsafe` for cross-loop delivery job-thread↔uvicorn). `bus/log.py` = durable event
  log in SQLite (`zaelar.db`, table `events`, WAL). `bus/sse.py` = SSE bridge to the frontend (`GET /events`).
  HYBRID transport: direct calls on the voice hot path + events for async/fan-out. **No Kafka/broker.**
- `frontend/` — the interface as a **build-less ES-module** app, migratable to Solid (reactive core + services +
  components + widget desktop). Voice through the **LiveKit client** (`services/session-lk.js` + the SDK vendored in
  `frontend/vendor/`). See `zaelar-modules.md §Frontend`. **The frontend's NATIVE surfaces = «SYSTEM widgets»,
  UNTOUCHABLE**: their SINGLE CANONICAL LIST lives in **`frontend/app/core/system-surfaces.js`**
  (`SYSTEM_SURFACES` + `isSystemSurface()`) — activity honeycomb, camera/mic, orb, TopBar, connection state, chat
  (Chat/Processes/Crons), status panel ◉, config ⚙, benchmarks, debug ◷, memory map 🧠, wizard 🧭, vault 🔐, notice
  banner and boot splash. `main.js` MOUNTS them from that list (no duplication). The generator/`lifecycle` NEVER
  touch them (they only touch `widgets/<id>/`). **Everything else on screen is a USER WIDGET** (catalog
  `widgets/<id>/`, full-stack `manifest.json` + `data.py` + `widget.js`), variable and created by/for the user
  **even when shipped by default** — like the connectors. Adding a new native surface = adding it to
  `system-surfaces.js`. Every voice-addressable surface carries a FIXED `name` + `aliases` (hardcoded in the front,
  NOT editable) — mirrored in the backend `widgets/system_surfaces.py` (sync test) so the name resolver knows them.
  Every user-widget card paints a generic HEADER (in `desktop.js`, without touching its `widget.js`) with the NAME +
  a ⚙ that unfolds its editable ALIASES.
- `server/` — FastAPI app + routers + entrypoint (`server/__main__.py`); runs the **LiveKit agent worker EMBEDDED**
  in the process (lifespan), and starts in that same lifespan the `nucleo/` loop, the supervisor of `backed` widgets
  and the memory-queue consumer. Routers: `livekit_api` (token + config + session.js swap), `voice_api`, `cron_api`
  (`/api/cron`), `wizard_api`, `spotify_api`, `config_api` (`/api/config*` — the full-screen configuration area),
  **`memory/vault_api`** (`/api/vault/*` — the secrets vault, always mounted), widgets, pages.
- `widgets/` — full-stack widgets (`data.py` + `widget.js` per folder), generator, catalog, runtime. Two *kinds* in
  `manifest.json`: `passive` (default) and **`backed`**: a widget with its own process (`owner.py`) supervised by
  `widgets/supervisor.py` (mailbox + restart with backoff + disable after N failures, isolated from voice). Backed
  widgets = **`navegador`** (a real web browser inside zaelar) and **`mensajeria`** (unified WhatsApp + Telegram
  messaging; its owner triages inside the widget itself with a LOCAL model, gated `"gate":"nucleo"`).
  **`widgets/background.py`** = the **BACKGROUND execution scheduler with a cycle**: a widget declares
  `"background": {"every": "1m"}` and keeps working OFF-SCREEN at its period (minimum 1 s) — a passive widget's
  `data.py:tick(ctx)` run in a thread, or a `tick` command queued to a backed owner — to refresh data and **write to
  memory** what the operator may ask about by voice. `widgets/actions.py` = action semantics; `widgets/refs.py` =
  resolving references to items.
- `config/` — runtime settings managed by the UI (gitignored): `settings.json` (⚙ STT/TTS/voice/language),
  `connectors.json` (connector flags + credentials), `v2.json` (model routing `fast`/`code_agent` + **`memory`**
  [reranker + embedding] + `active_brain()`), `meshkore.json`. Each with its owner module
  (`settings.py`/`connectors.py`/`v2.py`) and a **redacted public view** (secrets → `<key>_set: bool`; any key ending
  in `api_key` is redacted). `profiles.py` + `doctor.py` = coordinated profiles + detector (the setup wizard);
  `credentials.py` = the single writer of the credential store. **`balances.py`** = external API balances
  (proactive where the provider exposes it — ElevenLabs — and reactive through a classified error for the rest). The
  **full-screen configuration area** (⚙) is served by `server/config_api.py` (choose API/model per PIECE) +
  `frontend/app/components/ConfigPanel.js`; its balance alerts appear in the status dialog (◉).
- `connectors/` — external connectors; **`connectors/files/` = files in the CLOUD** (Google Drive + OneDrive: a
  typed provider registry + shared PKCE + one client per provider behind the **agnostic facade** `service.py`, which
  returns ONE normalized shape — a third provider does not touch the widget; doc `zaelar-cloud-files.md`);
  `connectors/meshkore/` = the native cluster channel (a third I/O next to voice + chat), driven by the
  **FlashBrain engine in the UNTRUSTED profile** (`brain.py` adapts the channel to the engine →
  `nucleo/flash/cluster.py`, tools off + identity-safe system prompt) with a conversation **capsule**
  (`capsule.py`); `connectors/architect/` = a code/projects provider over the shared MeshKore daemon
  (`[[architect.*]]` tags, operator-only); `connectors/whatsapp/` = personal WhatsApp (vendored Baileys bridge);
  `connectors/telegram/` = personal Telegram (Telethon userbot); `connectors/email/` = **personal email** (IMAP/SMTP
  in **pure stdlib**, logic vendored from the Hermes adapter — read + triage + **reply** over SMTP with threading;
  app password + Gmail/Outlook/other presets); `connectors/messaging/` = the **shared messaging layer** (with
  OUTBOUND: a `pending_reply` queue + `msg.reply` → the `reply_message` tool behind the confirm-gate). See
  `zaelar-modules.md §Connectors`. Beyond its own connectors, zaelar orchestrates external services: the MeshKore
  network's agents, external MCP servers and third-party APIs give it access to bookings and a wide range of
  external services.
- `tests/agent_headless/harness/` — synthetic conversational evaluation harness + judge.
- `tests/voice/e2e/mic/` — headless self-test of the microphone→STT transport over WebRTC.
- `tests/voice/e2e/agent/` — voice tester: a second LiveKit participant that TALKS to zaelar and a JUDGE that
  evaluates what it DOES.

`files/` was folded into the episodic layer of `memory/` (a compatibility shim) and holds **`files/attachments.py`**
(V2-809): what the upload door does for a file added to the CHAT — kind from the bytes, the declared limits
(`config/attachments.default.json`), the bounded reading (text, PDF text layer, an image read by the
`image_reader` model), and the turn's state of what he just attached (CRIT-M11). Root (non-modules): `README.md`,
`Makefile`, `requirements.txt` + `.venv/`, `Dockerfile`/`.dockerignore`, `scripts/` (per-OS install tooling),
`CLAUDE.md`. **Logging → `.meshkore/logs/`** (do not create `logs/` at the root).

Also declared in `cluster.yaml`: `i18n/` (multilingual runtime + language preparation), `update/` (the
user-visible build number and the reload signal), `daemon/` (the LOCAL daemon, not the shared MeshKore one),
`tools/` (developer review aids), `files/` (the compatibility shim above) and `scripts/`.

## A request's life and the spoken rules

- `nucleo/spec.py` — a request is born with its END STATE (manifest `done_when`, the escalate call's `done_when`,
  the brief's `end_state`); RAM ledger + the task row's `spec` artifact.
- `nucleo/circuit.py` — the pulse re-verifies every open spec; the bound is the operator's (genesis `circuit.retries`);
  the verdict is what the mouth says.
- `nucleo/request_row.py` — every request that acts is ONE `tasks` row (`kind=inline` included); `nucleo/tasks.py`
  maps a worker session onto that row.
- `rules/` — every standing rule and preference is a scoped row; `rules.shape` writes it once from his words,
  `consent.decide` reads its gate, `rules.prompt` composes only the notes in play (`zaelar-rules.md`).

Architecture: `zaelar-architecture.md` §5h (the request) and §5i (the turn's doors, in order).

## Pieces split out of larger files

Each one is a verbatim move with no behaviour change; the source module imports the names back, so callers and
monkeypatches keep working. Look here before grepping for a name that seems to have disappeared.

- `nucleo/flash/tool_executor.py` — the voice turn's tool executor (out of `providers/nucleo.py::_run_inner`).
- `nucleo/flash/post_stream.py` — the chain that runs after the model's stream ends (same origin).
- `nucleo/flash/probe_after.py` — the post-model blocks of the text probe's `run_turn` (`probe.py`).
- `nucleo/flash/commission_guards.py` — the commission readers (out of `router_guards.py`).
- `nucleo/flash/anthropic_sse.py` — the Anthropic SSE parser (out of `fast_client.py`).
- `nucleo/flash/payload_fill.py` — the payload fills of a direct widget action (out of `direct_action.py`).
- `nucleo/dispatch_listener.py` — the escalation listener; `dispatch.py` stays the facade.
- `nucleo/workers/session_notes.py` — the session's notes as a mixin; `nucleo/workers/tool_steps.py` — tool-step readers.
- `memory/workflows_store.py` — the `workflows` table (out of the memory facade).
- `server/canvas_api.py` — the canvas routes, on their own router (out of `voice_api.py`).
- `voice/interrupt_grammar.py` — the hard-interrupt grammar (out of `attention.py`).
- `voice/engine/pipeline/prewarm.py` — the worker prewarm (out of `pipeline/agent.py`).
- `i18n/langspec.py` — the `LangSpec` dataclass (out of `voice/engine/core/langs.py`).
- `connectors/email/headers.py` — header and sender-authentication readers (out of `mailbox.py`).
- `widgets/agenda/twins.py`, `widgets/youtube/helpers.py`, `widgets/mensajeria/{answers,timing}.py` — out of
  each card's `data.py`.

The size ratchet (`tests/infrastructure/unit/test_files_and_functions_only_shrink.py`, node 7.57) stops the split
files from growing back.

## Reference docs by mechanism (not listed in `CLAUDE.md`)

| Mechanism | Doc |
|---|---|
| A known phrase skips the model | `.meshkore/docs/modules/zaelar-action-map.md` |
| One bounded-choice primitive and where it may sit | `.meshkore/docs/modules/zaelar-decision-model.md` |
| One canonical home per datum; what memory is not for | `.meshkore/docs/architecture/zaelar-domain-stores.md` |
| A commission's durable record | `.meshkore/docs/modules/zaelar-jobs.md` |
| The workflow table (what serves this kind of errand) | `.meshkore/docs/modules/zaelar-workflow-table.md` |
| A message with several tasks becomes a list | `.meshkore/docs/modules/zaelar-task-lists.md` |
| The agenda's numbered task lists | `.meshkore/docs/modules/zaelar-agenda-task-lists.md` |
| The agent's own filesystem (`library/`) | `.meshkore/docs/modules/zaelar-agent-filesystem.md` |
| Speaker identity | `.meshkore/docs/modules/zaelar-speaker-identity.md` |
| Directing a research errand | `.meshkore/docs/architecture/zaelar-research-direction.md` |
| The Google connector (one account, six doors) | `.meshkore/docs/modules/zaelar-google-connector.md` |
| Cloud files connectors + explorer | `.meshkore/docs/modules/zaelar-cloud-files.md` |
| Photos picker + gallery | `.meshkore/docs/modules/zaelar-fotos-connector-and-widget.md` |
| Video widget + video-account connector | `.meshkore/docs/modules/zaelar-video-widget-and-account-connector.md` |
| Embedded torrent add-on | `.meshkore/docs/modules/zaelar-torrent-addon.md` |
| Mobile shell (PWA) | `.meshkore/docs/modules/zaelar-mobile-shell.md` |
| Update channel | `.meshkore/docs/modules/zaelar-update-channel.md` |
| Local daemon: build/release, threat model | `.meshkore/docs/ops/zaelar-daemon-build.md`, `.meshkore/docs/security/zaelar-daemon-security.md` |
| Where a browser window for him can open — a display here, a connected daemon that declares `browser.auth` (registered by its transport), or nowhere (a sign-in then BLOCKS the process and says why) | `nucleo/browser_window.py` (its docstring is the reference) |
| Config tabs + connector registry, widget naming | `.meshkore/docs/architecture/zaelar-config-connectors-v2083.md`, `.meshkore/docs/architecture/zaelar-widget-naming-v2082.md` |
| Memory re-verification cycle | `.meshkore/docs/ops/anexos/zaelar-memory-cycle-playbook.md` |
