---
title: Zaelar Modules
category: modules
updated: 2026-08-16
owner: ricart
status: current
---

| Module     | Path           | Description                                                                 |
|------------|----------------|-----------------------------------------------------------------------------|
| voice      | voice/         | Voice pipeline core (LiveKit engine in `voice/engine/`): providers, turn control, observer, tag protocol, STT, audio filter, TTS |
| nucleo     | nucleo/        | **Brain «Colmena»** (default `BRAIN=nucleo`). `flash/` = FlashBrain (sub-second voice, non-reasoning model per-invocation); `websearch.py` = SHARED web search (both brains, layered providers, V2-022); `dispatch.py`+`memory_agent.py`+`agentes/` = SlowBrain (async Claude Code/Codex `CodeAgent`, web search via native WebSearch/WebFetch); `loop.py` (orchestrator ~1 Hz) + `scheduler.py` (own cron) + `cron_api.py` (`/api/cron`) + `sparks.py`. Exposed to voice as `voice/engine/llm/providers/nucleo.py`. |
| memory     | memory/        | **Central memory** — SQLite `zaelar.db` (sqlite-vec + FTS5 + RRF + graph + forgetting). Absorbed the old `files/` as an episodic layer. `server_api.py` = `/api/files/*` + `/api/memory/map` (memory-map visualizer, V2-014). |
| bus        | bus/           | **Event bus** — in-process pub/sub (generalizes `voice/observer.py`) + durable SQLite log + SSE bridge. |
| observability | observability/ | **WHO · WHEN · in which FLOW** (V2-090) — completes the event log (`bus/log.py`, which already records WHAT happens) with the axes needed to ANALYZE it: `identity.py` (stable per-install `user_id` + per-session `session_id`), `flows.py` (read by correlation id — end-to-end flows with real duration, families, actors, tokens, errors), `api.py` (`/api/observability/*`). Read-only: the bus's sink stays the sole writer to `events`. |
| frontend   | frontend/      | Voice interface — self-contained ES-module app (no build), Solid-migration-ready (see §Frontend below) |
| server     | server/        | FastAPI app + routers + entrypoint (`python -m server`); HTTP API (voice, ICE, settings, widgets, pages) |
| widgets    | widgets/       | Full-stack widgets (data.py + widget.js per folder), generator, catalog, runtime |
| config     | config/        | Runtime settings (persisted in settings.json)                               |
| connectors | connectors/    | External connectors. `meshkore/` = native multi-cluster WebSocket I/O channel (see §MeshKore below). `architect/` = Architect code/project provider over the shared MeshKore daemon (see §Architect below). `whatsapp/`+`telegram/` over `messaging/` = the unified personal inbox (see §Messaging connectors). Future: email, LinkedIn, X |
| testing    | tests/         | Plataforma única: suites por dominio, catálogos schema 2, runners terminal/CI, harnesses headless/voz/browser y Test Observatory realtime en `127.0.0.1:8765`. Entrada de agentes: `tests/README.md`. |

All modules declared in `.meshkore/public/cluster.yaml`.

> **Layout invariant** — the repo root holds no loose `.py`/`.html`; every module lives in its own domain folder.
> Entrypoint: `make run` → `python -m server` (the server lifespan starts the embedded LiveKit worker, the `nucleo/`
> loop, the widgets supervisor and the memory queue consumer).

## Nucleo module (`nucleo/`) — zaelar's OWN brain «Colmena», two speeds

`nucleo/` is zaelar's brain — its own, with no external agent. Default `BRAIN=nucleo` (`config/v2.py:active_brain()`,
env-first). It runs at two speeds:

- **FlashBrain** (`nucleo/flash/`) — the sub-second, non-reasoning **voice** layer. It occupies the LLM slot of the
  voice engine as the provider `voice/engine/llm/providers/nucleo.py` (a `livekit.agents.llm.LLM` in streaming): the
  stream reads the last user turn, runs the fast model, and emits `ChatChunk`s already cleaned by
  `voice/tag_protocol.py` (side-effects) + `voice/speech.py`. Its model is chosen **per invocation** from
  `config/v2.py` `fast` section (`FAST_PROVIDER`/`FAST_MODEL`/`FAST_BASE_URL`/`FAST_API_KEY`) — a local Ollama model
  or an AIMLAPI/Grok cloud model (comparison in `.meshkore/docs/ops/zaelar-model-benchmarks.md`). It creates/cancels
  cron via `nucleo/scheduler`. **Hard constraint: the voice model MUST be non-reasoning** (a reasoner adds 5s+ of
  thinking latency to the real-time path). Reasoning belongs off the critical path — that is the SlowBrain.
  **Memory is OUT of the synchronous turn** (V2-011): the STATE block (name/treatment/topics) comes from a
  per-session cache (`nucleo/flash/memory_cache.py` — TTL + async refresh + invalidation on the bus signal
  `memory.updated`), and semantic **recall** (`nucleo/flash/prompt.compose_recall` → embeddings) is **on demand**
  (heuristic `prompt.needs_recall`, es/en) and **off the event loop** (`asyncio.to_thread`). A chat turn never
  fires the retriever, so it closes ~1s; the per-turn latency breakdown is emitted as a `timing` event on `/debug`
  (baseline vs. after in `zaelar-model-benchmarks.md §4`).
