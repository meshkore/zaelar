# zaelar — personal voice assistant, cerebro propio «Colmena» (nucleo/). Docs: README.md (install) + .meshkore/docs/.
PY=./.venv/bin/python

.PHONY: help run run-nucleo run-lk lk-server agent-worker stop down sim smoke test test-widgets install-livekit install-stt install-tts install-whatsapp install-telegram reset reset-dry reset-restart flash flash-repl flash-serve doctor

help:
	@echo "zaelar targets:"
	@echo "  make run            - run the voice app locally (http://localhost:43917) — cerebro «Colmena» (nucleo)"
	@echo "  make stop           - PARA todo (server+LiveKit+workers) y DESCARGA los modelos Ollama (ahorra batería). Alias: make down"
	@echo "  make sim            - run the bot-vs-bot reasoning simulator + judge (all personas)"
	@echo "  make smoke          - quick single-persona sim (no judge)"
	@echo "  make test           - import/health checks (no real voice; safe to run in CI)"
	@echo "  make test-widgets   - per-widget harness: contract + view_data golden shape + widget.js parse"
	@echo "  make install-livekit- install the native LiveKit server binary (so 'make run' needs NO Docker)"
	@echo "  make install-stt    - install FREE LOCAL speech-to-text (Whisper) — private, no per-use cost"
	@echo "  make install-tts    - install FREE LOCAL text-to-speech (Kokoro) — private (default stays Aura-2)"
	@echo "  make install-whatsapp - one-time: install the vendored WhatsApp bridge deps (INI-014; WA_ENABLED=1 in .env)"
	@echo "  make install-telegram - one-time: install the Telegram userbot deps (telethon+segno) (INI-015; TG_ENABLED=1 in .env)"
	@echo "  make reset-restart  - borra la MEMORIA HUMANA + observabilidad (conserva credenciales/auth/cookies) y RE-ARRANCA de cero"
	@echo "  make reset          - solo borra la memoria humana (no arranca); 'make reset-dry' = ver qué haría sin tocar nada"
	@echo "  make doctor         - analiza el sistema (hardware/Ollama/claude/keys) → informe para el wizard de config (V2-040)"
	@echo "  make flash-serve    - server HEADLESS (sin voz/navegador) para el CANAL DE PRUEBA del FlashBrain (POST /api/flash/say)"
	@echo "  make flash T=\"...\"   - inyecta UN turno de texto al FlashBrain y muestra respuesta+acción+latencia (server ya arrancado)"
	@echo "  make flash-repl     - conversación interactiva por texto con el FlashBrain (3ª forma de testing, V2-032)"

# Voice app on LiveKit (INI-012): servidor LiveKit (binario NATIVO, sin Docker) + web con worker EMBEBIDO.
# Docker es solo fallback si no está el binario → `make install-livekit`.
# Cerebro = «Colmena» PROPIO (BRAIN=nucleo, EPIC-v2-colmena): FlashBrain (nucleo/) + memoria central + SlowBrain,
# SIN Hermes. Modelo rápido POR INVOCACIÓN (config/v2, gestionado por la UI).
run:
	BRAIN=nucleo bash scripts/run-livekit.sh

# Alias explícito de `make run` (mismo cerebro nucleo).
run-nucleo:
	BRAIN=nucleo bash scripts/run-livekit.sh

# Alias explícito del stack LiveKit (BRAIN=nucleo por defecto; override con BRAIN=…).
run-lk:
	BRAIN=$(or $(BRAIN),nucleo) bash scripts/run-livekit.sh

# PARAR todo + DESCARGAR modelos Ollama (ahorra batería). No toca credenciales/memoria/datos. Vuelve con `make run`.
# La frontera exacta (qué procesos para / qué modelos descarga) vive en scripts/stop.sh (auto-documentado).
stop down:
	bash scripts/stop.sh

# RESET DE MEMORIA HUMANA (empezar un test de cero). Borra SOLO la memoria humana (zaelar.db + episódica + stores de
# widgets/mensajes) Y la observabilidad (timeline + sesiones + el log durable de eventos que vive en zaelar.db), y
# CONSERVA credenciales/auth/cookies (WhatsApp/Telegram/Wallapop/cluster) para no re-autenticar en cada prueba.
# La frontera exacta (qué se borra / qué se conserva) vive en scripts/reset-memory.sh (auto-documentado).
reset:
	bash scripts/reset-memory.sh
# Ver qué borraría/conservaría SIN tocar nada.
reset-dry:
	bash scripts/reset-memory.sh --dry-run
# Reset + re-arranque LIMPIO del stack (como 'make run'): memoria a cero, credenciales intactas, log de eventos a cero.
reset-restart:
	bash scripts/reset-memory.sh --yes && BRAIN=nucleo bash scripts/run-livekit.sh

# ── DETECTOR de capacidades / informe del sistema (V2-040) ────────────────────────────────────────────────
# Evalúa la máquina (hardware, Ollama+modelos, claude CLI, livekit, chromium, deps, credenciales) y escribe el
# informe a .meshkore/logs/system-report.json — el WIZARD web lo lee para pre-configurar el perfil y detectar huecos.
# Úsalo al instalar o cuando cambie el entorno.  Detalle: initiatives/V2-040-perfiles-wizard-config.md
doctor:
	@$(PY) -m config.doctor

