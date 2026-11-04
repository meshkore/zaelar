# zaelar — personal voice assistant. FastAPI + LiveKit Agents, cerebro propio «Colmena» (BRAIN=nucleo).
# Build from the repo root:  docker build -t zaelar .
#
# CLOUD PROFILE: this Linux x86 image does NOT carry the LOCAL model routes (mlx Metal is darwin-only and is
# skipped by pip; no Ollama, no livekit-server binary). It DOES carry the Claude Code CLI (brain workers) and
# Playwright's Chromium (browser widget). It runs with the `cloud` profile: STT/TTS/brain/memory through cloud
# providers, with their API keys provided via environment variables.
FROM python:3.12-slim

# System deps: ffmpeg/libsndfile for aiortc (WebRTC) + resampling; build tools for pyrnnoise.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first (layer cache).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# NOTE — the ONNX models (fastembed embedding + jina reranker) are NOT baked into the image: they are
# downloaded at runtime on first use. Set MEMORY_RERANK=off to skip loading the ~1.1GB reranker, or mount a
# persistent volume over the model cache so they download once instead of per boot.

# CLAUDE CODE CLI + CHROMIUM — the brain workers (nucleo/workers/) drive the `claude` CLI, and the navegador
# widget drives a real headless Chromium via Playwright; without these the image could only do voice. Node 24
# (NodeSource) provides `claude`; workers can point it at an Anthropic-compatible endpoint via
# ANTHROPIC_BASE_URL/AUTH_TOKEN (resolved from CODE_AGENT_BASE_URL + the provider key in the environment).
# Then Playwright's Chromium + its OS deps.
# The CLI is PINNED: an unpinned `npm install` is frozen by the builder's layer cache at whatever version it first
# resolved (measured: an image built 2026-11-01 carried 2.1.197 while 2.1.318 was current), and nothing said so.
# A new version is a one-line bump here, which also invalidates that layer. The release procedure checks it.
# Inside the image the CLI never updates itself: what runs is what the image says (`version.components()`).
ARG CLAUDE_CODE_VERSION=2.1.318
ENV DISABLE_AUTOUPDATER=1
RUN apt-get update && apt-get install -y --no-install-recommends curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION} \
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
COPY search ./search
COPY rules ./rules
COPY files ./files
COPY memory ./memory
COPY bus ./bus
COPY connectors ./connectors
# The WhatsApp bridge's Node deps are installed HERE, at build time. Left to the runtime self-heal in
# connectors/whatsapp/bridge_proc.py, `npm install` ran inside the container and failed every time: two deps are
# pinned to git commits (`git+ssh://` in the lockfile) and the image had neither git nor an ssh key, so the bridge
# never started and the QR never appeared. `npm ci` against the lockfile, with GitHub's ssh URLs read as https;
# git leaves the image afterwards.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && git config --global url."https://github.com/".insteadOf "ssh://git@github.com/" \
    && cd connectors/whatsapp/bridge && npm ci --omit=dev && npm cache clean --force \
    && git config --global --unset-all url."https://github.com/".insteadOf \
    && apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
    && test -d node_modules/@whiskeysockets/baileys
COPY widgets ./widgets
COPY config ./config
COPY frontend ./frontend
COPY i18n ./i18n
COPY observability ./observability
COPY library ./library
# update/ (V2-553) — the update channel. It carries `update/BUILD`, the ONE version number a user is
# ever shown, and this COPY is the only way that number reaches production: there is no `.git` inside
# the image, so the commit only arrives as the ZAELAR_COMMIT build arg below.
COPY update ./update
# Root-level modules the packages import (NOT part of any package dir). version.py backs /api/status +
# the observer's per-event `ver` stamp; without it the engine ran but the Status panel showed "No
# module named 'version'" (found live 2026-08-05). Only ship RUNTIME root modules here — conftest.py is
# pytest-only and must stay out.
COPY version.py .
# THE COMMIT, baked at build time (V2-837 G1). There is no `.git` in the image, so without this every event said
# `bNN+nogit` and two images of one build number were indistinguishable. The builder passes it:
#   docker build --build-arg ZAELAR_COMMIT=$(git rev-parse --short HEAD) .
# `version.sha()` reads the ENV first; a self-host clone (no build arg) keeps reading its own repository.
ARG ZAELAR_COMMIT=""
ENV ZAELAR_COMMIT=${ZAELAR_COMMIT}
LABEL org.opencontainers.image.revision=${ZAELAR_COMMIT}
# ⚠️ These COPYs are BY NAME — every top-level runtime package must be listed here, or the image
# ships without it and the engine crash-loops on boot (ModuleNotFoundError) — e.g. a missing
# `COPY i18n` once crash-looped the image with "No module named 'i18n'". When you add a new top-level module, add its COPY here.

ENV HOST=0.0.0.0 \
    PORT=8080 \
    BRAIN=nucleo \
    ZAELAR_ENGINE=livekit \
    ZAELAR_PROFILE=remote \
    DEPLOY_ENV="fly·cdg"
# NOTE: `ZAELAR_PROFILE=cloud` was the default here before, but
# voice/engine/core/profile.py only recognizes "remote"/"local" (a DIFFERENT, lower-level profile
# system than config/profiles.py's UI-facing "local"/"cloud" package, which explicitly translates
# "cloud" → engine_profile "remote"). "cloud" silently fell back to profile.py's "remote" defaults
# anyway (voxtral/cartesia/aimlapi) — same practical effect, but "remote" is what this layer
# actually understands; fixed for clarity, not because behavior changed.
EXPOSE 8080

# Keys (DEEPGRAM/AIMLAPI/...) + CF_TURN_* + WEBRTC_HOST are provided via environment variables.
CMD ["python", "-m", "server"]
