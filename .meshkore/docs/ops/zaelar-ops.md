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
- **Architect (proveedor de código/proyectos)**: `ARCHITECT_URL` + `ARCHITECT_TOKEN` + `ARCHITECT_PARENT` — see
  **§4** (what it is, where the token lives, how to test it).

A **maximally-free** start: `make install-stt` (Whisper local) + `make install-tts` (Kokoro local TTS) + a LOCAL
FlashBrain model on Ollama → zero per-turn cost. Zero-install STT fallback: `STT_PROVIDER=browser` (Chrome).

## 3. Brain («Colmena» = `nucleo/`) + memory + model routing

The brain runs **in-process** inside the server; the `server/` lifespan starts the FlashBrain provider, the
orchestrator loop (`nucleo/loop.py`), its own cron/scheduler (`nucleo/scheduler.py`, panel at `/api/cron`,
`nucleo/cron_api.py`), and the memory queue consumer. Nothing to install or upgrade separately.

**Two speeds.** **FlashBrain** (`nucleo/flash/`) owns the hard-realtime voice turn (~sub-second) and is exposed to
the voice engine as the provider `voice/engine/llm/providers/nucleo.py`. **SlowBrain** (`nucleo/dispatch.py` +
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

**Operator profile seed (best-effort, read-only).** On boot, `memory/seed_from_hermes.py` does a one-shot,
read-only import of the operator profile from `~/.hermes` **if that folder exists** — so an existing local setup
carries name/language/projects into zaelar's memory. It never writes to `~/.hermes`. The file
`~/.hermes/memories/USER.md` is personal and **must never be committed**.

## 4. Architect daemon (MeshKore remote control) — proveedor de código/proyectos por voz

**Qué es.** El daemon MeshKore es un servicio **único y compartido de esta máquina** (NO lo arranca zaelar) que
sirve a TODOS los proyectos del operador (ikamiro, cavioca, reddit, …). Cada proyecto tiene un manager
(**architect-master**) que planifica, ancla tareas en su roadmap y despacha agentes de código; toda la actividad
es visible en el cockpit del Architect. zaelar lo consume como **proveedor de código/proyectos**: por voz, el brain
transmite la intención del operador con las tags silenciosas `[[architect.ask:<proyecto>]]…` /
`[[architect.new]]{json}` y el resultado (asíncrono, 30s-10min) vuelve por voz proactiva + nota `[SISTEMA]`.
Código: `connectors/architect/` (client REST · service ask→poll→entrega · brief con la lista de proyectos viva).
Doc completa: `zaelar-modules.md §Architect` · seguridad: `zaelar-security.md §Architect provider channel`.

**Cómo nos conectamos (contrato del daemon):**
- Base: `ARCHITECT_URL` (def **`https://127.0.0.1:5573`**, TLS **autofirmado** — el cliente solo relaja la
  verificación para hosts loopback; una URL no-loopback exige certificado válido).
- Cada request lleva `Authorization: Bearer $ARCHITECT_TOKEN` y, para operar sobre un proyecto,
  `X-MeshKore-Project: <id>`.
- Endpoints que usamos: `GET /projects` (lista viva — **cambia**, re-listar siempre) ·
  `POST /team/architect-master/ask` `{"text": …}` → `202 {request_id}` ·
  `GET /team/requests/<id>` → `{status: queued|running|done|error, result_text}` ·
  `POST /projects` `{"parent","name"}` (crear proyecto).
- **Un ask a la vez por proyecto** (429 = ocupado); el conector NO encola un segundo — lo rebota con nota.

**El token — dónde vive y cómo se rota.** `ARCHITECT_TOKEN` en **`.env` en la raíz del repo** (gitignored; JAMÁS
se commitea, ni aparece en briefs/notas/voz — regla dura del conector). Si se filtra o llega un **401/403**, el
operador lo **rota en el cockpit del Architect → Config → Remote control** y se pega el nuevo en `.env` (reiniciar
zaelar para recargarlo). Variables (documentadas sin valores en `config/.env.example`):
`ARCHITECT_URL` · `ARCHITECT_TOKEN` · `ARCHITECT_PARENT` (carpeta por defecto para `[[architect.new]]`) ·
`ARCHITECT_ASK_TIMEOUT` (def 900s). Las tags `[[architect.*]]` son **operator-only** — la allowlist del bridge de
cluster no las admite, así que un peer no confiable jamás dirige los proyectos del operador.

**Smoke test (sin voz, 10 segundos):**
```
./.venv/bin/python -c "
import asyncio, server.common
from connectors.architect import client
print(asyncio.run(client.list_projects()))"
# → lista de {id,name,path}.
```

**Prueba por voz.** Con zaelar corriendo, decir p. ej. *«pregúntale al arquitecto de ikamiro qué hay en el
roadmap»* → el brain emite `[[architect.ask:ikamiro]]…`; zaelar dice que lo pone en marcha; al terminar el
manager, la respuesta llega sola por voz (y como nota si estás hablando). Observabilidad: eventos `🏗️ Architect`
en `/debug`; los encargos en curso salen en el brief del brain (responde «¿cómo va?» sin inventar).

**Troubleshooting:** `401/403` → token rotado (ver arriba) · `429` → ese proyecto ya tiene un turno en curso,
esperar · sin respuesta tras 15 min → el encargo puede seguir vivo en el cockpit; preguntar de nuevo con otro
`[[architect.ask]]` · `ARCHITECT_TOKEN no configurado` → falta la var en `.env`. Tests del conector:
`./.venv/bin/pytest connectors/architect/ -q`.

## 5. Run
```
make run                 # = BRAIN=nucleo scripts/run-livekit.sh → http://localhost:43917 (Chrome)
```
`make run` levanta el stack completo: el **servidor LiveKit nativo** (`make install-livekit`; Docker solo fallback)
+ la web con el **agent worker EMBEBIDO** en el proceso, con el cerebro «Colmena» (`BRAIN=nucleo`). Aliases:
`make run-nucleo` (idéntico) · `make run-lk` (override `BRAIN=…`). Depurar por separado: `make lk-server` (solo el
servidor LiveKit dev) · `make agent-worker` (solo el worker contra un LiveKit ya arriba).

Open **http://localhost:43917 in Chrome** (mic needs localhost or HTTPS). `/architecture` = live diagram + docs ·
`/debug` = live event timeline. Self-test (no browser): `./.venv/bin/python harness/mic_selftest.py`.

### Reset de memoria — empezar un test de cero (`make reset-restart`)
```
make reset-dry           # muestra qué borraría/conservaría SIN tocar nada
make reset               # borra SOLO la memoria humana (no arranca)
make reset-restart       # borra + re-arranca el stack de cero (make run)
```
Para probar la memoria **desde cero** ("¿cómo te llamas?", "¿dónde vives?") **sin re-autenticar** Telegram/WhatsApp/
Wallapop/cluster en cada prueba. `scripts/reset-memory.sh` (auto-documentado; portable a bash 3.2) borra la
**memoria humana** (`memory/_data/zaelar.db` +wal/shm — incluye el log durable de eventos del bus —, episódica,
stores de contenido de widgets/mensajes) **y la observabilidad** (`.meshkore/logs/sessions/` + `timeline-latest.jsonl`,
para poder AUDITAR el test contra la BD a cero), y **CONSERVA** credenciales/auth/cookies:
`connectors/whatsapp/_session` (Baileys) · `connectors/telegram/_session` · `widgets/_data/navegador/profile`
(cookies Wallapop/Google) · `memory/_data/search_browser` · `config/*.json` (tokens WS del cluster) · `.env` ·
`.meshkore/credentials/`. La frontera funciona porque el storage está **separado por directorio** (`.gitignore`); el
script usa rutas EXPLÍCITAS (nunca `rm -rf` sobre un padre compartido — p.ej. `memory/_data/` contiene la BD **y** el
perfil de búsqueda). Tras el reset, zaelar arranca con `operator_name=None` y la memoria a 0 → el perfil crece durante
el test y se puede comparar observabilidad ↔ BD.

## 6. Defaults at a glance
| Función | Default | Gratis? | Alternativas (en código) |
|---|---|---|---|
| STT | **Whisper local** (`auto`) | **sí·local** | browser (free), deepgram, groq (free-tier), aiml (opt-in router) |
| TTS | **Deepgram Aura-2** | free-tier | **kokoro** (gratis·local), cartesia, elevenlabs |
| Brain | **nucleo** («Colmena», propio, in-process) | — | direct/local (baselines OpenAI-compat). NO usar modelos de razonamiento en la capa de voz |
| Fast model | por invocación (`config/v2`) | según proveedor | local Ollama (gratis) · AIMLAPI/Grok (nube) — non-reasoning obligatorio |
| Memory embeddings | embeddinggemma (Ollama) | **sí·local** | fastembed (fallback) |
| VAD/turno | LiveKit (Silero + turn-detector) | sí·local | — |
| WebRTC TURN | Cloudflare/STUN | sí | — |
| Widget code-gen / SlowBrain | Claude Code headless | — | Codex |

## 7. Distribution / installer TODOs (so it reproduces everywhere)
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
