---
title: Zaelar Product Context
category: product
updated: 2026-07-09
owner: ricart
status: current
---

# zaelar — Project context (single source of truth for onboarding)

> Read this to start from zero and continue without friction. zaelar is an **independent product**. This
> `.meshkore/docs/` folder is the **portable knowledge** (context + diagrams + modules + decisions) that travels
> with it. The design source of truth for the current system is `EPIC-v2-colmena` (`.meshkore/roadmap/`) + the
> live diagram at `/architecture`.

## 1. What zaelar is
A **voice-first personal-life assistant** (warm, remembers you, helps run your day). It speaks by voice, shows
**graphical widgets** on a canvas when useful, and runs on its **OWN brain** — the `nucleo/` module («Colmena»):
a two-speed brain (**FlashBrain** for the sub-second voice turn + **SlowBrain** async agents) with its **own
central memory** (`memory/`, SQLite) and cron/proactivity. No external agent. Runs locally at
**http://localhost:43917** (`cd zaelar && make run`).

Status: voice round-trip works (STT→nucleo→TTS, streaming); memory persists across sessions (`memory/`); widgets
(agenda coach + weather/search + navegador) work with a drag-and-drop desktop; speaker-gate v1 filters other
voices; cloud demo parked on fly. Pending: more importers/connectors, wake-word, SpeakerGate v2.

