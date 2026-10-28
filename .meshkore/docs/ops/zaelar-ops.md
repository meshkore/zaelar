---
title: Zaelar Setup & Ops
category: ops
updated: 2026-07-09
owner: ricart
status: current
---

# zaelar — Setup & reproduce (for running here AND for distribution)

> Goal: anyone (or a future you) can reproduce a working zaelar from a clean machine. Default policy: **free/local
> where it makes sense** (see the provider catalogs). The visual map is `/architecture` → Diagrama; the live
> provider table is → Sistema. Source-of-truth docs: this file, `.meshkore/docs/architecture/`, `.meshkore/docs/product/`.
>
> zaelar's brain is **its own**: the module `nucleo/` («Colmena», two speeds — **FlashBrain** on the voice turn +
> **SlowBrain** async), with a **central memory** (`memory/`, SQLite) and an in-process **event bus** (`bus/`).
> There is no external agent to install or update.
>
> **Quick start for a fresh clone lives in the repo-root [`README.md`](../../../README.md)** (cross-platform: macOS /
> Windows / Linux). This file is the deeper ops reference; keep the two aligned when install steps change.

## 0. Prerequisites
- **Python 3.12** (the venv is pinned to it).
- **A modern Chrome/Edge** (best WebRTC support; mic needs localhost or HTTPS).
- **LiveKit server (native binary)** — `make install-livekit` (macOS Homebrew · Linux get.livekit.io · Windows
  release binary on PATH). The core runs on the native `livekit-server`; **Docker is only a fallback** if the
  binary is missing.
- **Ollama** — for the LOCAL model paths: memory embeddings (`embeddinggemma`, `ollama pull embeddinggemma`; fallback
  `nomic-embed-text`), the local messaging triage classifier (`qwen2.5:3b`), and an optional local FlashBrain model.
  Cloud model routing does not need it. Ollama is a system service, not a pip package.
- **Node ≥ 18 + Claude Code CLI** (`npm i -g @anthropic-ai/claude-code`, authenticated) — used by the on-demand
  widget generator (`widgets/generator.py`) AND the SlowBrain code-agent tier (`nucleo/agentes/`, `claude -p`).
  zaelar auto-discovers `claude` on PATH/nvm/homebrew. (Codex is an alternative code-agent adapter.)
- **Playwright Chromium** (only for the `navegador` widget) — `python -m playwright install chromium`.

## 1. Code + Python env
```
cd zaelar
python3.12 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```
`requirements.txt` pins the **LiveKit Agents** voice engine (`livekit-agents[silero,turn-detector]` + provider
plugins), FastAPI/uvicorn, `sqlite-vec` (embedded vector store for `memory/`), and `playwright` (for the navegador
widget). Nothing else is needed for the cloud/browser STT paths. The recommended **free local Whisper STT** is a
one-command add — `make install-stt` (macOS → MLX Whisper on Apple Silicon; Windows → `scripts/install-stt-win.ps1`
→ faster-whisper). Models download on first use, not bundled in git (see §5).

## 2. Config

Two layers, and **the UI store wins over `.env`**:
- **`.env`** (repo root, gitignored) — power-user / headless fallback. `cp config/.env.example .env` then fill the
  keys for the providers you choose. `config/.env.example` documents every knob + its default.
- **UI-managed stores** (gitignored JSON the frontend writes; product invariant "install once, then everything from
  the interface"): `config/settings.json` (⚙ panel → STT/TTS/voice/language), `config/connectors.json` (connector
  enable flags + credentials, written by the messaging widget), `config/v2.json` (model routing, see §3). End users
  never edit `.env`.

Key choices:
- **STT** (`STT_PROVIDER=auto`, local-first): install free **Whisper local** with `make install-stt` (macOS) or
  `scripts/install-stt-win.ps1` (Windows) → runs 100% on-device, private, no per-use cost. Without it, `auto` falls
  back to the best usable: `deepgram` (paid, proven) → `groq` (free-tier) → `aiml` (router, reuses your AIMLAPI key)
  → `browser` (free, Chrome, zero-install). Pin any explicitly via `STT_PROVIDER=whisper|browser|deepgram|groq|aiml`.
  On Apple Silicon Whisper runs in-process by Metal (`mlx-whisper large-v3-turbo`); non-Mac → faster-whisper (cuda/cpu).
