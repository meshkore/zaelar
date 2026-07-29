# V2-040 — Perfiles LOCAL/CLOUD coordinados + WIZARD de primer arranque (config "sin tocar código", listo para deploy)

**Origen (operador, 2026-07-15):** «ha llegado la hora de ver todo esto bien organizado». Pensando en un **deploy en
la nube** (que exige configurar todas las piezas externas) y a la vez conservar el **perfil local** (Ollama + voz
local). Quiere **2 perfiles por defecto**, que **todo sea configurable sin afectar al código**, y un **wizard de
primer arranque** que evalúe el sistema, detecte qué se puede usar y ofrezca instalar lo que falte (o dar el comando).

## Diagnóstico (survey de 3 agentes, 2026-07-15)

Las **bases ya son correctas**: casi toda la config resuelve **store JSON (lo escribe la UI) → env (fallback) →
default en código**, con secretos redactados a `<clave>_set` y subsistemas provider-swappable y **fail-open**. No hay
que rearquitecturar; hay que **UNIFICAR y EXPONER**.

El problema real: **"local vs cloud" son HOY tres interruptores desconectados**:
1. `voice/engine/core/profile.py` — `ZAELAR_PROFILE=remote|local` ya existe, pero SOLO fija STT/TTS/LLM del motor de
   voz, y solo como defaults (el override por-componente gana → hybrids). Congelado en el import (cambiar = reinicio).
2. `config/v2.py` — routing del cerebro + **memoria** (embedding/rerank/mem-processor), con SUS PROPIOS defaults
   local/auto/cloud, independientes de `ZAELAR_PROFILE`.
3. `config/settings.py` — el ⚙ escribe `ZAELAR_STT/TTS/LANGUAGE/ATTENTION` a env en el arranque; NO toca el perfil
   ni el proveedor de LLM.

→ Elegir "local" hoy fija la voz pero deja embeddings/rerank/CORAZÓN/FlashBrain donde estuvieran. No hay **una sola
palanca**, ni **paquete con nombre** que un wizard pueda aplicar, ni un **JSON default** que siembre el primer
arranque (los módulos arrancan de sus defaults en código). ~150 variables de entorno inventariadas.

**Los failovers YA están bien** (fail-open, se conservan): websearch por capas según key (Perplexity→Tavily→Brave→
Google-Chromium gratis→DDG) · embeddings (ollama `embeddinggemma`→fastembed→hash) · reranker (jina local CPU→OpenAI)
· STT (metal→cuda→cpu) · TTS (Kokoro Metal→onnx CPU→FastAPI, nunca mudo) · FlashBrain (NO es failover automático: es
elección de config `fast.provider`; ante fallo habla una frase de reserva, no cambia de proveedor).

**Defectos independientes hallados (a corregir):**
- **El deploy cloud está ROTO hoy**: el `Dockerfile` copia `brains/` pero NO `nucleo/` ni `memory/`, aunque el doc de
  deploy dice que el contenedor corre `BRAIN=nucleo`. La imagen no puede arrancar el cerebro actual.
- **Nombres de STT divergen**: docs/`.env.example` anuncian `STT_PROVIDER=auto|whisper|browser|deepgram|groq|aiml`,
  pero el registro vivo del motor solo conoce `voxtral|deepgram|whisper_local` (los demás son legado Hermes).
- **`ZAELAR_PROFILE` desconocido degrada en SILENCIO a `remote`** (una errata pasa sin aviso).

## Decisiones del operador (2026-07-15)

- **Superficie = WEB + script de sistema.** Un comando Python/Makefile genera un **informe del sistema** (fichero)
  que la web LEE. Como el server es LOCAL, un **botón en la web puede RE-EJECUTAR** el detector. El wizard **valida
  la config ANTES de dar acceso**: las credenciales que YA tenemos aparecen puestas; las que falten, se piden.
