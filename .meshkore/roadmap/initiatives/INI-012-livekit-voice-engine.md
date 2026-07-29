---
id: INI-012
title: Migración del motor de voz Pipecat → LiveKit Agents
status: done
owner: ricart
modules: [voice, brains, server, frontend, config]
updated: 2026-07-06
---

## Goal

Reemplazar el motor de voz actual (Pipecat `SmallWebRTCTransport`, VAD en navegador, TurnBroker/TurnGate,
brains como `FrameProcessor`) por el motor validado en el repo **voice-lab-2** (LiveKit Agents 1.6.4, ver su tag
`v2.0`): `AgentSession` que es dueña de streaming, turnos, VAD, barge-in y *preemptive generation*, con un
registry limpio de providers y perfiles `remote`/`local`. El motor nuevo da mejor latencia y turn-taking; zaelar
aporta todo el producto (brain Hermes/duo, widgets, conectores, frontend, proactividad, cron).

## Dirección elegida (estudio previo)

**zaelar es la casa; el motor LiveKit entra en zaelar.** NO se mueve zaelar dentro de voice-lab-2. Razón: el
producto pesa ~10× el motor y zaelar ya aísla el motor tras seams estables (un `*LLMProcessor` por brain,
`tag_protocol`/`speech`/`brain_notes`/`proactive` puros y portables, widgets/conectores agnósticos del transporte,
frontend con ~2/3 UI portable y el acoplamiento de voz concentrado en ~6 ficheros). Ambas direcciones convergen en
el mismo estado final; ésta preserva estructura MeshKore, docs, deploy e historial.

## Decisiones / defaults tomados (autónomo, go-ahead 2026-07-06)

- **Infra LiveKit**: servidor **self-hosted en Docker `--dev`** (mismo patrón que voice-lab-2 `scripts/run.sh`),
  no LiveKit Cloud. En prod se cambia el `--dev` por servidor configurado o Cloud (se documentará en deploy).
- **Topología de procesos**: 3 procesos como voice-lab-2 — (1) servidor LiveKit (Docker), (2) *agent worker*
  (`python -m voice.engine.agent dev`), (3) servidor web zaelar (FastAPI: tokens + UI + routers de producto).
- **Seam del brain**: Hermes/duo se exponen como un **provider `livekit.agents.llm.LLM` en streaming** (registrado
  en el registry portado), NO como `FrameProcessor`. La lógica del `HermesLLMProcessor` (drain de `brain_notes`,
  `turn_lock` compartido con cluster, `strip_tags` → side-effects widget/cluster/cron/architect, `speech.inline`,
  clasificación control/error, salud, barge-in→`acp.cancel()`) migra al `LLMStream._run()`.
- **Turn-taking**: por defecto se adopta el **turn-taking nativo de LiveKit** (VAD Silero + MultilingualModel +
  timers de AgentSession + `allow_interruptions`). `voice/endpointing.py` (lógica pura, con tests) se conserva en
  el repo como referencia/fallback; no se re-cablea en la primera pasada. Riesgo consciente: perder el
  comportamiento afinado de INI-009 (retención dinámica, barge-in por voz sostenida ≥800ms). Se re-evalúa tras la
  prueba de voz en vivo; si degrada la UX, se re-expresa `endpointing.py` sobre hooks de LiveKit.
- **`voice/observer.emit`** se extrae de su dependencia de Pipecat (hoy `voice/observer.py` importa frames Pipecat)
  a un módulo sin Pipecat, para que widgets/conectores/brain no arrastren Pipecat por import. El canal SSE
  `/events` hacia el frontend se mantiene idéntico.
- **Frontend**: `session.js` se reescribe como adaptador del **LiveKit client SDK** que escribe las MISMAS señales
  del store; se borran VAD/STT de navegador (`frontend/vad/*`, ~16MB) porque LiveKit los provee; el visualizer se
  re-alimenta de los tracks de LiveKit. Todo lo demás (widgets, chat, tema `--hb-*`, paneles) intacto.
- **Providers**: se portan los de voice-lab-2 (STT voxtral/deepgram/whisper; TTS cartesia/kokoro; LLM
  aimlapi/openai/gemini/glm/claude/local) + los nuevos `hermes`/`duo`. Se mantiene la regla dura **solo modelos
  NO-razonadores en la ruta de voz**.