- **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` + `nucleo/agentes/`) — the **async** tier off the
  voice path. `nucleo/agentes/` is a `CodeAgent` interface with headless adapters (Claude Code `claude -p`, Codex)
  chosen from `config/v2.py` `code_agent` section (`CODE_AGENT_*`). `nucleo/memory_agent.py` is the **memory agent**
  — the SINGLE writer to `memory/`, composing minimal context by heuristic + a cheap LLM router. `nucleo/dispatch.py`
  is the dispatcher: it composes a dynamic prompt `[context + task]` for the CodeAgent (model per invocation),
  consumes `escalate.requested` off the bus, and delivers by voice + UI (`voice/proactive`).
- **Escalation** — the FlashBrain calls the tool `escalate_to_slowbrain(request)` (an OpenAI-compatible function
  call, not a text tag) → the dispatcher runs the SlowBrain in the background and delivers the result via
  `voice/proactive` + a `[SISTEMA]` note, so the fast layer never blocks the turn and never claims work it didn't do.
- **Web search — SHARED, model-agnostic capability (V2-022, `nucleo/websearch.py`)** — a **own primitive** used by
  **both brains** (we don't rely on model-native search; Grok/GLM/Z.AI lack it, Claude Code has it). **Who decides to
  search = the model, via function-calling** — no separate classifier. **Three modalities:** (1) direct datum +
  synthesis → the FlashBrain's `web_search(query)` tool, resolved **in the same turn** (~1-2s, no card, no browser);
  (2) navigating a marketplace (Amazon/Wallapop) → the **navegador** (`automate_web`, there's no search endpoint for
  that datum); (3) deep research/report → the **SlowBrain** CodeAgent with native `WebSearch`/`WebFetch` (enabled in
  `dispatch._tools_for`) and/or this primitive. **Layered provider, quality-first, auto-upgrade by key**
  (`websearch.provider()`): AI-answer (Perplexity Sonar → Tavily, synthesized + cited) → snippets (Brave) → **free**
  (DuckDuckGo HTML, in-process `httpx`, no key, always available); `WEBSEARCH_PROVIDER` forces one. Runs **off the
  event loop** (`asyncio.to_thread`); the answer is shaped to voice/language by the **model the turn already pays
  for** (2nd pass — rephrases an AI answer, or synthesizes from snippets) → ≈0 marginal LLM cost. Fail-open (degrades
  down the chain). Wired in `nucleo.py::_run`; routing enforced in `router.TOOLS` + `prompt._FAST_RULES`. See §5b of
  `zaelar-architecture.md`. Observability: `search` events on `/debug` (provider + ai + count + ms).
- **Attention gate (V2-015, `voice/attention.py`)** — the mic is always open, so BEFORE the FlashBrain acts, the
  provider (`nucleo.py::_run`) checks whether the turn is DIRECTED at zaelar. Mode `ZAELAR_ATTENTION` (UI-managed in
  `config/settings.py`, ⚙; env fallback): `smart` (default) = directed if it carries a **wake-word** ("zaelar" +
  STT phonetic variants) or falls inside the **active-conversation window** (`ZAELAR_ATTENTION_WINDOW`, def 30s after
  the last directed turn); `wakeword` = always require the wake-word; `ptt` = push-to-talk (frontend signal on the
  data topic `zaelar-ptt`); `always` = old behavior. A non-directed turn emits an `ambient` observer event and
  RETURNS — no action, no reply, and it does NOT drain `brain_notes` (they wait for the next attended turn). The
  kickoff greeting does NOT open the window (so a session started mid-meeting has no initial window for ambient
  speech to slip into); typed chat/paste is always directed (`agent.py` marks `note_directed`). A **hard interrupt**
  (`attention.hard_interrupt`, deterministic es/en) — "cierra los widgets / para / silencio" — is checked on the FULL
  text BEFORE the gate and executes immediately (`[[close]]` / stop), so it can never be buried in a giant turn; and
  `attention.clamp_input` caps the turn length (`ZAELAR_FAST_MAX_INPUT`) while PRESERVING an explicit command clause
  instead of blindly truncating the tail. Signal to watch: the `ambient` event (see `zaelar-observability.md`).
- **Orchestrator + cron** — `nucleo/loop.py` (~1 Hz) runs the orchestration; `nucleo/scheduler.py` is zaelar's OWN
  cron backed by `memory.journal`; `nucleo/cron_api.py` exposes `/api/cron` (the ⏰ panel); `nucleo/sparks.py` fires
  scheduled tasks + double-gated "sparks", triggers the memory consolidator off the hot path, and reports by voice +
  UI. All mounted in the server lifespan under `BRAIN=nucleo`.
- **Rails (V2-042, `nucleo/rails.py` + `nucleo/flash/music_flow.py`)** — the orchestration pattern for common
  CONDUCTED behaviors (fuzzy music, video, deep site searches, recursive watches…). A rail = a deterministic
  resolve→validate→act chain IN CODE (the FlashBrain stays non-reasoning; any 2nd pass reuses the turn's model) +
  its tool + **live RUNS** (`nucleo/rails.py`: a RAM registry projected to `state.rails` → rendered "Rails en curso"
  in the composed state; a FAILED run is kept ISOLATED as `sin_resolver` with label+attempts+TTL, resumable next turn
  — "era de Sinatra"; transitions emit `rail` events on `/debug`; `reset_all` clears them via `rails.clear_all`) +
  **typed memory writeback** (`memory.ingest_message(source=<rail>)`). Per-rail prompt guidance is injected ONLY
  while a run is live (`nucleo/flash/prompt._rails_directive` ← `rails.prompt_lines`) — zero prompt cost at rest.
  First rail = fuzzy music (`music_flow.py`, §Music connectors); the **widget circuit is the founding rail**
  (§Widgets). Pattern + domain map: `roadmap/initiatives/V2-042-rails-comportamientos-conducidos.md`.
- **Homeostasis (V2-070, `nucleo/homeostasis.py`)** — the **autonomic health supervisor**, a **sibling of the
  brain, not part of it**: it runs no model and does no reasoning; it keeps the **MACHINE** healthy, deterministically.
  Mounted in the server lifespan with `start(app)`/`stop()` (like the messaging/widgets supervisors), off the voice
  loop, fail-open, gated by env `ZAELAR_HOMEOSTASIS`. Binary rule (each resource is healthy or degraded→heal), THREE
  checks: (1) **LiveKit engine** — detects in-process degradation via a `logging.Handler` on the `livekit` logger
  (markers `wait_pc_connection timed out` / `entrypoint did not exit`) and, only when SAFE (voice off + channel idle
  ≥120s), **recycles the embedded worker** (`aclose` + `make_server` + new task, no process restart) with a cooldown;
  when unsafe it alerts the operator once and touches nothing; (2) **logs** — rotates `timeline-latest.jsonl` /
  `meshkore.jsonl` by rename over a size cap + prunes old archives; (3) **capsules** — evicts concluded+old per-peer
  capsules and caps the total (`sys_kv` `capsule:*`, via `memory.kv_keys(prefix)`/`memory.kv_del(key)`). **Distinct
  from the widgets `supervisor.py`**: the widgets supervisor watches widget *owner processes* (backed widgets);
  homeostasis watches the *machine itself* (LiveKit engine, logs, capsules). Emits observer events kind
  `homeostasis` (labels `start`/`degraded`/`recycle`/`rotate`/`evict`/`alert`); tests `tests/infrastructure/unit/core/test_homeostasis.py`
  (13 deterministic). Born from the 2026-07-25 incident: the embedded LiveKit worker degraded after ~7h and nothing
  self-healed until a manual restart. Initiative: `roadmap/initiatives/V2-070-homeostasis-anti-degeneracion.md`.

`BRAIN=direct`/`local` are plain-model baselines (no two-speed brain). The cluster channel uses the SAME FlashBrain
engine (`nucleo/flash/`) in the UNTRUSTED profile — tools off + identity-safe (§MeshKore).

## Memory module (`memory/`) — central human-like memory, 100% local

One SQLite file, `zaelar.db` (WAL, in `memory/_data/`), is the shared substrate the FlashBrain, the memory agent and
the widgets write, and the retriever reads directly (WAL, ms). The retriever does NOT run inside the synchronous
voice turn (V2-011): the FlashBrain reads a cached state block and does on-demand recall off the event loop — see
§Brain above. Design doc: `.meshkore/docs/architecture/zaelar-memory.md`. Pieces:

- **Schema** — tables `state · memories · vec_memories · fts_memories · edges · episodic · journal`.
- **Queue + writer** — a single writer (`nucleo/memory_agent.py`); embeddings computed at insert time. The queue
  consumer starts in the server lifespan (`ZAELAR_MEMORY`, default 1).
- **Embeddings** — `embeddinggemma` (768-dim) via Ollama, fallback fastembed, deterministic degradation.
- **Retriever** — sqlite-vec vector search + FTS5 keyword → **RRF** (k=60) → score `α·rel + β·rec + γ·imp + δ·use` →
  `graph_expand` over `edges`.
- **State / graph / consolidator** — a fixed `state` table (µs reads); graph edges; a consolidator (Ebbinghaus decay
  + dedup + weight-based eviction, pinned rows untouchable — "forgetting").
- **Episodic layer** — this ABSORBED the former `files/` module. A paste/drop upload calls
  `memory.write_episode(data, filename, mime)` (`memory/episodic.py`) → the binary lands in the memory data-dir
  (`memory/_data/episodic/`) alongside a **searchable summary** embedded into `memory.query` (vec + FTS; the binary
  loads lazy). See §Files below.
- **API** — `memory/api.py` facade + a `memory.updated` signal on the bus. `memory/api.py::map()` returns the WHOLE
  memory (state + memories grouped by layer short/long + `edges` + every per-unit metadatum) for the **memory-map
  visualizer** (V2-014); `memory/server_api.py` serves it read-only at **`GET /api/memory/map`** (`no-cache`). Real
  time: the server bridges `memory.updated` onto the `observer` topic (→ GET /events) as `{kind:"memory"}` so the map
  refreshes live without polling — see §Frontend (MemoryMap) + `zaelar-observability.md`.
- **`memory/seed_from_hermes.py`** — a one-shot, best-effort, READ-ONLY importer that seeds the operator profile from
  `~/.hermes` if that directory exists on the machine. It never writes to `~/.hermes` and is a no-op when absent.

## Bus module (`bus/`) — the in-process nervous system

`bus/` is zaelar's in-process **pub/sub** for signals (asyncio; a generalization of the old `voice/observer.py`),
with `fnmatch` topic patterns and a loop-agnostic `emit_sync` (`call_soon_threadsafe`, so events cross the
job-thread↔uvicorn loop boundary). `bus/log.py` is a durable event log in SQLite (`zaelar.db`, `events` table, WAL)
wired as a sink. `bus/sse.py` bridges the bus to the frontend: `voice/observer.py` is re-expressed as a subscriber of
the `observer` topic and `GET /events` is unchanged. Transport is **hybrid** — direct calls on the hot voice path,
events for async/fan-out. No Kafka, no broker.

## Frontend module (`frontend/`) — ES modules, no build, Solid-migration-ready

The interface is a self-contained ES-module app. **No build step, no npm** — the browser loads the modules directly;
the server just serves `frontend/` at `/static`. Designed so a future migration to Solid.js is mechanical.

```
frontend/
  index.html              thin bootstrap: <link> styles + vendored VAD <script>s + <script type=module> main.js
  pages/                  architecture.html · debug.html (internal pages)
  app/
    main.js               entry — mounts components, creates the widget desktop, starts the visualizer
    styles.css            all UI CSS (the widget desktop injects its own)
    core/
      reactive.js         createSignal / createEffect / createMemo / batch / onCleanup  ← Solid-COMPATIBLE API
      dom.js              h() hyperscript (the JSX-equivalent) + raw() + mount() + $
      store.js            app-wide reactive state as signals (conn, mic, cam, botSpeaking, voices, theme, …)
    services/             framework-agnostic logic — migrates UNCHANGED
      session.js          the WebRTC/session ENGINE (start/stop/reset/reconnect, mic+camera, speaker gate)
      theme.js            dark/light mode — applies the `theme` signal to `<html data-theme>` + persists it
      audio.js  vad.js  stt.js  sse.js  status.js  visualizer.js  voiceCommands.js  api.js
    components/           function components (read store, build DOM via h(), run effects) — map 1:1 to Solid
      Orb · CameraUnit · TopBar · SettingsModal · ConnStatus · Alert · ChatWall · StatusPanel · CronPanel · MemoryMap
      (ChatWall = text channel: type/paste → session.sendText → data channel → server ClientTextInjector → user turn;
       Ctrl/Cmd+V anywhere feeds it. CronPanel = the `/api/cron` view onto the `nucleo/` scheduler.)
      Orb = zaelar PERSONIFIED; it owns a BOWL (concave semicircle) of FIVE frameless controls UNDER the orb —
      L→R: ⏰ cron (opens CronPanel; MOVED here from the TopBar, V2-014) · 🧠 memory (opens the MemoryMap visualizer,
      store.memOpen) · 🔊 mute zaelar's voice (CENTRE, lowest) · 📝 toggle LIVE CAPTIONS · 🤖 attention gate
      (blue/ON = `wakeword`, only acts on "zaelar/harvis"; grey/OFF = `always`, listens+answers to everything,
      default) which flips `attention_mode` LIVE via the SAME settings seam the ⚙ uses (POST /api/settings;
      voice/attention.py::mode() reads ZAELAR_ATTENTION per turn → no reconnect) and reflects the real mode on load
      (V2-016 T139/T140). All BLUE when ON/open, grey when OFF/closed; the bowl arc is pure CSS (translateY per
      nth-child — centre dips, edges rise). These are zaelar's OWN things; the PROJECT icons (◉ status · ⌗ docs ·
      ◷ debug · ☾/☀ theme · ⚙ · Reset) stay UP in the TopBar. The caption overlay crawls above the orb
      (teleprompter, last 3 lines), driven by LiveKit's AUDIO-SYNCED transcription (RoomEvent.TranscriptionReceived
      in session-lk.js → store.captionSeg), so the text advances IN SYNC with the spoken voice; LIVE only, the chat
      wall keeps the history.
      INVARIANT (product): NO floating notifications anywhere — a proactive push surfaces by voice + live caption +
      a chat-wall entry (deduped), never a toast. The old Notice toast component was removed for this.
      MemoryMap = the 🧠 "map of zaelar's memory" (V2-014): a full-screen system view (overlay like /debug, NOT a
      widget) of how the central memory (memory/, V2-002/003) is composed IN REAL TIME. Three SIDE-BY-SIDE COLUMNS
      (left→right, each its own block with a coloured top rail + header, nodes flowing vertically inside) —
      ESTADO (narrow, 1 node wide; the fixed state table, near-empty until V2-013 populates it, and seeing that empty
      is the point), CORTO PLAZO (narrow, 2 nodes wide; level 'short'), LARGO PLAZO (the WIDEST column, 4 nodes wide;
      'mid'/'long', the one that grows) — each memory a node/card with tiny ~8px text +
      scoring (importance) + date/time + metadata (kind, weight bar, access_count, pinned), readable by ZOOM (wheel)
      + PAN (drag); the concept GRAPH (edges) drawn as SVG curves between nodes. Data: `GET /api/memory/map`
      (read-only, no-cache) → `{state, layers:{short,long}, edges, counts}` with every per-unit field, served by
      `memory/api.py::map()` (see the Memory module section). REAL-TIME, no polling: the server bridges the bus signal
      `memory.updated` onto the `observer` topic (→ GET /events) as `{kind:"memory"}` (server/__init__.py);
      services/sse.js calls store.bumpMemory(); MemoryMap refetches (debounced) ONLY while open.
    lib/
      draggable.js        makeDraggable (drag + position persistence)
      speaker-gate.js     owner-voice acoustic gate (unchanged)
    widgets/
      desktop.js          widget window-manager (independent; talks only the widgets HTTP contract)
  vad/                    vendored browser-VAD (onnx + wasm + worklet), served at /static/vad/
