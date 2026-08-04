# zaelar — personal voice assistant. FastAPI + LiveKit Agents (INI-012), cerebro propio «Colmena» (BRAIN=nucleo).
# Build from the repo root:  docker build -t zaelar .
#
# PERFIL EN LA NUBE (V2-040): esta imagen Linux x86 NO trae las rutas de modelo LOCAL (mlx Metal es darwin-only y
# se salta en el pip install; no hay Ollama, ni binario livekit-server, ni Chromium de Playwright, ni el CLI de
# Claude). El deploy corre con el **perfil `cloud`**: STT/TTS/cerebro/memoria por proveedores de nube (claves como
# secretos de Fly). Para el navegador/Ollama en la nube habría que añadir esas piezas a la imagen aparte.
FROM python:3.12-slim

# System deps: ffmpeg/libsndfile for aiortc (WebRTC) + resampling; build tools for pyrnnoise.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg libsndfile1 ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first (layer cache).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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