## Estado / fases

- [x] Punto de partida limpio y revertible: voice-lab-2 tag `v2.0`; zaelar baseline commiteado, tag `pre-livekit`,
      rama `feat/livekit-migration` (main intacto). Reversión: `git checkout main && git reset --hard pre-livekit`.
- [x] Infra + deps (livekit-agents 1.6.4 + plugins INSTALADOS en el .venv, Makefile `run-lk`/`lk-server`, `run-livekit.sh`).
- [x] Motor portado a `voice/engine/` (registry, perfiles, providers, AgentSession, `make_server()` embebible). Import OK.
- [x] Providers del brain hermes/duo/direct como `llm.LLM` streaming + `runtime.locked_ask()` (turno serializado
      loop-agnóstico). Import OK; `BRAIN=hermes→HermesLLM`, `BRAIN=duo→DuoLLM`.
- [x] Servidor: `/api/token` + `/api/livekit`; worker EMBEBIDO en el lifespan (AgentServer THREAD) tras
      `ZAELAR_ENGINE=livekit`; brief de capacidades + speaker proactivo en la entrypoint. Build OK ambos modos.
- [x] Frontend: `session-lk.js` (adaptador LiveKit client, misma interfaz) + SDK vendorizado; switch sin build
      (server sirve session-lk.js en la URL de session.js en modo livekit). `node --check` OK.
- [ ] **PENDIENTE (requiere entorno del operador): prueba de voz en vivo** — `make run-lk` (Docker LiveKit + mic +
      claves), hablar, validar latencia/barge-in/turnos, widgets, brain. Es la aceptación real; solo el operador puede.
- [x] Wiring: handler del agente para texto de chat por data channel (`data_received` → `generate_reply`); emit de
      `transcript`/`bot_speech`→SSE en la entrypoint (para voiceCommands/chat wall/orb). A validar en vivo.
- [ ] Ítems conocidos (arreglar tras la prueba en vivo):
      · `/api/status` "Sistema de voz" usa `active.count()` (era Pipecat); el worker embebido de LiveKit no se
        registra ahí → puede mostrar "en espera" durante una llamada real. Cablear un contador de sesión vivo.
      · `/api/test-voice` (audición de voz en el ⚙) devuelve 501 — falta implementar síntesis de muestra sobre
        los plugins TTS de LiveKit.
      · Cambio de voz aplica en reconexión (SETTINGS del motor es frozen a import); revisar si conviene hot-reload.
- [ ] Post-aceptación: turn-taking eval (¿nativo LiveKit vs `endpointing.py`?), retirar Pipecat (resolver conflicto
      onnxruntime), docs sync (CLAUDE/README/cluster/arquitectura) + bump de versión, merge a main.

## Estado a 2026-07-06 (fin de la sesión de construcción)

TODO el código de la migración está escrito y commiteado en `feat/livekit-migration` (4 commits sobre el baseline),
verificado a nivel de **import/build/sintaxis** en el venv de zaelar. NO verificado en runtime: el bucle de voz en
tiempo real necesita servidor LiveKit (Docker) + micro + navegador + claves, que valida el operador. `main` intacto.

Nota entorno: instalar livekit subió `onnxruntime` a 1.27 (Pipecat pedía 1.24.3). El camino Pipecat legacy (`make run`)
sigue importando, pero si diera problemas de VAD/turn, ese conflicto es la causa — se resuelve al retirar Pipecat.

## Upgrade heredado de voice-lab-2 (2026-07-06, réplica de `local`@30725e6)

voice-lab-2 (rama `local`, baseline `v1.0-remote`) recibió 4 mejoras de VELOCIDAD/FIABILIDAD/PRECISIÓN del STT
local. Se heredan en zaelar **de forma aditiva** (sin tocar la lógica STT/LLM/TTS/VAD/turnos), adaptadas a las
convenciones de zaelar (prefijo `ZAELAR_*`, inglés, worker EMBEBIDO `AgentServer`/`rtc_session` en vez de
`cli.run_app(WorkerOptions)`):