```

**Migration path to Solid (why it's "natural and fast").** Three layers, three migration costs:
1. **core/reactive.js** — exposes the EXACT Solid signatures (`const [v,setV]=createSignal(0)`, `createEffect`,
   `createMemo`). To migrate: delete the file, re-point imports to `solid-js`. Component/service code is unchanged.
2. **components/** — plain functions that read signals and build DOM with `h()`. The only manual step is converting
   `h(tag, props, …children)` to JSX (1:1 mapping; a reactive child/attr is a function `() => signal()` → `{signal()}`).
3. **services/** — pure logic (WebRTC, audio, VAD, STT, SSE, fast-path). No framework ties → **zero changes**.

`widgets/desktop.js` and `lib/speaker-gate.js` are already isolated modules and stay as-is. The front-end's whole job
is **audio I/O + a thin reactive shell around widgets that the brain (`nucleo/`) drives** — no business state lives in the client.

**Theme (dark by default).** `app/core/store.js` holds a `theme` signal (`"dark"|"light"`, seeded from
`localStorage.hb_theme`, default `"dark"` — a full-white canvas at night was the original complaint). `TopBar.js`
has a ☾/☀ toggle icon; `services/theme.js` applies the choice as `<html data-theme="…">` and persists it. All of
`styles.css` is driven by ONE namespace of CSS custom properties on `:root` (`--hb-bg`, `--hb-ink`, `--hb-muted`,
`--hb-line`, …, plus unprefixed app-shell vars `--canvas`/`--chrome-line`/`--mono`/`--sans`) redefined under
`:root[data-theme="light"]` — no component/JS branches on theme, it's pure CSS cascade, and no separate
app-internal-vs-widget alias layer: the app chrome and every widget read the exact same variables (see §Widgets
below). `styles.css §WIDGET KIT` also has optional `hbk-*` helper classes (`hbk-card`, `hbk-hd`, `hbk-empty`,
`hbk-chip`, `hbk-btn`, …) for the layout patterns that repeat across widgets, to keep new widgets' own CSS small.
(Tailwind was evaluated for this and declined — INI-011 — it would require either a build step, breaking the
"no build/no npm" architecture above, or a CDN/runtime JIT, breaking widgets' "self-contained/no CDN" rule; a
plain CSS variable is also simply less code than a `dark:` utility pair per element.)

**Boot sequence + splash (INIT → BARRIER → greet).** First load is gated by a full-screen splash
(`components/BootOverlay.js` + the `boot-anim.js` render engine) that plays the **«Colmena sináptica»**: a neural
constellation which ASSEMBLES ITSELF IN PARTS — one cluster of nodes lights up per boot phase — then, on `listo`,
IMPLODES into the orb, handing off to the live voice visualiser. Pure `<canvas>`, no deps, themed via `--hb-*`
(dark/light), honours `prefers-reduced-motion`. Phases are a single source of truth in the store
(`store.BOOT_PHASES` = `encendiendo → voz → memoria → reflejo → listo`, signal `bootPhase`) and are advanced by
**REAL milestones**, never timers: the frontend reports `voz` (mic granted in `session-lk.js`); the agent reports
`memoria`/`reflejo` over the "vl2" data channel (`{type:"boot",phase}`); `listo` = init done (`{type:"ready"}`),
with `store.bootReady` lifting the veil. **The ordering barrier is in the backend** (`voice/engine/pipeline/agent.py`):
after `session.start` the agent emits the phase milestones and then `ready` **BEFORE** dispatching the kickoff
greeting — so the voice never runs *under* the splash (it used to: `ready` fired ~5s after the greeting started).
INIT (voice live + central memory composed via `memory_cache.prime` + STT/TTS warm) completes → splash implodes →
THEN zaelar greets. A 60s safety timeout in `session-lk.js` unblocks a stuck boot; later reconnects never re-lock.

## Widgets module (`widgets/`) — the dynamic widget OS

Widgets are zaelar's visual surface: self-contained cards on the canvas that the active brain summons by voice. The
whole point is that there can be **thousands, all dynamic** — created / modified / shown / hidden on demand — and
that **no single widget can ever break the rest of the system**. That isolation is the prime directive; every design
choice below serves it. A dedicated diagram + lifecycle deep-dive lives at `/architecture` → tab **Widgets**.

**Anatomy — one folder per widget** (`widgets/<id>/`, fully independent, add/remove = drop/delete a folder):

| File | Role |
|------|------|
| `manifest.json` | `{id,version,title,description,whenToUse,keywords[],entry}` (+ optional `transient`, `background`, `runtime` — see §Widgets that PRODUCE something). Feeds the catalog + voice→widget matching. |
| `widget.js` | ES module `export function render(el, data, ctx)`. Self-contained, no libs/CDN/network, injects its own `<style>` once, `textContent` for untrusted data. `ctx = {action(name,payload), close(), top(), running}` (`running:false` = the operator STOPPED the agent). Styled with the `--hb-*` CSS variable contract (`--hb-bg`, `--hb-ink`, `--hb-muted`, `--hb-line`, `--hb-accent`/`--hb-accent2`, `--hb-risk`, `--hb-neutral`, `--hb-warn-*`) — never a hardcoded hex — so every widget follows the app's dark/light theme (`frontend/app/styles.css`) with zero JS, live, even while open. Full list + fallback pattern in `widgets/AGENTS.md`. |
| `data.py` | `view_data(q="") -> dict` (server-side, **stdlib only**, never raises) + optional `apply_action(action, payload)`. |
| `notes.md` | **Per-widget context / memory** — the running log of decisions & constraints. The generator agent READS it before editing and APPENDS after, so it never regresses a past choice. This is the "own context folder" for regeneration. |
| `__init__.py` | empty (makes it importable as `widgets.<id>`). |

**Widgets are the FOUNDING rail (§Nucleo → Rails) — THREE distinct conductions, don't confuse them.** Operating a
widget is a different behavior from creating/modifying it or opening/closing it, and all three are separated in code:
**(1) OPERATE its DATA** — the FlashBrain runs a widget's declared action itself, instantly, via the `widget_data`
tool → `apply_action` (FAST/CONFIRM gate, V2-025; item references resolved by `widgets/refs.py`, V2-026). Each widget
declares its FUNCTIONS + conduct INSTRUCTIONS **modularly in its own `manifest.json`** (`actions` + `usage`), and its
memory writeback goes through the sanctioned seams (`ctx.remember`/`ctx.ingest`, `memory.write` with a slot) — never
the DB directly. **(2) CREATE / MODIFY the CODE** — escalate to a worker (the SlowBrain owns widget CODE). **(3)
OPEN / CLOSE / DELETE on the canvas** — text tags `[[show]]`/`[[close]]`/`[[move]]` + `delete_widget` (with confirm,
V2-017). The details:

**Who builds them (two speeds, don't confuse them).** The *decision* to show/create/modify/delete a widget or change
its data only ever emits a silent tag — the brain is **never** the one writing widget code. **The SlowBrain is the
owner of a widget's CODE** (V2-025): creating a new widget, modifying an existing one (its UI/schema/logic), or
handing it data that must first be looked up (`[[push]]`) all require the SlowBrain. But **WORKING WITH a widget's
DATA is NOT the SlowBrain's job** — every action a widget declares (its `apply_action` vocabulary) is a **data-op the
FlashBrain runs itself, instantly**, via `[[widget.data:id]]` (see "Per-action execution mode" below). The
**FlashBrain** (the fast voice layer, `nucleo/flash/`; non-reasoning model per-invocation from `config/v2.py` `fast`
section — Ollama local or AIMLAPI/Grok cloud; full comparison in `.meshkore/docs/ops/zaelar-model-benchmarks.md`)
handles `[[show:id]]`/`[[close:id]]`/`[[close]]`/`[[move]]`, deleting a widget (with confirmation, V2-017), AND all
declared data actions directly — the ONLY things it escalates via `escalate_to_slowbrain` are CREATE/MODIFY-code and
data-to-look-up. This is enforced in **code, not just the prompt** (`voice/engine/llm/providers/nucleo.py`): if the
fast layer emits `create`/`modify`/`push` it's dropped and the turn auto-escalates; a `widget.data` tag is resolved by
the canonical mode (FAST/CONFIRM/ESCALATE, `widgets/actions.py`), never blindly escalated — the same "zaelar decides,
not the model" posture used for cluster safety. The actual widget CODE is always written by a **separate, local, headless
Claude Code CLI** (`claude -p`, spawned by `generator.py`) — file tools only (Write/Edit/Read, no Bash), scoped to
the zaelar dir, one agent at a time, hard timeout. `WIDGET_GEN_MODEL` overrides the coder model. No brain ever
programs a widget; the SlowBrain delegates to a real, sandboxed coding agent.

**Lifecycle & the tag protocol** (parsed in `voice/tag_protocol.py`, stripped from speech):
`[[show:id]]` · `[[close:id]]`/`[[close]]` · `[[create:id]]spec[[/create]]` · `[[modify:id]]change[[/modify]]` ·
`[[delete:id]]` (removes the folder AND its `_data/<id>.json` store — full lifecycle, no orphan state) ·
`[[push:id]]{json}[[/push]]` (brain hands data to a widget) ·
`[[widget.data:id]]{"action":..,"payload":{..}}[[/widget.data]]` (the SlowBrain changes a widget's OWN saved data — e.g.
"add a meeting to my agenda" → `{"action":"add_meeting","payload":{...}}`). The desktop
(`frontend/app/widgets/desktop.js`) is the window-manager; it talks ONLY the widgets HTTP contract (`GET /widgets`,
`/widgets/{id}/{manifest,widget.js,data}`, `POST /widgets/{id}/action`, `POST /widgets/{generate,modify}`,
`DELETE /widgets/{id}`). `GET /widgets/{id}/widget.js` serves with `Cache-Control: no-cache` (`widgets/server_api.py`)
— `desktop.js`'s `import()` has no cache-busting query on first load, so without this an edited widget.js could keep
being served stale from the browser cache indefinitely (W-009).

**The FlashBrain works with widget DATA directly, via a generic bridge (V2-025/V2-026).** The **primary invocation
path is a function-calling tool** `widget_data(widget_id, action, item, payload)` (`nucleo/flash/router.py`), NOT an
inline tag: a small non-reasoning model emits function calls reliably (it calls `web_search` perfectly) but forgets
inline `[[widget.data]]` tags and, when it does emit one, invents item ids — so V2-026 moved data-ops onto the tool
(the tag stays as a fallback). Both converge in the provider's `_apply_widget_data`, which routes to
`widgets.dispatch_tag()` (`widgets/__init__.py`) → `widgets/server_api.py:brain_action()` → the SAME
`apply_action(action, payload)` the widget's own UI buttons call (off-loop, bounded pool; a `backed` widget routes to
its owner's mailbox instead). The brain learns each widget's action vocabulary + how to drive it from its
**manifest.json `actions` field** (`{"name": {"desc":"...", "payload":{...}[, "confirm": true]}}`) plus an optional
top-level `"usage"` guide, surfaced by `widgets/brief.py:_actions_brief()` — an action NOT declared there is invisible
even if `apply_action` accepts it. A widget with mutable data MUST declare it (`widgets/AGENTS.md`, `generator.py`'s
`_CONTRACT`), and the validation gate REJECTS a declared/handled mismatch (see "Per-action execution mode").

**Item references resolved to real ids — the model never invents them (V2-026, `widgets/refs.py`).** The operator
speaks in natural language ("mark the daemon task done", "snooze the Reddit thing"), never ids. The model passes a
natural-language `item`; `refs.resolve(widget_id, action, ref)` matches it (fuzzy, stdlib difflib + token overlap,
accent-insensitive) against the widget's LIVE items and fills the real id. The widget exposes them via an optional
`data.py:ref_index() -> [{"id","label","field"}]`; the id field to fill (`taskId` vs `projectId`) is read from the
action's declared `payload`, so `drop_project` (→`projectId`) targets the *project* Atlas, not the same-named
task. Ambiguous/no-match → the brain ASKS instead of acting on the wrong item. The brief also lists `items ahora:` per
widget so the model knows what exists. Relative dates/times ("mañana", "a las cinco") are normalised in the widget
layer (`agenda.data._resolve_date/_resolve_time`), and `live_state` gives the model today+tomorrow explicitly so it
never web-searches the date. `agenda` is the reference (`add_meeting`/`done`/`drop`/`snooze`/`not_now`/`drop_project`
+ `ref_index`). Widgets with their own connector tag (e.g. `mensajeria`'s `[[msg.*]]`) don't need this bridge.

**Background execution — off-screen work on a declared cycle (V2-034, `widgets/background.py`).** A core
consideration for EVERY widget: does its data change on its own, off-screen, such that the operator might ask
about it by voice without ever opening the card? Most widgets: NO — foreground-only, `view_data()` runs on
demand. Those that do (an inbox, a feed, weather) declare a cycle in `manifest.json`: `"background": {"every":
"1m"}` (also a bare string `"1m"`/`"30s"`/`"1h"` or a number of seconds; **minimum 1s**). Two shapes, one
declarative idea:
- **passive + `background`** — lightweight, no process. A shared scheduler calls `data.py:tick(ctx)` every cycle
  OFF the hot path (`asyncio.to_thread`, since data.py is sync stdlib). `tick` refreshes and `store.save`s only if
  data changed (idempotent → no SSE flood), and writes what the operator might ask about into central memory via
  the sanctioned `ctx` — `ctx.remember(text, slot="<widget>:<key>")` (slot → SUPERSEDE, no pile-up) or
  `ctx.ingest(source, entity, text)`. Crucially, memory access comes through `ctx`, NOT an import, so `data.py`
  stays stdlib-only (the generator gate still enforces that). `meteo-soria` is the reference (`every:1h` →
  `tick` writes "Tiempo en Soria ahora…" to `slot=weather:soria`; a voice "¿qué tiempo hace en Soria?" then
  answers fresh even if the card was never opened).
- **backed** — heavy, a live owner process that self-schedules (the navegador's Chromium, mensajeria's
  connectors). A backed widget IS background by nature; if it declares `background` the scheduler enqueues a
  `tick` command to its owner's mailbox each cycle (else it's left alone — `mensajeria` self-polls and does not
  declare it). `mensajeria` is the reference for the whole point: off-screen → triage → memory → voice.

Invariants: runs in the server lifespan (same loop as voice + the backed supervisor); a `tick` that raises or
hangs is isolated (caught, traced under `observer` kind `background`, per-widget overlap skipped) — it can never
take down voice or another widget. The generator gate (`_validate_background`) REJECTS a passive widget that
declares `background` without a `tick()`, or an unparseable `every`.

**Data refresh — SSE push, NEVER polling.**
`widgets/store.py:save()` is the single choke point EVERY mutation path flows through (a widget's own `ctx.action`,
the brain via `[[widget.data]]`, a connector writing directly via its own store wrapper, first-run seeding) — it emits
one `observer.emit("widget", "data", {"id":...})` per write. `sse.js` routes that to `desktop.refreshData(id)`,
which re-fetches `GET /widgets/{id}/data` **once** and re-renders **only if** the widget is currently open AND the
JSON signature actually changed. No `setInterval` anywhere, on either side: `widget.js` is barred from
`fetch`/`XMLHttpRequest`/`WebSocket`/`EventSource` (the static gate), so a widget can never poll itself. A widget
that isn't open simply gets no event (nothing to refresh); reopening it always loads current data via its normal
`show()` path.

**Editing data — two paths, both funnel through the same `apply_action`.** (1) The widget's own UI: `ctx.action(name,
payload)` → `POST /widgets/{id}/action` → `data.py:apply_action()`, wired to buttons the widget's own `widget.js`
renders (e.g. `mensajeria`'s `read`/`dismiss`/`clear`/`connect`/`disconnect`). (2) Voice, via the FlashBrain:
`[[widget.data:id]]` → the exact same `apply_action()`, in-process, no HTTP round-trip (the data-op runs on the fast
layer, per its mode). Neither path is a generic "edit this widget's data" UI — a widget's mutable surface is only ever
what its own `apply_action` (and declared `actions`) expose. Structural changes to the CODE (new fields, layout,
logic) go exclusively through voice → `escalate_to_slowbrain` → the coding agent, never a data-op.

**Per-action execution mode — data-op ALWAYS, irreversibility SEPARATE (V2-025).** The old `"safe": true|false` flag
was overloaded: it conflated "can the fast layer run this?" with "is this irreversible?". So `add_meeting` sat at
`"safe":false` and **auto-escalated to a code agent** that had nothing to build (just the same `apply_action`) — a
trivial data mutation that took minutes and once hung >6 min. Wrong: a data mutation is never code work. The fix —
one canonical resolver, `widgets/actions.py::classify(spec, name)`, read identically by the gate
(`nucleo/flash/frontend.py::action_mode`), the provider's forced boundary, and the brief — gives each declared action
ONE of three modes:
- **FAST** (default for every declared action): the FlashBrain emits `[[widget.data]]` and it runs immediately, no
  round-trip. Declaring an action *is* granting the fast layer permission to run it.
- **CONFIRM** (irreversible): the FlashBrain still runs it — it is NOT escalated to code — but only after the operator
  says yes (reuses `widgets/confirm.py`, the same Sí/No overlay + deterministic yes/no net as delete; sibling of
  `nucleo/danger.py`). Marked `"confirm": true` (alias `"irreversible": true`) or inferred by a NARROW heuristic
  (pay/send/publish/delete-all) over the action name+desc.
- **ESCALATE** (`"escalate": true`, explicit escape hatch, rare): forced to the SlowBrain. NOT for data mutations.

Back-compat: `"safe":true`→FAST, `"safe":false`→FAST (or CONFIRM if the heuristic trips) — it no longer escalates;
`"safe"` is deprecated, new widgets use `"confirm"`. Only CREATE/MODIFY the widget's CODE goes to the SlowBrain. The
boundary is a JSON declaration the operator/generator controls, not something the model self-asserts — same posture as
cluster safety. **Validation keeps it honest** (`widgets/generator.py::_validate_actions_sync`): for a passive widget,
every declared action must have a matching `apply_action` branch and every handled branch must be declared — a
mismatch (dead entry / invisible action) is REJECTED at the gate, and the `_CONTRACT` tells the coding agent to
regenerate the `actions` + `usage` in sync on every create/modify. `backed` widgets (`navegador`, `mensajeria`) skip
this data.py check — their actions run through the owner's mailbox, which the supervisor owns.

**Voice→widget identification (`runtime.identify()`)** — runs on every transcript, so it must stay local and
sub-millisecond. Today it is **lexical-semantic, stdlib-only**: accent-insensitive normalization, word-aligned
keyword-phrase hits (classic weights), fuzzy per-token match (`difflib`, catches STT typos like *tarrgona*),
id/title dominance, and a capped description/whenToUse token-overlap signal that can tiebreak but never summon a
widget by prose alone. The index is cached against the catalog signature (mtime), so per-call work is just the
query — viable for catalogs of thousands. **Planned next step (when the catalog outgrows lexical recall): a true
semantic tier** — local embeddings (e.g. a small ONNX sentence encoder) computed per manifest at catalog-index
time and per query at ask time, cosine-ranked, with the manifest catalog remaining the single source of truth and
the lexical scorer kept as the exact-match fast path and fallback. Same API shape (`match/ambiguous/candidates`).

**Generation is async + closes the loop.** Building a widget takes ~1–2 min; the `[[create]]` is fire-and-forget, so
the brain must NOT claim "done". On completion the generate/modify endpoint pushes a one-shot `[SISTEMA]` note back
to the brain's next turn (`voice/brain_notes.py` → drained in the brain adapter): success (with the exact id) or
failure (+ a spoken/UI alert). The brain then stops mis-claiming and never references a widget id that didn't build.

**Storage — INDEPENDENT per widget, CODE and DATA in separate directories (revised 2026-07-07).** `widgets/store.py`
gives each widget its own **directory** at `widgets/_data/<id>/` — `state.json` inside it is the primary JSON
(`store.load(id, default)` / `store.save(id, db)`, identical contract to before), and `store.data_dir(id)` hands out
the directory itself for anything beyond a flat file (media, attachments, a criteria doc). CODE (`widgets/<id>/`) and
DATA (`widgets/_data/<id>/`) are deliberately two different directories, not one: `[[modify]]`/`[[delete]]`/
regeneration rewrite the CODE folder, so data living there would be destroyed by the widget's own next edit. (Older
widgets that still have the flat `widgets/_data/<id>.json` file migrate automatically, lazily, the first time
`store.load`/`save` touches them — same philosophy as the schema `_v` migration, no script, no data loss.) One data
directory per widget so a bad widget can only corrupt *its own* state — never another's, never the system's.
System-produced data the widget only observes (e.g. `.meshkore/logs/` for the cluster registry) is read with stdlib,
never copied in. A single brain-wide shared store was rejected: it couples widgets and breaks the isolation invariant.

**Communication is brain-mediated (chosen model).** Widgets are dumb and isolated: they never talk to each other,
hold no long-lived connections, run no background threads. Orchestration is 100% the active brain (the FlashBrain,
or the SlowBrain on escalation) — it reads one widget's data and pushes to another via the tag protocol. (No client-
side cross-widget calls; cross-module events go through the `bus/`.)

**Fault isolation, enforced at every layer** (why one widget can't sink the ship):
- Catalog (`runtime.py`) parses each manifest in its own try/except → a broken manifest is skipped, not fatal.
- A missing/broken `data.py` → the endpoint returns 404, the server keeps running.
- `render()`/mount errors are caught in `desktop.js` → that one card closes, the canvas and other widgets live on.
- **Validation gate** (`generator._validate`): before a widget joins the catalog it must have a valid manifest, a
  `widget.js` with `export function render`, a `data.py` that compiles **and whose `view_data(q="")` actually runs and
  returns a dict** (runtime smoke-test). A `modify` that fails validation is rolled back to the last working version.
- **CSS class-collision check** (`generator._scan_widget_js`, 2026-07-07): rejects a widget whose injected `<style>`
  uses a class name ALSO defined as a BARE (unscoped) rule in the app-wide `frontend/app/styles.css` — CSS applies
  both rules to any element with that class regardless of the widget's own wrapper scoping, so the global rule's
  properties (position/display/etc.) silently leak onto the widget's element. This shipped live once:
  `mensajeria`'s `.conn` (its connection-setup card) collided with the app's bare `.conn{position:fixed;left:20px;
  bottom:14px;...}` (the mic/SSE status line) and got yanked out of the widget card to a fixed screen corner,
  reading as a second, detached window. `mensajeria` (`.conn`→`.linkcard`, `.me`→`.mine`) and `meteo-soria`
  (`.ic`→`.wicon`, which had been silently inheriting an unwanted bordered icon-button box) were fixed the same day.
  `hbk-*`/`hb-*` prefixed classes are exempt (the intentionally-shared kit and widget-chrome contract).

### Widgets that PRODUCE something — the `runtime` contract (V2-092, `widgets/producers.py`)

A widget that keeps doing something after the operator stops looking — playing audio/video, recording, running a
live process — is not just a view, and the system needs to be able to **stop it**. That came from a real failure
(operator, 2026-08-13): with the agent STOPPED via ⏻, a YouTube video kept playing, **restarted itself on page
reload**, and played on top of the music player at the same time.

The fix is not a special case per widget — widgets are GENERATED, so next month's podcast card would break the same
way and nobody would remember to add its `if`. It is a DECLARATION in the manifest, read by `widgets/producers.py`:

```json
"runtime": {
  "output": "audio",                                   // exclusive channel it takes (omit = competes for none)
  "produce": ["load", "play", "restart", "unmute"],     // actions that START it producing
  "suspend": "pause",                                  // the action that makes it STOP
  "active_when": {"videoId": true, "paused": false}     // how "is producing" reads from view_data()
}
```

Three capabilities then work for **any** widget, present or future:

- **Global stop** — `suspend_all()` silences everything that is producing, knowing nobody by name. Driven by
  `nucleo/runstate.py` (the server-side ⏻; see `CLAUDE.md` §Decisiones and initiative `V2-092-parar-es-parar.md`).
- **Channel exclusivity** — taking `output` suspends whoever else held it. The speaker is ONE.
- **Gate** — while the agent is stopped, `produce` actions are refused (`agent_stopped`). Everything else (navigate
  the card, change view, lower the volume) still works: stopping the agent is not freezing the UI.

Details that matter: `active_when` is evaluated against `view_data()` (the widget's own truth, not a copy), accepts
dotted paths (`yt.paused`) and a LIST of conditions (AND inside one, OR between them) for a widget that can produce
more than one way — `musica` plays through Spotify (remote device) or YouTube-audio (hidden iframe), two different
states. `suspend` and every `produce` entry must be REAL declared actions; a typo there would be a stop that stops
nothing, silently, so `tests/browser/unit/widgets/test_producers.py` (testmap **4.16**) asserts it against the real
manifests.

Everything funnels through `widgets/server_api._dispatch` (same path for the UI and the brain): gate → action →
exclusivity. Suspending itself goes through `dispatch_raw`, bypassing the gate — otherwise stopping while already
stopped would refuse itself.

On the client, `widget.js` gets `ctx.running` (a live getter from the canvas): `false` means the agent is stopped, so
never autoplay on mount — and for an `<iframe>` keep `autoplay=0` **out of the `src` itself**, because a pause sent
afterwards arrives late and the first instant is audible.

### Widget-apps ("backed" widgets) — INI-016, users `navegador` + `mensajeria`

Everything above describes a **passive** widget: one writer (the widget's own `ctx.action`, or the brain), no
background process, view_data computes/reads on demand. That model does not fit a widget that is really a small
**app** with a live backend — one that holds external connections and writes its own data from OUTSIDE any
request/response cycle. So there is a second, formal widget *kind* — **not a rewrite of the passive model, an
addition next to it**. Its two users today are the `navegador` widget (§Navegador below) and the `mensajeria`
widget (last bullets).

- **`"kind": "passive" | "backed"`** in `manifest.json` (default `passive` — zero change for the 9 passive widgets
  that exist today). A `backed` widget additionally declares `"backend": {"owner": "owner.py"}` — a module in its own
  folder exposing `async def start()` / `async def stop()` / `async def handle(action, payload)`, the same "drop a
  file with the right name and the host discovers it" convention `data.py`'s `view_data`/`apply_action` already use.
- **The supervisor (`widgets/supervisor.py`), started in the server lifespan** (`server/__init__.py`, SAME event
  loop as voice). On boot it scans `runtime.catalog()` for `kind=="backed"`, imports each folder's `owner.py`, and
  runs it under a supervised task: a **mailbox** (`asyncio.Queue`, cap `WIDGETS_BACKED_QUEUE`=128) drained in order,
  **restart with exponential backoff** on crash, and **auto-disable after N consecutive failures**
  (`WIDGETS_BACKED_MAX_FAILS`=4) — degrading to the last-known frozen state rather than hammering the server. Every
  lifecycle transition is traced via `voice/observer.py` with `kind:"backed"` (labels `start`/`crash`/`disabled`/
  `cmd_error`/`dropped`/`import_error`). A crashing owner can never take down the voice pipeline or another widget.
  Every backed widget is discovered this way — "add a widget = drop a folder, no server changes" — with no bespoke
  wiring in `server/__init__.py`.
- **ONE writer per data directory, by construction.** A `backed` widget's owner is the SOLE writer of its
  `widgets/_data/<id>/` — so an `apply_action` and a background task can never race on the same file. The face
  (`data.py` + `widget.js`) is READ + **ENQUEUE**: for a backed widget `apply_action` is NOT applied inline —
  `widgets/server_api.py`'s `_route_backed()` (used by BOTH `POST /widgets/{id}/action` AND the brain's
  `[[widget.data]]` via `brain_action()`) drops the command into the owner's mailbox instead, and the owner drains
  it in order on its own schedule. Same external contract (UI clicks, the brain's `[[widget.data]]`, and the
  FlashBrain's "safe" actions all call it exactly as today); the mutation just happens a moment later, inside the owner, instead of
  inline in the request. `data.py.apply_action` stays only as a safety net for when the owner isn't alive.
  Eliminates the two-writer race by construction, not by locking harder.
- **Binary assets served generically** — new endpoint `GET /widgets/{wid}/asset/{name}` (`widgets/server_api.py`)
  serves a binary file (e.g. the navegador's viewport screenshot) from that widget's own `store.data_dir(wid)`,
  path-safe and `Cache-Control: no-cache` (the widget cache-busts with `?v=<rev>`). Any backed widget with rendered
  media reuses it; nothing widget-specific in the server.
- **The isolation directive is reformulated for `backed`, not dropped.** Passive's "no backend, no live connections,
  no threads" becomes: own EXCLUSIVELY your `data_dir()` (same as passive), expose a command mailbox instead of
  writing inline, and be supervised (crash-isolated, restart-with-backoff, resource-capped) — this ENABLES scale
  (live connections, subprocesses, heavy jobs) instead of forbidding it, while keeping the same guarantee: one
  widget's failure never reaches another widget or the voice pipeline.
- **Refresh generalizes for free.** The SSE-push model (`widgets/store.py:save()` as the single choke
  point, no polling — see above) fires regardless of WHO calls `save()`. A `backed` widget's owner writing on its
  own schedule (a message arrived, a fresh screenshot rendered) already pushes a refresh to any open card — no new
  mechanism, just keep routing every write through `widgets/store.py`, never a bypass.
- **`mensajeria` as a backed widget** — `mensajeria` is `kind:"backed"` with `"backend":{"owner":"owner.py",
  "gate":"nucleo"}`. The connectors (`connectors/whatsapp`, `connectors/telegram`) are STATELESS: they only PUBLISH
  `connector.msg` / `connector.status` to the bus and drain `msg.mark_read` (`connectors/messaging/ingest.py`).
  Triage + store live INSIDE the widget owner: `widgets/mensajeria/owner.py` subscribes to the bus, triages with an
  internal `triage_agent` (a **LOCAL** model — `qwen2.5:3b` via Ollama — enforcing the privacy invariant that nothing
  personal leaves the machine; the classifier impl lives in `connectors/messaging/triage.py`), dumps message content
  to `memory/` (kind `msg`), surfaces the relevant via `voice/proactive` + `[SISTEMA]`, and on a read/clear action
  publishes `msg.mark_read` so the right connector marks it read in its app. The supervisor `"gate"` is a GENERAL
  mechanism: any backed widget can require a brain mode.
- **Multi-platform sub-flows stay INSIDE the widget's own card, never a separate window** (operator requirement,
  2026-07-07). `mensajeria` already does this correctly (`qrCard`/`connectCard`/`credsCard` all append into the
  SAME root as the message list — confirmed by the `.conn` collision bug above, which only LOOKED like a second
  detached panel; the DOM was always one card). The rule for every future multi-platform/multi-channel widget:
  whatever sub-view is needed (connect a new account, show a setup form, confirm an action) renders inside that
  ONE card — even filling it entirely — never a second `.hb-win`, never a fixed/floating bar elsewhere on screen.
  Voice must be able to both enter AND leave a sub-view ("conéctame WhatsApp" → shows the QR inside the card;
  "quítame eso" / "vale, déjalo" → drops back to the message list) — this is just `apply_action`/`view_data`
  reflecting a UI-only state, not a data mutation, so it doesn't need the SlowBrain or even `[[widget.data]]`.
- **One messaging widget, period — new channels join it, they never get their own widget.** Standing rule (already
  true for `mensajeria` unifying WhatsApp+Telegram): when email, X/Twitter, or anything else is added, it goes
  INTO `mensajeria` (more platforms in `PLAT`/`ORDER`, more badge colors), never a parallel `email` or `twitter`
  widget. The operator should never have to check N separate inboxes-as-widgets to see what needs attention.
- **Per-widget voice vocabulary should be scoped to widgets CURRENTLY OPEN, not the whole catalog — not designed
  yet** (operator requirement). Today `widgets/brief.py:_actions_brief()` lists EVERY widget's declared
  actions on EVERY turn, unconditionally — fine at 9 widgets, won't scale to hundreds. The idea: the FlashBrain
  prompt should only carry the action vocabulary (and any per-widget voice synonyms — "el widget de WhatsApp" / "el
  de Telegram" both meaning `mensajeria`, on top of what `runtime.identify()`'s keyword matching already gives for
  free) for widgets that are ACTUALLY OPEN on the canvas right now — a closed widget shouldn't cost the fast brain
  any context budget. This needs `desktop.js`'s open-widget list to reach the prompt-building step (`nucleo/flash/`
  calls `widgets.brief.for_brain()` server-side, with no visibility into what's rendered client-side) —
  likely via the SAME live-state channel that already reports cluster/cron status, or a small
  `desktop.capabilities()`-style report pushed to the server per
  turn. Not designed in detail yet; revisit when the catalog grows enough that the current unconditional brief
  becomes a real prompt-size problem, or when it's needed to disambiguate action names that collide across widgets.

### Navegador (`widgets/navegador/`) — a real web browser + web-task agent inside zaelar (first `backed` widget, INI-016)

A REAL browser inside zaelar that the voice layer orchestrates: it opens sites, and it runs **autonomous web
TASKS** ("in Wallapop, find me an enduro bike under 5000€ and give me the best ones") — each task studies the page,
extracts the real listings, ranks them, and returns the top picks. Files: `owner.py` (the live Chromium backend +
`TaskBrowser`), `agent.py` (the automation loop), `tasks.py` (the task registry), `data.py`+`widget.js` (the card),
`manifest.json` (kind `backed`).

**Why a real browser, not an iframe.** Almost no site allows being iframed (`X-Frame-Options` / CSP
`frame-ancestors`) — and even if it did, same-origin policy would stop us scripting it. So the real browser is a
**Chromium (Playwright)** in `owner.py`; the widget shows a **screenshot** of the viewport (1280×800, served via
`GET /widgets/navegador/asset/<name>`, cache-busted by `shot_rev`). This is computer-use: the backend drives the
page programmatically and voice/automation plug in on top.

**HEADLESS by default (2026-07-08).** The Chromium runs **headless — behind the scenes, no window** — so it never
steals the operator's OS focus/cursor (with a visible window the operator couldn't type on their own machine while
the bot worked). The captures are enough. Visible mode is opt-in (store `navegador_visible=true`, env
`ZAELAR_NAVEGADOR_VISIBLE=1`, or the runtime `_visible_override` used by login — see Authentication). There is NO
`bring_to_front()` anywhere (it stole focus; Playwright screenshots background tabs fine).

**One window, PERSISTENT ISOLATED profile.** `owner._ensure_page()` uses `launch_persistent_context(_profile_dir(),
headless=…)`. The profile lives in `widgets/_data/navegador/profile/` (gitignored) → **cookies/logins persist to
disk**, no re-auth each run. It is a SEPARATE profile from the operator's own Chrome and from any automation on
ports 9222/9200: own instance, internal pipe. A debug port is optional and configurable (store
`navegador_remote_port` / env `NAVEGADOR_REMOTE_PORT`), **never 9222/9200** (ignored if set). Chromium launches
lazily on the first command.

> **Not the browser: a factual lookup.** A one-shot factual question ("who won the match?", the weather, a price)
> is NOT a browser task and must NOT open the navegador — that was the original bug (it fell through to
> `automate_web` and hung on "Pensando…"). Those go to the FlashBrain's lightweight `web_search(query)` tool
> (`nucleo/websearch.py`, §Nucleo / §5b of the architecture doc): layered providers (AI-answer Perplexity/Tavily →
> Brave → free DuckDuckGo), off-loop, answered in the same turn, no card. The navegador is for TASKS on a site
> (navigate/fill/buy/compare listings) — there's no search endpoint that returns that datum.

**Two ways to drive it (both from the fast voice layer, as real function/tool calls — not tags):**
- `browse_web(action, target)` — MANUAL browsing (`open`/`search`/`youtube`/`close`). Reuses ONE singleton card
  (fixed task id `"browse"`) so casual browsing never proliferates widgets.
- `automate_web(goal)` — a TASK. Each goal creates its own task + its own vertical card. This is the agent.

**One task = one card = one browsing lane (hard, in code).** The card model is `navegador::<taskid>` (canvas
instance ids, `desktop.js`). Internal tabs a task opens to read listings are ABSORBED/reaped (`_reap_popups`),
never new cards. Anti-proliferation is enforced in code, not just prompt: (a) one browser action per turn;
(b) `automate_web` never also calls `browse_web`; (c) `tasks.similar_active()` DEDUPES — the operator refining the
same request across several STT turns ("busca motos"… "de menos de 5000") reuses the same card (word-overlap ≥0.4);
distinct tasks (moto vs piso) stay separate. Task cards are ephemeral (not persisted to localStorage).

**The automation loop (`agent.py`) — hybrid DOM+vision, model-tiered.** A goal-driven loop drives the task's tab:
each step reads a TEXT snapshot of the interactive elements (accessibility tree → cheap) and picks the next action
by function-calling; **human behaviour** (Bézier mouse + typing jitter) lives in Playwright (free). Escalation
ladder when stuck (page unchanged or same action repeated): DOM → **vision** (attaches a screenshot, acts by
pixel coordinates; multimodal, verified on AIMLAPI) → **advanced model** (2nd stuck, if configured). Cerebro = a
dedicated cheap model (`NAVEGADOR_AGENT_MODEL`, default `anthropic/claude-haiku-4.5`), NOT the SlowBrain; optional strong
tier `NAVEGADOR_AGENT_MODEL_STRONG` for bottlenecks the cheap one can't pass. Starts on the current page (rule: don't
leave the site for an external search engine); anti-wander (stay on the results grid, don't dive into one listing).
Orchestration: `automate_web` → the nucleo orchestrator creates the task, opens its card, **the SlowBrain plans** the
goal (best-effort), then the loop executes off the voice path. FlashBrain orchestrates · SlowBrain plans · loop executes.

**Results (extraction + ranking).** When a task ends on a results grid, `TaskBrowser.extract_listings()` scrapes the
real listings via a page-side JS heuristic (requires a price, excludes ads/tracking, dedups by `/item/` path — no
logos/ads/noise), then `agent.summarize_results()` (the cheap model) picks the best + writes a conclusion. Stored in
`task.results` → the card renders photo+price+link+conclusion. Success is by RESULT (if ranked items exist the task
completed, even if the loop closed with an empty `done`).

**The card UX (`widget.js`, vertical, resizable, ~560px).** Top: mini-browser screenshot (capped ~300px). Then a
**PHASE line with a spinner** — the PROCESS, not clicks ("buscando…" → "recopilando anuncios" → "investigando los
mejores" → ✓ "listo"; `tasks.set_phase`). Then a **feed of MILESTONES** ("14 anuncios encontrados", "3 mejores
seleccionados") — raw clicks/navigations go only to `/debug`, never the feed (`tasks.milestone` vs the observer).
Then **results** (photos 84px + price + link + conclusion). The card grows downward with content (up to ~82vh, then
scrolls). Closing the card closes its tab (`cancel_task`).

**Governance & safety.** `automate`/`click`/`type` are `"safe": false` (the DECISION to automate escalates to the
SlowBrain; the mechanical loop runs cheap off-path). **Confirm-gate**: before clicking an IRREVERSIBLE control
(`_DANGER_RE`: comprar/pagar/publicar/borrar…) the task PAUSES, asks the operator (feed + voice) and WAITS for OK
(timeout → doesn't act). **Q&A by voice**: a task can ask (`tasks.ask` → status `needs_input`); the fast prompt
surfaces the waiting task; the operator's reply is routed via the `answer_web_task` tool → `tasks.answer`.

**AUTHENTICATION — logging into the operator's own accounts (INI-016; approach = open a REAL browser, 2026-07-10).**
To use the operator's account (Wallapop, Google, LinkedIn…) we do **NOT** inherit cookies from the operator's system
Chrome (Chrome encrypts cookies with the macOS Keychain and locks its profile while running — fragile, invasive).
Instead we log in ONCE in OUR persistent profile (`widgets/_data/navegador/profile/`) and reuse it. Flow:
- **Never invents credentials.** A DETERMINISTIC login-wall detector (`agent._looks_like_login`: known login URL or a
  password field) fires BEFORE the model can type — fixes the 2026-07-10 bug where the loop typed `user@gmail.com`
  into Google's login and spun. The loop also has a `need_login` action for walls the URL doesn't reveal.
- **Real window + versatile login reach** (`owner.py::_authenticate` → `_reach_login`): relaunches Chromium
  **VISIBLE** straight at the site's login — a known login URL (`_LOGIN_URLS`), or else it opens the domain and
  **clicks the "sign in" link** by text (multilingual), **avoiding the register link**. A real Chrome window appears
  on the operator's Mac; the card shows `awaiting_login=True`.
- **Auto-detection, ZERO manual steps** (`_login_watch`): watches the window (~2.5s) and detects on its own when the
  operator is in (left the login/register page + new cookies appeared) → closes itself, relaunches **headless**, and
  resumes the task. The **"Ya he iniciado sesión"** button and the `login_done` voice tool remain as a silent safety
  net (not requested). Timeout 10min → gentle reminder, never kills the task.
- **"Already authenticated" guard** (`_already_authenticated`): before opening anything, it checks headless whether a
  session already exists (not a login page + no visible "sign in" button) → does NOT reopen the login; resumes the
  task directly. Fixes reopening Wallapop's login while already logged in.
- **Fallback**: `_authenticate_window` (action `auth_window`) is the same real-window flow. An interactive in-canvas
  login (headless + forwarded input, for cloud) was prototyped but **dropped** — it only covered plain logins and
  failed on Google/CAPTCHA/passkeys; it lives in the git reflog, not the tree.
- **Memory** (`auth_memory.py`, via the facade): the secret (cookies) NEVER enters memory (lives in the profile);
  only the FACT of the session (`record_session_established`, slot per site → supersede) and a recoverable checkpoint
  (`set_state({auth_pendiente})`). See `zaelar-memory.md §Acciones↔memoria`.
- **FlashBrain tools** (`nucleo/flash/router.py`): `authenticate_web(site)` (ONLY explicit login — "conéctame a X";
  web searches/tasks escalate to automate) and `login_done`. Operator-only by construction.
- **Verified**: a PERSISTENT cookie (with expiry) + localStorage survive the headed→headless relaunch (same
  profile) — which is what real logins use. **Caveat**: pure SESSION cookies (no expiry) are not persisted across a
  browser close by web design.

**YouTube exception**: a static screenshot can't play video, so the owner resolves the `videoId` (HTML scrape, no
API key) and navigates the tab to the watch page. **Search engine = Bing** by default (`NAVEGADOR_SEARCH`): Google
CAPTCHAs headless Chromium, DuckDuckGo 418s; Bing renders fine.

**Observability.** `kind:"navegador"` events to `/debug` (`navigate`/`screenshot`/`vision_click`/`task_start`/
`task_step`/`task_stuck`/`task_upgrade`/`task_done`/`launched`/`dismiss_overlay`/`tab_open`…). Cookie/consent banners
are auto-accepted (`_dismiss_overlays`: waits for the CMP button — consentmanager/OneTrust/Didomi — clicks it, waits
for it to close).

**Config knobs:** `NAVEGADOR_AGENT_{MODEL,MODEL_STRONG,BASE_URL,API_KEY,MAX_STEPS}` (loop brain), `NAVEGADOR_SEARCH`
(engine), `NAVEGADOR_REMOTE_PORT` / store `navegador_remote_port` (debug port), store `navegador_visible` / env
`ZAELAR_NAVEGADOR_VISIBLE` / `ZAELAR_NAVEGADOR_HEADLESS` (headless vs visible). **Dependency:** `playwright>=1.61` +
`python -m playwright install chromium` (~150 MB); without it the owner disables itself (supervised), taking nothing
else down.

**Pending (planned, INI-016):** cheap/local per-listing STUDY engine (open each listing → parse with a local model,
one paid call for the final judgment) with a Chromium context per task; UI toggle for headless/visible.

**Reserved ids** (never a widget): `generator`, `server_api`, `runtime`, `store`, `brief`, `supervisor`, `_data`,
`__pycache__`.

**House style & the build contract for the coding agent** live in `widgets/AGENTS.md` (palette, layout, keywords,
persistence, isolation, comms) — the generator prompt points every headless agent at it.

## Files — folded into memory's episodic layer (§Memory)

`files/` is **no longer a standalone module**: the central memory absorbed it as an **episodic layer**. There is no
flat `files/uploads/` tray anymore — an upload's bytes live in the memory data-dir (`memory/_data/episodic/`, next
to `zaelar.db`). `files/server_api.py` and `files/store.py` remain only as thin **compatibility shims** delegating
to `memory/api.py`. Design: `.meshkore/docs/architecture/zaelar-memory.md`.

**The two frontend gestures (unchanged).** Both are wired at the top level (`window`) in `frontend/app/main.js`, so
they work from anywhere in the app — no panel to open, no drop-zone:
- **Paste an image** (Ctrl/Cmd+V, anywhere): the global `paste` listener inspects `clipboardData.items` first — a
  `kind==="file"` with `type` starting `image/` is uploaded (`source=paste`) and `preventDefault()`d, before (and
  without blocking) the text-paste branch that feeds the chat.
- **Drag & drop a file** (anywhere, any type): global `dragover` (`preventDefault` so the browser doesn't navigate
  away) + `drop` (uploads every `File` in `e.dataTransfer.files`, `source=drop`).

Both funnel into `uploadFile(file, source)` (`main.js`): a `FormData` POST to `/api/files/upload`, and on success a
dim, italic, centered `sys` line in the chat log (`store.pushChat({role:"sys",…})`, styled in `styles.css`
`.cw-msg.sys` via the `--hb-*` theme variables). No preview/thumbnail UI by design — the confirmation line is the
only visible feedback.

**The endpoint → the episodic layer.** `POST /api/files/upload` now lives in **`memory/server_api.py`**
(`multipart/form-data`, fields `file` + `source`, 50 MB cap, no auth — local-only app). Each upload calls
**`memory.write_episode(data, filename, mime)`** (`memory/episodic.py`), which stores the binary AND generates a
**searchable summary** embedded into the memory index (participates in `memory.query` via vec + FTS; the binary
loads **lazy**). `GET /api/files` lists episodic files. Anything left in the old `files/uploads/` from before is
imported at boot by `memory.migrate_inbox()` (lazy, idempotent, **non-destructive** — it never deletes the source).

**How the brain finds a file — via memory recall, NOT multimodal inline.** The uploaded file's summary is already in
`memory/`, so the brain's retriever surfaces it on the hot path when relevant — no absolute-path note, no protocol
change. Threading the file inline into the turn as multimodal content is deliberately NOT done: the operator's real
asks ("resume este PDF", "mira esta captura y dime qué ves") are satisfied by a follow-up turn where the SlowBrain
reads the file with its own tools, with zero extra surface in the LLM plumbing.

**Widgets write durable data to memory (V2-003).** Beyond its UI `store.save()` (canvas SSE, unchanged), a widget
that produces durable data also dumps it to the central memory for brain recall. First case: `mensajeria` writes
each new incoming message to `memory/` (kind `msg`) — fire-and-forget via the queue, best-effort, a failure never
touches the UI store or the triage. The per-widget store stays for UI state; memory is for recall.

## MeshKore connector (`connectors/meshkore/`) — a third I/O channel next to voice & chat

> Full end-to-end algorithm (connection lifecycle, exact guard order, permission-gated dev-worker + its
> filesystem jail): `zaelar-cluster-channel.md`. Threat model: `zaelar-security.md`.

zaelar's native link to **MeshKore clusters**, so zaelar can talk to OTHER agents and run tasks collaboratively.
It is **pure I/O + a brain-agnostic bridge** — it does NOT think. Design principle: the connector never imports a
brain; server wiring injects one. **One mind (V2-069):** the SAME FlashBrain engine conducts a cluster turn, in the
**UNTRUSTED profile** — `connectors/meshkore/brain.py` adapts the channel to the engine (resolves the off-voice model
tier) and delegates to `nucleo/flash/cluster.py` (**tools OFF in code** + identity-safe system that never exposes
operator PII). A peer can make zaelar reason + talk, never act **by default**. Conversation state lives in the
per-peer **capsule** (`capsule.py`). **V2-076** built the permission-gated version of what V2-010 scoped: an
operator-granted per-cluster profile (`perms.py`+`store.py`) can open `escalate_to_slowbrain` to a scoped
dev-worker (disposable cwd, `Bash` only to `nucleo/git_cli.py`, repo-authorized), additionally gated on an
operator-set objective per relationship (`perms.gate_dev_by_objective`, set via the operator-only tool
`set_cluster_objective`) — see `zaelar-security.md` for the full threat model; the dev-worker's filesystem jail
is code-enforced (`nucleo/dev_worker_guard.py`, a real Claude Code PreToolUse hook), closed 2026-07-26.

Files:
- `client.py` — `MeshKoreClient`: one persistent WS to one cluster. Protocol: connect to
  `wss://api.meshkore.com/v1/clusters/{id}/ws?token=&agent=&did=`; inbound frames `ready|presence|message|ack|error`;
  send `{to, payload}` (omit `to` = broadcast; ≤ 64 KB). WS ping keepalive + reconnect with backoff.