- **TTS**: `TTS_PROVIDER=deepgram` (Aura-2 — **free-tier**: ~$200 credit ≈ 13M chars, then $0.030/1k; not free
  forever) · **`kokoro`** (truly-free, unlimited, private LOCAL TTS — `make install-tts`; on Apple Silicon runs
  in-process by Metal, ~0.3s to first audio, with a Kokoro-FastAPI per-phrase fallback) · `cartesia` · `elevenlabs`.
- **Brain**: `BRAIN=nucleo` (default) — zaelar's own «Colmena» brain, in-process, no external agent. Model routing
  (fast layer + code agent) lives in `config/v2.py` / `config/v2.json`, UI-managed (see §3). `BRAIN=direct`/`local`
  are plain-model baselines for debugging.
- **Runtime ⚙**: STT/TTS/language/fast-model can be set BY HAND from the gear panel (in both the assistant and
  `/architecture` headers) without editing files — persisted to `config/settings.json` / `config/v2.json`, applied
  on the next reconnect.
- **Architect (code/project provider)**: `ARCHITECT_URL` + `ARCHITECT_TOKEN` + `ARCHITECT_PARENT` — see
  **§4** (what it is, where the token lives, how to test it).

A **maximally-free** start: `make install-stt` (Whisper local) + `make install-tts` (Kokoro local TTS) + a LOCAL
FlashBrain model on Ollama → zero per-turn cost. Zero-install STT fallback: `STT_PROVIDER=browser` (Chrome).

## 3. Brain («Colmena» = `nucleo/`) + memory + model routing

The brain runs **in-process** inside the server; the `server/` lifespan starts the FlashBrain provider, the
orchestrator loop (`nucleo/pulse/loop.py`), its own cron/scheduler (`nucleo/pulse/scheduler.py`, panel at `/api/cron`,
`nucleo/cron_api.py`), and the memory queue consumer. Nothing to install or upgrade separately.

**Two speeds.** **FlashBrain** (`nucleo/flash/`) owns the hard-realtime voice turn (~sub-second) and is exposed to
the voice engine as the provider `voice/engine/llm/providers/nucleo.py`. **SlowBrain** (`nucleo/dispatch/` +
`nucleo/memory_agent.py` + `nucleo/agentes/`) does async memory/tools/reasoning off the voice path, reached via
`escalate_to_slowbrain`.

**Model routing (`config/v2.py`, UI-managed, persists to `config/v2.json`, store wins over `.env`):**
- **Fast (voice) model** — `fast` section (`FAST_PROVIDER`/`FAST_MODEL`/`FAST_BASE_URL`/`FAST_API_KEY`): a local
  Ollama model or an AIMLAPI/Grok cloud model, chosen **per invocation**. **Hard constraint: it MUST be a
  non-reasoning model** — a reasoning model adds seconds of thinking latency on the real-time path (5s+ TTFT) and
  makes zaelar slow/silent. Reasoning belongs OFF the critical path (that is what SlowBrain does). Changes apply on
  the next voice reconnect.
- **Code agent (SlowBrain tier)** — `code_agent` section (`CODE_AGENT_*`): Claude Code / Codex behind the
  `CodeAgent` interface in `nucleo/agentes/`.

**Memory** (`memory/`) is a single local SQLite file `zaelar.db` (`memory/_data/`, WAL) — sqlite-vec vector search +
FTS5 keyword + RRF fusion + a small graph + Ebbinghaus-style forgetting. It absorbed the old file inbox as an
**episodic** layer: `POST /api/files/upload` (`memory/server_api.py`) writes the bytes into the memory data-dir plus
a searchable summary. Embeddings come from `embeddinggemma` via Ollama (fallback fastembed).