- **STT local hardware-adaptativo** (`voice/engine/core/accel.py` NUEVO + `speech/stt/whisper_local.py`): detecta el
  hardware al arrancar y elige el backend más rápido con fallback — **metal** (Apple Silicon, `mlx-whisper
  large-v3-turbo`, ~0.15s) → **cuda** (NVIDIA, faster-whisper float16) → **cpu** (faster-whisper int8, universal).
  Override: `ZAELAR_WHISPER_DEVICE=auto|metal|cuda|cpu`. `RESOLVED_DEVICE` se expone en `/api/livekit` (`sttDevice`) +
  log + evento `worker_start`. AMD/ROCm → CPU (hueco a PR).
- **Anti-alucinación de Whisper sin cambiar de modelo**: GATE de energía/duración ANTES de transcribir
  (`ZAELAR_STT_RMS_GATE=0.012`, `ZAELAR_STT_MIN_SEC=0.25`) — mata el "Thank you" fantasma en silencio/ruido (Whisper
  alucina con `no_speech_prob=0`, confiado; solo la ENERGÍA lo caza) — + decodificación anti-bucle
  (`condition_on_previous_text=False`, `temperature=0`, thresholds no_speech/logprob/compression, `initial_prompt` EN).
  Verificado en Mac: silencio→`''`, voz real→transcripción correcta ("Go ahead, what's the weather doing today?").
- **Arranque de agente rápido**: `prewarm`/`setup_fnc` ahora carga el modelo Whisper (executor idle) y el `entrypoint`
  lo reutiliza (`ctx.proc.userdata["stt"]`); `make_server` fija `num_idle_processes=1` + `initialize_process_timeout=90`
  → executor caliente esperando (la `ProcPool` calienta también el executor THREAD).
- **Sala única por sesión + aislamiento** (`server/livekit_api.py` + `pipeline/agent.py`): `/api/token` acuña
  `zaelar-<uuid>` por conexión (un agente zombi que tarda en drenar ya no bloquea el dispatch del siguiente) e
  identidad única; el worker acepta SOLO salas con prefijo `SETTINGS.room_name` vía `on_request=request_fnc` (si zaelar
  y voice-lab-2 comparten el LiveKit dev local, ningún worker roba las salas del otro). El front y el tester (INI-013)
  ya toman la sala del token, así que son compatibles sin cambios.
- **instrument**: consume la excepción del `publish_data` al cerrar (silencia "Task exception was never retrieved");
  `config(**extra)` lleva `sttDevice` al contrato de la UI de debug.

Deps nuevas (`requirements.txt`, con markers → multiplataforma): `mlx-whisper>=0.4` (solo Apple Silicon arm64),
`psutil>=5.9`. `faster-whisper` ya estaba. Verificado import/build/`make_server`/detección `metal` + transcripción
real en el venv de zaelar. Sigue **pendiente** la aceptación de voz en vivo por el operador.

### TTS local por Metal (réplica de `local`@03aed8c, 2026-07-06)

Fix de latencia del TTS local (la regresión de los "3-4s"): en Apple Silicon el TTS Kokoro corre **in-process por
Metal** (`mlx-audio`, `ZAELAR_TTS_DEVICE=auto|metal|fastapi`, `ZAELAR_KOKORO_MLX_MODEL=mlx-community/Kokoro-82M-bf16`)
→ ~0.3s al primer audio (era ~1-2s en Docker/CPU). `prewarm`/`setup_fnc` carga también el modelo Metal en el executor
idle y el `entrypoint` lo reutiliza (`ctx.proc.userdata["tts"]`). mlx-audio tiene un **bug de shapes en su vocoder**
que revienta algunas frases (peor en español, ~1/4 en mis pruebas; ~1/6 en voice-lab-2) → `try/except` con **fallback
por-frase a Kokoro-FastAPI**; el warm es resiliente (una frase mala no desactiva Metal). ⚠️ El fallback exige
Kokoro-FastAPI (Docker/CPU) corriendo; sin él esas frases quedan mudas. Deps (markers Apple Silicon): `mlx-audio`,
`misaki[en]` (G2P inglés: num2words+spacy), `phonemizer-fork`, `espeakng-loader` + `brew install espeak-ng`.