- `manager.py` — `MeshKoreManager`: registry of 1..N clusters; funnels every inbound frame into one async sink.
- `bridge.py` — `ClusterBridge`: turns each inbound frame into a **labelled** brain input (`[cluster:acme · message
  from agent 'bravo'] …`), **prepends the per-peer capsule** (who they are, the running summary, the objective, open
  loops, and the PHASE — so it never re-introduces itself), runs it through the injected brain, parses `[[cluster.*]]`
  tags out of the reply and routes them back to the cluster, and runs the **heartbeat**. Also the **stall guard**
  (V2-069): when a peer keeps repeating, it sends one assertive, on-goal message, then goes silent and alerts the
  operator once. Tracks a minimal per-cluster `engaged` flag.
- `capsule.py` — the per-`(cluster,peer)` **conversation capsule**: relationship memory on the central store
  (`sys_kv`, `trust=untrusted`, quarantined) — dossier + summary + objective + open loops + phase + stall counters.
- `brain.py` — adapts the channel to the FlashBrain engine (untrusted profile): resolves the model tier and delegates
  to `nucleo/flash/cluster.py`.
- `store.py` — cluster creds persisted to `config/meshkore.json` (gitignored, chmod 600) + ephemeral paste-staging
  + token redaction for logs.
- `server_api.py` — `/api/meshkore/*` (status, stage, connect, send, disconnect). NATIVE = always mounted.
- `brief.py` — teaches the brain the outbound tag protocol + live cluster status (injected into the voice kickoff
  brief and prepended to each off-pipeline cluster turn).

