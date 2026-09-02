# zaelar — personal voice assistant. FastAPI + LiveKit Agents (INI-012), cerebro propio «Colmena» (BRAIN=nucleo).
# Build from the repo root:  docker build -t zaelar .
#
# PERFIL EN LA NUBE (V2-040): esta imagen Linux x86 NO trae las rutas de modelo LOCAL (mlx Metal es darwin-only
# y se salta en el pip install; no hay Ollama ni binario livekit-server). SÍ trae (desde 2026-08-05) el **CLI de
# Claude Code** (brain workers) y el **Chromium de Playwright** (navegador) para que cloud tenga la MISMA
# capacidad que local. El deploy corre con el **perfil `cloud`**: STT/TTS/cerebro/memoria por proveedores de nube
# (claves como secretos de Fly: AIMLAPI_KEY para la memoria —CORAZÓN de escritura Y sueño REM, ambos por AIMLAPI
# desde 2026-08-09—, Z_AI_API_KEY para los workers, etc.).
FROM python:3.12-slim

# System deps: ffmpeg/libsndfile for aiortc (WebRTC) + resampling; build tools for pyrnnoise.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first (layer cache).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOTE — baking the ONNX models (fastembed embedding + jina reranker) into the image was TRIED here
# 2026-08-05 to kill the per-boot HuggingFace download, but the RUN step did NOT persist on Fly's
# remote builder (the model download didn't survive into the image layer — verified: /root/.cache is
# empty on the resulting image, while the SAME download works fine at runtime). So it's left OUT rather
# than shipped as a silently-failing `|| true` no-op. The per-boot download is already neutralized for
# the demo where it mattered: demo/pool machines run MEMORY_RERANK=off (so the 1.1GB reranker is never
# loaded — see cloud/provisioner/src/machineConfig.js) and the small embedding download is hidden by
# the pre-booted warm pool. FOLLOW-UP for real paying accounts (which keep the reranker ON): bake via a
# LOCAL build (`flyctl deploy --local-only`, where the builder has normal network) or cache the models
# on the per-account Fly Volume so they download once, not per boot.

# CLAUDE CODE CLI + CHROMIUM — the two runtime engines the cloud image was missing (2026-08-05). The
# brain workers (nucleo/workers/) DRIVE the `claude` CLI, and the navegador widget drives a real
# headless Chromium via Playwright; without these in the image, cloud could only do voice — no brain
# workers, no web browsing. Node 20 (NodeSource) provides `claude`; workers point it at Z.ai via
# ANTHROPIC_BASE_URL/AUTH_TOKEN (resolved from CODE_AGENT_BASE_URL + the Z_AI_API_KEY secret, injected
# per machine — see cloud/provisioner/src/machineConfig.js). Then Playwright's Chromium + its OS deps.
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update \
    && python -m playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# App code — one COPY per domain package (no .venv/.env/logs/harness — see .dockerignore). Módulos VIVOS del
# estándar (cluster.yaml): el cerebro «Colmena» (nucleo/), la memoria central (memory/), el bus (bus/) y los
# conectores. `brains/` YA NO EXISTE (Hermes retirado, V2-009) — copiarlo reventaba el build.
COPY server ./server
COPY voice ./voice
COPY nucleo ./nucleo
COPY memory ./memory
COPY bus ./bus
COPY connectors ./connectors
COPY widgets ./widgets
COPY config ./config
COPY frontend ./frontend
COPY i18n ./i18n
COPY observability ./observability
# update/ (V2-553) — the update channel. It carries `update/BUILD`, the ONE version number a user is
# ever shown, and this COPY is the only way that number reaches production: there is no `.git` inside
# the image, so `version.sha()` is "nogit" here and the file is the sole surviving source of truth.
COPY update ./update
# Root-level modules the packages import (NOT part of any package dir). version.py backs /api/status +
# the observer's per-event `ver` stamp; without it the engine ran but the Status panel showed "No
# module named 'version'" (found live 2026-08-05). Only ship RUNTIME root modules here — conftest.py is
# pytest-only and must stay out.
COPY version.py .
# ⚠️ These COPYs are BY NAME — every top-level runtime package must be listed here, or the image
# ships without it and the engine crash-loops on boot (ModuleNotFoundError). This bit us on
# 2026-08-04: V2-089 added the `i18n/` package + `server/i18n_api.py` (imported unconditionally by
# server/__init__.py) but nobody added `COPY i18n` here → the whole cloud demo crash-looped
# "No module named 'i18n'" for days. When you add a new top-level module, add its COPY here.

ENV HOST=0.0.0.0 \
    PORT=8080 \
    BRAIN=nucleo \
    ZAELAR_ENGINE=livekit \
    ZAELAR_PROFILE=remote \
    DEPLOY_ENV="fly·cdg"
# NOTE (found 2026-07-24, INI-018): `ZAELAR_PROFILE=cloud` was the default here before, but
# voice/engine/core/profile.py only recognizes "remote"/"local" (a DIFFERENT, lower-level profile
# system than config/profiles.py's UI-facing "local"/"cloud" package, which explicitly translates
# "cloud" → engine_profile "remote"). "cloud" silently fell back to profile.py's "remote" defaults
# anyway (voxtral/cartesia/aimlapi) — same practical effect, but "remote" is what this layer
# actually understands; fixed for clarity, not because behavior changed.
EXPOSE 8080

# Keys (DEEPGRAM/AIMLAPI/...) + CF_TURN_* + WEBRTC_HOST are injected as Fly secrets (see fly.toml / deploy).
CMD ["python", "-m", "server"]