### Multidioma con catálogo alineado (2026-07-06, a petición del operador)

zaelar pasa a ser **multilingüe con default castellano** (antes era inglés). Nuevo `voice/engine/core/langs.py` =
**catálogo único** de idiomas soportados (`LangSpec`: kokoro_lang, whisper_prompt, reply_directive, voces Kokoro
nativas + default). Regla dura: **la voz nunca cruza el idioma** — `voices.selected_voice()` valida la voz contra el
idioma activo (una voz es Kokoro es rechazada en pipeline en → cae al default en), Cartesia es multilingüe (una voz +
`language`). Todo el motor (whisper/voxtral/deepgram/cartesia/kokoro/agent) lee `langs.current_code()` **live** (env
`ZAELAR_LANGUAGE`, que el ⚙ escribe en caliente) → un cambio de idioma aplica **al reconectar**, y re-alinea STT + voz
TTS + directiva de idioma del brain a la vez. El ⚙ deriva la lista de idiomas del catálogo y, al cambiar de idioma,
realínea la voz Kokoro persistida. Hoy **es + en** con voces verificadas en Metal (es: ef_dora/em_alex/em_santa,
default ef_dora; en: af_bella/af_nicole/am_michael/am_adam, default af_bella — `af_heart` descartada como default por
disparar el bug de shapes). Añadir un idioma (de/fr/…) = una entrada `LangSpec` con su voz nativa verificada.
Verificado: switch es⇄en cambia lang_code + voz + prompt, guard anti-poisoning (em_alex rechazada en en), Metal es 3/4
y en 4/4 por proceso, y el ⚙ realínea la voz al cambiar idioma. Pendiente: switch **por voz** (tag `[[lang:xx]]` →
persistir + reconectar) — groundwork listo (persistencia+realineado ya existen); falta el tag en el brain + señal de
reconexión al front.

### Core SIN Docker (2026-07-06, a petición del operador)

El operador no quiere que el **core** de zaelar dependa de Docker (le da problemas/cuelgues + carga de despliegue). El
único uso de Docker en el core era el servidor LiveKit dev. Ahora corre desde el **binario nativo `livekit-server`**
(`brew install livekit` / `curl -sSL https://get.livekit.io | bash` / release de GitHub en Windows; `make
install-livekit`). `scripts/run-livekit.sh` y `make lk-server` **prefieren el binario nativo** y solo caen a `docker
run` si no está. Verificado: `livekit-server --dev` nativo arranca en ws://127.0.0.1:7880 y `make run` (BRAIN=direct)
levanta el stack completo **sin crear ningún contenedor**. zaelar no usa Docker para sandboxing (el canal de cluster
usa controles duros "tools denegadas", no contenedores). El **tester (INI-013) SÍ puede usar Docker** (su LiveKit
dedicado, aislamiento, scraping) — es la única parte donde Docker es aceptable.

## Testing (acordado 2026-07-06 — a la espera de la spec del operador)

Lo que hay: `make test` (integrity/health), `harness/` bot-vs-bot + juez (cerebro a nivel de TEXTO, sin audio).
Falta y se hará: un **agente de audio de prueba** — 2º participante LiveKit que HABLA guiones (TTS) y ESCUCHA
(STT) a zaelar por el stack real; reutiliza la infra de providers del motor. Dimensiones a evaluar (las 4, por
decisión del operador): **latencia** (ttft/ttfb de las métricas LiveKit), **turn-taking/barge-in** (pausa no corta,
voz sostenida sí, backchannels ignorados — INI-009), **cerebro+widgets** (correcciones, memoria Hermes, disparo de
tags/widgets), **robustez** (reconexión, sesiones largas, degradación de provider, multi-turno).
Estado: **el operador prepara la spec de cómo montarlo**; no scaffoldear hasta entonces.

## Aceptación

La migración NO se da por "terminada" hasta que el operador hable con zaelar sobre el motor LiveKit con latencia
aceptable, barge-in y turn-taking correctos, y con widgets/brain/conectores funcionando. Ese último paso requiere
hardware (micro) + Docker + claves y lo valida el operador.