Outbound tag protocol (parsed in `voice/tag_protocol.py`, stripped from speech like widget tags):
`[[cluster.connect]]{json}[[/cluster.connect]]`, `[[cluster.send:NAME]]{json}[[/cluster.send]]`,
`[[cluster.done:NAME]]`, `[[cluster.disconnect:NAME]]`.

Channel brain (`connectors/meshkore/brain.py::make_brain` → `nucleo/flash/cluster.py::respond`): the FlashBrain engine
in the UNTRUSTED profile. Per turn the bridge frames the input with the peer capsule + cluster status + the security
trailer (LAST); cross-turn state lives in the capsule, not the process. It runs OUTSIDE any voice turn — cluster work
continues with no browser open. It offers **no tools** and its system never exposes operator PII, so an untrusted peer
can make zaelar reason + talk but never act (see `zaelar-security.md`).

Config (env, sensible defaults): `MESHKORE_WS_BASE`, `MESHKORE_AGENT_HANDLE`, `MESHKORE_DID`, `MESHKORE_TICK_SECS`,
`MESHKORE_IDLE_SECS`, `MESHKORE_AUTORECONNECT`, and (BRAIN=direct only) `MESHKORE_MISSION_MODEL`.

## Architect connector (`connectors/architect/`) — code/project PROVIDER over the MeshKore daemon