**Voice reliability (current focus).** A recurring "zaelar doesn't hear me" has had several distinct causes;
each was localized with the **AudioProbe RMS in `/debug`** (don't guess STT vs echo vs brain — read the meter
first; the ladder is in §12). Settled config: the browser captures the **fully-processed mic**
— echoCancellation + noiseSuppression + **autoGainControl** + voiceIsolation. This is what enables CONTINUOUS
interactive listening on speakers + barge-in: echoCancellation removes zaelar's own TTS so it doesn't transcribe
itself, and autoGainControl re-amplifies your voice after that subtraction (echoCancellation ALONE leaves it at
rms≈0.01 → killed → "no me escucha while it talks"). **Audio is captured separately from video** (requesting both
can bind the mic to the camera's silent input); and the UI shows a live **mic level meter + device name + a mic
picker**, mirrored to `/debug` via `/api/client-log`. Open edge seen in testing: a browser can deliver
**exactly-zero** audio when macOS denies the *app* (Chrome) microphone permission at the OS level even though the
*site* permission is granted — fixed in System Settings, not in code.

## 2. The pieces (and the golden rule: layers are independent)
- **Voice core** — the LiveKit **AgentSession** engine (`voice/engine/`): STT → brain → TTS, streaming. It runs
  **EMBEDDED** in the server process (`AgentServer`, thread job executor), not as a separate process. Turn-taking,
  VAD and barge-in are governed by LiveKit (Silero VAD + the `MultilingualModel` turn-detector +
  `allow_interruptions`) — no custom watchdog on the critical path; proactivity comes from the nucleo loop/cron
  instead. **STT defaults to local Whisper** (MLX on Apple Silicon via mlx-whisper, faster-whisper on Win/Linux;
  free·private, `make install-stt`), with cloud STT (Deepgram/AIMLAPI) as explicit opt-ins. **TTS** defaults to
  Deepgram Aura-2 (es+en); Kokoro local is the free, unlimited, private option. The top level of `voice/` is the
  **brain-agnostic contract** (kept pure): `tag_protocol.py`, `prompt.py`, `brain_notes.py`, `proactive.py`,
  `observer.py` (SSE), plus the STT/TTS backends and the provider registry (`voice/engine/llm/providers/`).
- **Brain = `nucleo/`** (zaelar's OWN, default `BRAIN=nucleo`; `config/v2.py` `active_brain()`). Two speeds:
  **FlashBrain** (`nucleo/flash/`) is the sub-second voice layer — a **non-reasoning** model chosen per-invocation
  (Ollama local or AIMLAPI/Grok cloud, `config/v2.py` `fast` section), exposed to the voice engine as provider
  `voice/engine/llm/providers/nucleo.py`. **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` +
  `nucleo/agentes/`) runs async Claude Code / Codex agents (the `CodeAgent` interface) for memory/tools/reasoning
  off the voice path — reached by the FlashBrain calling `escalate_to_slowbrain`. The orchestrator loop
  (`nucleo/loop.py`, ~1 Hz) + own cron (`nucleo/scheduler.py`, persisted in `memory.journal`) + panel
  (`nucleo/cron_api.py`, the `/api/cron` panel) + `nucleo/sparks.py` own proactivity. **The FlashBrain model MUST
  be non-reasoning** on the voice path (a reasoner adds seconds of thinking latency; see §7 decisions).
- **Widgets** — isolated visual layer in `widgets/` + browser window-manager `frontend/app/widgets/desktop.js`. One
  folder per widget (manifest + widget.js + data.py), per-widget JSON store, catalog-driven HTTP API.
- **Speaker gate** — `frontend/app/lib/speaker-gate.js`: learns the owner's voice on connect and filters other voices
  before they reach the orchestrator.
- **Debug/observability** — every voice/turn/latency/brain/widget event flows through the event bus (`bus/`) and
  `voice/observer.py` → `/debug` (live page) and `/api/debug` (JSON); the frontend reads the `/events` SSE stream.
- **Web UI** — the `frontend/` **ES-module app** (no build step; the browser loads the modules directly; the server
  just serves `frontend/`). Structured for a later Solid.js migration: `core/reactive.js` mirrors Solid's
  `createSignal`/`createEffect`, components build DOM via `h()`, services (LiveKit client/audio/SSE) are framework-free
  (full map: `.meshkore/docs/modules/zaelar-modules.md` §Frontend). `index.html` is a thin bootstrap.
  The canvas: bottom-centre voice orb (zaelar's voice spectrum), draggable camera box with the mic spectrum overlaid,
  power/reset, Docs/Debug links, a **☾/☀ dark/light theme toggle** (dark by default — pure CSS custom properties,
  no reload, widgets repaint live too, see `.meshkore/docs/modules/zaelar-modules.md` §Frontend), and a **text chat
  wall** (type/paste to the agent via a data channel → a normal user turn; Ctrl/Cmd+V anywhere feeds it too).
  Tapping the orb cycles voices **within the current provider** (provider/language are changed in the ⚙ panel
  below). **⚙ config panel** (gear icon in BOTH the `/architecture` header and the assistant `/` header): set STT
  provider, TTS provider, and language BY HAND at runtime (no file editing) — backed by GET/POST `/api/settings`
  (`config/settings.py`); overrides persist to `config/settings.json` (gitignored), apply to env at boot, and take
  effect on the next voice reconnect. (Brain model routing lives in `config/v2.py`, not the ⚙ panel.)
  **Mic-blocked indicator**: a red 🚫 ring over the orb when the mic is muted, occupied by another app (e.g.
  SuperWhisper), or capturing silence. **Camera/voice box** (Google-Meet style): narrower spectrum strip with a MIC
  toggle + a CAMERA toggle to its right (crossed-out red when off; state persists across refresh); drag the whole
  unit from ANY point. Honest note: the camera is **LOCAL-only** today — vision isn't wired, zaelar can't "see" you
  yet; the toggle is the UX foundation. **Desktop persistence**: open widgets + their positions survive
  refresh/reopen (`localStorage hb_desktop`; transient widgets like the activity rail are not persisted).
  **WebRTC auto-reconnect**: a dropped established connection silently reconnects. Still has a **mic diagnostics**
  path: live RMS level, active device name, mic picker, mirrored to the debug stream via `POST /api/client-log`.
  Server: FastAPI in `server/`.

**Isolation is verified**: `widgets/` and the voice/brain core only touch through documented, guarded bridges
(`widgets/brief`, `voice/brain_notes`, `voice/proactive` — each wrapped in try/except so a failure degrades, never
propagates). A broken widget cannot crash the audio; widget `data.py` additionally runs OFF the event loop with a
hard timeout.

## 3. How to run
```
cd zaelar
make install-stt         # once (recommended): free LOCAL Whisper STT → private, no per-use cost (Win: scripts/install-stt-win.ps1)
make install-livekit     # once: the native livekit-server binary (the core does NOT require Docker)
make run                 # voice app with the nucleo brain (BRAIN=nucleo) → http://localhost:43917  (port fixed: 43917)
make test                # import/health check
```
Self-contained: `zaelar/.venv` (cloned, APFS) + `zaelar/.env`. **Cron/proactivity runs on the nucleo orchestrator
loop** (`nucleo/loop.py` + `nucleo/scheduler.py`, own cron persisted in `memory.journal`, panel `nucleo/cron_api.py`)
— in-process, no external agent, no launchd service.

## 4. Architecture & couplings (the contracts)
- **Voice ↔ Brain**: the nucleo provider (`voice/engine/llm/providers/nucleo.py`) sits in the LLM slot; the
  FlashBrain answers the voice turn in ~sub-second and, when the turn needs memory/tools/reasoning, calls
  `escalate_to_slowbrain` → `nucleo/dispatch.py` (async CodeAgent, result delivered back via `voice/proactive` +
  a bus/`[SISTEMA]` note). Memory lives in `memory/` (SQLite), shared across voice + chat + the MeshKore channel.
- **Brain ↔ Widgets bridge** (one-directional, additive, guarded): on connect, `widgets/brief.for_brain()` (the
  catalog + today's agenda + the **silent-tag protocol**) is injected into the brain. The brain decides to surface
  a widget by ending its reply with a silent tag `[[show:ID]]` / `[[close:ID]]` / `[[close]]`. The nucleo provider
  strips the tag from speech and emits a `widget` event on the bus; the SSE stream carries it to the browser, where
  the desktop runs `desktop.show(id)` / `desktop.close(id)`. (A front-side keyword fast-path also exists as a
  fallback.) If the widget layer is absent/errors, voice continues. **Id drift is tolerated**: the brain doesn't
  always emit the exact catalog id (e.g. it says `agenda-today` for the `agenda` widget), so `Desktop._resolve()`
  matches the emitted id against the live catalog (exact → prefix → contains) before fetching — otherwise the
  widget would 404 silently and never appear.
- **Widget contract** (browser): `render(el, data, ctx)` where `ctx.action(name,payload)→newData` and
  `ctx.close()`. Lazy-loaded per widget via dynamic `import('/widgets/ID/widget.js')`.
- **Widget HTTP API** (catalog-driven, `widgets/server_api.py`): `GET /widgets` · `/widgets/identify?q=` ·
  `/widgets/{id}/manifest|widget.js|data?q=|context` · `POST /widgets/{id}/action`. `wid` is normalized at the
  edge (no path/import traversal).
- **Desktop API** (`frontend/app/widgets/desktop.js`): `show(id,{q}) · close(id) · closeAll() · has(id) · list() ·
  capabilities()`. Owns drag (9-dot grip), z-order (newest on top), tiling→overlap placement, loader + "boop".
- **Per-widget store** (`widgets/store.py`): one isolated JSON per widget under `widgets/_data/`. Atomic writes
  (temp+os.replace), locked. No shared DB for UI state. (Durable data a widget produces is additionally written to
  the central `memory/` for brain recall — see zaelar-modules.md; the per-widget store stays for UI state.)

## 5. Brain config + models (nucleo)
- **Model routing lives in `config/v2.py`** (env-first, hot-applied on reconnect), NOT in an external agent config:
  - `fast` section (`FAST_PROVIDER`/`FAST_MODEL`/`FAST_BASE_URL`/`FAST_API_KEY`) — the FlashBrain voice model,
    chosen **per invocation**; a **NON-reasoning** model (Ollama local or AIMLAPI/Grok cloud). Do NOT use a
    reasoning model on the voice path (seconds of thinking latency; see §7).
  - `code_agent` section (`CODE_AGENT_*`) — the SlowBrain CodeAgent tier (Claude Code / Codex, `nucleo/agentes/`).
  - `flags.brain` / env `BRAIN` — `active_brain()`, default `nucleo`; `direct`/`local` are plain-model baselines.
- **Memory** = `memory/` (SQLite `zaelar.db`): persona/context + episodic layer (which absorbed the old `files/`
  inbox) + the message content the messaging widget writes. Single-writer queue, embeddings on insert, vector +
  keyword retrieval (sqlite-vec + FTS5 → RRF), graph edges, Ebbinghaus-style forgetting. On first boot,
  `memory/seed_from_hermes.py` does a **one-shot, read-only** import of the operator profile from `~/.hermes` if
  present (best-effort); `~/.hermes/memories/USER.md` is the operator's personal profile and is **never committed**.
  The `⚙` panel (`config/settings.py`) still handles only STT/TTS/voice/language.

## 6. Adding a widget (scales to thousands)
Drop a folder `widgets/<id>/` with: `manifest.json` (id, version, title, description, whenToUse, keywords,
entry:"widget.js"), `widget.js` (exports `render(el,data,ctx)`), and optionally `data.py` (`view_data(q="")`,
`apply_action(action,payload)`, `coach_context()`). The catalog auto-discovers it (cached, mtime-invalidated);
the brain learns it via `brief.for_brain()`; the desktop lazy-loads it. No server edits.

## 7. Decisions log (don't lose these)
- **zaelar is independent** from the interview app; the sim harness comes from `prototype_candidate/`. zaelar
  extracted to its own repo; `.meshkore/docs/` is the portable knowledge.
- **The brain is zaelar's OWN** (`nucleo/`, «Colmena») — an in-process two-speed brain with its own memory
  (`memory/`) and event bus (`bus/`). No external agent, no per-turn CLI spawn: the FlashBrain is a warm streaming
  provider in the LLM slot; the SlowBrain does async work off the voice path.
- **Language**: voice-driven. STT multilingual; default Spanish, but a returning user is greeted in their preferred
  language **from memory**; switches live on request. Voice is always language-aligned.
- **Voice (TTS)**: default **Deepgram Aura-2** (es+en codeswitching: Selena/Javier/Diana/Carina/Aquila). HONEST
  cost: Aura-2 is **free-tier** (~$200 credit ≈ 13M chars, then $0.030/1k chars) — not free forever. **Kokoro
  local** (Spanish, Apache-2.0) is the truly-free, unlimited, private LOCAL TTS (`make install-tts`; enable in the
  ⚙ panel or `TTS_PROVIDER=kokoro`). Cartesia/ElevenLabs are cloud (paid) alternatives. Tap the orb to cycle voice
  **within the current provider**. Cost taxonomy used in the UI: "gratis"=local·unlimited · "free-tier"=credit then
  paid · "pago"=paid from the start.
- **Voice (FlashBrain) model = a NON-reasoning model.** A reasoning model on the real-time path adds seconds of
  thinking latency (5s+ TTFT) and risks never closing the voice turn → zaelar goes silent. A non-reasoner answers
  in ~1s. Reasoning belongs OFF the critical path, in the SlowBrain (§5).
- **Widgets isolated** (own layer, own store, lazy load) — designed for thousands; brain drives them via silent
  tags, not hard-coupling.
- **Speaker gate v1** = acoustic fingerprint (pitch+centroid+loudness); v2 = Picovoice Eagle (needs AccessKey).
- **Cost framing**: paid hops = LLM (AIMLAPI fast model, cheap) + TTS (Aura-2, **free-tier** then paid); **STT is
  free/local by default** (Whisper local via `make install-stt`), and **Kokoro local TTS** (`make install-tts`) is
  the truly-free unlimited voice. Everything else free/local. Growth path: local model + Kokoro → ~0 per-turn cost.

## 8. Growth direction (roadmap)
Next: index `identify()` + show disambiguation candidates (DONE 2026-07-03 — lexical-semantic tier); persist
widget layout/prefs ("don't show X" → memory); approaching-agenda-item countdown widget (cron-driven); SpeakerGate
v2 (Eagle). Then the JARVIS roadmap: importers WhatsApp→Telegram→Gmail (need accounts/auth), live channels,
connectors X/LinkedIn, wake-word (0-token), mobile via Telegram/WhatsApp. Later: local models for cost; widget
auto-modification via a `CodeAgent` interface.

## 9. Credentials used (NAMES + location only — never commit values)
- `zaelar/.env` (gitignored): `AIMLAPI_KEY`, `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, `ELEVENLABS_API_KEY`,
  `GEMINI_API_KEY`, `OPENAI_API_KEY`; TURN: `WEBRTC_HOST`, `TURN_URLS/USERNAME/CREDENTIAL` (public Open Relay) —
  for robust mobile, Cloudflare `CF_TURN_KEY_ID/CF_TURN_API_TOKEN` (lives on the fly app, not local).
- Model keys for the brain live in `zaelar/.env` / `.meshkore/credentials/zaelar.env` (AIMLAPI etc.), routed by
  `config/v2.py`.
- Cloudflare DNS token: `…/meshkore/.meshkore/credentials/cloudflare-token.txt` (DNS only; no Calls/TURN perm).
- Fly.io account: personal (`rjj@proars.com`), app `zaelar` (region cdg), parked (scale-to-zero).
- Email/relay + Picovoice (future): provided by the operator when needed.

## 10. Libraries & external APIs
- **livekit-agents** (the AgentSession voice engine: STT/LLM/TTS plugins, Silero VAD, `MultilingualModel`
  turn-detector — runs EMBEDDED in the server process) + the native **livekit-server** binary
  (`make install-livekit`; **no Docker in the core**), **fastapi/uvicorn**, the vendored **LiveKit browser SDK**
  (`frontend/vendor/`), **loguru**, **python-dotenv**.
- STT default: **Whisper local** (MLX on Apple Silicon / faster-whisper on Win-Linux, on-device, free). TTS local:
  **Kokoro** (Apache-2.0, Spanish, `make install-tts`). APIs (optional/alt): **Deepgram** (STT nova-3 + Aura-2 TTS),
  **Cartesia** (Sonic TTS), **AIMLAPI** (OpenAI-compatible LLM router → the FlashBrain fast model, e.g.
  `x-ai/grok-4-fast-non-reasoning`, routed by `config/v2.py`). SlowBrain agents: **Claude Code / Codex** CLIs
  (`nucleo/agentes/`). Memory: **SQLite** (sqlite-vec + FTS5) + **Ollama** embeddinggemma (fallback fastembed).
  Widgets: **open-meteo** + **wttr.in** (weather, keyless), **DuckDuckGo html** (web search, best-effort);
  `navegador` = **Playwright** Chromium. Cloudflare (DNS/TURN), fly.io (deploy).

## 11. Repo layout  (root has NO loose .py/.html; see zaelar-modules.md)

Two independent sides — **client** (`frontend/`, the browser app) and **server** (a single Python app made of the
MeshKore modules below) — talk over WebRTC + HTTP + SSE. Entry: `make run` → `python -m server`.
```
zaelar/
  frontend/      CLIENT — self-contained ES-module app (no build), Solid-migration-ready
    index.html   thin bootstrap (link styles + <script type=module> main.js)
    pages/       architecture.html · debug.html
    app/
      main.js    entry: mounts components, creates the widget desktop, starts the visualizer
      core/      reactive.js (Solid-compatible signals) · dom.js (h() hyperscript) · store.js (reactive state)
      services/  session-lk.js (LiveKit client) · audio · sse · visualizer · voiceCommands · api
      components/ Orb · CameraUnit · TopBar · SettingsModal · ConnStatus · Alert · ChatWall
      lib/       draggable.js · speaker-gate.js       widgets/ desktop.js (window manager)
    vendor/      vendored LiveKit browser SDK
  server/        SERVER — FastAPI app + routers + entrypoint (__main__.py); runs the LiveKit agent worker EMBEDDED
  voice/         VOICE ENGINE (server-side): engine/ (LiveKit AgentSession + STT/LLM/TTS providers, incl.
                 providers/nucleo.py), tag_protocol.py, observer.py, prompt.py, brain_notes.py, proactive.py, speech/
  nucleo/        BRAIN «Colmena» (BRAIN=nucleo): flash/ (FlashBrain) · dispatch.py + memory_agent.py + agentes/ (SlowBrain) · loop.py · scheduler.py · cron_api.py · sparks.py
  memory/        CENTRAL MEMORY — SQLite zaelar.db (sqlite-vec + FTS5 + RRF + graph + forgetting); absorbed old files/ as episodic layer; seed_from_hermes.py (one-shot read-only importer)
  bus/           EVENT BUS — in-process pub/sub (generalizes voice/observer.py) + durable SQLite log + SSE bridge
  connectors/    external I/O: meshkore/ (cluster WS · FlashBrain untrusted profile · per-peer capsule) · architect/ · whatsapp/ · telegram/ · messaging/ (shared)
  widgets/       WIDGETS full-stack per folder (manifest.json + widget.js + data.py) + runtime, store, server_api, brief, supervisor; _data/
  config/        .env.example · settings.py → settings.json (⚙ STT/TTS/voice/language) · v2.py (model routing + active_brain)
  tests/agent_headless/harness/       dev/eval: run.py, user_sim.py, judge.py, personas/  (not shipped)
  tests/voice/e2e/agent/        voice tester (INI-013): 2nd LiveKit participant that SPEAKS + LISTENS
  scripts/       install tooling (install-stt/tts-*.sh/.ps1)
  .meshkore/     MeshKore Standard v27 — public/cluster.yaml, docs/, modules/, roadmap/; logs → .meshkore/logs/
  Dockerfile · fly.toml · .dockerignore · Makefile · requirements.txt · CLAUDE.md   (root manifests; .venv shared)
```
**Ours vs external:** the brain (`nucleo/`) and memory (`memory/`) are FIRST-PARTY — zaelar does not depend on an
external agent. The remaining external pieces are (a) the SlowBrain CodeAgent CLIs (Claude Code / Codex, invoked by
`nucleo/agentes/` — installed software, not our code), (b) the vendored WhatsApp Baileys bridge
(`connectors/whatsapp/bridge/`, copied+patched, `VENDORED_FROM.md`), and (c) the vendored LiveKit browser SDK
(`frontend/vendor/`). See `.meshkore/docs/conventions/zaelar-conventions.md` → "First-party vs external".

## 12. Where to look when…
- **"zaelar doesn't hear me"** → read the **`audio` RMS in `/debug`** before changing anything; it pinpoints the
  failing layer (real speech RMS ≈ 0.05–0.3):
  1. **No `audio` events at all** → browser/WebRTC isn't delivering audio (permission / connection), not STT.
  2. **`audio` events but RMS ≈ 0 the whole session** → the browser is capturing silence *before* the network.
     Exactly `0.000` (vs the ~0.001 noise floor of a live mic) ⇒ OS/permission/device, not code: macOS Settings →
     Privacy → **Microphone → enable the browser** (toggle off/on + Cmd-Q relaunch); pick the right input device;
     close apps holding the mic (e.g. SuperWhisper). Confirm with the on-screen **mic meter** (red/⚠️muted) and the
     `client` events in `/debug`.
  3. **RMS healthy but no `transcript`** → STT layer: wrong `STT_LANGUAGE`, or a cloud provider out of funds.
  4. **transcripts but garbled / zaelar answering itself** → echo (transcribing its own TTS through speakers);
     the browser's echoCancellation handles it (default); headphones also fix it; full fix = SpeakerGate v2.
- "voice not responding" → `/debug`: `transcript` but no `brain` prompt = turn/VAD; `brain` prompt but no
  reply/`error` = brain.
- "doesn't remember me" → the central memory `memory/` (SQLite `zaelar.db`); the greeting must be memory-aware (it
  is).
- "widget didn't appear" → brain tag in the reply (`/debug` shows `widget` events) or front intent; `/widgets`.
  If the brain emitted a near-miss id, `Desktop._resolve()` should map it — check the console `widget id resolved`.
- architecture/diagram → the Docs web hub (`/architecture`) or `.meshkore/docs/architecture/zaelar-architecture.md`.