- **Instalación = automática en la medida de lo posible.** Un clic desde el navegador para lo acotado al proyecto
  (`pip`, `playwright install chromium`, `ollama pull <modelo>`); si los permisos del SO lo impiden (Windows/Mac),
  se dan los **comandos para copiar/pegar**. «Simplificar la vida al usuario.»

## Diseño

### 1. `config/profiles.py` — el perfil como concepto COORDINADO (una sola palanca)
Resolver: nombre de perfil → set COMPLETO de defaults coordinados a través de los 3 ejes (motor de voz + routing v2 +
memoria embed/rerank/mem-processor). Aplica un **patch coordinado** a los stores (`v2.py` + `settings.py`) y fija
`ZAELAR_PROFILE`. El override por-componente sigue ganando (hybrids intactos). Dos perfiles de fábrica:
- **`local`** — whisper_local + kokoro_local + FlashBrain Ollama + embeddings Ollama + rerank local + CORAZÓN local.
  Cero keys de nube para voz/memoria. (El CodeAgent del SlowBrain = `claude` CLI, sigue necesitando su key → línea
  aparte en el wizard.)
- **`cloud`** — voxtral/deepgram + cartesia/elevenlabs + FlashBrain AIMLAPI + embed/rerank/proc en nube. Solo keys,
  sin modelos locales. **= objetivo del deploy.** (`remote` queda como ALIAS de `cloud` por compatibilidad.)

### 2. `config/doctor.py` — detector de capacidades (compartido web+CLI)
Reusa `voice/engine/core/accel.detect()` + sondas: tipo de host (Apple Silicon / Linux / contenedor), Ollama
accesible + modelos presentes, `claude` CLI en PATH, binario `livekit-server`, Chromium de Playwright, y qué keys
están puestas (del credential store, redactadas). Escribe un **informe JSON** a una ruta conocida y lo imprime.
CLI: `python -m config.doctor`. Recomienda perfil (Apple Silicon + Ollama → `local`; si no → `cloud`).

### 3. Escritor del credential store (NUEVO, sensible)
Hoy `.meshkore/credentials/zaelar.env` solo se LEE (`server/common.py`). El wizard necesita ESCRIBIR keys ahí
(gitignored, chmod 600). Módulo dedicado con vista redactada (nunca devolver la key al frontend).

### 4. Wizard (overlay web, rápido y saltable)
`(0)` corre el detector → informe. `(1)` elegir **Local/Cloud** con el detector pre-seleccionando el default sensato
(un clic = aceptar y entrar). `(2)` huecos del perfil elegido con **acción de instalar** (un clic) o **comando para
copiar**, + swaps de ahorro ("estás en STT de nube — instala Whisper local para no pagar"). `(3)` credenciales:
pre-rellenas del store (`_set`), se piden las que falten. **Gate**: no da acceso hasta validar la config.

## Fases
1. **Fundamentos** — `config/profiles.py` (resolver coordinado + aplicar patch) + `config/doctor.py` (detector + CLI +
   informe JSON) + escritor del credential store + tests. ← ESTA fase primero.
2. **API del server** — `/api/wizard/{report,state,profile,install,credentials,complete}` (el server local puede
   shell-out al detector/instaladores).
3. **Frontend** — overlay del wizard (gate de primer arranque, pick de perfil, huecos+instalar/copiar, form de creds).
4. **Coherencia + defectos** — arreglar Dockerfile (copiar `nucleo/`+`memory/`), nombres de STT, validación de
   perfil; docs (README multi-OS, zaelar-ops, zaelar-deploy, zaelar-conventions §config-UI, cluster.yaml, diagrama
   `/architecture`); revisión de alineación.

## Invariantes / cuidado
- **Config gestionada por la UI** es invariante de producto — el wizard es web; el CLI es apoyo de instalación/headless.
- Perfil = solo mueve DEFAULTS; el override por-componente SIEMPRE gana (hybrids en máquinas flojas).
- Los failovers existentes NO se tocan (ya fail-open). El wizard configura, no reemplaza la degradación en runtime.
- Secretos: nunca al frontend (redacción `<clave>_set`); el credential store en chmod 600.
- No adaptar la MEMORIA a tests ni hardcodear datos (mandato del operador; ver V2-031/V2-033) — aquí solo tocamos
  MECÁNICA de config, no contenido de memoria.