Voice-driven remote control of the operator's **shared MeshKore daemon** (`https://127.0.0.1:5573`, one service
for ALL projects on this machine — zaelar does NOT run a daemon). It joins the provider catalog next to the ones
that already write code (headless Claude Code for widgets, the SlowBrain CodeAgent): the brain **decides and relays intent**; each
project's **architect-master** plans, anchors tasks and dispatches worker agents; all activity is visible to the
operator in the Architect cockpit. A project the daemon builds can later be adopted however we like (e.g. as a
widget) — the connector just carries intent out and results back.

Files:
- `client.py` — REST client: `GET /projects`, `POST /team/architect-master/ask` (202 → `request_id`),
  `GET /team/requests/{id}` (poll), `POST /projects` (create). Bearer token + `X-MeshKore-Project` routing header
  on every call; self-signed TLS accepted **only for loopback hosts**; 429 → `ArchitectBusy`.
- `service.py` — the async job loop (same shape as widget generation): fire `ask`, poll 3s→5s up to
  `ARCHITECT_ASK_TIMEOUT` (def 900s), then close the loop BOTH ways — `voice/proactive.notify` (voice+UI, long
  results spoken trimmed) and a `[SISTEMA]` note via `voice/brain_notes` so the brain knows the real outcome.
  **One ask in flight per project** (daemon rule); a second ask to a busy project is rejected with a note, never
  queued blind.