# ── CANAL DE PRUEBA HEADLESS del FlashBrain (V2-032, 3ª forma de testing) ──────────────────────────────────
# Inyecta texto y lee la respuesta SIN voz/interfaz/sala LiveKit → iteración rapidísima desde Claude Code.
# Flujo típico:  make reset  (memoria+observabilidad a cero)  →  make flash-serve  (en otra terminal)  →
#                make flash T="hola, ¿cómo te llamas?"   ó   make flash-repl
# `flash-serve` levanta SOLO el server (lifespan: memoria/bus/estado/prompt), sin navegador de búsqueda ni
# necesidad de livekit-server (la voz no se usa en este canal). El endpoint /api/flash/say vive en ese proceso.
flash-serve:
	BRAIN=nucleo ZAELAR_ENGINE=livekit BROWSER_SEARCH=0 ZAELAR_PREWARM=0 $(PY) -m server

# One-shot: inyecta un turno. Uso: make flash T="me llamo Alex y vivo en Soria"
flash:
	@$(PY) -m nucleo.flash.probe $(T)

# REPL interactivo (Ctrl-D para salir; /reset limpia la ventana de conversación del probe).
flash-repl:
	@$(PY) -m nucleo.flash.probe

# Solo el servidor LiveKit dev (para depurar el worker a mano contra él). Binario NATIVO si está; Docker si no.
lk-server:
	@if command -v livekit-server >/dev/null 2>&1; then \
	  echo "▶ livekit-server nativo (sin Docker)"; \
	  livekit-server --dev --bind 127.0.0.1 --node-ip=127.0.0.1; \
	else \
	  echo "▶ livekit-server vía Docker (fallback; 'make install-livekit' para evitarlo)"; \
	  docker rm -f zaelar-livekit >/dev/null 2>&1 || true; \
	  docker run --rm --name zaelar-livekit -p 7880:7880 -p 7881:7881 -p 7882:7882/udp \
	    livekit/livekit-server --dev --bind 0.0.0.0 --node-ip=127.0.0.1; \
	fi

# Native LiveKit server binary → 'make run' no necesita Docker. macOS: brew · Linux: get.livekit.io · Win: releases.
install-livekit:
	@if command -v brew >/dev/null 2>&1; then brew install livekit; \
	elif [ "$$(uname)" = "Linux" ]; then curl -sSL https://get.livekit.io | bash; \
	else echo "Windows: descarga livekit-server de https://github.com/livekit/livekit/releases y ponlo en el PATH"; fi
	@livekit-server --version 2>/dev/null || echo "instala el binario y verifica con: livekit-server --version"

# Solo el agent worker (asume un servidor LiveKit ya arriba en ws://127.0.0.1:7880).
agent-worker:
	$(PY) -m voice.engine.pipeline.agent dev

sim:
	$(PY) harness/run.py

smoke:
	$(PY) harness/run.py skeptic 3

# Per-widget harness: contract gate + golden view_data() shape + ES-module parse (widgets/harness.py).
test-widgets:
	$(PY) -m widgets.harness

# Import/health check: builds the FastAPI app + the assistant prompt without doing real I/O.
test:
	$(PY) -c "import sys; sys.path.insert(0,'.'); import server; from voice.prompt import build_system_prompt; \
	assert server.app.title=='zaelar'; assert 'zaelar' in build_system_prompt().lower(); print('OK zaelar imports + prompt')"

# FREE LOCAL speech-to-text (faster-whisper). After this, STT_PROVIDER=auto runs 100% on-device (private, free).
install-stt:
	bash scripts/install-stt-mac.sh   # Windows: ./scripts/install-stt-win.ps1 (PowerShell)

# FREE LOCAL text-to-speech (Kokoro). Optional — the default TTS is Aura-2 (better es+en codeswitching).
install-tts:
	bash scripts/install-tts-mac.sh   # Windows: ./scripts/install-tts-win.ps1 (PowerShell)

# WhatsApp triage connector (INI-014): one-time install of the VENDORED Baileys bridge's Node deps. After this,
# set WA_ENABLED=1 in .env and `make run` starts everything (the server spawns the bridge as a child process —
# no separate command). `make run` also self-heals this install if node_modules is missing.
install-whatsapp:
	cd connectors/whatsapp/bridge && npm install
	@echo "✅ WhatsApp bridge listo. Pon WA_ENABLED=1 en .env y arranca con 'make run' → di 'muéstrame WhatsApp'."

# Telegram triage connector (INI-015): one-time install of the userbot deps (Telethon + segno for the QR). Telegram
# is a PURE-PYTHON in-process connector (no Node bridge). After this, get TG_API_ID/TG_API_HASH from
# my.telegram.org, set them + TG_ENABLED=1 in .env, and `make run` starts everything (the server spawns the userbot
# task — no separate command). The service also self-heals this install if the deps are missing at boot.
install-telegram:
	$(PY) -m pip install telethon segno
	@echo "✅ Telegram listo. Pon TG_API_ID/TG_API_HASH (de my.telegram.org) y TG_ENABLED=1 en .env, arranca con 'make run' → di 'muéstrame mensajes' y escanea el QR."