## Bitácora
- **2026-07-15** — Survey de 3 agentes (config stores · inventario ENV+perfiles · failovers/deps/deploy). Diseño
  aprobado por el operador (superficie web+script, instalación automática-primero). Iniciativa creada. Arranca Fase 1.
- **2026-07-15 · Fase 1 (commit eec70a2)** — `config/profiles.py` (resolver coordinado local/cloud + `apply`) +
  `config/doctor.py` (detector + CLI `make doctor` → `.meshkore/logs/system-report.json`) + `ZAELAR_PROFILE` en
  `settings.ENV_KEYS`. 29 tests. Verificado en vivo (Apple Silicon+Metal+Ollama → `local`).
- **2026-07-15 · Fase 2** — API del server + escritor del credential store:
  - `config/credentials.py` = ÚNICO escritor de `.meshkore/credentials/zaelar.env` (chmod 600, escritura atómica
    preservando comentarios, aplica en caliente a `os.environ`, vista redactada solo-presencia, borra con valor
    vacío). 7 tests.
  - `server/wizard_api.py` (`/api/wizard/{state,report,profile,credential,install,complete}`) montado SIEMPRE
    (config-UI es invariante, no gated por BRAIN). `state` = first_run + perfil activo + perfiles + informe +
    catálogo de instaladores. `install` EJECUTA los acotados al proyecto (playwright/ollama pull/stt/tts, job en
    background + poll `/install/{job}`) y DEVUELVE el comando para los de sistema (ollama/livekit/claude). first_run
    marcado en `settings.wizard_done`. Verificado en vivo: los 6 endpoints OK, credencial throwaway sin rastro.
- **2026-07-15 · Fase 3** — overlay web del wizard: `frontend/app/components/WizardModal.js` (3 pasos: elegir
  perfil con el detector recomendando → resolver huecos [Instalar con un clic lo del proyecto vía job+poll, o
  copiar el comando de sistema] → credenciales pre-rellenas por presencia). Señal `store.wizardOpen`, **auto-abre
  en el primer arranque** (`main.js` consulta `/api/wizard/state`), reabrible desde el TopBar (🧭). API en
  `services/api.js`, estilo `.wiz-*` con variables `--hb-*` (tema dark/light). Verificado E2E en Chromium headless:
  auto-abre, 2 tarjetas, recomendado resaltado, avanza de paso, botón 🧭 presente, sin errores JS del wizard.
- **2026-07-15 · Fase 4** — coherencia + defectos + docs:
  - Dockerfile: quitado `COPY brains` (carpeta inexistente → build roto) + copiar nucleo/memory/bus/connectors +
    ENV BRAIN=nucleo/ZAELAR_ENGINE=livekit/ZAELAR_PROFILE=cloud + nota de que la imagen Linux no trae modelos locales.
  - `config/.env.example`: STT/TTS a las vars REALES del motor (ZAELAR_STT/ZAELAR_TTS + registro real), marcado como
    fallback del wizard (STT_PROVIDER/TTS_PROVIDER eran Hermes-era, nadie los lee).
  - Docs: README §2 reescrita alrededor del wizard (+ `make doctor`); `zaelar-conventions §Configuration is
    UI-managed` añade el wizard/perfiles/credential-writer; `cluster.yaml §config` (Fase 1). Suite config 29 verde;
    el server construye con el router del wizard.
  - **Pendiente menor**: diagrama `/architecture` (topología sin cambio de modelo/proveedor → impacto bajo; el
    wizard es capa de config, no de runtime) + revisión de alineación formal. **Wizard FUNCIONAL y verificado E2E.**