- `brief.py` — teaches the brain the tag protocol + live project list (cached 60s, refreshed in background —
  `for_brain()` is called per-turn by the FlashBrain prompt and must never block) + in-flight asks (so the brain
  can answer "¿cómo va?" without inventing).

Outbound tag protocol (parsed in `voice/tag_protocol.py`, silent like all tags):
`[[architect.ask:PROJECT]]<natural-language question or order>[[/architect.ask]]` and
`[[architect.new]]{"name", "parent"?}[[/architect.new]]`. Dispatched from operator turns (FlashBrain voice turns
and SlowBrain turns); **never from cluster turns** (the bridge allow-list only admits `cluster.send/done` — an
untrusted peer can never drive the operator's projects).

Config (`.env`, gitignored): `ARCHITECT_URL` (def `https://127.0.0.1:5573`), `ARCHITECT_TOKEN` (bearer; rotated
from the cockpit → Config → Remote control), `ARCHITECT_PARENT` (default folder for `architect.new`),
`ARCHITECT_ASK_TIMEOUT`. The token is never rendered into briefs, notes or speech.

Tests: `tests/connectors/unit/architect/test_architect.py` (tag parsing incl. split-chunk hold; ask lifecycle with a fake
client: happy path, busy rejection, error status, missing config).

## Messaging connectors (`connectors/{whatsapp,telegram,messaging}/`) — the unified inbox

zaelar reads the operator's **personal** WhatsApp, Telegram and Email, unified behind ONE `mensajeria` widget
(§Widget-apps). The connectors are **STATELESS** in v2 «Colmena»: they only PUBLISH `connector.msg` /
`connector.status` to the bus and drain `msg.mark_read` + **`msg.reply`** (`connectors/messaging/ingest.py`); triage +
store live inside the `mensajeria` widget owner (backed), which classifies with a **LOCAL** model (`qwen2.5:3b` via
Ollama — nothing personal leaves the machine) and dumps content to `memory/`. Read + mark-read + **RESPONDER**
(V2-051, email today; auto-responder still deferred, flag OFF).

- `connectors/whatsapp/` — reads the operator's WhatsApp (QR-linked device) via a **VENDORED Baileys bridge**
  (`connectors/whatsapp/bridge/`): a copied + patched Node bridge with `// ZAELAR-PATCH:` markers (mark-read
  endpoint + observe mode) and a `VENDORED_FROM.md` recording provenance, so it is fully owned by this repo and does
  not depend on any external agent.
- `connectors/telegram/` — a **Telethon USERBOT** (the operator's personal account, NOT the Bot API, so it can read
  personal chats), linked by a QR shown IN the canvas (generated with `segno`). Pure-Python, in-process asyncio — a
  **black-box library**, nothing vendored.
- `connectors/email/` — the operator's **personal email** (V2-051). The CLEANEST connector: **stdlib-only**
  (`imaplib`/`smtplib`), NO Node bridge (WhatsApp) NOR third-party lib (Telegram). `mailbox.py` = pure IMAP/SMTP logic
  **vendored + adapted** from Hermes' email adapter — poll with UID dedup via `BODY.PEEK` (no `\Seen` on read),
  multipart/HTML→text, noreply/bulk filter, SPF/DKIM/DMARC verdict (trust metadata, not an authz gate — we read the
  operator's OWN mailbox), SMTP reply with `In-Reply-To`/`References` threading. `config.py` = UI-managed store wins
  over `.env`, provider presets (Gmail/Outlook/iCloud/Yahoo/otro). `service.py` = asyncio engine; IMAP/SMTP always via
  `to_thread`; publishes to the bus + drains `msg.mark_read` (→ IMAP `\Seen`) and `msg.reply` (→ SMTP). Auth =
  IMAP/SMTP + **app-password** (V2-051). **V2-055 (email connectors at max):** `providers.py` = the single
  REGISTRY / list of email connectors (gmail/outlook/yahoo/icloud/generic-imap: hosts + `auth_methods` + `OAuthSpec`
  + domain deduction); `oauth.py` = OAuth2 authorization-code + PKCE (authorize URL, code exchange, token store in
  `.meshkore/credentials/email_oauth.json` chmod 600, auto-refresh), model-agnostic per provider, DORMANT until an
  app is registered (like Spotify). Transport decision: **XOAUTH2 over IMAP/SMTP** (`mailbox.xoauth2_sasl`) → Gmail
  AND Outlook reuse the SAME `mailbox.py` (token replaces password), no REST APIs. **Outlook is OAuth-ONLY**
  (Microsoft disabled basic-auth Sept-2024). `config.mailbox()` picks oauth vs password via `auth_method()`.
  Reused: Hermes `google_chat/oauth.py` + `microsoft_graph_auth.py` patterns + our `spotify/auth.py`. Remaining
  (per-provider app registration + server callback + widget "sign-in" UX + live verification) = initiative V2-055.
- `connectors/messaging/` — the SHARED layer all build on: `triage.py` (the LOCAL platform-agnostic classifier),
  `store.py` (the unified store `widgets/_data/mensajeria.json` — per-platform link state + item list +
  `pending_read` + **`pending_reply`** queues), `notify.py` (proactive voice + `[SISTEMA]` note, shared throttle),
  `brief.py` (the combined numbered brief the brain sees), `ingest.py` (the bus seam: `connector.msg`/
  `connector.status`/`msg.mark_read`/**`msg.reply`**, `MarkReadInbox`/**`ReplyInbox`** per platform), `control.py`
  (UI connect/disconnect), and `[[msg.*]]` dispatch routed by `item.platform`. **RESPONDER (V2-051):** the FlashBrain
  tool `reply_message` → the `mensajeria` `reply` data-op (`confirm:true`) → CONFIRM gate reads the draft and asks OK
  → `pending_reply` → owner drains → `msg.reply` → the channel's connector sends. Generic across channels
  (WhatsApp/Telegram to inherit). Initiating a message to a NAMED contact who hasn't written = **contacts subsystem
  (V2-052, design)**: contacts as PERSON-data in central memory, channels per contact, default-channel deduction,
  Apple/Google Contacts connectors, and eventual agent-to-agent networking.

## Music connectors (`connectors/{music,spotify}/`) — voice-driven playback (V2-041)

zaelar plays music by voice ("pon música", "ponme a Frank Sinatra", "sube la música", "siguiente", "pausa"). The
mechanism is **connector-agnostic**: the FlashBrain tool `play_music` and the `musica` widget both talk to a single
seam; providers plug in behind it — "the music surface works with ANY connector that can stream". It is the first
non-widget **rail** (§Nucleo → Rails); `nucleo/flash/music_flow.py` drives the resolve→validate→act chain.

- `connectors/music/` — the **agnostic seam** (like `connectors/messaging/` is for WhatsApp+Telegram):
  `base.py` = the `MusicProvider` contract (`connected/search/play/pause/resume/next/previous/set_volume/
  now_playing/status`) + normalized `Track`/`NowPlaying`/`MusicResult` (carrying a ready hablable phrase);
  `registry.py` = a LAZY provider registry (`active()` = first connected); `__init__.py` = the facade
  `control(action, query)` used by `play_music`. Fail-safe (never raises); es/en messages (monolingual). Each play
  is **written back to central memory** (`memory.ingest_message(source="music", entity=artist)`, done by the music
  rail) → history + tastes readable via `recent_by_source("music")` and by the retriever ("pon algo que me guste").
- `connectors/spotify/` — the **first provider**: the Spotify Web API. `client.py` = a sync httpx REST client
  (`search` + `/me/player/*` control) with **NO_ACTIVE_DEVICE recovery** (finds a Spotify Connect device and passes
  its `device_id`); `auth.py` = **OAuth 2.0 Authorization Code + PKCE** (no client-secret) — `client_id` in the
  credential store, tokens in `.meshkore/credentials/spotify.json` (chmod 600, auto-refresh), the callback served by
  `server/spotify_api.py` (`/api/spotify/{status,connect,callback,disconnect}`); `provider.py` implements the
  contract. Ported+trimmed from the retired Hermes agent's Spotify plugin. ⚠️ Playback control needs **Spotify
  Premium + an active device**. The FlashBrain drives it **in-turn off the event loop** (`asyncio.to_thread`, like
  `web_search`, V2-011). One-click connect: set `SPOTIFY_DEFAULT_CLIENT_ID` (zaelar's own app — a PKCE client_id is
  not a secret) and the user just logs in; otherwise they paste their own client_id (register the app at
  developer.spotify.com with Redirect URI `http://127.0.0.1:43917/api/spotify/callback`). Future slots: Apple, radio.
- `connectors/music/youtube_audio.py` — the **free, no-login fallback** provider: resolves a song to a YouTube
  `videoId` (YouTube Data API if `YOUTUBE_API_KEY`, else a stdlib scrape) and plays **only its AUDIO, hidden, inside
  the `musica` widget** (never the `youtube` widget — they are SEPARATE: video vs music). It's always `connected()`
  so "pon música" always plays something; the registry prefers Spotify when connected, else this. Its `play()`
  writes the command to the `musica` widget store (`yt` block); the widget mounts a hidden `<iframe>` and applies it.
- **`musica` widget** (`widgets/musica/`, passive, hand-built) — the music SURFACE, like the `mensajeria` connection
  cards: guided Spotify connect (`ctx.action("connect")` → gets the authorize URL → `window.open`), a Spotify player
  card (now-playing + controls) when connected, and a YouTube-audio card with a **hidden persisted iframe** (reused
  across re-renders so pause/volume don't restart the song) when not. It talks only to `connectors/music` — a future
  provider needs no widget change. **NOT** the `youtube` widget (that's video); the two never mix.

Enabling a connector is **UI-managed** (INI-015): the operator never edits `.env`. `config/connectors.json`
(written by the `mensajeria` widget's guided flow) holds the enable flags + Telegram credentials, with a redacted
public view (secrets never returned to the frontend). Future channels (email, X, LinkedIn) join `mensajeria`, never
their own widget.