**No external profile seed.** The memory starts empty and grows from conversation. A file such as
`~/.hermes/memories/USER.md`, if present on a machine, is personal and **must never be committed**.

## 4. Architect daemon (MeshKore remote control) — code/project provider by voice

**What it is.** The MeshKore daemon is a **single service shared by the whole machine** (zaelar does NOT start
it) that serves ALL of the operator's projects. Each project has a manager (**architect-master**) that plans,
anchors tasks in its roadmap and dispatches coding agents; all activity is visible in the Architect cockpit.
zaelar consumes it as a **code/project provider**: by voice, the brain passes the operator's intent on with the
silent tags `[[architect.ask:<project>]]…` / `[[architect.new]]{json}`, and the result (asynchronous, 30 s–10 min)
comes back through proactive voice + a `[SISTEMA]` note.
Code: `connectors/architect/` (REST client · ask→poll→deliver service · brief with the live project list).
Full doc: `zaelar-modules.md §Architect` · security: `zaelar-security.md §Architect provider channel`.

**How we connect (the daemon's contract):**
- Base: `ARCHITECT_URL` (default **`https://127.0.0.1:5573`**, **self-signed** TLS — the client only relaxes
  verification for loopback hosts; a non-loopback URL requires a valid certificate).
- Every request carries `Authorization: Bearer $ARCHITECT_TOKEN` and, to act on a project,
  `X-MeshKore-Project: <id>`.
- Endpoints we use: `GET /projects` (live list — **it changes**, always re-list) ·
  `POST /team/architect-master/ask` `{"text": …}` → `202 {request_id}` ·
  `GET /team/requests/<id>` → `{status: queued|running|done|error, result_text}` ·
  `POST /projects` `{"parent","name"}` (create a project).
- **One ask at a time per project** (429 = busy); the connector does NOT queue a second one — it bounces it with
  a note.

**The token — where it lives and how it is rotated.** `ARCHITECT_TOKEN` in **`.env` at the repo root**
(gitignored; NEVER committed, and never in briefs/notes/voice — a hard rule of the connector). If it leaks or a
**401/403** arrives, the operator **rotates it in the Architect cockpit → Config → Remote control** and pastes
the new one into `.env` (restart zaelar to reload it). Variables (documented without values in
`config/.env.example`): `ARCHITECT_URL` · `ARCHITECT_TOKEN` · `ARCHITECT_PARENT` (default folder for
`[[architect.new]]`) · `ARCHITECT_ASK_TIMEOUT` (default 900 s). The `[[architect.*]]` tags are **operator-only** —
the cluster bridge's allowlist does not admit them, so an untrusted peer can never direct the operator's projects.

**Smoke test (no voice, 10 seconds):**
```
./.venv/bin/python -c "
import asyncio, server.common
from connectors.architect import client
print(asyncio.run(client.list_projects()))"
# → a list of {id,name,path}.
```

**Voice test.** With zaelar running, say e.g. *«pregúntale al arquitecto de <proyecto> qué hay en el roadmap»* →
the brain emits `[[architect.ask:<project>]]…`; zaelar says it is starting it; when the manager finishes, the
answer arrives on its own by voice (and as a note if you are talking). Observability: `🏗️ Architect` events in
`/debug`; errands in flight appear in the brain's brief (it answers «¿cómo va?» without inventing).

**Troubleshooting:** `401/403` → token rotated (see above) · `429` → that project already has a turn in flight,
wait · no answer after 15 min → the errand may still be alive in the cockpit; ask again with another
`[[architect.ask]]` · `ARCHITECT_TOKEN no configurado` → the var is missing from `.env`. Connector tests:
`./.venv/bin/pytest connectors/architect/ -q`.

## 5. Run
```
make run                 # = BRAIN=nucleo scripts/run-livekit.sh → http://localhost:43917 (Chrome)
```
`make run` brings up the full stack: the **native LiveKit server** (`make install-livekit`; Docker only as a
fallback) + the web app with the **agent worker EMBEDDED** in the process, with the «Colmena» brain
(`BRAIN=nucleo`). Aliases: `make run-nucleo` (identical) · `make run-lk` (override `BRAIN=…`). Debugging the halves
separately: `make lk-server` (the LiveKit dev server only) · `make agent-worker` (the worker only, against a
LiveKit that is already up).

Open **http://localhost:43917 in Chrome** (mic needs localhost or HTTPS). `/architecture` = live diagram + docs ·
`/debug` = live event timeline. Self-test (no browser): `./.venv/bin/python -m tests.voice.e2e.mic.mic_selftest`.

### Memory reset — starting a test from zero (`make reset-restart`)
```
make reset-dry           # shows what it would delete/keep WITHOUT touching anything
make reset               # deletes ONLY the human memory (does not start)
make reset-restart       # deletes + restarts the stack from zero (make run)
```
To test memory **from zero** ("what's your name?", "where do you live?") **without re-authenticating**
Telegram/WhatsApp/Wallapop/cluster on every run. `scripts/reset-memory.sh` (self-documented; portable to bash 3.2)
deletes the **human memory** (`memory/_data/zaelar.db` +wal/shm — including the bus's durable event log —,
episodic, widget/message content stores) **and the observability** (`.meshkore/logs/sessions/` +
`timeline-latest.jsonl`, so the test can be AUDITED against the zeroed DB), and **KEEPS** credentials/auth/cookies:
`connectors/whatsapp/_session` (Baileys) · `connectors/telegram/_session` · `widgets/_data/navegador/profile`
(Wallapop/Google cookies) · `memory/_data/search_browser` · `config/*.json` (cluster WS tokens) · `.env` ·
`.meshkore/credentials/`. The boundary works because storage is **separated by directory** (`.gitignore`); the
script uses EXPLICIT paths (never `rm -rf` on a shared parent — e.g. `memory/_data/` holds the DB **and** the
search profile). After the reset, zaelar starts with `operator_name=None` and memory at 0 → the profile grows
during the test and observability can be compared against the DB.

## 6. Defaults at a glance
| Function | Default | Free? | Alternatives (in code) |
|---|---|---|---|
| STT | **Whisper local** (`auto`) | **yes·local** | browser (free), deepgram, groq (free-tier), aiml (opt-in router) |
| TTS | **Deepgram Aura-2** | free-tier | **kokoro** (free·local), cartesia, elevenlabs |
| Brain | **nucleo** («Colmena», own, in-process) | — | direct/local (OpenAI-compatible baselines). NO reasoning models on the voice layer |
| Fast model | per invocation (`config/v2`) | depends on provider | local Ollama (free) · AIMLAPI/Grok (cloud) — non-reasoning mandatory |
| Memory embeddings | embeddinggemma (Ollama) | **yes·local** | fastembed (fallback) |
| VAD/turn | LiveKit (Silero + turn-detector) | yes·local | — |
| WebRTC TURN | Cloudflare/STUN | yes | — |
| Widget code-gen / SlowBrain | Claude Code headless | — | Codex |

## 7. Distribution notes (so it reproduces everywhere)
- **Bundle vs download**: keep models OUT of git. Local backends already shipped as one-command installers
  (`make install-stt` → MLX/faster-whisper offline STT; `make install-tts` → Kokoro offline TTS), models download on
  first use. Cross-platform (`scripts/install-stt-mac.sh` / `install-stt-win.ps1`; TTS analogously). Each turns a
  paid API into a free local equivalent post-install.
- **Native LiveKit**: `make install-livekit` ships the server binary so `make run` needs no Docker.
- **Secrets**: never commit `.env`, `config/settings.json`, `config/connectors.json`, `config/v2.json`, or
  `~/.hermes/memories/USER.md` (personal). Ship `config/.env.example` only.
- **Connectors**: WhatsApp/Telegram triage are one-time installs (`make install-whatsapp` / `make install-telegram`)
  and are then activated + linked entirely from the messaging widget (QR in the canvas), never by hand-editing
  `.env` (product invariant "install once, then everything from the interface").
