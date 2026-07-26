# zaelar

> **`.meshkore/` en este repo es un SYMLINK a `../.meshkore`** (2026-07-22): la gestión del proyecto (roadmap,
> iniciativas, docs canónicas, credenciales locales de dev, logs) vive en la RAÍZ del workspace `zaelar/` — ver
> `../CLAUDE.md` — porque coordina `engine/`+`web/`+`cloud/` a la vez, no solo este subrepo. Todas las rutas
> `.meshkore/...` de este documento siguen funcionando igual (mismo contenido, distinta ubicación física); solo
> requiere el layout de monorepo local (`engine/` junto a sus hermanos bajo `zaelar/`) — un self-hoster que clona
> `engine` en solitario no lo tiene ni lo necesita (configura sus credenciales por la UI, no por `.meshkore/`).

Asistente personal por voz **multidioma** (por defecto **castellano**), siempre activo. Arquitectura: STT →
**cerebro propio «Colmena»** → TTS, sobre **LiveKit Agents**. El cerebro (`nucleo/`), la memoria (`memory/`) y la
proactividad son **nuestros**: zaelar no depende de ningún agente externo.

**Run**: `make run` (= `BRAIN=nucleo`) → levanta el stack LiveKit (servidor LiveKit **nativo, sin Docker** + web con
worker EMBEBIDO) en http://localhost:43917 (Chrome). **El core NO requiere Docker**: usa el binario `livekit-server`
(`make install-livekit`); Docker es solo fallback si falta el binario. `BRAIN=direct`/`BRAIN=local` = baselines de
modelo pelado (sin memoria/tools). `make lk-server` / `make agent-worker` para depurar por separado.

## MeshKore Standard v27

Este repo sigue el **MeshKore Standard v27**. Toda la documentación, módulos y roadmap viven en `.meshkore/`.
Los agentes DEBEN trabajar dentro de esta estructura — no crear `docs/` ni carpetas ad-hoc fuera de ella.

### Documentación canónica (`.meshkore/docs/`)

| Categoría | Archivo |
|---|---|
| Architecture | `.meshkore/docs/architecture/zaelar-architecture.md` |
| **Modularidad / contratos de acoplamiento** | `.meshkore/docs/architecture/zaelar-modularity.md` |
| **Memoria central** | `.meshkore/docs/architecture/zaelar-memory.md` |
| Product / Context | `.meshkore/docs/product/zaelar-product.md` |
| Deploy | `.meshkore/docs/deploy/zaelar-deploy.md` |
| Ops / Setup | `.meshkore/docs/ops/zaelar-ops.md` |
| Conventions | `.meshkore/docs/conventions/zaelar-conventions.md` |
| Modules | `.meshkore/docs/modules/zaelar-modules.md` |
| Security | `.meshkore/docs/security/zaelar-security.md` |
| **Change protocol** | `.meshkore/docs/ops/zaelar-change-protocol.md` |
| **Audit workflow** | `.meshkore/docs/ops/zaelar-audit-workflow.md` |
| **Docs & structure sync** | `.meshkore/docs/ops/zaelar-docs-sync.md` |
| **Widgets change workflow** | `.meshkore/docs/ops/zaelar-widgets-workflow.md` |
| **Memory change workflow** | `.meshkore/docs/ops/zaelar-memory-workflow.md` |
| **Alignment review** | `.meshkore/docs/ops/zaelar-alignment-review.md` |
| **Model/latency benchmarks** | `.meshkore/docs/ops/zaelar-model-benchmarks.md` |
| **Testing playbook** | `.meshkore/docs/ops/zaelar-testing.md` |
| **Monitorización de conversaciones de cluster** | `.meshkore/docs/ops/zaelar-cluster-conversation-monitoring.md` |
| Observabilidad / debug | `.meshkore/docs/ops/zaelar-observability.md` |

> Instalación / arranque para quien clona el repo: **[`README.md`](README.md)** en la raíz (multi-plataforma
> macOS/Windows/Linux). Es la puerta de entrada; el detalle vive en `zaelar-ops.md`. Mantener ambos alineados.

**Protocolo de cambio ("pasa el protocolo"):** cuando el operador dice *"pasa el protocolo"*, ejecutar la
checklist de `zaelar-change-protocol.md` (reiniciar+verificar → versión → diario/iniciativa/contexto → commit →
push si hay remote → deploy si hay prod). No hay que recordar los pasos de memoria: viven en ese doc.

**Workflow de auditoría ("pasa la auditoría"):** cuando el operador dice *"pasa la auditoría"* / *"audita el
sistema"*, ejecutar `zaelar-audit-workflow.md` — reconocimiento del contexto → fan-out en paralelo por 4 dominios
(voz/cerebro/server · frontend/widgets · seguridad cluster · alineación docs) → síntesis → informe + plan P0-P3.
Verifica que código, arquitectura, contexto y el módulo de seguridad siguen alineados cada vez que el proyecto crece.

**Sync de docs/estructura (automático):** todo cambio que toque la **estructura** (módulos, layout, deps, instalación)
o **decisiones/invariantes/seguridad** ejecuta `zaelar-docs-sync.md` — actualizar README (raíz, multi-plataforma),
`CLAUDE.md`, `cluster.yaml`, la doc de categoría y el **diagrama de arquitectura**, con la regla de oro "que aparezca
en contexto + docs + arquitectura". Es el paso de coherencia docs↔estructura dentro del change protocol.

**Revisión de alineación ("pasa la revisión de alineación"):** al cerrar CUALQUIER cambio que toque arquitectura, un
módulo, un flujo o una decisión/invariante, ejecutar `zaelar-alignment-review.md` — checklist reutilizable que
verifica que **código ↔ contexto (CLAUDE.md) ↔ docs canónicas ↔ diagramas HTML (`/architecture`: pestañas
Arquitectura/Memoria/FlashBrain/SlowBrain/Widgets + modelos-en-uso + sello "Actualizado") ↔ roadmap (tareas done +
bitácora, servido al Architect por el daemon) ↔ tests** cuentan la MISMA historia (estado actual, sin dirty/legacy).
Es la puerta de calidad de cada cambio; trae sondas `grep`/`node --check` y un template de informe.

**Workflow de cambios en widgets ("pasa el workflow de widgets"):** cuando el operador dice **"pasa el workflow de
widgets"** (o "revisa/cierra el cambio de widgets"), o al cerrar tú mismo un cambio ESTRUCTURAL del sistema de
widgets (contrato de `manifest.json`/`data.py`/`widget.js`, protocolo de tags, despacho cerebro↔widget, storage,
refresco, gate de validación), ejecutar `zaelar-widgets-workflow.md` — mapa "qué tocaste → qué actualizar" (contrato
del generador, brief, prompt del FlashBrain, docs canónicas, **diagrama Y teoría** de `architecture.html`), repaso de
impacto en widgets existentes, pruebas (`make test-widgets` + prueba en vivo si toca gobernanza), reinicio si hubo
cambios `.py`, y commit/push SOLO si el operador lo pide. Un cambio trivial dentro de un solo widget (su propio
`data.py`/`widget.js`) no lo dispara — solo actualiza el `notes.md` de ese widget.

**Workflow de cambios en la memoria ("pasa el workflow de memoria"):** cuando el operador dice **"pasa el workflow
de memoria"**, o al cerrar tú mismo un cambio ESTRUCTURAL de la memoria (schema/píldora, el CORAZÓN de escritura
`mem_processor`/`memory_agent`, retriever/scoring, capas y velocidades de lectura, consolidador/olvido, cola/writer,
observabilidad/visor), ejecutar `zaelar-memory-workflow.md` — **mapa de impacto "qué tocaste → qué revisar/notificar"**
de TODOS los escritores (FlashBrain conv-buffer, `ingest_utterance`, `remember`, widgets/mensajería, reset, episódica)
y lectores (`memory_cache`, `compose_recall`, `compose_context`, visor `/api/memory/map`) para verificar que sus
interacciones (guardar Y leer) siguen alineadas con la versión nueva, + migración de schema, + docs (zaelar-memory.md,
CLAUDE.md, diagrama Memoria de `/architecture`), + tests, + commit. Evita re-investigar cada vez a quién afecta un
cambio de memoria. Termina SIEMPRE con la revisión de alineación.

**Testing del bot ("lanza un test del bot"):** cuando el operador dice **"lanza un test del bot"**, **"lanza la
batería (de escenarios)"** o **"prueba el bot en tuen"**, ejecutar `zaelar-testing.md` — el playbook autocontenido:
**Paso 0 = ALINEACIÓN** (comprobar que `tester/scenarios.py` cubre los módulos principales y los cambios de las
ÚLTIMAS 48 h — `git log --since` + decisiones `V2-0xx` nuevas; si falta, añadir el escenario ANTES de lanzar) →
prioridades (latencia · coste bajo · memoria · búsqueda precisa · **navegación web profunda Wallapop/coches.net con
extracción de datos reales, con/sin login** · robustez · multiidioma) → lanzar (`tester/run_battery.sh` con settle,
o `cron_tick.sh`) → evaluar con el JUEZ distinguiendo **bug real (trace-confirmado) vs ruido de STT del tester vs
rigidez del juez** (y comparación HUMANA de lo extraído en navegación) → arreglar código si hay bug → **archivar el
informe del día en `tester/reports/<YYYYMMDD>-<desc>/`** (histórico consultable). Catálogo legible de escenarios en
`tester/anexos/catalogo-escenarios.md`. No hay que recordar los pasos: viven en el playbook.

> **Diagrama de arquitectura — MOVIDO al sitio público (2026-07-24):** `frontend/pages/architecture.html` y la
> ruta `/architecture` de este repo se **retiraron** — ya no tenía sentido servir un panel interno (con editor de
> modelos ⚙ en vivo) desde el propio motor. Los diagramas (Arquitectura general, FlashBrain, Brain Workers,
> Memoria, Widgets) viven ahora como contenido **público, curado y en inglés** en `web/` bajo `/technology`
> (`web/src/pages/technology/*.astro`), con las rutas de código internas, nombres de variable y detalle de
> incidentes/costes RECORTADOS a propósito (audiencia externa, no engineering interno). **Ya NO es un espejo
> automático del código** — es una foto seleccionada a mano. Si tocas topología/modelo/proveedor de forma
> significativa, actualiza también los diagramas en `web/src/pages/technology/` como paso manual (no lo hace
> ningún workflow todavía); la fuente de verdad DETALLADA sigue siendo `.meshkore/docs/architecture/` y este
> `CLAUDE.md`. Los workflows `zaelar-docs-sync.md`, `zaelar-widgets-workflow.md`, `zaelar-memory-workflow.md` y
> `zaelar-alignment-review.md` todavía referencian el `architecture.html` viejo — pendiente una pasada de limpieza
> en esos docs (no hecha en este cambio; pregúntale al operador si quiere "pasa el protocolo" sobre ellos).

### Módulos declarados (`.meshkore/public/cluster.yaml`)

Antes de crear un módulo nuevo, declararlo en `.meshkore/public/cluster.yaml`. Raíz SIN `.py`/`.html` sueltos;
arranque `make run` → `python -m server`.

- `voice/` — **motor LiveKit** en `voice/engine/` (INI-012): `AgentSession` (streaming, turnos, VAD, barge-in,
  preemptive-gen) + registry de providers + perfiles remote/local (`core/`, `speech/`, `llm/`, `pipeline/agent.py`
  con `make_server()` embebible, `speech/voices.py`). El turn-taking/VAD/barge-in los gobierna LiveKit (VAD Silero +
  turn-detector `MultilingualModel` + `allow_interruptions`). Nivel superior = contrato del cerebro **puro y
  agnóstico del transporte**: `tag_protocol.py`, `speech.py`, `brain_notes.py`, `proactive.py`, `prompt.py`,
  `health_state.py`, `llm_health.py`, `observer.py` (SSE), `attention.py` (gate de atención V2-015 — decide qué
  turno va dirigido a zaelar; ambient vs atendiendo).
- `nucleo/` — **cerebro propio «Colmena»**: FlashBrain ORQUESTADOR + workers Claude Code (V2-036; el "SlowBrain
  cerebro aparte" se disolvió). Se expone al motor como provider
  `livekit.agents.llm.LLM` (`voice/engine/llm/providers/nucleo.py`, `BRAIN=nucleo` = default). `nucleo/flash/` =
  **FlashBrain** reflejo sub-segundo (`router.py` clasifica el input + `fast_client.py` cliente de modelo rápido
  no-razonador **por invocación** + `frontend.py` gestor de frontend/widgets + `procs.py` lanzador de procesos +
  `escalate.py` escalado + `prompt.py` [ensambla el prompt del turno V2-027: ESTADO compuesto + capa TERSA de
  recursos, ~30 líneas] + `memory_cache.py` [cachea `memory.compose_state()` fuera del turno + siembra la misión] +
  `prewarm.py` [calienta FlashBrain+browser en el arranque, V2-024] + `dialog.py` [estabilidad conversacional V2-032:
  break-loop + poda de historial + anti-degeneración, COMPARTIDO por voz y probe] + `probe.py` [canal de PRUEBA
  headless, 3ª forma de testing: `POST /api/flash/say`]). `nucleo/websearch.py` (hermano de `flash/`) = **búsqueda web COMPARTIDA** por los dos cerebros
  (V2-022, ver decisión clave); `nucleo/browser_search.py` = capa **Google GRATIS vía Chromium persistente** (V2-024). **Latencia — la memoria NO está en el turno síncrono**
  (V2-011): el bloque de ESTADO (nombre/trato/temas) sale de `memory_cache` (caché de sesión, TTL + refresco async
  + invalidación por `memory.updated`), y el recall semántico (`prompt.compose_recall`) es **bajo demanda**
  (`prompt.needs_recall`) y **fuera del event loop** (`asyncio.to_thread`) — el turno de charla nunca dispara el
  retriever. `nucleo/loop.py` (~1 Hz) + `nucleo/scheduler.py` (**cron PROPIO** respaldado
  por `memory.journal`) + `nucleo/cron_api.py` (`/api/cron`, panel ⏰) + `nucleo/sparks.py` (chispas doble-gate) =
  **loop orquestador** (tareas programadas + proactividad + dispara el consolidador de memoria off-hot-path + reporta
  por voz+UI; montado en el lifespan con `BRAIN=nucleo`). `nucleo/dispatch.py` (dispatcher: compone prompt
  [contexto+tarea] → CodeAgent con modelo por invocación, consume `escalate.requested` del bus, entrega por voz+UI) +
  `nucleo/memory_agent.py` ★ (agente de MEMORIA, único escritor a `memory/`; su `compose_context` = **dossier v2
  multi-eje** del worker V2-056: perfil sin misión + reglas + ⚠️ críticos SIEMPRE + recall + `by_concepts` + agenda,
  solo durables, `to_thread`) + `nucleo/mem_processor.py` ★ (el CORAZÓN de escritura V2-013: **`gpt-4.1-mini` vía
  OpenAI** por config `§memory` desde V2-056 — bench §12: 98.3% vs qwen2.5:7b local 86.2%, que queda de OPCIÓN; key
  POR ENDPOINT + salud con alerta por racha de fallos [incidente 2026-07-17/19: 2 días caído en silencio];
  escribir puede ser lento, prioriza escribir BIEN — DESTILA cada turno en píldoras curadas — dato+metadatos,
  decide DESCARTAR/ESTADO/CORTO/LARGO + importancia + `slot`; off-hot-path, fail-open a la heurística [que ya NO
  ensucia: degrada a short+TTL]; **GATES de PRECISIÓN deterministas V2-033**:
  descarta peticiones/preguntas/ack reificadas, no deja que un nombre garbleado del STT pise la identidad del `state`
  —cuarentena— y no hace durable una preferencia efímera) + **`nucleo/workers/`** (**Brain Workers V2-038** —
  sustrato AGNÓSTICO: `base.py` [`WorkerBackend`/`WorkerEvent`/`WorkerSpec`], `claude_session.py` [stream-json vivo],
  `generator_session.py` [widgets, envuelve el generador matable], `codex_session.py` [stub], `registry.py`
  [`get_backend` por config, mezclable], `session.py` [`WorkerSession` + `SessionRecord`]) = capa de trabajo async
  INTERACTIVA. `nucleo/agentes/` (interfaz `CodeAgent` one-shot V2-036 — `worker/web/web_cc/otros.py` **PARKEADOS**
  en V2-038; solo se reutilizan sus helpers de detección de widget). **Puentes de los workers**: `nucleo/mem_cli.py`
  (`hbmem` — memoria serial, recall/remember por HTTP) · `nucleo/agent_report.py`+`nucleo/agent_api.py` (`hbnote` —
  reporte de fase al bus) · **`nucleo/worker_bridge.py`+`nucleo/worker_api.py`** (`hbask`/`hbact`/`hbsay` —
  pregunta/pide-tool/dice al usuario, plano request/response V2-038, `/api/worker/act`, política + piggyback + token) ·
  `nucleo/nav_cli.py`+`widgets/navegador/act_api.py` (`hbweb` — conducir el navegador) · **`nucleo/widget_cli.py`**
  (`hbwidget` — LEER/OPERAR un widget del canvas: `read`/`data`/`show`/`close`, acción `widget_data` de
  `/api/worker/act` con gate del catálogo canónico + provenance worker; V2-061, el PUENTE que refleja en los widgets
  lo hecho en la realidad). `nucleo/danger.py` = gate de
  acciones irreversibles. **`nucleo/susurro/`** (V2-053) = **auto-auditoría conversacional «Susurro»** — enchufado
  SOLO por el bus (topic `turn.completed` + fricción), modelo potente configurable §susurro, correcciones de
  catálogo cerrado (ver decisión clave). **`nucleo/homeostasis.py`** (V2-070) = **LATIDO AUTÓNOMO** — el tercer
  nivel, HERMANO del cerebro (no parte de él): mantiene la MÁQUINA sana (recicla el motor LiveKit degradado cuando es
  seguro, rota logs, evicta cápsulas muertas), determinista y SIN LLM, `start()/stop()` en el lifespan como los otros
  supervisores; ver decisión clave «Homeostasis».
- `memory/` — **memoria central** tipo humana, SUBSTRATO 100% local (los LLM de escritura van por API — ver
  decisión clave), un solo fichero SQLite `zaelar.db` (WAL, en
  `memory/_data/`): substrato compartido que escriben el FlashBrain, el agente de memoria y los widgets, y lee el
  retriever en la ruta caliente (ms). **`memory.compose_state()`** (V2-027) compone el **ESTADO COMPARTIDO** que
  ven los dos cerebros — misión (`state.mission`) + situacional + conversación reciente sintetizada — como lectura
  DIRECTA (µs, sin LLM ni retriever); lo cachea `nucleo/flash/memory_cache` fuera del turno. Cada recuerdo es una
  **PÍLDORA**: dato canónico (`text`) + metadatos (`slot`/`meta`, schema v2). **`slot`** = clave canónica del hecho singular (`operator.name`, `goal.current`…) →
  el writer hace **supersede/dedup EXACTO sin LLM** ("el más reciente MANDA": mismo dato = refuerza; dato cambiado =
  invalida TODOS los vigentes — auto-curativo). El **vocabulario de slots vive en el REGISTRO ÚNICO
  `memory/slots.py`** (auditoría 2026-07-14): alias + campo de `state` + flag de identidad, consumido por writer
  (`canon_slot`), memory_agent (gate P0b) y el prompt del procesador (catálogo GENERADO) — las tres capas no pueden
  divergir; el consolidador añade `heal_slots()` (normaliza legacy + colapsa multi-vigentes en cada sueño). El
  **contrato v2 del átomo** añade `value` (→ `state_patch` sintetizado MECÁNICAMENTE del registro) y `change:
  none|update|correction` (señal de cambio del PROPIO procesador multilingüe → el gate anti-garble la consume; las
  regex es/en quedan de backstop, no de mecanismo único). Tablas `state·memories·vec_memories·fts_memories·edges·episodic·journal` ·
  cola + writer (único escritor, embeddings al insertar) · embeddings (embeddinggemma 768 vía Ollama, fallback
  fastembed; provider configurable `memory.embed_*` + `memory/reembed.py` con firma de modelo) · retriever
  (sqlite-vec + FTS5 → RRF k=60 → score α·rel+β·rec+γ·imp+δ·uso → **reranker** cross-encoder local `memory/rerank.py`
  → graph_expand) · grafo ·
  consolidador (sueño LIGERO: decay Ebbinghaus POR VENTANA + dedup + prune_invalid + eviction por peso, pinned
  intocable) · **`memory/rem.py`** (V2-056: sueño PROFUNDO «fase REM» diario — repara vectores `embed_pending` +
  dedup SEMÁNTICO por coseno + INSIGHTS por concepto [`slot=insight:<c>`, hook LLM inyectado desde
  `nucleo/memllm.py`] + higiene con alerta; kill-switch `ZAELAR_REM`) · capa **episódica** (absorbió el
  antiguo `files/`: paste/drop → `memory/server_api.py` → `memory.write_episode`, binario + resumen buscable, carga
  lazy) · fachada + señal `memory.updated` por el bus. `memory/seed_from_hermes.py` = importador one-shot que siembra
  el perfil del operador desde `~/.hermes` si existe (best-effort, solo-lectura). **`memory/vault.py`** ★ (V2-060:
  BÓVEDA de secretos del operador CIFRADOS — cripto asimétrica sealed box vía PyNaCl + sobre passphrase Argon2id +
  passkeys WebAuthn PRF; tablas `vault_meta`/`vault_secrets`), **`memory/secrets.py`** (detección FAIL-CLOSED +
  redacción) y **`memory/vault_api.py`** (`/api/vault/*`, loopback) — ver la decisión clave «Bóveda de secretos».
  Diseño en `zaelar-memory.md`.
- `bus/` — **Sistema Nervioso**: pub/sub de señales in-process (asyncio, patrones fnmatch + `emit_sync`
  loop-agnóstico vía `call_soon_threadsafe` para entrega cross-loop job-thread↔uvicorn). `bus/log.py` = log durable
  de eventos en SQLite (`zaelar.db`, tabla `events`, WAL). `bus/sse.py` = puente SSE al frontend (`GET /events`).
  Transporte HÍBRIDO: llamadas directas en la ruta caliente de voz + eventos para lo async/fan-out. **Nada de
  Kafka/broker.**
- `frontend/` — interfaz como app de **módulos ES sin build**, migrable a Solid (core reactivo + services +
  components + widget desktop). Voz vía **cliente LiveKit** (`services/session-lk.js` + SDK vendorizado en
  `frontend/vendor/`). Ver `zaelar-modules.md §Frontend`.
- `server/` — FastAPI app + routers + entrypoint (`server/__main__.py`); corre el **agent worker de LiveKit
  EMBEBIDO** en el proceso (lifespan), y arranca en ese mismo lifespan el loop de `nucleo/`, el supervisor de
  widgets `backed` y el consumidor de la cola de memoria. Routers: `livekit_api` (token + config + swap de
  session.js), `voice_api`, `cron_api` (`/api/cron`), `wizard_api` (V2-040), `spotify_api` (V2-041), `config_api`
  (V2-043: `/api/config*` — el área de configuración full-screen), **`memory/vault_api`** (V2-060: `/api/vault/*` —
  bóveda de secretos, montado siempre), widgets, pages.
- `widgets/` — widgets full-stack (`data.py` + `widget.js` por carpeta), generador, catálogo, runtime.
  Dos *kinds* en `manifest.json`: `passive` (por defecto) y **`backed`**: un widget con proceso propio (`owner.py`)
  supervisado por `widgets/supervisor.py` (mailbox + reinicio con backoff + desactivar tras N fallos, aislado de la
  voz). Widgets backed = **`navegador`** (un navegador web real dentro de zaelar) y **`mensajeria`** (mensajería
  unificada WhatsApp+Telegram; su owner triaja en el propio widget con un modelo LOCAL, gated `"gate":"nucleo"`).
  **`widgets/background.py`** (V2-034) = planificador de **ejecución en BACKGROUND con ciclo**: un widget declara
  `"background": {"every": "1m"}` y sigue trabajando OFF-SCREEN en su periodo (mínimo 1s) — `data.py:tick(ctx)` de
  un passive corrido en un hilo, o un comando `tick` encolado a un owner backed — para refrescar datos y **volcar
  a memoria** lo que el operador pueda preguntar por voz (ver decisión). `widgets/actions.py` = semántica de
  acciones (V2-025); `widgets/refs.py` = resolución de referencias a items (V2-026).
- `config/` — settings runtime gestionados por la UI (gitignored): `settings.json` (⚙ STT/TTS/voz/idioma),
  `connectors.json` (flags+credenciales de conectores), `v2.json` (routing de modelos `fast`/`code_agent` +
  **`memory`** [reranker + embedding, V2-030] + `active_brain()`), `meshkore.json`. Cada uno con su módulo dueño
  (`settings.py`/`connectors.py`/`v2.py`) y **vista pública redactada** (secretos → `<clave>_set: bool`; cualquier
  clave que termine en `api_key` se redacta). `profiles.py`+`doctor.py` = perfiles coordinados + detector (wizard
  V2-040); `credentials.py` = único escritor del credential store. **`balances.py`** (V2-043) = saldo de APIs
  externas (proactivo donde se expone —ElevenLabs—, reactivo por error clasificado para el resto). El **área de
  configuración full-screen** (⚙, V2-043) se sirve por `server/config_api.py` (elige API/modelo por PIEZA) +
  `frontend/app/components/ConfigPanel.js`; sus alertas de saldo salen en el diálogo de estado (◉).
- `connectors/` — conectores externos; `connectors/meshkore/` = canal nativo de clusters (3er I/O junto a voz+chat),
  conducido por el **motor del FlashBrain en perfil UNTRUSTED** (V2-069: `brain.py` adapta el canal al motor →
  `nucleo/flash/cluster.py`, tools off + system identidad-safe) con **cápsula** de conversación (`capsule.py`);
  `connectors/architect/` = proveedor de código/proyectos sobre el
  daemon MeshKore compartido (tags `[[architect.*]]`, operator-only); `connectors/whatsapp/` = WhatsApp personal
  (bridge Baileys vendorizado); `connectors/telegram/` = Telegram personal (userbot Telethon); `connectors/email/` =
  **email personal** (V2-051, IMAP/SMTP **stdlib puro**, lógica vendorizada del adaptador de Hermes — leer+triar+
  **responder** por SMTP con threading; app-password + presets Gmail/Outlook/otro; el más limpio de los tres);
  `connectors/messaging/` = **capa compartida** de mensajería (ahora con OUTBOUND: cola `pending_reply` + `msg.reply`
  → tool `reply_message` con confirm-gate). Ver `zaelar-modules.md §Connectors`. Slots futuros: LinkedIn, X.
  **Contactos como memoria + envío-a-persona (mándale un mensaje a X) + conectores Apple/Google + red de agentes =
  iniciativa de DISEÑO `V2-052` (pendiente de OK del operador).**
- `harness/` — harness de evaluación (self-test de mic/pipeline).
- `tester/` — tester de voz (INI-013): 2º participante LiveKit que HABLA con zaelar y un JUEZ que evalúa lo que HACE.

`files/` quedó plegado en la capa episódica de `memory/` (shim de compatibilidad). Raíz (no-módulos): `README.md`,
`Makefile`, `requirements.txt` + `.venv/`, `Dockerfile`/`fly.toml`/`.dockerignore`, `scripts/` (tooling de
instalación por-OS), `CLAUDE.md`. **Logging → `.meshkore/logs/`** (no crear `logs/` en la raíz).

### Roadmap e iniciativas (`.meshkore/roadmap/`)

Las iniciativas activas están en `.meshkore/roadmap/initiatives/`. Anclar cada tarea a una iniciativa. El diseño del
cerebro «Colmena» vive en `.meshkore/roadmap/EPIC-v2-colmena.md`.

### Daemon (NO es por-proyecto)

El daemon de MeshKore es un **servicio único compartido** (hospedado en `daemon.meshkore.com`), que da
servicio a todos los proyectos del cluster. **Este repo NO arranca ni incluye un daemon propio.** La adopción
del estándar se hace apuntando el front del Architect a la URL de la carpeta `.meshkore/` de zaelar; el daemon
la lee, identifica el proyecto por `public/cluster.yaml` y lo onboarda (incluido el bloque `MESHKORE_PREAMBLE`).
No crear `.meshkore/daemon.py`, ni targets `make meshkore`, ni bindear el puerto 5570 desde aquí.

## Decisiones clave

- **Dominios públicos → motor local (CERRADO 2026-07-22)**: `server/__main__.py` arranca DOS listeners a la
  vez: el de siempre en `43917` (HTTP plano, para las bridges internas `nucleo/*_cli.py` — sin cambios) y
  uno adicional en `44317` sirviendo **HTTPS con un certificado compartido** (`certs/local.zaelar.com/`,
  mismo cert para toda instalación self-host, modelo Plex `*.plex.direct` — ver el README de esa carpeta
  para el porqué, la caducidad y cómo renovarlo). Es lo que permite que `https://local.zaelar.com:44317`
  (DNS: registro A pelado a `127.0.0.1`, nunca pasa por el borde de Cloudflare) muestre un dominio real en
  la barra de direcciones en vez de "localhost". **El puerto se queda visible a propósito** — ocultarlo del
  todo exigiría escuchar en el 443 (privilegiado, pide sudo/admin, contradice "arranca fácil, sin sudo") o
  un túnel por-usuario (mucha más infra); ambos descartados. Detalle completo (los 4 registros DNS, la
  entrada inteligente `my.zaelar.com` que cae aquí cuando no hay cuenta cloud, pendientes de renovación):
  `project/concept/docs/ops/domains-and-local-access.md` (workspace `zaelar/`, fuera de este repo).
- **Motor de voz = LiveKit Agents** (`voice/engine/`, INI-012): `AgentSession` es dueña de streaming, turnos, VAD,
  barge-in y preemptive-generation. Corre **EMBEBIDO** en el proceso del servidor web
  (`AgentServer(job_executor_type=THREAD)`), NO como proceso aparte — porque zaelar asume **un solo proceso**: la
  memoria central `memory/`, el bus de eventos `bus/`, el buzón `brain_notes`, el registro de `proactive`, la cola
  SSE de `observer` y el loop de `nucleo/` (cron+consolidación) viven todos ahí. **Coordinación loop-agnóstica**: el
  `asyncio.Lock` no vale entre el loop del job-thread y el de uvicorn → la entrega cross-loop usa
  `call_soon_threadsafe` (`bus.emit_sync`). Requiere **servidor LiveKit** (binario nativo local `--dev`;
  Cloud/self-hosted en prod).
- **Cerebro propio «Colmena» — FlashBrain ORQUESTADOR + workers Claude Code** (`nucleo/`, EPIC-v2-colmena, redseñado
  en **V2-036** 2026-07-13). El **FlashBrain** (`nucleo/flash/`) ocupa el slot del LLM del motor de voz (provider
  `nucleo`) y atiende cada turno en ~1s: charla, control de widgets, Q&A de estado desde el bloque de estado vivo, y
  **lanza y sigue** los procesos largos. Cuando el turno necesita memoria/tools/razonamiento, llama a
  **`escalate_to_slowbrain(request)`** → `nucleo/dispatch.py` (**gestor de sesiones SIN cerebro**: pool + registro de
  sesiones vivas + entrega) despacha la tarea a un **worker Claude Code headless** que **la CONDUCE con SU
  inteligencia** (`nucleo/agentes/worker.py` genérico; `nucleo/agentes/web_cc.py` web vía el puente de navegador
  `hbweb`; `nucleo/agentes/code.py` widgets vía el generador). El resultado vuelve por `voice/proactive` (voz+UI).
  **El "SlowBrain como cerebro razonador aparte" se DISOLVIÓ:** ya no hay un segundo cerebro; cada worker Claude Code
  ES un slow-brain-por-tarea (razona, usa tools, accede a memoria). El FlashBrain puede, EN EL TURNO, escalar a un
  modelo un poco mejor si una RESPUESTA necesita más elaboración (2º pase conversacional, no un worker). **Pool**
  (`code_agent.max_parallel`, def 3) acota la concurrencia. Piezas VIEJAS **parkeadas** (muertas, revertibles):
  `nucleo/agentes/otros.py`, `nucleo/agentes/web.py`, y el bucle Haiku de `widgets/navegador/agent.py`. El loop
  orquestador (`nucleo/loop.py` ~1 Hz + `nucleo/scheduler.py` cron + `nucleo/sparks.py`) añade proactividad y
  consolidación. Detalle: `.meshkore/roadmap/initiatives/V2-036-smartbrain-claude-code.md`. **La tool de escalado
  se llama `escalate_to_slowbrain` por LEGADO** (el SlowBrain-cerebro se disolvió aquí); hoy LANZA un worker
  headless. **Catálogo de tools del FlashBrain (canónico) = `zaelar-architecture.md §8`** (reflejado en el diagrama
  de `/architecture`); tocar `router.TOOLS` obliga a sincronizar esa doc + diagrama + tests (`zaelar-docs-sync.md §Tools`).
- **Workers Claude Code = memoria serial + reporte por el bus + pool** (V2-036; endurecido en la auditoría de
  memoria 2026-07-14): un worker Claude Code accede a la
  memoria como **pieza serial e independiente** — pide un dato (`python -m nucleo.mem_cli recall`) y guarda un dato
  (`… remember --slot`), hablando por HTTP con el server vivo (`/api/memory/recall|remember`) → **preserva el
  escritor único** (no abre la BD). La escritura exige el **token por-tarea** (`ZAELAR_TASK_TOKEN`, headers de
  `mem_cli`) y entra por **`memory_agent.remember_external`** — mismos gates de precisión que la voz: NUNCA toca
  `state`, los **slots de IDENTIDAD están vetados** (un worker no habla por el operador) y la procedencia queda
  estampada (`meta.source="worker:<id>"`). La memoria admite acceso **concurrente** entre el FlashBrain y N workers
  (lecturas WAL + escrituras por cola); NUNCA un lock global. Al arrancar recibe el bloque «CONTEXTO DE MEMORIA»
  (`dispatch._compose_context` → `memory_agent.compose_context`) **+ «CONVERSACIÓN RECIENTE» verbatim**
  (`dispatch._recent_conversation_block` ← `memory.recent_window`; fix sesión 22:40 2026-07-16: una escalada tersa
  —«¿por qué no se oye?»— llegaba SIN contexto conversacional y el worker investigaba lo equivocado; el contexto se
  adjunta DETERMINISTA, no se delega a la reformulación del modelo rápido). Reporta su fase con `python -m nucleo.agent_report
  phase` (`/api/agent/report` → `dispatch.session_phase` → el ESTADO `sessions` → el prompt del FlashBrain como
  "PROCESOS DE FONDO", para asociar cada pregunta/orden a SU sesión). Conduce el navegador con `python -m
  nucleo.nav_cli` (`/api/navegador/act` → `TaskBrowser` del owner). Tools acotadas (`dispatch._tools_for` +
  `claude_session._BRIDGE_TOOLS`): **NUNCA un `Bash` pelado** — Bash SOLO a esos CLIs (invariante del escritor
  único). El id de escalada viaja por `ZAELAR_TASK_ID`, el de la pestaña por `ZAELAR_NAV_TASK`. Solo el resultado
  **OK** de una tarea se recuerda como píldora durable.
- **Brain Workers INTERACTIVOS — sesiones vivas, bidireccionales y AGNÓSTICAS del motor** (`nucleo/workers/`,
  V2-038, 2026-07-14; diseño en `.meshkore/roadmap/initiatives/V2-038-brain-workers-interactivos.md`). El worker
  one-shot (`claude -p`) se convierte en una **sesión VIVA** que el FlashBrain gobierna. **Agnóstico del motor
  (requisito nº1 del operador):** una sola costura `WorkerBackend`/`WorkerEvent`/`WorkerSpec` (`workers/base.py`);
  backends `claude_session` (stream-json), `generator_session` (widgets — envuelve `widgets/generator.py`
  conservando su contrato+validación, ahora **matable** por token), `codex_session` (stub); `registry.get_backend`
  elige por config y es **mezclable** (Claude web + Codex código a la vez). **`dispatch.py` = gestor de sesiones**:
  **REGISTRO ÚNICO EN RAM = fuente de verdad** (absorbe `escalate._tasks`/`_INFLIGHT`/`_SESSIONS` viejos), **kill de
  GRUPO** (`killpg`, mata al `claude` y sus hijos), **cola de inyección** (↓ `pending→delivered`), `resolve_sessions`
  determinista. **Tres canales:** (1) ↓ **inyectar** un refinamiento a un worker vivo (`send_to_worker` →
  `dispatch.inject_soon`; entrega PRINCIPAL por **piggyback** en las respuestas de los puentes — reemplaza el
  dedup-descartar de V2-029: un «además, verde» se INYECTA, no se tira); (2) ↑ **a estado** (fase auto-derivada del
  stream + `hbnote`); (3) ↑ **preguntar/pedir con respuesta** (`hbask`/`hbact` → **`nucleo/worker_api.py`**
  `/api/worker/act`, plano request/response con re-poll idempotente, **política ALLOW/CONFIRM/DENY en el server**,
  `use_tool` sobre un catálogo FILTRADO — el FlashBrain **presta sus tools** al worker, p.ej. `web_search`; CONFIRM =
  `ask_user` auto-generado; **token por-tarea** `ZAELAR_TASK_TOKEN`; **piggyback** en toda respuesta). El **FlashBrain
  dirige** con `send_to_worker`/`stop_worker`/`answer_worker` (situacionales: solo con workers/ask vivos), backstops
  deterministas (`router.looks_like_stop_work`) y **precedencia** de turno corto (`hard_interrupt` no engulle un
  stop-de-worker; confirm > ask-activo > stop). El **loop supervisa** (`nucleo/loop.py`: proyecta RAM→ESTADO ~1 Hz,
  relata los `ask` con **atribución** + abre la ventana de atención, avisa de encallamiento/timeout SIN matar a
  ciegas). **Cross-loop:** todo comando de sesión desde el turno de voz se **marshalea** al loop del server
  (`inject_soon`/`cancel_soon`/`answer_active_soon`, §V2-038 §v3·D; nunca `await` de una op de worker en el turno).
  **Reset/lifespan:** `reset_all`/apagado del server **matan de verdad** (`dispatch.cancel_all`) + barrido de
  huérfanos al arrancar (`run-livekit.sh`). El frontend RECONCILIA los chips contra `GET /api/tasks` (registro RAM)
  al (re)conectar → fin de los chips huérfanos. Piezas one-shot **parkeadas** (revertibles): `nucleo/agentes/
  {worker,web,web_cc,otros}.py`.
- **Gate de ATENCIÓN — el micro abierto no actúa sobre voz ambiente** (`voice/attention.py`, V2-015, 2026-07-09):
  con el micro SIEMPRE abierto, zaelar trataba TODO lo oído como órdenes — en una reunión capturó voz ambiente,
  alucinó, abrió widgets, escaló tareas al SlowBrain y enterró un "cierra los widgets" dentro de un turno gigante
  (`✂️ input recortado 14076→1600`) que lo truncó. El gate decide si un turno va **DIRIGIDO** a zaelar ANTES de
  actuar. Modo `ZAELAR_ATTENTION` (**gestionado por la UI**, ⚙ `config/settings.py`; env = fallback): `smart`
  (default) = dirigido si hay **wake-word** ("zaelar" + variantes fonéticas que el STT confunde: harvey/arbi/jarbi…)
  o si cae en la **ventana de conversación activa** (`ZAELAR_ATTENTION_WINDOW`, def 30s tras el último turno
  dirigido); `wakeword` = exige wake-word siempre; `ptt` = push-to-talk (señal del frontend por el topic de datos
  `zaelar-ptt`); `always` = comportamiento antiguo (todo es turno). Un turno **no dirigido NO produce acción ni
  respuesta**: emite un evento `ambient` (observer → `/debug` + SSE `/events`) y RETORNA antes de drenar notas,
  escalar o despachar tags. Cableado en `voice/engine/llm/providers/nucleo.py::_run`; el **kickoff (saludo de
  zaelar) NO abre la ventana** a propósito (si la sesión arranca en una reunión, no hay hueco inicial en el que la
  voz ambiente se cuele como dirigida y auto-extienda la ventana) — el operador abre la conversación con la
  wake-word; el **chat/paste escrito** siempre va dirigido (`agent.py` marca `note_directed`). **Interrupción DURA**
  (`attention.hard_interrupt`, agnóstica de idioma es/en, DETERMINISTA — no depende del LLM): "cierra los widgets /
  cierra todo" → `[[close]]` inmediato; "para/silencio/basta/stop" → corta (el barge-in de LiveKit ya paró el TTS)
  sin generar respuesta — se comprueba sobre el texto COMPLETO y ANTES del gate, así **nunca queda enterrada** en un
  turno grande. **Fin de turno acotado con comando preservado** (`attention.clamp_input`): al recortar por longitud
  (`ZAELAR_FAST_MAX_INPUT` 1600) se antepone la cláusula del comando explícito en vez de truncar a ciegas los
  últimos N chars. Y el **triaje de mensajería** ya no inyecta una nota `[SISTEMA]` por batch/turno
  (`connectors/messaging/notify.py`, `_NOTE_GAP` 90s) — dejaba de inundar el FlashBrain (otra causa de los turnos
  gigantes).
- **Latencia del turno — la memoria FUERA del camino caliente** (V2-011): el turno de voz NUNCA hace I/O de
  memoria síncrono en el event loop (embeddings/retriever bloquearían el LLM y el streaming del TTS → segundos por
  frase). (1) el bloque de ESTADO
  (nombre/trato/temas) sale de un **caché de sesión** (`nucleo/flash/memory_cache.py`, TTL + refresco async
  off-loop + invalidación por la señal `memory.updated` del bus) — el turno lee un string ya compuesto; (2) el
  **recall semántico** (`prompt.compose_recall`) es **bajo demanda** (heurística `prompt.needs_recall`, es/en) y
  **fuera del event loop** (`asyncio.to_thread`) — la charla normal nunca dispara embeddings; (3) refuerzo/write
  van por la cola async de `memory/queue.py`. El event loop nunca se bloquea por I/O de memoria. Medido con el
  tester: memory p50 1139ms (baseline 3726avg), widget p50 1031ms (baseline 5885avg), recall REAL conservado
  (ver `zaelar-model-benchmarks.md §4`). Desglose por fase visible en `/debug` (evento `timing`).
- **Circuito de CORTO PLAZO de interacción con el operador** (V2-035, 2026-07-14, doc `zaelar-memory.md §Circuito
  de corto plazo`): el FlashBrain debe estar SITUADO en cada turno sin inflar el prompt — "lo básico siempre + lo
  pesado bajo demanda". (A) **Suelo de identidad SAGRADO**: `memory_cache._store` NUNCA sobrescribe el bloque de
  estado bueno con vacío (un `compose_state()` que falla un instante bajo contención de BD devolvía `('','')` y
  borraba el nombre → "no sé quién eres" intermitente aunque el nombre estuviera en el estado). (B) **Ventana
  sembrada**: `brain._window` (últimos turnos verbatim) se SIEMBRA del buffer conversacional persistente
  (`memory.recent_window`) al arrancar — antes arrancaba vacía y se perdía "de qué hablábamos" en cada reinicio/
  reconexión; cableado en la voz (`nucleo.py::_run`) Y en el probe. (C) **2º pase de corto plazo**: cuando el turno
  referencia la interacción reciente (`prompt.needs_recent`, es/en) se inyecta el buffer AMPLIADO verbatim
  (`compose_recent_block`) FUERA del event loop — hermano de `needs_recall` (que es para el dato DURABLE por
  significado). La charla normal no lo lleva (prompt ligero). Telemetría `recent_fired` en `/debug`.
- **El canvas es AUTORITATIVO — reconciliar al (re)conectar** (V2-035, 2026-07-14): el frontend reporta
  `open_widgets` por `POST /api/canvas/state`, pero solo al CAMBIAR el canvas → un reinicio del server con la página
  abierta dejaba el estado del cerebro DESINCRONIZADO del DOM (creía abierto lo que no, ignoraba lo restaurado del
  `localStorage`). `session-lk.js` re-reporta el set REAL al (re)conectar la sesión. Regla de prompt: la línea
  «Widgets ABIERTOS» del estado ES la verdad de la pantalla; ante un widget que el cerebro no abrió este turno, no
  lo niega (pudo quedar de antes; ofrece cerrarlo) y responde a lo que se pregunta AHORA, no al tema anterior.
- **ESTADO = contexto VARIABLE con UI vivo — el cerebro sabe lo que el operador tiene DELANTE** (`memory/state.py`,
  doc `zaelar-memory.md §Capas`): el ESTADO (la parte VARIABLE del prompt, frente a la FIJA del núcleo) incluye,
  además del perfil, el **CONTEXTO DE UI VIVO** — `open_widgets` (widgets abiertos en el canvas) y `activity`
  (tareas del SlowBrain en marcha). Fuente de verdad = el **frontend** (autoritativo del canvas): reporta el set
  abierto en `desktop._persist()` → `POST /api/canvas/state` → `set_state({open_widgets})` (normaliza ids de
  instancia + dedup); las tareas las escribe `nucleo/dispatch.py`. Viaja SIEMPRE en el prompt vía `memory_cache`
  (off-hot-path, respeta V2-011: el POST dispara `memory.updated` → recompone fuera del loop) y es **visible en el
  mapa de la memoria** (columna ESTADO). Con esto el FlashBrain resuelve "modifica/abre el widget de X" mirando lo
  abierto — si es el único o está en pantalla, **actúa sin preguntar** (regla en `flash/prompt.py`); y el SlowBrain
  **desempata por el widget abierto** en `widgets/runtime.identify(open_ids=…)`, matando el bug de generar un widget
  basura cuando la referencia era ambigua (`nucleo/agentes/code.py` pide desambiguación en vez de caer a CREATE).
- **RAILS — comportamientos comunes CONDUCIDOS** (`nucleo/rails.py`, V2-042): música difusa, vídeo, watch
  recursivo… cada uno = cadena determinista EN CÓDIGO (FlashBrain sigue NO-razonador) + tool + **runs vivos en
  `state.rails`** (fallos AISLADOS `sin_resolver` reanudables) + guía de prompt inyectada SOLO con run vivo
  (`prompt._rails_directive`) + writeback `ingest_message(source=<rail>)`. 1er rail = música
  (`nucleo/flash/music_flow.py`); los widgets son el rail FUNDACIONAL (maquinaria propia, no se reescribe). La
  música tiene **COLA** (V2-047 F4): `play_music action=queue` apila; el widget avisa `ended` (evento real del
  player YouTube, no timeout) → el conector avanza al siguiente EN CÓDIGO (el pulso NO tiene que vigilar; el
  FlashBrain no espera) + guard no-reiniciar-lo-que-suena. **Patrón canónico y taxonomía:
  `.meshkore/roadmap/initiatives/V2-042-rails-comportamientos-conducidos.md`; robustez sesión 23:15: V2-047.**
- **«Sistema arena» — rails/widgets/tools auto-generados, BRAIN RULES + USER RULES, genética (V2-046, DISEÑO
  2026-07-16):** no se puede hardcodear una tool+rail por caso de uso (detonante: `play_video` V2-045). La visión
  ya está construida a medias (generator = widgets sobre la marcha; rails V2-042; brief data-driven; ESTADO) —
  el plan es nombrar/declarar/generalizar, no rediseñar. **BRAIN RULES** = la genética primigenia hardcodeada
  (lock de idioma + capa de operación + descripciones de `router.TOOLS` + guards deterministas); **USER RULES** =
  reglas por-usuario persistidas en el ESTADO (`state.rules`, nace en blanco — **CONSTRUIDO 2026-07-16, A1**: la
  tool `set_style_directive` aplica la regla YA (directiva de sesión) Y la persiste off-loop vía
  `memory.add_user_rule` [dedup, cap 8, la más reciente manda]; retirarla = la misma tool + guard determinista
  `router.looks_like_rule_removal` («olvida esa regla») → `remove_user_rule` con match difuso; render en
  `compose_state §B` «REGLAS DEL OPERADOR» — con rules vacío el prompt es byte-idéntico; paridad voz/probe, y
  fuera el anti-patrón de lanzar un worker para guardar una preferencia); rails
  declarados por manifest + tools por widget = DESPUÉS; **genética transmisible en red** = PLACEHOLDER (solo entre
  conocidos, cuarentena `trust=untrusted` + gate del generador como validador de genes). Criterios canónicos
  tool-nativa vs widget+rail y plan completo: `.meshkore/roadmap/initiatives/V2-046-sistema-arena.md` +
  `zaelar-architecture.md §5e`.
- **Bóveda de secretos del operador — cifrado E2E + passkeys (V2-060, CONSTRUIDO 2026-07-21, rama
  `feat/v2-060-boveda-secretos-cifrados`, no mergeado):** zaelar guarda y sirve secretos del USUARIO (contraseña de
  Netflix, IBAN/tarjeta, nº de cuenta cripto, private key de wallet) sin que estén NUNCA en claro. **Cómo funciona,
  de punta a punta:**
  - **GUARDAR (auto, FAIL-CLOSED).** Cada turno, `nucleo/memory_agent.ingest_utterance` corre PRIMERO el gate de
    secretos (`memory/secrets.py`: patrones Luhn/IBAN/BIP-39/`0x…`/`sk-…` + marcadores «contraseña de X es Y», es/en;
    ante la duda CIFRA). Si detecta un secreto: **redacta** el valor del texto (el LLM destilador ve «secreto
    guardado», jamás el valor) y lo **sella** con `memory/vault.py`. Escribir **NO pide desbloqueo** (usa la clave
    pública). Sin bóveda aún → `secret_needs_vault` (el frontend propone crearla). Storage **partido**: la ETIQUETA
    («contraseña de Netflix») vive en claro y BUSCABLE en `memories` (`meta.vault=1`); el VALOR va cifrado y opaco en
    `vault_secrets` (tabla nueva, schema v3) — nunca embebido, logueado, en un prompt ni accesible a un worker.
  - **LEER (out-of-band).** El operador pide un secreto → el FlashBrain llama a la tool **`reveal_secret`**
    (`router.TOOLS`); `nucleo/flash/vault_flow.py` resuelve la etiqueta (match difuso, conservador) y el provider
    (`voice/.../nucleo.py`) Y el probe (`nucleo/flash/probe.py`) — impls PARALELAS — entregan el valor **OUT-OF-BAND**:
    nunca entra en un prompt del modelo NI en el observer/logs; el frontend lo pide a **`/api/vault/reveal`**
    (loopback). Si la bóveda está bloqueada → pide desbloqueo (abre el modal); si no existe → propone crear.
  - **CRIPTO (asimétrica + sobre).** `memory/vault.py`: par de claves; la **pública en claro** sella (escribir sin
    clave), la **privada** va ENVUELTA por N métodos de desbloqueo (patrón sobre). Métodos: **passphrase** (Argon2id,
    recuperación + vía Linux) y **passkey WebAuthn `prf`** (Touch ID/Windows Hello, salt del PRF derivado de la
    pública). El desbloqueo es **server-side = modo CÓMODO** (clave privada en RAM con TTL; el default elegido por el
    operador). Rotar la passphrase re-envuelve solo su sobre. El descifrado ESTRICTO en el navegador (zero-knowledge)
    queda para F4/cloud (necesita libsodium-WASM).
  - **FRONTEND NATIVO** (no widget): `frontend/app/components/VaultModal.js` + `services/vault.js` (REST + WebAuthn
    `prf` enroll/unlock) — crear/desbloquear (passphrase O huella), mostrar el valor, gestionar aparatos. Se abre solo
    con los eventos SSE `kind:"secret"` que emite el cerebro (`services/sse.js`). API: `memory/vault_api.py`
    (`/api/vault/*`, loopback en lo sensible). Acceso manual: `window.zaelar.vault()`.
  - **USER RULES DURAS (2ª clase).** `state.security` (p.ej. `secrets_voice`) — configuración/seguridad aplicada
    **determinista EN CÓDIGO**, INVIOLABLE, fuera del cap-8 de las rules de estilo (V2-046). `nucleo/flash/vault_rules.py`
    detecta comandos de voz («no me digas los secretos por voz» → solo pantalla; «modo máxima seguridad»; «léemelos por
    voz») y los persiste. Enforcement en el reveal: modo cómodo (default) DICE el valor por voz; `secrets_voice=False`
    → solo pantalla.
  - **Invariante duro:** passphrase / clave privada / PRF de la passkey JAMÁS en un LLM, worker, log/observer,
    `state` o píldora. Distinta del **credential store** del SISTEMA (`.meshkore/credentials/zaelar.env`, claves de
    zaelar). Testing: dominio `seguridad_datos` (`tester/scenarios.py`, prioridad nº8 en `zaelar-testing.md`; el
    tester usa PASSPHRASE, la biometría no es testeable). Detalle: `V2-060-boveda-secretos-cifrados.md` +
    `zaelar-security.md` / `zaelar-memory.md` / `zaelar-conventions.md`.
- **«Susurro» — auto-auditoría conversacional y mejora continua** (`nucleo/susurro/`, V2-053, 2026-07-17; diseño
  y plan en `.meshkore/roadmap/initiatives/V2-053-susurro-autoauditoria.md`): el bucle test→fix parchea el routing
  del no-razonador caso a caso (81 fixes/5 días, ~55% clase routing) y NO generaliza — la pieza que faltaba es un
  **auditor interno**: un modelo POTENTE (config `§susurro`, por la UI; FUERA del camino de voz → puede razonar;
  default `gpt-4.1-mini`) que, ante **FRICCIÓN** (detector determinista es/en: queja/corrección del operador,
  petición repetida, turno degradado, rail `sin_resolver`, `worker.stuck`, **+ turno de RIESGO V2-061:
  `friction.risky_decision` = acción de widget sin escalar, para intervenir ANTES de la queja**), recibe una ventana
  comprimida (conversación verbatim + decisiones por turno + eventos filtrados + ESTADO) y devuelve correcciones de un
  **catálogo CERRADO** — `repair_say` (frase de reparación → `brain_notes` [SISTEMA], hablada en el turno
  siguiente; el probe también drena, paridad V2-053), `finding` (→ `.meshkore/logs/susurro/findings.jsonl` con
  dedup + topic `susurro.finding`, lo consume el dev-loop) y **`worker_action` (F2, V2-061): RE-RUTEA — dispara el
  worker correcto vía `escalate` cuando el rápido dejó sin ejecutar una acción real (dedup vs sesiones vivas)**.
  **Enchufado SOLO por el bus** (topic semántico
  **`turn.completed`** emitido por `observer.turn_detail`, punto ÚNICO voz+probe — audit de modularidad
  2026-07-17, doc `zaelar-modularity.md`), montado en el lifespan con **kill-switch de 1ª clase**
  (`ZAELAR_SUSURRO` + `susurro.enabled`), cooldown + single-flight, fail-open duro. **Observabilidad TOTAL**
  (regla del operador): eventos kind `susurro` con el payload ENVIADO al LLM, la respuesta CRUDA y cada
  corrección con su ANTES/DESPUÉS → timeline + /debug + bus/log. **INVARIANTE: NUNCA modifica BRAIN
  RULES/prompt de sistema en runtime** — mejora en dos velocidades: runtime corrige la capa MUTABLE (F2/F3:
  user_rules/workers/estado/memoria con gates); los findings cambian la genética por DESARROLLO (git+tests).
  Verificado e2e (suite `tests/e2e/susurro/run_probe_suite.py`, histórico longitudinal + escenario
  `susurro_reparacion` en la batería): queja→diagnóstico correcto→reparación hablada, ciclo ~2.5-2.9s.
- **Acciones ENCADENADAS realidad↔widgets↔memoria + inteligencia asertiva de DOS velocidades** (V2-061, 2026-07-21;
  detalle en `.meshkore/roadmap/initiatives/V2-061-acciones-encadenadas-realidad-widgets-memoria.md`): muchas órdenes
  necesitan su reflejo en la REALIDAD + en los datos locales de un widget + en la memoria, encadenados y verificables
  en el tiempo (detonante: «cancela la ITV» = cancelar en la web donde se reservó → borrar la cita de la agenda →
  actualizar memoria → verificar; NO un `drop` de agenda ni un «hecho» falso). El mini no da para deducir esta clase
  solo (medido). Solución en **tres capas SIN cableado** (condición del operador: situaciones infinitas, la lenta NO
  en cada turno): **(1)** FlashBrain con mejor DISCRIMINACIÓN — la descripción de `escalate_to_slowbrain` distingue
  gestionar la LISTA local de un widget (`widget_data`) de EJECUTAR/DESHACER un COMPROMISO real (escala; el widget es
  ESPEJO) + guard determinista del pronombre suelto (`router.looks_like_bare_ref`) + continuidad conversacional en
  `flash/prompt.py`; **(2)** **«Susurro» que DEDUCE y ACTÚA** (F2, off-hot-path, ver decisión anterior): audita el
  turno de RIESGO por COMPRENSIÓN y RE-RUTEA con `worker_action` sin frenar el turno; **(3)** worker con MÉTODO
  general (`dispatch._METHOD_BLOCK`: entender-plano→localizar-memoria→ejecutar-real→REFLEJAR en widgets/memoria→
  verificar todos los planos→iterar) + puente genérico **`hbwidget`** (`nucleo/widget_cli.py`). No hay rails por-caso:
  el worker deduce el plan de cualquier tarea.
- **Búsqueda web = capacidad COMPARTIDA por los dos cerebros, model-agnóstica** (`nucleo/websearch.py`, V2-022):
  no dependemos de que el modelo traiga búsqueda nativa (Grok/GLM/Z.AI no la tienen; Claude Code sí) — es un
  primitivo PROPIO. **Quién decide buscar = el propio modelo, por function-calling** (no hay clasificador aparte):
  al FlashBrain le llegan la pregunta + el catálogo de tools y él decide en un paso responder de memoria (el ESTADO
  ya va en el prompt), hacer la cuenta él mismo, llamar a `web_search`, o escalar. **TRES modalidades que NO se
  confunden:** (1) **dato directo + SÍNTESIS** (`web_search`, este módulo) → "¿quién ganó?", el tiempo, un precio,
  una previsión; el FlashBrain lo resuelve **EN el turno** (~1-2s, sin tarjeta ni navegador); (2) **navegar un
  marketplace** (Amazon/Wallapop: no hay buscador que dé ese dato, hay que ENTRAR) → el **navegador**
  (`automate_web`, SlowBrain); (3) **investigación/informe** con muchos datos actuales → el **SlowBrain** (CodeAgent
  con `WebSearch`/`WebFetch` nativos de Claude Code, habilitados en `dispatch._tools_for`; y/o este primitivo en
  bucle). **Proveedor por CAPAS, CALIDAD primero, auto-upgrade por key** (`websearch.provider()`): **respuesta-IA**
  ya sintetizada+citada (**Perplexity Sonar** → **Tavily**, si hay `PERPLEXITY_API_KEY`/`TAVILY_API_KEY`) →
  **snippets** (**Brave**, `BRAVE_SEARCH_KEY`) → **GOOGLE vía Chromium propio** (GRATIS, V2-024) → **DDG** (último
  recurso, sin key ni navegador). `WEBSEARCH_PROVIDER` fuerza uno; `BROWSER_SEARCH=0` apaga la capa Google. Sin
  ninguna key el DEFAULT es **Google** (mejor que DDG, gratis). **Capa Google = `nucleo/browser_search.py`**
  (V2-024, idea del operador: no pagar Perplexity si Google es gratis): un **Chromium headless PERSISTENTE y
  CALIENTE** (perfil propio en `memory/_data/search_browser/`, aislado del navegador-widget y del Chrome del
  operador) que vive en el loop del server y se **calienta en el arranque** (prewarm, ver abajo) → 1ª búsqueda ya
  rápida. `search_google()` (async, dueña del browser) parsea de forma CONSERVADORA: el **widget del tiempo**
  (`#wob_*`, respuesta exacta) o un fragmento destacado real como `answer` (ai=True, el cerebro lo adapta); si no,
  answer vacío y el cerebro sintetiza los **snippets orgánicos** (Aemet/ESPN/Marca… mucho mejores que DDG). NUNCA
  da un answer dudoso (una respuesta MAL es peor que ninguna). Puente `search_sync` (agenda en el loop del server
  vía `run_coroutine_threadsafe`) para el `to_thread` de `websearch`. **Fail-open a DDG** si Google bloquea
  (CAPTCHA/tráfico inusual) — Google castiga el scraping de forma intermitente; es gratis a cambio de fragilidad,
  por eso una key de pago sigue ganando. Medido: **~1-2s** (vs DDG 4-11s). Sin ninguna key funciona gratis. **Latencia:** la búsqueda
  es I/O de red → **fuera del event loop** (`asyncio.to_thread`, respeta V2-011); la respuesta se **adapta a
  voz/idioma con el modelo que el turno YA paga** (2º pase; si viene de un buscador-IA solo la moldea, si son
  snippets la sintetiza) → coste marginal ≈0, ni LLM extra ni MCP de pago obligatorio. **Routing** forzado en
  `router.TOOLS` + `prompt._FAST_RULES`. Fail-open (degrada por la cadena; si todo falla el cerebro lo dice, nunca
  revienta ni bloquea la voz). Observabilidad: eventos `search` en `/debug` (proveedor + ai + nº + latencia).
- **Prewarm del camino caliente en el ARRANQUE** (`nucleo/flash/prewarm.py`, V2-024): el PRIMER turno tardaba 6-8s
  y los siguientes ~1s. Causa: la 1ª llamada al FlashBrain (AIMLAPI/Grok tras Cloudflare) monta TLS + handshake +
  arranque del modelo en frío. Se **absorbe en el arranque del server** (lifespan, `create_task`, fire-and-forget,
  SOLO `BRAIN=nucleo`) con una query MÍNIMA (`max_tokens=1`) — corre **mientras el frontend pinta el loader de la
  malla cerebral**, así cuando el usuario puede hablar el modelo YA está caliente (~1s, no 8s). En paralelo calienta
  el **Chromium de búsqueda** (`browser_search.ensure_started`) y **enlaza el loop del server** (`set_loop`) para el
  puente sync de la búsqueda. Nunca bloquea ni lanza (local Ollama ya usa `keep_alive`; sin key no hay nada que
  montar). Medido: prewarm ~2.3s en boot → primer turno real caliente.
- **Prompt del FlashBrain = ESTADO compuesto + petición, ~30 líneas (no ~280)** (`nucleo/flash/prompt.py` +
  `memory.compose_state()`, V2-027, 2026-07-11): el system prompt se recomponía cada turno y era ENORME (persona
  inglesa estática de `voice/prompt.py` + `_FAST_RULES` de ~75 líneas que DUPLICABAN las descripciones de las tools
  + `for_brain()` volcando TODOS los widgets con acciones/payloads/items y AGENDA CONTEXT + briefs de conector, cada
  turno). Saturaba al modelo pequeño (olvidaba acciones, llamaba a `web_search` de más) e inflaba TTFT/coste.
  **Rediseño:** el cerebro recibe **[ESTADO compuesto dinámicamente] + [petición]**. El ESTADO lo compone la
  MEMORIA (`memory.compose_state()` → `(bloque, op, stats)`, contrato en `zaelar-memory.md`): **A** MISIÓN/identidad
  (vive en la memoria — `state.mission`, sembrada al arrancar por `memory_cache.prime()` desde `langs.LangSpec.mission`
  en el idioma del operador, NO un prompt inglés hardcodeado), **B** situacional (operador + widgets ABIERTOS + tareas
  + perfil durable saliente), **C** conversación reciente SINTETIZADA (corto plazo con cap agresivo, NO el volcado
  crudo de 30 líneas ni la memoria larga). Es lo COMPARTIDO por ambos cerebros; cada uno añade su capa TERSA de
  RECURSOS (`nucleo/flash/prompt._flash_layer`: reglas de voz en 3-4 frases + catálogo de widgets `id — misión` con
  sus acciones-nombre inline vía `widgets.brief.for_prompt(open_ids)` + 1 línea de web_search y del navegador). El
  **"cuándo SÍ/NO" de cada tool vive en su descripción** (`router.TOOLS`), única fuente por tool — no se duplica en
  prosa. Items vivos + coach + briefs de conector SOLO cuando su widget está ABIERTO (culpable #6 fuera del turno
  normal). Sigue cacheado FUERA del turno (V2-011: `memory_cache` cachea `compose_state`, refresco async +
  invalidación por `memory.updated`; lectura DIRECTA µs, sin LLM ni retriever). **Frontera dura CANVAS vs DATOS en el
  prompt:** MOSTRAR/ABRIR/CERRAR un widget = TAGS `[[show:ID]]`/`[[close]]` (NUNCA `widget_data`); `widget_data` es
  SOLO para cambiar los DATOS de dentro (reforzado en la regla de voz Y en la descripción de la tool tras verlo
  fallar en pruebas). Medido con INPUT LIMPIO (probe directo al modelo, sin STT): prompt ~30-45 líneas (según widgets
  abiertos), y las 6 rutas correctas (data-op→`widget_data`, mostrar→`[[show]]`, cerrar→`[[close]]`, borrar→
  `delete_widget`, charla→sin tool, dato del mundo→`web_search`). **V2-028** podó el **kickoff**
  (`voice/engine/pipeline/agent.py`): ya NO re-inyecta el brief verboso de capacidades como `user_input` del saludo
  — el system prompt por turno ya lleva el ESTADO + recursos tersos, así el PRIMER turno tampoco arrastra el
  volcado viejo. **V2-029** (tras el e2e completo) arregló 4 asperezas del pipeline conversacional: (a) **frontera
  MEMORIA↔AGENDA** — «recuérdame que <hecho>» (aunque diga "hasta el viernes") NO es una cita NI una escalada: el
  FlashBrain lo **reconoce con naturalidad sin tool** porque el **auto-ingest** (`ingest_utterance`, corre CADA
  turno) ya lo guarda; `add_meeting` es SOLO un EVENTO con fecha/hora; (b) **frase de espera variada + dedup de
  escalada** (`nucleo.py` + `langs.filler_still_working`): si el operador insiste mientras el SlowBrain trabaja, no
  se abre una escalada duplicada y la voz dice "sigo con ello" en vez de repetir el mismo "dame un momento";
  (c) **web_search no pre-responde** y luego busca (evita dos respuestas contradictorias); (d) el **SlowBrain no
  filtra jerga interna** en la voz (`dispatch._build_prompt`: nunca "píldora"/"memoria de largo plazo"/"base de
  datos") + ventana de dedup de tareas de navegador 45→90s. Todo del ciclo e2e; el motor con INPUT LIMPIO ya era
  coherente (el rojo de la batería era ruido de STT del tester + estado polucionado + rigidez del juez).
- **Cerebro de voz = NO-razonador** (regla dura): un modelo de razonamiento añade segundos de "thinking" (5s+ TTFT)
  en el camino de tiempo real → zaelar se queda lento/mudo. El FlashBrain usa SOLO modelos rápidos no-razonadores; el
  razonamiento vive OFF del camino crítico, en el SlowBrain.
- **Routing de modelos — POR INVOCACIÓN** (`config/v2.py`, gestionado por la UI, persiste en `config/v2.json`):
  prioridad = **latencia** sin quedarnos sin inteligencia. Nunca una env global de modelo (concurrencia de sesiones):
  `config/v2.py` guarda los DEFAULTS y el cerebro los pasa en cada invocación.
  - **FlashBrain** (sección `fast`): **producción actual = `anthropic/claude-haiku-4.5` vía AIMLAPI** (NO-razonador;
    `AIMLAPI_KEY` presente en el store `tester.env` + `.env`). El A/B de V2-034 lo eligió por **fiabilidad de
    routing/introspección**. ⚠️ AIMLAPI va tras Cloudflare y 403/blip-ea intermitente (el cliente spoofa User-Agent);
    un blip puntual puede marcar el ◉ `llm` en rojo hasta el siguiente turno OK (health self-clears). **`grok
    (xAI) está BANEADO en el FlashBrain**: el único rápido (`grok-4.20-0309-non-reasoning`) MIS-RUTEA —contesta
    "Hecho"/`widget_data` a una PREGUNTA de memoria, causa de "conversaciones absurdas"—; los correctos (grok-4.3/4.5)
    son razonadores → violan "voz=no-razonador". **NUNCA grok en la capa de voz** (canónico: `zaelar-model-benchmarks.md
    §9/§13`). `nucleo/flash/fast_client.py::resolved_api_key()` resuelve la key **por endpoint** (aimlapi→`AIMLAPI_KEY`,
    groq.com→`GROQ_API_KEY`, gemini→`GEMINI_API_KEY`). **Alternativas válidas** (UI/`config/v2.json §fast` o env
    `FAST_PROVIDER`/`FAST_MODEL`/…): **Groq** (`llama-3.3-70b-versatile`, muy rápido, `GROQ_API_KEY`); **local Ollama**
    (`qwen2.5:14b-instruct`, gratis/sin red pero **patoso y LENTO** —~19s/turno con contención de GPU→ NO como capa de
    voz). ⚠️ NO
    usar `gemini-2.5-flash-LITE` (no invoca tools) ni ningún `*-reasoning`/`3.x-flash` (thinking ON).
  - **SlowBrain CodeAgent** (sección `code_agent`): `provider` `claude_code`/`codex`, con modelo por invocación y
    override por tipo de tarea (`model_memory`/`model_web`/`model_code`).
  - `active_brain()` (env-first `BRAIN`, default `nucleo`) selecciona el cerebro; `BRAIN=direct`/`local` = baselines
    de modelo pelado. Reasoners de nube (GLM-4.6/5.2) NUNCA en el path de voz.
- **Memoria central** (`memory/`, doc `zaelar-memory.md`): un solo SQLite `zaelar.db` (WAL) con sqlite-vec + FTS5 +
  RRF + grafo + olvido-por-peso + capa episódica. **Único escritor** = el agente de memoria (`nucleo/memory_agent.py`);
  el retriever lee directo (WAL). **Invariante de oro de latencia (V2-013, reafirmado por el operador 2026-07-14):
  ESCRIBIR puede ser LENTO — LEER debe ser MÁXIMA VELOCIDAD.** Escribir bien es lo prioritario: dedicarle el tiempo
  que haga falta para colocar cada dato en su capa (ESTADO/CORTO/LARGO), no duplicar, puntuar el peso/importancia,
  organizar los conceptos del grafo y calcular embeddings — todo **off-hot-path** (cola async, fire-and-forget); no
  hace falta que escritura y lectura sean inmediatas. La LECTURA, en cambio, es la que paga el FlashBrain en el turno
  (compone el prompt, responde, actúa) → **JAMÁS un LLM ni I/O de memoria síncrono al leer**. La escritura pasa por
  el **CORAZÓN** (`nucleo/mem_processor.py`, **`gpt-4.1-mini` vía OpenAI** por config `§memory` desde V2-056
  2026-07-20 — bench de destilación §12 (`zaelar-model-benchmarks.md`): **98.3%** vs qwen2.5:7b local 86.2%, que
  queda como OPCIÓN local; key resuelta **POR ENDPOINT** + **SALUD de 1ª clase** (alerta por racha de fallos +
  `status()` — el incidente 2026-07-17/19 lo dejó 2 días caído en silencio) que DESTILA cada turno en **píldoras**
  (dato canónico + metadatos) y decide DESCARTAR/ESTADO/CORTO/LARGO + importancia + `slot` — LENTO a propósito,
  nunca en el turno; fail-open a la heurística regex, que ya NO ensucia (degrada a short+TTL 3d, nunca durable
  crudo). El sueño tiene DOS fases: el consolidador LIGERO (horario) y la **fase REM** (`memory/rem.py`, V2-056,
  diaria): repara vectores + dedup semántico + **INSIGHTS por concepto** + higiene con alerta — detalle en
  `zaelar-memory.md §Sueño PROFUNDO`. **La lectura NUNCA lleva LLM** — tres velocidades
  directas: ESTADO `memory.state()` (µs, cacheado, SIEMPRE en el prompt), CORTO `memory.recent_short()` (µs, working
  set entero, sobre-incluye), LARGO `memory.query()` (retriever RRF ms, bajo demanda + `asyncio.to_thread`, la única
  capa que tolera esperas — con DOS gatillos desde V2-056: prefetch `needs_recall` + **tool `recall`**, el modelo
  decide recordar; y el worker recibe el **dossier v2** de `compose_context` — críticos SIEMPRE + `by_concepts` +
  agenda + reglas). **Cómo la USA el resto del sistema** (guía en `zaelar-memory.md §Cómo la USA el resto del
  sistema`): guardar algo que dijo el operador → `memory_agent.ingest_utterance()`; recordar un resultado/hecho →
  `memory_agent.remember({text,kind[,slot]})`; **volcar un dato entrante de una FUENTE (mensajería/cluster/agente)
  → `memory.ingest_message(source, entity, text[, trust, durable])`** — vía TIPADA unificada (multi-fuente): indexa
  `source`+`entity` en `meta` (→ consulta directa por tipo `memory.recent_by_source(source[,entity])`) y `trust`
  (`operator`/`external` entran al prompt pasivo; **`untrusted`** de peers de cluster queda en **CUARENTENA** —
  nunca en el prompt, solo por consulta explícita, anti prompt-injection); volcar datos de un widget →
  `memory.write(...[,slot])`; leer → `state()`/`recent_short()`/`query()`/`recent_by_source()` según la velocidad.
  **Nunca** BD directa ni LLM/I-O síncrono de memoria
  en la ruta de voz. Sustituye a cualquier memoria externa: la persona/instrucciones se inyectan en cada conexión
  desde `memory/` + `nucleo/flash/prompt.py`. **MONOLINGÜE — la memoria vive en el IDIOMA DEL OPERADOR** (decisión
  2026-07-10): el sistema entero se adapta a UN idioma (el de la persona; castellano por defecto, ver `langs.py`);
  el CORAZÓN destila cada píldora en ese idioma canónico **traduciendo** lo que venga en otro y **nunca descarta un
  dato durable por estar en otro idioma** → la lectura es siempre mismo-idioma (cero gap cross-lingual, sin indexar
  N idiomas). El FlashBrain entiende varias lenguas (STT+modelo) y sus gates son es/en, pero lo que se GUARDA/RECUERDA
  queda en el idioma del operador. Además el FlashBrain **NUNCA expone al operador las capas internas de memoria**
  ("corto/largo plazo", "base de datos"): responde con naturalidad o pide el dato como un humano.
- **Recuperación del recall LARGO = RERANKER model-agnostic, LOCAL por defecto** (`memory/rerank.py` +
  `memory/rerank_local.py`, config `config/v2.py` §`memory`, V2-030, 2026-07-12): a escala (cientos de recuerdos)
  el embedding local bi-encoder ordena "borroso" — la respuesta está en el top-10 (~82%) pero no en el top-1/3. Un
  **cross-encoder** que reordena el top-N del RRF **leyendo query+recuerdo juntos** cierra la mayor parte del hueco:
  medido (`tests/e2e/memory/bot/scale_eval.py`, 442 durables) **recall@1 41.6→56.2%, recall@3 62.3→68.7%** (empata
  al techo OpenAI 69%), MRR 0.544→0.642, lat p50 114→260ms. **Default `local`** = `jina-reranker-v2-base-multilingual`
  vía fastembed (ONNX/**CPU → cero contención con la GPU** de STT/TTS), gratis, 100% local. **Mismo patrón
  LLM-agnostic que el routing del cerebro** (`fast`/`code_agent`): proveedor CONFIGURABLE por la UI/config, **cloud =
  cambiar `rerank_provider`** — `openai` (LLM listwise, techo +8.6pts recall@1 a cambio de coste/datos-a-la-nube) /
  `cohere`/`voyage` (slots) / `off`. **Invariantes:** SOLO recall LARGO, **fuera del hot path** (ya es bajo demanda +
  `to_thread`), **ESTADO/CORTO intactos** (lectura µs sin modelo); **FAIL-OPEN duro** (error/sin-modelo → orden del
  retriever intacto, nunca rompe); no-generativo (reordena, no inventa → no viola no-alucinación); fundido con
  recencia/importancia (`rerank_blend`). Calienta el modelo en el arranque (`prewarm._warm_rerank`). El **embedding
  también es configurable** (§`memory.embed_provider/embed_model`, `auto`=local por defecto) pero cambiarlo EXIGE
  **re-embed** (`memory/reembed.py`: firma del modelo en `<db>.embedsig` + `check()` que avisa al arrancar si el
  modelo cambió sin reindexar — **nunca mezclar espacios vectoriales en silencio**). **Subir el techo del recall =
  iniciativa `V2-031`** (memoria de fidelidad máxima; ver `zaelar-memory.md §Re-ranking` + `zaelar-model-benchmarks.md
  §6/§7`): el techo real es `found@10` (~82%, lo que el retriever ni trae). **Hallazgo T1 (medido): un embedding local
  más fuerte (bge-m3 1024d) NO sube el techo** — el eje NO es el bi-encoder. Las palancas reales, en orden: (1)
  **write-completeness** (el diagnóstico mostró que la mayoría de "no recuperados" NO están guardados, no son fallos
  de retrieval), (2) retrieval de lo guardado (pool + **paráfrasis al escribir** + grafo), (3) **memoria
  auto-evaluativa continua** que se auto-sondea y REPARA (T5), (4) consolidación semántica. Externo = solo tier
  PREMIUM (nunca default; o los mismos modelos en VPS-GPU propio). ⚠️ El test bot SIEMBRA con embeddings `hash`
  (`runner.py:702`) → medir recall SEMÁNTICO exige re-embeber con el modelo real (`embed_bench.py`); en producción se
  escribe siempre con embeddinggemma.
- **Sistema Nervioso** (`bus/`): pub/sub in-process + log durable SQLite + puente SSE. Es el sustrato de eventos
  entre voz, loop, agentes y frontend (`escalate.requested`, `memory.updated`, `widget`, `observer`…). Transporte
  híbrido (directo en la ruta caliente de voz; eventos para async/fan-out). Nada de brokers externos.
- **Perfiles remote/local** (`ZAELAR_PROFILE`): `remote` = voxtral/cartesia/aimlapi; `local` = whisper/kokoro/ollama.
  Override por componente con `ZAELAR_STT`/`ZAELAR_TTS`/`ZAELAR_LLM_PROVIDER` (híbridos). El servidor LiveKit local
  (`--dev`) no necesita TURN; en prod se configura el servidor/Cloud.
- **Multidioma con catálogo alineado** (`voice/engine/core/langs.py`, single source of truth; default **castellano**):
  al cambiar de idioma (⚙ o por voz), **STT (lang+initial_prompt), voz TTS e idioma de respuesta del cerebro se
  re-alinean juntos**. Invariante: **la voz nunca puede quedar cruzada con el idioma** — las voces Kokoro son
  por-idioma (`ef_dora`=es, `af_bella`=en) y `voices.selected_voice()` rechaza una voz no nativa del idioma activo
  (cae al default); Cartesia es multilingüe (una voz + `language`). Un idioma solo entra al catálogo si tiene voz
  nativa verificada (hoy **es + en**). Los providers leen `langs.current_code()` (lee `ZAELAR_LANGUAGE`, que el ⚙
  escribe en caliente) → el cambio aplica **al reconectar**.
- **TTS local por hardware (Metal)** (`voice/engine/speech/tts/kokoro.py`): en Apple Silicon el TTS Kokoro corre
  **in-process por Metal** (`mlx-audio`, `ZAELAR_TTS_DEVICE=auto|metal|fastapi`) → ~0.3s al primer audio. `prewarm`
  carga el modelo Metal en el executor idle y el entrypoint lo reutiliza. mlx-audio tiene un **bug de shapes en su
  vocoder** que revienta algunas frases (peor en español) → `try/except` con **fallback por-frase a Kokoro-FastAPI**
  (Docker/CPU), y el warm es resiliente (una frase mala no desactiva Metal). ⚠️ El fallback necesita Kokoro-FastAPI
  corriendo; el perfil local debe levantarlo. Non-Mac → Kokoro-FastAPI/CPU o Cartesia (remote).
- **TTS cloud FIABLE — ElevenLabs** (`voice/engine/speech/tts/elevenlabs.py`, V2-035, 2026-07-13): el Kokoro Metal
  local **peta mucho** por contención de GPU con Ollama (voz lenta/entrecortada/muda) → para producción y el deploy
  en la nube la voz debe ir SIEMPRE bien. **ElevenLabs** entra como TTS cloud (streaming, auto-cancel en barge-in,
  igual que Cartesia) con modelo **BARATO/rápido `eleven_flash_v2_5`** (multilingüe → castellano nativo). Se activa
  por la UI (⚙ `tts_provider=elevenlabs`) o `ZAELAR_TTS=elevenlabs`; voz por `ELEVENLABS_VOICE_ID`/⚙ (multilingüe,
  cualquiera habla ES). Clave `ELEVENLABS_API_KEY` en el **credential store** (nunca en el repo). Validado end-to-end
  (síntesis real). Providers TTS disponibles: `cartesia` · `elevenlabs` · `kokoro_local`.
- **STT local por hardware** (`voice/engine/core/accel.py` + `speech/stt/whisper_local.py`): backend por hardware
  con fallback **metal** (Apple Silicon, `mlx-whisper large-v3-turbo`) → **cuda** → **cpu** (`ZAELAR_WHISPER_DEVICE`).
  **Anti-alucinación + robustez a ruido LEJANO**: gate de energía/duración antes de transcribir
  (`ZAELAR_STT_RMS_GATE`=**0.02** subido de 0.012 el 2026-07-12, `ZAELAR_STT_MIN_SEC`=0.25) — el operador habla a
  ~60cm (rms alto ~0.05-0.1); un grito/TV/tráfico a varios metros llega atenuado (~0.005-0.018) → cae bajo el umbral
  y no se transcribe, así una voz de fondo NO dispara un turno fantasma (que gastaría STT+memoria+eventos). Es el
  knob PRINCIPAL de ruido: súbelo si aún se cuela, bájalo si pierde tu voz. Complementa al **VAD Silero**
  (`activation_threshold`=**0.5** subido de 0.4, `prefix_padding`=0.8 conserva el onset → sin "te comes la primera
  palabra"): el VAD filtra lo no-humano, el gate RMS filtra lo humano-pero-lejano (que el VAD dejaría pasar). Mata
  además el "Gracias/Thank you" fantasma + decodificación anti-bucle (`condition_on_previous_text=False`, temp 0,
  thresholds; `initial_prompt` por idioma). Pendiente (más adelante): rechazar TV/voz cercana no-operador
  (fingerprint/diarización, tipo Super Whisper).
- **Sistema de widgets** (`widgets/`, doc completa en `zaelar-modules.md §Widgets`): tarjetas dinámicas en el
  canvas, **una carpeta autónoma por widget** (`manifest.json` + `widget.js` + `data.py` + `notes.md`). Invariante
  prime: **un widget nunca puede romper el resto** (fallo → estado vacío, aislado). **Frontera DATOS vs CÓDIGO**
  (V2-025, ver decisión siguiente): **TRABAJAR con los datos** de un widget (sus `actions` declaradas → `apply_action`)
  lo hace el **FlashBrain al instante** con `[[widget.data:ID]]`, NUNCA escalando; **CREAR/MODIFICAR el CÓDIGO** de un
  widget (nuevo widget, cambiar su UI/esquema/lógica) lo hace el **SlowBrain** (razonamiento con tools, escribe
  código, ~1-2 min). El FlashBrain también hace `[[show]]`/`[[close]]`/`[[move]]` y **BORRAR un widget** (V2-017:
  determinista → no necesita agente headless). Solo CREAR/MODIFICAR-código y volcar datos-a-buscar escalan por
  `escalate_to_slowbrain`, forzado en código.
- **Acciones de widget = FRONTERA datos/código + gate de irreversibilidad (NO de escalado)** (`widgets/actions.py`,
  V2-025, 2026-07-11): el flag `"safe"` estaba SOBRECARGADO — mezclaba «¿puede la capa rápida hacer esta mutación?»
  con «¿es irreversible?». Consecuencia real: `add_meeting` («añade una cita a la agenda») estaba `"safe":false` →
  se **auto-escalaba a un AGENTE DE CÓDIGO** que no tenía nada que programar (solo el mismo `apply_action`), tardaba
  minutos y se colgó >6 min. Una mutación de datos NO es trabajo de código. **Rediseño:** toda acción DECLARADA en el
  `manifest.json` (`actions: {name:{desc,payload}}`) es una **data-op** que el FlashBrain ejecuta ÉL MISMO por su
  `apply_action` (o el mailbox del owner si es `backed`) — jamás se escala. `widgets/actions.py::classify()` da el
  modo canónico (una sola fuente de verdad que leen el gate `nucleo/flash/frontend.py::action_mode`, la frontera
  forzada del provider y el brief): **FAST** (por defecto, la hace ya), **CONFIRM** (irreversible: la hace igual pero
  pide OK antes, reutilizando `widgets/confirm.py` — hermano de `nucleo/danger.py`; se marca `"confirm":true`/
  `"irreversible":true` o se deduce de un heurístico ESTRECHO pagar/enviar/publicar/borrar-todo sobre nombre+desc),
  **ESCALATE** (vía de escape EXPLÍCITA `"escalate":true`, rara, NO para datos). El **SlowBrain queda SOLO para
  CREAR/MODIFICAR el CÓDIGO**. **Compat:** `"safe":true`→FAST; `"safe":false`→ya NO escala (FAST, o CONFIRM si el
  heurístico salta); `"safe"` deprecado (los manifests nuevos usan `confirm`). **Guía de uso OBLIGATORIA y
  VALIDADA:** cada widget con `apply_action` declara sus `actions` + un `"usage"` (cómo conducirlo, que el FlashBrain
  ve en `widgets/brief.py`); el gate del generador (`widgets/generator.py::_validate_actions_sync`) **rechaza** un
  widget cuyas acciones declaradas no casen con su `apply_action` real (acción declarada sin rama = muerta; rama sin
  declarar = invisible al cerebro) y el `_CONTRACT` obliga a regenerarlas en sincronía. La confirmación IRREVERSIBLE
  se ejecuta por `apply_action` al decir "sí" (`widgets/confirm.py` acarrea la mutación) — **sin escalar a código**.
  El FlashBrain sigue NO-razonador.
- **Data-ops por FUNCTION-CALLING + resolución de referencias a items** (`nucleo/flash/router.py` tool `widget_data`
  + `widgets/refs.py`, V2-026, 2026-07-11): V2-025 dejó la SEMÁNTICA correcta, pero el modelo rápido no-razonador
  (Grok) **no emitía de forma fiable el tag inline** `[[widget.data:ID]]` (dice "hecho" y no lo hace) y, cuando lo
  emitía, **inventaba los ids** de los items (marcó `done` con `taskId="09:00–11:00"`, el rango horario, en vez de
  `t_daemon`) porque no los conocía. Function-calling SÍ es fiable (el mismo modelo llama a `web_search` perfecto).
  **Fix:** (1) las data-ops se invocan por una **tool** `widget_data(widget_id, action, item, payload)` (camino
  PRINCIPAL; el tag inline queda de RESERVA) — ambos convergen en `_apply_widget_data` del provider, que respeta el
  gate FAST/CONFIRM/ESCALATE de V2-025. (2) **Referencias a items en lenguaje natural**: el operador no sabe ids;
  el modelo pasa `item` en lenguaje natural ("la tarea del daemon", "el proyecto CryptoKnight") y `widgets/refs.py`
  lo resuelve al **id REAL** contra los items VIVOS del widget (`data.py:ref_index()` → `[{id,label,field}]`), NUNCA
  lo inventa; el campo a rellenar (`taskId`/`projectId`…) se deduce del `payload` declarado en el manifest, así
  "descarta el proyecto CryptoKnight" (→`projectId`) apunta al proyecto y no a la tarea homónima. Fuzzy stdlib
  (difflib + tokens, acento-insensible); si es **ambiguo/no existe, PREGUNTA** en vez de actuar sobre el item
  equivocado. El brief expone `items ahora:` por widget (labels vivos) para que el modelo referencie con
  naturalidad. (3) **Fechas/horas del habla**: `live_state` da la fecha EXPLÍCITA (hoy+mañana en YYYY-MM-DD, el
  modelo ya no busca la fecha por web) y `agenda.data` normaliza "mañana"/"a las cinco" → `date` correcto + `17:00`.
  (4) Ack hablado (`langs.data_ack`) si el modelo va directo a la tool sin hablar (nunca mudo). Medido con INPUT
  LIMPIO (sin el STT del tester): las 4 data-ops apuntan al item correcto y la cita aparece en `state.json`.
- **Widgets en BACKGROUND — ejecución OFF-SCREEN con ciclo declarado** (`widgets/background.py`, V2-034,
  2026-07-12): un widget no siempre trabaja solo cuando está a la vista. Algunos deben seguir vivos AUNQUE la
  tarjeta esté cerrada — el de mensajería recibe mensajes de sus conectores, los tría y **escribe lo nuevo en la
  memoria**, así una pregunta por voz ("¿tengo mensajes?") responde con datos ACTUALES aunque el widget nunca se
  haya abierto. Es capacidad de PRIMER NIVEL: **cada widget decide DELIBERADAMENTE si corre en background** (la
  mayoría NO — un buscador, un gráfico computado al leer, son foreground-only y `view_data()` va bajo demanda).
  Un widget que SÍ lo necesita declara su CICLO en el manifest: **`"background": {"every": "1m"}`** (atajo string
  `"1m"`/`"30s"`/`"1h"` o nº de segundos; **mínimo 1s**). Dos formas, una sola idea declarativa: **(A) passive +
  `background`** (nuevo, LIGERO, sin proceso) — el planificador llama a `data.py:tick(ctx)` cada ciclo **fuera del
  hot path** (`asyncio.to_thread`, porque `data.py` es stdlib); `tick` refresca (`store.save` idempotente → SSE
  solo si cambió) y **vuelca a memoria** por el `ctx` SANCIONADO (`ctx.remember(text, slot=…)`/`ctx.ingest(…)` —
  así `data.py` NO importa el core y sigue stdlib-only; usa `slot` para SUPERSEDE, no acumular); **(B) backed** (ya
  existente, PESADO) — un `owner.py` con conexión viva (Chromium del navegador, conectores de mensajería) que se
  auto-agenda: un backed ES background por naturaleza, y si declara `background` recibe un comando `tick` en su
  buzón cada ciclo. **Aislamiento total**: un `tick` que revienta/tarda no tumba la voz ni otro widget ni el
  planificador (capturado, trazado `observer` kind `background`, solape evitado por widget). Arrancado en el
  lifespan del server junto al supervisor backed. El gate del generador (`_validate_background`) **rechaza** un
  passive que declare `background` sin `tick()`, o un `every` inválido; el `_CONTRACT` y `AGENTS.md` lo enseñan
  como consideración OBLIGATORIA de todo widget. Ejemplos: `mensajeria` (backed, off-screen→memoria→voz) y
  `meteo-soria` (passive `every:1h` → `tick` vuelca "Tiempo en Soria ahora…" a `slot=weather:soria`).
- **Ciclo de vida de widgets + memoria — CREAR/MODIFICAR = SlowBrain; BORRAR = FlashBrain con confirmación**
  (`widgets/lifecycle.py` + `widgets/confirm.py`, V2-017, 2026-07-09): borrar un widget NO se escala (arreglado el
  bug en que "borra el widget de Meteo" caía al ramal de CREAR de `nucleo/agentes/code.py` y generaba un widget
  basura). El FlashBrain llama a la tool **`delete_widget(widget_id)`** → abre una **CONFIRMACIÓN** (overlay
  «¿Borrar? Sí/No» pintado a nivel del host sobre la tarjeta — genérico, no toca el `widget.js`); el operador
  confirma por **botón** (`POST /widgets/{id}/confirm`) o por **voz** ("sí/no", detección DETERMINISTA es/en en
  `widgets/confirm.classify_reply` + tool `confirm_widget_delete`). Solo entonces `lifecycle.delete_widget` borra
  (rm carpeta + `store.delete` + invalida catálogo + cierra la tarjeta). **Integración con la memoria** (protocolo
  en `zaelar-memory.md §Acciones ↔ memoria`): **nunca se borra el histórico** — al crear se registra un evento de
  ALTA (`record_created`), al borrar una **LÁPIDA** (`«X» BORRADO el <fecha> a petición del operador`), así el
  recall responde *"ese widget lo mandaste borrar ayer"* aunque ya no exista. Borrar ≠ cerrar (`[[close]]` se
  reabre; borrar es para siempre). El cerebro cambia los datos de
  un widget con `[[widget.data:id]]{"action":..,"payload":{..}}[[/widget.data]]`, que llama al MISMO `apply_action()`
  que los botones de la UI (vocabulario declarado en el `manifest.json`, bajo `"actions"`). Quien PROGRAMA los
  widgets es un **Claude Code local headless** (`claude -p`, `widgets/generator.py`). **Storage independiente por
  widget, CÓDIGO y DATOS en carpetas separadas** (`widgets/store.py` → `widgets/_data/<id>/state.json` +
  `store.data_dir(id)` para media) — separado del código (`widgets/<id>/`) para que `[[modify]]`/regeneración nunca
  borre datos. **Refresco por SSE, nunca polling**: `store.save()` es el ÚNICO punto que emite "los datos de este
  widget cambiaron"; el canvas re-pinta el widget abierto una sola vez, solo si sus datos cambiaron — cero
  `setInterval`. **Comunicación mediada por el cerebro**: los widgets son tontos, no se hablan entre sí; el cerebro
  orquesta (lee uno, `[[push]]` a otro). Generación asíncrona (~1-2 min) → el resultado vuelve al cerebro como nota
  `[SISTEMA]` (`voice/brain_notes.py`) para que no cante "hecho" ni invente ids. Validación ejecuta `view_data()`
  antes de admitir al catálogo; `modify` con rollback; rechaza clases CSS que colisionen con `frontend/app/styles.css`.
  **Regla:** cualquier sub-flujo de un widget (conectar una cuenta, formulario, confirmación) se queda DENTRO de su
  misma tarjeta, nunca una ventana/barra separada — y un canal de mensajería nuevo (email, X…) se añade DENTRO de
  `mensajeria`, nunca como widget propio.
- **Widgets "backed" + supervisor** (`widgets/supervisor.py`, INI-016): el *kind* `backed` añade un widget con
  **proceso propio** junto al `passive`. `manifest.json` declara `"kind":"backed"` + `"backend":{"owner":"owner.py"}`;
  el owner expone `async start()/stop()/handle(action,payload)` y es el **ÚNICO escritor** de su `widgets/_data/<id>/`.
  El supervisor (arrancado en el lifespan de `server/__init__.py`, MISMO loop que la voz) escanea el catálogo por
  `kind=="backed"`, importa cada `owner.py` y lo corre con **mailbox** (asyncio.Queue), **reinicio con backoff** y
  **desactivación tras N fallos** (`WIDGETS_BACKED_MAX_FAILS`=4, degrada al último estado congelado); todo trazado por
  `voice/observer.py`. Un owner que revienta nunca tumba la voz ni otro widget. La cara (`data.py`+`widget.js`) pasa a
  READ + ENCOLAR: `widgets/server_api.py:_route_backed()` mete el comando en el mailbox del owner (misma ruta para
  `POST .../action` y el `[[widget.data]]` del cerebro). Endpoint genérico `GET /widgets/{id}/asset/{name}` sirve un
  binario (p. ej. una captura) desde el `data_dir()`, path-safe + no-cache. Un backed puede exigir un modo de cerebro
  con `"gate":"nucleo"` (el supervisor solo arranca su owner con ese cerebro).
- **navegador — navegador web REAL + agente de tareas web** (`widgets/navegador/`, INI-016; doc COMPLETA en
  `zaelar-modules.md §Navegador`): primer widget `backed`. **NO iframe** (X-Frame-Options/CSP) → Chromium (Playwright)
  en `owner.py`; el widget muestra una **captura** (asset endpoint, cache-bust por `shot_rev`). **HEADLESS POR
  DEFECTO** (corre por detrás, sin robar foco). Visible solo opt-in (`navegador_visible`/`ZAELAR_NAVEGADOR_VISIBLE=1`).
  **UNA ventana, perfil PERSISTENTE** (`widgets/_data/navegador/profile/`, gitignored) **AISLADO del Chrome del
  operador**; puerto debug configurable (`navegador_remote_port`/`NAVEGADOR_REMOTE_PORT`, nunca 9222/9200). Acepta
  banners de cookies (`_dismiss_overlays`: consentmanager/OneTrust/Didomi). YouTube = videoId scrapeado. Buscador =
  Bing (`NAVEGADOR_SEARCH`). **Dep:** `playwright>=1.61` + `python -m playwright install chromium`.
- **navegador — TAREAS: una tarea = una tarjeta = una pestaña** (INI-016): dos formas de conducir desde el FlashBrain
  (tool calls, NO tags): **`browse_web`** (navegar a mano; tarjeta SINGLETON id `"browse"`) y **`automate_web(goal)`**
  (TAREA; una tarjeta por objetivo). 1:1 tarjeta ↔ pestaña ↔ tarea. Piezas: **`tasks.py`** (registro
  id/estado/fase/eventos/resultados/pregunta; SSE por tarjeta); **`owner.py::TaskBrowser`** (una pestaña por tarea,
  misma ventana; `handle("automate")` SPAWNEA → N en paralelo; popups absorbidos `_reap_popups`; cerrar tarjeta cierra
  pestaña); **orquestación** (crea tarea → abre tarjeta → el **SlowBrain PLANIFICA** → bucle ejecuta off-voz);
  **bucle `agent.py`** HÍBRIDO DOM→visión→modelo-avanzado (cerebro barato dedicado `NAVEGADOR_AGENT_MODEL` def
  `anthropic/claude-haiku-4.5`; `NAVEGADOR_AGENT_MODEL_STRONG` al atascarse; humano Bézier+jitter; anti-atasco). 
  **Resultados**: `extract_listings()` (anuncios reales, exige precio, dedup, sin ads) + `summarize_results()`
  (modelo barato → top-3 + conclusión). **Anti-proliferación EN CÓDIGO**: 1 acción por turno · `automate_web` no
  llama a `browse_web` · `tasks.similar_active()` deduplica refinamientos del STT. **Tarjeta** vertical/redimensionable:
  mini-navegador + línea de FASE con spinner + feed de HITOS + resultados.
- **navegador — AUTENTICACIÓN = abrir un navegador REAL** (INI-016, 2026-07-10): para usar la cuenta del operador
  (Wallapop, Google, LinkedIn…) **NO se heredan las cookies del Chrome del sistema** (cifradas por Keychain): se
  loguea UNA VEZ en NUESTRO perfil persistente y ya queda. Piezas (todo en `widgets/navegador/`):
  - **Nunca inventa credenciales** — detector DETERMINISTA de muro de login (`agent._looks_like_login`: URL de
    login conocida o campo password) que actúa ANTES de dejar teclear al modelo (arregla el bug 2026-07-10 en que el
    bucle tecleó `user@gmail.com` en el login de Google y giró en círculos). El bucle también tiene la acción
    `need_login` para muros que la URL no delata.
  - **Ventana real + login versátil** (`owner.py::_authenticate`→`_reach_login`): abre el Chromium **VISIBLE**
    directamente en el login del sitio — URL de login conocida (`_LOGIN_URLS`) o, si no, abre el dominio y **clica el
    enlace «iniciar sesión»** por texto multi-idioma **evitando el de registro**. La sesión se guarda sola en el
    perfil persistente (`widgets/_data/navegador/profile/`).
  - **Auto-detección, CERO pasos manuales** (`_login_watch`): vigila la ventana (~2.5s) y detecta solo cuándo entras
    (dejó login/registro + cookies nuevas) → cierra sola y sigue con la tarea. El botón «Ya he iniciado sesión» y el
    tool de voz `login_done` quedan como red de seguridad, no se piden. Timeout 10min → recordatorio, nunca mata.
  - **Guarda «ya autenticado»** (`_already_authenticated`): antes de abrir NADA comprueba (headless) si ya hay
    sesión (no es login + no hay botón «iniciar sesión» visible) → NO reabre el login; retoma la tarea directamente.
  - **Fallback**: `_authenticate_window` (acción `auth_window`) es el mismo flujo de ventana real; se PROBÓ un login
    interactivo dentro del canvas (headless, para cloud) pero se DESCARTÓ (solo cubría logins normales; fallaba en
    Google/CAPTCHA/passkeys) — queda en reflog, no en el árbol.
  - **Memoria** (`auth_memory.py`, vía fachada): el SECRETO (cookies) NUNCA entra en memoria (vive en el perfil); solo
    el HECHO de la sesión (`record_session_established`, slot por sitio → supersede) y un CHECKPOINT recuperable
    (`set_state({auth_pendiente})`, calca `nucleo/reset.py`). Ver `zaelar-memory.md §Acciones↔memoria`.
  - **Tools FlashBrain** (`nucleo/flash/router.py`): `authenticate_web(site)` (SOLO login explícito: «conéctame a
    X»; las tareas/búsquedas web se ESCALAN a automate) y `login_done`. Operator-only por construcción.
  - **Confirm-gate**: antes de una acción IRREVERSIBLE (`nucleo/danger.py` comprar/pagar/publicar/borrar) la tarea
    PARA y pide OK (feed+voz, timeout→no ejecuta). `automate`/`click`/`type` = `safe:false`.
- **«Una sola mente» — el FlashBrain conduce TODA conversación** (V2-069, 2026-07-25): hablar con el operador o con
  otro agente es el MISMO acto → **un solo motor**, no piezas paralelas. El acto se modula por dos perillas: **QUIÉN**
  (operador/agente → de ahí cae la CONFIANZA: tools y memoria permitidas) y **PROFUNDIDAD** (reflejo/razonar/actuar →
  de ahí cae el modelo: rápido/razonador/worker; la voz pone el tope duro no-razonador, off-voz puede razonar). Los
  procesos complejos (investigar/tools) NO son un sistema aparte: son la profundidad «actuar» del mismo acto (misma vía
  de workers). **Perfil UNTRUSTED** (agente) = tools apagadas EN CÓDIGO + system identidad-safe (`build_cluster_system`
  nunca toca `compose_state`) → la memoria/PII del operador es incorruptible por una charla de agente. El estado de
  cada conversación vive en su **cápsula** (`connectors/meshkore/capsule.py`): memoria-de-relación scope-partido sobre
  la MISMA memoria central (dossier + resumen + objetivo + bucles abiertos + FASE saludo→sondeo→trabajo→cierre +
  detección de atasco), raíz=operador (confiable) vs peer=untrusted (cuarentena). La FASE mata la re-presentación (no
  saludar en trabajo/sondeo); el **guardia de atasco** (bridge, umbrales 2/4) corta el bucle pronto (asertivo 1× →
  callar + avisar al operador). Susurro hereda el canal por `turn.completed`. Detalle:
  `.meshkore/roadmap/initiatives/V2-069-una-sola-mente.md`.
- **«Homeostasis» — el LATIDO AUTÓNOMO del sistema** (`nucleo/homeostasis.py`, V2-070, 2026-07-25; detonante: el
  incidente del motor LiveKit degradado del 2026-07-25 — tras ~7h de bucle `wait_pc_connection timed out` el chat/voz
  dejó de responder y NADA lo curó). El sistema emula a un humano en **tres niveles, y solo dos piensan**: **Mente**
  (FlashBrain — conduce, PIENSA con modelo), **Conciencia** (Susurro — audita la CONVERSACIÓN, PIENSA con modelo) y
  **Autónomo/homeostasis** (esta pieza — mantiene la MÁQUINA, **NO piensa, cero LLM**). Como el latido o el sistema
  inmune: no se decide, se ejecuta. **Por eso vive AL LADO del cerebro, no dentro** — meter reintentos/reciclados/
  rotación en el FlashBrain lo ensuciaría con lógica que no es inteligencia. **Regla del binario del operador: cada
  recurso tiene DOS estados, sano/degradado → curar** (no 200 estados). Es el watchdog de sesión promovido a **código
  durable** que no muere al cerrar la sesión. Arrancado en el lifespan con el patrón `start(app)`/`stop()` de los
  otros supervisores (messaging/widgets), fuera del bucle de voz. **Tres chequeos**, cada uno aislado (fail-open
  duro — un fallo del mantenimiento JAMÁS toca voz/chat): **(1) MOTOR LiveKit** — detección IN-PROCESS por el logging
  del SDK (`wait_pc_connection timed out`/`entrypoint did not exit`, ventana+umbral); si es **SEGURO** (voz apagada +
  canal inactivo ≥2min) **recicla el worker embebido** (`aclose`+`make_server`+nueva task, SIN reiniciar el proceso —
  clava el incidente del 25/07 en caliente), con cooldown anti-bucle; si NO es seguro (voz/canal vivos), **avisa al
  operador** (1×) y no toca nada; **(2) LOGS** — rota `timeline-latest.jsonl`/`meshkore.jsonl` por rename (seguros:
  abren `"a"` por escritura → el siguiente append recrea) al superar el tope + poda archivos viejos; **(3) CÁPSULAS**
  — evicta las concluidas+viejas y acota el total (`sys_kv capsule:*`, con `memory.kv_keys`/`kv_del`). Kill-switch de
  1ª clase `ZAELAR_HOMEOSTASIS`; observabilidad TOTAL (evento `homeostasis` en el timeline). **Invariantes:** NUNCA
  toca el FlashBrain ni la PII del operador; reciclar solo cuando es seguro, si no avisar; determinista y testeable
  SIN incidente real (funciones puras + watcher + rotación real: `nucleo/test_homeostasis.py`, dominio 9 del mapa de
  tests). La memoria ya se auto-cura (schema/olvido/dedup); esta pieza cubre lo que NO: motor de voz, logs, cápsulas.
  Detalle: `.meshkore/roadmap/initiatives/V2-070-homeostasis-anti-degeneracion.md`.
- **Canal nativo MeshKore** (`connectors/meshkore/`): 3er I/O (voz+chat+cluster), conducido por el **MISMO motor del
  FlashBrain en perfil UNTRUSTED** (V2-069 «una sola mente»): hablar con el operador o con un agente es el MISMO acto.
  `connectors/meshkore/brain.py` adapta el canal al motor (resuelve el TIER de modelo off-voz, hoy GLM-5.2) y delega en
  `nucleo/flash/cluster.py` (FastClient **no-streaming** `complete()` + `prompt.build_cluster_system` identidad-safe +
  defensas de `dialog`, **tools APAGADAS en código**). Un peer puede hacer que zaelar razone y hable, nunca actuar. El
  estado de la conversación vive en la **cápsula** (`connectors/meshkore/capsule.py`, memoria-de-relación scope-partido)
  — ver la decisión clave «V2-069». El enrutado seguro de input no confiable al `CodeAgent` (deny-tools/sandbox) sigue
  pendiente (V2-010).
- **Seguridad del canal de cluster** (`connectors/meshkore/security.py` + `bridge.py`): el cluster habla con agentes
  externos **no confiables**. Controles DUROS, no solo prompts (detalle en `zaelar-security.md`):
  - El **canal lo conduce el motor del FlashBrain en perfil UNTRUSTED** (V2-069): **tools APAGADAS en código**
    (`nucleo/flash/cluster.py` no ofrece ninguna) + system **identidad-safe** (`build_cluster_system` NUNCA llama a
    `compose_state` → no filtra nombre/PII del operador ni el catálogo de widgets). No hay superficie de
    tool/terminal/fichero que denegar. La frontera de seguridad es un **perfil de capacidades determinista** ligado
    al trust del interlocutor. Postura fail-closed.
  - **Memoria del cluster = observación PASIVA, COMPRIMIDA y CUARENTENADA** (`connectors/meshkore/mem_ingest.py`,
    V2-021 T170): el bridge destila cada intercambio con un peer (entrante+saliente) en una **síntesis evolutiva
    por peer** (modelo LOCAL off-hot-path, fire-and-forget; fail-open acotado) guardada con
    `slot="cluster:<cluster>:<peer>"` + `trust="untrusted"` → NUNCA en el prompt pasivo ni en el recall; solo por
    `recent_by_source` ("¿qué has hablado con Zalo?"). Es la síntesis en prosa que nutre el DOSSIER de la cápsula
    (V2-069). Contenido redactado (secretos) y handles neutralizados antes de persistir. Apagable con `MESHKORE_MEMORY=0`.
  - **Allowlist de tags en turno de cluster**: solo `cluster.send`/`cluster.done`; `connect`/`disconnect` son
    operator-only (bloqueados desde un turno de peer).
  - Entrada: peer envuelto en `⟦UNTRUSTED PEER MESSAGE⟧` (con neutralización de fence-escape) y `trailer()` **al
    FINAL** del prompt — invariante *nuestro prompt va último*. Salida: `scan_outbound()` **bloquea entero** ante
    secreto duro y **redacta** solo huellas (`did:key` + `MESHKORE_SECRET_TERMS`); los nombres de modelo NO se
    redactan (tema legítimo).
  - **Protección de RECURSOS — que no nos endosen el trabajo caro** (V2-071, 2026-07-25; el TERCER robo tras datos e
    inyección): un peer puede dirigirnos para que generemos SU código/informe → gastamos NUESTROS tokens sin
    reciprocidad. Se detecta el DESEQUILIBRIO y se protege **en SILENCIO** (no se le comunica al peer). Hermano del
    guardia de atasco de V2-069: determinista, en el bridge, tolerante a la asimetría normal (un diagrama/decisión
    puntual NO salta — exige volumen + ratio + señal de offload). `security.looks_like_offload()` (detecta peticiones
    de PRODUCIR, es/en, acentos normalizados) + balance por-peer en la cápsula (`given`/`received`/`offloads`/
    `code_out`, `capsule.meter`) + `capsule.resource_verdict()` (equilibrado/sesgado/explotación). Protección:
    directiva SILENCIOSA inyectada antes de generar (sé breve · **el código va por el REPOSITORIO, no por el canal**)
    + `security.guard_code_outbound()` (un VOLCADO grande de código → puntero al repo, como se redacta un secreto;
    siempre activo, snippet pequeño pasa) + aviso al operador 1× en explotación + evento observer `resource` (la
    DETECCIÓN que pidió el operador). Env: `MESHKORE_CODE_MAX_CHARS`/`_LINES`. Detalle:
    `.meshkore/roadmap/initiatives/V2-071-proteccion-recursos-cluster.md`.
  - Plano de control REST `/api/meshkore/*`: **loopback-only** (o `MESHKORE_API_TOKEN`), anti DNS-rebind, y `/send`
    pasa por `scan_outbound`. Transporte `wss://` obligatorio (salvo `MESHKORE_ALLOW_INSECURE=1`). Flood cap
    (`MESHKORE_MAX_INFLIGHT`, def 8).
  - El cluster (texto+URLs sobre WS) **no tiene ruta a micro/cámara/voz** (client-side sobre la sesión WebRTC local).
    Postura `MESHKORE_SECURITY=strict` por defecto.
- **Reglas en TRES niveles + PACTO de conversación agente-agente** (V2-072, 2026-07-25; detalle en
  `.meshkore/roadmap/initiatives/V2-072-pacto-conversacion-agente-agente.md`): las reglas se aplican
  **jerárquicamente** — **(1) SISTEMA/duro** (genética BRAIN RULES + seguridad: trailer, tools-off, `scan_outbound`,
  guardia de recursos V2-071 — inviolable, en código) **> (2) OPERADOR** (`state.rules` V2-046; y por-peer) **> (3)
  PACTO** = normas **NEGOCIADAS entre los dos agentes** para SU relación. El pacto **solo existe en el túnel
  agente-agente** (cluster), nunca en un canal con un humano (WhatsApp), y **nunca afloja** un nivel superior (solo
  restringe nuestra conducta, jamás concede capacidades — vocabulario CERRADO). Vive en la **cápsula** por-peer
  (`capsule.pact`: `cadence_s`/`medium`/`scope`/`note`/`by`). Se **propone al SALUDAR** (reconcilia V2-067: sigue sin
  proponer objetivo/tarea, pero SÍ normas de comunicación — cadencia, código-por-repo, alcance), la mente lo
  **registra** con el tag `[[cluster.pact:<cluster>]]{to,cadence_s,medium,scope,note}` (allowlist del turno de
  cluster) cuando hay acuerdo, se **inyecta** en cada turno (`pact_compose`, bajo el trailer y las reglas del
  operador) y la **CADENCIA se aplica de verdad** (throttle real en `cluster.send`: `capsule.cadence_wait` espera lo
  pactado antes de otro mensaje → arregla la queja de que bombardeábamos a zalo). Un pacto del OPERADOR (`by=operator`)
  no lo pisa el peer. Consultable (va en el prompt) y enmendable (el tag actualiza). Tests: `test_pact.py`, nodo 6.6.
- **Criterio de conversación por INTELIGENCIA — parar/ceder el turno cuando no fluye** (V2-073 → **rediseñado a
  V2-075** por decisión del operador, 2026-07-26): con el OPERADOR la conversación siempre FLUYE; con un **agente
  externo** que se embucla, no sigue el ritmo o nos hace perder el tiempo, hay que **valorar con criterio** y, si no
  fluye, **PARAR** — no bombardear. **CLAVE (corrección de principio):** el juicio semántico de «esto no tiene
  sentido / el otro no me sigue» **NO se hace con patrones hardcodeados** — un regex de frases («⛔», «no puedo», «503»)
  solo se adapta a UN peer y falla con el siguiente; las formas de degenerar son infinitas. **Lo decide un MODELO**
  (`connectors/meshkore/evaluator.py`): un evaluador INDEPENDIENTE (2ª perspectiva, read-only, catálogo CERRADO
  `health`∈flowing/stuck/dead_end/imbalanced/off_track × `action`∈continue/concise/hand_back/pause, fail-open) que lee
  la ventana reciente + métricas y juzga como un humano. SEGURO sobre contenido untrusted (sin tools; distinto de
  Susurro+`worker_action`, diferido a V2-010). Corre **off-hot-path en el heartbeat** (throttle `MESHKORE_EVAL_SECS`,
  solo charlas activas); el bridge **aplica** el veredicto (ceder turno con `capsule.PACE_HANDBACK` / pausar+avisar /
  conciso). La **DECISIÓN es del modelo; el código ejecuta.** Lo DETERMINISTA queda solo para lo estructural y
  genérico: repetición EXACTA (dedup, quema de tokens), `capsule.near_repeat` (casi-repetición, señal), ratio de
  recursos, seguridad. Detalle: `.meshkore/roadmap/initiatives/V2-075-criterio-conversacion-inteligencia.md` (+ V2-073
  histórico). Tests: `test_pace.py`, nodo 6.7.
- **Sello de VERSIÓN — saber qué código corre y qué versión generó cada línea** (`version.py`, V2-074, 2026-07-26):
  tras varios reinicios con código nuevo no había forma de CONFIRMAR que la instancia viva y las líneas del timeline
  eran de la versión actualizada. `version.py` expone `VERSION` semántica (a mano) + **SHA corto de git** (cambia por
  commit) + arranque del proceso → `short()` = `2.74+<sha>`. Se sella en **tres sitios**: (1) **instancia** — item
  `version` en `/api/status` (short + uptime); (2) **observabilidad** — `observer.emit` añade `ver` a **cada evento**
  del timeline → se ve qué versión produjo cada línea y se distinguen sesiones/reinicios; (3) **frontend** — el
  `StatusPanel` (◉) pinta los items genérico → la Versión sale sola. **Prueba del reinicio:** el `sha` de
  `/api/status` debe coincidir con `git rev-parse --short HEAD`; si no, la instancia NO cargó lo nuevo. **Subir
  `VERSION` a mano** al cerrar un bloque notable. Detalle: `.meshkore/roadmap/initiatives/V2-074-sello-version.md`.
- **Proveedor Architect** (`connectors/architect/`, doc en `zaelar-modules.md §Architect`): el daemon MeshKore
  compartido de la máquina (`https://127.0.0.1:5573` — zaelar NO arranca daemon) entra en el **catálogo de
  proveedores de código/agentes**, junto al Claude Code headless que programa widgets y al SlowBrain. El cerebro
  DECIDE y transmite la intención del operador (`[[architect.ask:<proyecto>]]…[[/architect.ask]]` /
  `[[architect.new]]{json}[[/architect.new]]`); el **architect-master** de cada proyecto planifica, ancla tareas y
  despacha agentes; el resultado (30s-10min, asíncrono) vuelve por `voice/proactive` + nota `[SISTEMA]`. **Un ask a la
  vez por proyecto**. Tags **operator-only** (la allowlist del bridge de cluster no las admite). Token en `.env`
  (`ARCHITECT_TOKEN`, rotable desde el cockpit), nunca renderizado en briefs/voz.
- **Mensajería personal UNIFICADA con triaje** (`connectors/whatsapp/` + `connectors/telegram/` sobre
  `connectors/messaging/`; widget `mensajeria` `backed`): zaelar lee el **WhatsApp** y el **Telegram** personales del
  operador — ambos enlazados por **QR pintado en el widget** — como **conectores STATELESS** que solo PUBLICAN al bus
  (`connector.msg` entrantes, dedup por `messageId`; `connector.status` link+QR) y drenan `msg.mark_read`. El **triaje
  + store viven DENTRO del owner del widget** (`"gate":"nucleo"`): un **clasificador LOCAL agnóstico de plataforma**
  (`qwen2.5:3b` vía Ollama — nada personal sale de la máquina; fallback remoto por `MSG_TRIAGE_MODEL`) decide qué es
  relevante, vuelca el contenido a `memory/` y avisa por `voice/proactive` + `[SISTEMA]`, marcando leído lo resumido.
  **UN SOLO store unificado** (`widgets/_data/mensajeria.json`) y **UN SOLO widget**: lista plana por urgencia con
  **badge por plataforma**, tarjetas de conexión con QR inline, control por voz `[[msg.read/dismiss/clear:N]]`
  (self-closing, operator-only; enruta por `item.platform`). Read + mark-read + **RESPONDER** (V2-051: tool
  `reply_message` → data-op `reply` con **confirm-gate** que lee el borrador antes de enviar; cola `pending_reply` +
  `msg.reply`/`ReplyInbox` por conector; hoy EMAIL, WhatsApp/Telegram lo heredan). **Acoplamiento**: WhatsApp =
  **vendoring** (bridge Baileys copiado + parcheado `// ZAELAR-PATCH:` + `VENDORED_FROM.md`, aislado de dependencias
  externas); Telegram = **black-box lib** (Telethon de terceros, Python puro in-process); **Email = stdlib puro**
  (IMAP/SMTP, `connectors/email/`, lógica vendorizada del adaptador de Hermes — V2-051). Slots futuros dentro del
  mismo widget: LinkedIn, X. **Envío a un contacto por NOMBRE + contactos en memoria + red de agentes = V2-052 (diseño).**
- **Configuración MANEJADA POR LA INTERFAZ — "instala una vez, todo lo demás desde la UI"** (invariante de producto;
  doc `zaelar-conventions.md §Configuration is UI-managed`): el usuario doméstico NO edita `.env` NUNCA. Cualquier
  capacidad que haya que activar o que pida credenciales (un conector, una key) se configura con un **flujo guiado
  dentro del widget**. La config runtime vive en JSON gitignored que ESCRIBE el frontend: `config/settings.json` (⚙:
  STT/TTS/voz/idioma), `config/connectors.json` (flags+credenciales de conectores) y `config/v2.json` (routing de
  modelos), cada uno con su módulo dueño y **vista pública redactada** (secretos → `<clave>_set: bool`). **El store
  MANDA sobre `.env`** (env = fallback power-user/headless). La API de control
  (`connectors/messaging/server_api.py POST /api/messaging/{plataforma}/connect|disconnect`) escribe el store Y
  arranca/para el subsistema **en caliente** → el QR/estado aparecen solos en el widget. Todo conector futuro sigue
  este patrón.
- **Tema dark/light** (`frontend/app/services/theme.js` + `core/store.js`, doc en `zaelar-modules.md §Frontend`):
  **dark por defecto** — señal `theme` persistida en `localStorage`, toggle ☾/☀ en el `TopBar`. Todo `styles.css`
  corre sobre variables CSS en `:root` redefinidas bajo `:root[data-theme="light"]`; cero ramas de JS por tema. Los
  **widgets** (aislados con su propio `<style>`) heredan el tema vía un contrato público `--hb-*` (`--hb-bg`,
  `--hb-ink`, `--hb-muted`, `--hb-line`, `--hb-accent`/`--hb-accent2`, `--hb-risk`, `--hb-neutral`, `--hb-warn-*`) —
  **nunca hex hardcodeado** — para que un widget abierto se repinte al vuelo. El prompt del generador
  (`widgets/generator.py _CONTRACT`) exige este contrato. Kit opcional de clases `hbk-*` en `styles.css §WIDGET KIT`.
  **`widgets/{id}/widget.js` se sirve con `Cache-Control: no-cache`** (`widgets/server_api.py`) — sin esto un fix
  podía quedar invisible por caché del navegador.
- **Controles del orbe = «EL OJO» — 7 iconos como párpado superior + ECG como párpado inferior (el orbe = iris,
  zaelar personificado)** (`frontend/app/components/Orb.js` + `frontend/app/lib/ecg.js`, doc en `zaelar-modules.md
  §Frontend`; V2-014 cuenco → V2-039 ojo, operador 2026-07-17 · almendra v4 2026-07-22): el conjunto se lee como un
  OJO formado por **los ICONOS como párpado superior y el PULSO como párpado inferior — sin trazo extra arriba**
  («arriba van los iconos, no una raya»). `ecg.js` dibuja SOLO el párpado inferior = el **electrocardiograma vivo**
  (late con el `loop.tick` real ~1 Hz vía `store.pulse`; se acelera con carga; plano = sin pulso real), rebanada de
  la almendra con comisuras a la altura del centro del orbe (±2.16·radio; alto ±1.24·radio → ancha, no huevo). Los
  7 iconos se colocan por CSS **SOBRE el MISMO círculo** (y = R−√(R²−x²): 0/6/23px para los 5 centrales; los 2
  extremos —reloj/robot— NO llegan a tocar las comisuras a propósito, ver nota de spacing más abajo), exteriores
  a ±149 → iconos y pulso cierran la almendra en las comisuras con el orbe de iris. Siete controles **sin marco**
  (izq→der): **⏰ cron · 🧠 memoria ·
  🔊 altavoz · ⏻ power (CENTRO/ápex) · 📝 subtítulos · ☾ tema · 🤖 gate**. **⏻ power** = la ÚNICA excepción al
  always-on: apagado EXPLÍCITO y persistido (`hb_power_off`) de la sesión de voz — `main.js` NO auto-reconecta
  mientras esté apagado; clic para volver — y, como el resto, es un `.orbic` sin marco (azul=on/gris=off), NUNCA
  el círculo relleno rojo que tuvo antes (operador 2026-07-22: "estropea la visión del ojo"). **☾ tema SUBIÓ del
  TopBar** (genérico/personal): un ÚNICO icono (luna), azul=oscuro/gris=claro — **nunca se cambia por el icono del
  sol** al desactivar (operador 2026-07-22: mismo lenguaje on/off en azul/gris que el resto de controles, sin
  intercambiar el glifo). Los iconos del
  PROYECTO (`TopBar.js`: ◉ estado · ⌗ docs · ◷ debug · ⚙ · 🧭 · Reset) se quedan arriba. El párpado lo dibuja CSS
  (`translateY` por `nth-child`: centro alto, extremos buceando a las comisuras); la curvatura de ambos arcos casa
  (φ≈72°). Estado visual: azul = on/abierto, gris = off/cerrado. 🔊 silencia la voz (invariante auto-correctiva
  anti-desmute del vendor) · 📝 muestra/oculta el **texto en vivo** · 🤖 **gate de atención** (OFF/gris = `always`;
  ON/azul = `wakeword`, solo actúa con «zaelar/harvis») alterna `attention_mode` **EN VIVO** por la MISMA costura de
  settings del ⚙ (`POST /api/settings`; `voice/attention.py::mode()` lee `ZAELAR_ATTENTION` cada turno, sin
  reconectar) y refleja el modo real al cargar (V2-016 T139/T140). El texto que dice zaelar sale como **subtítulo tipo teleprompter** sobre el
  orbe (últimas ~3 líneas) y va **SINCRONIZADO CON LA VOZ**: la fuente es la **transcripción de LiveKit acompasada al
  audio** (`RoomEvent.TranscriptionReceived` → `store.captionSeg`). El orbe NO se mueve (overlay `position:absolute`).
  Los subtítulos son **solo en vivo**; el histórico vive en el ChatWall. **Invariante de producto: nada de
  notificaciones flotantes** — un aviso proactivo sale por voz + subtítulo + entrada de chat (deduplicada con
  `store.pushAgentChat`), nunca un toast.
- **Visor de memoria (🧠 «mapa de la memoria») — DOS VISTAS** (`frontend/app/components/MemoryMap.js` +
  `memory/api.py::map()` + ruta `GET /api/memory/map`, V2-014 · redseño 2026-07-10): vista de sistema a pantalla
  (overlay, como `/debug` — NO un widget) que se abre desde el 🧠 del cuenco del orbe (`store.memOpen`). Un **toggle
  en la cabecera** alterna dos representaciones de la MISMA memoria (lo pidió el operador: separar contenido de
  organización, y NO mezclar corto con largo porque son storages distintos en la realidad):
  - **SLOTS** (la memoria TAL COMO SE GUARDA): tres **capas en COLUMNAS lado a lado** (izq→der, cada una un bloque
    con rail de color): **ESTADO** (tabla fija `memory/state.py`, conciencia de sí mismo/entorno; hoy casi vacía y
    VERLO vacío es el objetivo), **CORTO PLAZO** (`level=='short'`) y **LARGO PLAZO** (la MÁS ANCHA — `mid`/`long`).
    Cada recuerdo = una tarjeta con texto + **scoring** + fecha + metadatos (kind, weight con barra, access, pinned) —
    zoom (rueda) + pan (arrastre). **Iluminación en vivo** aquí (write=verde/overwrite=ámbar/query=azul, `[data-mid]`).
  - **CONCEPTOS** (la memoria TAL COMO SE ORGANIZA): **mapa conceptual de red** — cada concepto es un **nodo circular
    dimensionado por su nº de datos** (el número va DENTRO), relacionado con OTROS conceptos por aristas de
    **co-ocurrencia** (dos conceptos se enlazan si comparten una píldora; grosor = nº compartido). **SIN contenido** —
    es el plano de cómo se conecta la información (salud↔hábitos↔deporte↔objetivos↔proyectos…). **CORTO y LARGO son
    DOS MAPAS SEPARADOS** (paneles apilados): el LARGO usa el grafo persistido (aristas T126 del CORAZÓN), el CORTO
    deriva conceptos al vuelo (`memory/concepts.py::derive_concepts` — el corto no persiste aristas, son píldoras
    efímeras). El vocabulario de conceptos vive en **`memory/concepts.py`** (substrato): un solo sitio para cómo se
    ESCRIBE (backstop de `memory_agent`) y cómo se DIBUJA.
  `GET /api/memory/map` (read-only, `no-cache`) devuelve `{state, layers:{short,long}, concept_graph:{short,long con
  nodes[+count]/links[+weight]}, concepts, edges, counts}`. **Tiempo real sin polling** (ambas vistas): el server
  puentea la señal `memory.updated` del bus al topic `observer` (→ `GET /events`) como `{kind:"memory"}`
  (`server/__init__.py`); `services/sse.js` hace `store.bumpMemory()`; `MemoryMap` re-fetchea (debounced) SOLO si
  está abierto. Tema `--hb-*` (cero hex).

## Testing y rueda de mejora (INI-013)

zaelar se prueba **solo, sin micrófono humano**, con un agente tester independiente que HABLA con zaelar y un
JUEZ que evalúa lo que zaelar HACE (no lo que dice). **El PLAYBOOK autocontenido de "cómo se prueba" (trigger "lanza
un test del bot", Paso 0 de alineación, prioridades, evaluación, archivado) vive en
`.meshkore/docs/ops/zaelar-testing.md`**; el catálogo legible de escenarios en `tester/anexos/catalogo-escenarios.md`
y el histórico de informes por día en `tester/reports/<YYYYMMDD>-<desc>/`. Docs canónicas:
**«¿funciona todo bien?» → `./.venv/bin/python tests/run_testmap.py`**: el MAPA DE TESTS navegable — todo el testing
ordenado por **DOMINIO → CASO DE USO → CANAL** (9 dominios, nodos `N.M`), responde con el árbol numerado
"1.1 ✅, 1.2 ✅, 2.1 ✅…" y marca aparte los nodos VIVOS (exigen `make run`). Es la fuente de verdad de qué fichero
cubre cada caso; la narrativa/segunda-opinión (cobertura, huecos, duplicación) en `tests/TESTMAP.md`. Se extiende
1000→10000 por hojas (añadir ficheros a un nodo o un nodo nuevo), sin reescribir la espina. Docs canónicas:
`.meshkore/roadmap/initiatives/INI-013-voice-tester.md` (registro de pruebas + oleadas),
`.meshkore/docs/ops/zaelar-observability.md` (cómo depurar por logs), `.meshkore/docs/ops/zaelar-model-benchmarks.md`
(modelos/latencias). Cómo funciona:

> **TRES formas de testing** (el DETALLE completo — cómo lanzar, formatos, evaluación — vive en
> **`.meshkore/docs/ops/zaelar-testing.md`**, no aquí): (1) **MEMORIA** (`tests/e2e/memory/bot/`, taxonomía A–X);
> (2) **VOZ e2e** (INI-013, `tester/`) — realista, lento, con ruido de STT; (3) **canal de PRUEBA del FlashBrain por
> TEXTO** (V2-032, el más RÁPIDO, headless) — **úsalo siempre que toques cerebro rápido / conversación / prompt /
> memoria-estado / tools**: `make reset` → `make flash-serve` → `make flash T="…"` (ver el playbook para el resto).

Cómo funciona (canal de VOZ e2e, INI-013):

- **El tester** (`tester/`, `python -m tester.run`): se une a la MISMA sala LiveKit de zaelar como un **2º
  participante**, **habla por TTS** y **escucha+transcribe con Deepgram STT**. Un cerebro **DRIVE** (DeepSeek vía
  AIMLAPI) conduce el escenario/objetivo turno a turno. Uso: `./.venv/bin/python -m tester.run --scenario <id>` o
  `--goal "..." --turns N`, `--no-open` para no abrir navegador. **Requiere zaelar ya arrancado** (`make run`). Bucle
  nocturno: `tester/overnight.sh` + `tester/guard.sh`.
- **El juez** (`tester/judge/`, GLM-4.6 vía Z.AI, fallback DeepSeek): se suscribe a `GET /events` (el bus del
  observer) y evalúa el **comportamiento OBSERVABLE**: acciones de frontend (widgets `show`/`close`, navegador), tags
  del cerebro, escalados, latencias reales. Escribe un informe por sesión en `tester/runs/report_*.md` (+ `.json`,
  versionados; los `.wav`/`.log` se ignoran).
- **El prompt de iteración — el loop autónomo** (`/loop 20m <prompt>`, skill `loop`): re-invoca SIEMPRE el mismo
  ciclo: **(1) guarda** (`curl /api/brain`; si no responde, `make run` y esperar) → **(2) prueba** la siguiente
  oleada → **(3) arregla** en código si hay hallazgo → **(4) re-verifica** (reinicia si tocó `.py`) → **(5)
  documenta** una entrada FECHADA nueva al final de INI-013 → **(6) repite**.
- **Cron test→fix (cada 15 min) — el PROCEDIMIENTO ESTÁNDAR** (`tester/cron_tick.sh`, doc en INI-013 §Cron test→fix
  loop): cada disparo prueba **UN caso de uso COMPLETO** (no saludos triviales) rotando por `tester/scenarios.py`
  (mensajería · widgets · navegador/moto · conectores · memoria · búsqueda V2-022 · agenda · idea compleja…), el
  JUEZ lo puntúa (`overall>=4` = PASS, `dispatch_dead`/null = INFRA), y el agente **arregla el código si falla**,
  reinicia si tocó `.py`, **re-corre ese mismo escenario** y documenta. `cron_tick.sh` asegura zaelar UP, SALTA si el
  operador está en vivo, rota con cursor y aplica watchdog. Se prueba contra la **cuenta viva del operador**
  (autorizado: admin/pruebas; añadir/quitar datos reales OK, NUNCA crear perfiles ni romper).
- **Oleadas de prueba (A-L)**, en INI-013: A=fiabilidad de escalada, B=directiva de estilo, C=memoria de arranque,
  D=widgets, E/F=WhatsApp/Telegram, G=paste/ficheros, H=multilenguaje, I=latencia, J=regresión, K=widgets nuevos,
  L=cron/proactividad.
- **Evaluación A FONDO de la MEMORIA** (bot dedicado `tests/e2e/memory/bot/`): taxonomía de **24 dimensiones (A–X)**
  anclada a los benchmarks del estado del arte (LongMemEval/LoCoMo/MemBench/MemoryAgentBench/MemConflict/BEAM/STALE/
  Mem2ActBench) — alimenta la memoria incremental por el CAMINO REAL (`_brain_view`, sin LLM en la lectura) + pytest
  de regresión + tester en vivo para lo que es del LLM. **Teoría canónica** en `zaelar-memory.md §Evaluación de la
  memoria`; **mapa/cobertura** en `TAXONOMY.md`; **control de calidad cada 50 casos** en `EXIGENCIA.md`; oleadas
  fechadas en INI-013. Fronteras abiertas (T175/T177/T178/T179/T181/T182/T183) y mejoras aplicadas en `V2-021`.
- **UN solo sistema de log** (`voice/observer.py::emit(kind,label,…)`): TODO evento —cerebro, widgets, transcripts,
  `state`, `vad`/barge-in, `metric` STT/TTS/turno, `error`— se registra ahí y sale por SSE `GET /events` +
  `.meshkore/logs/timeline-latest.jsonl` + `.meshkore/logs/sessions/<id>.jsonl` + el anillo de `/debug`. El motor de
  voz (`agent.py`) llama a `emit()` directamente; `voice/engine/pipeline/instrument.py` **ya no** registra eventos —
  solo el handshake de arranque (topic `vl2`, para el splash) y una grabación de mic OPCIONAL (`ZAELAR_RECORD_MIC`,
  def OFF). El juez consume `GET /events`. Detalle en `zaelar-observability.md`. **Anti-flood (2026-07-12):** las
  `VADMetrics` (y cualquier métrica sin latencias reales) NO se registran — se disparaban ~2/s de forma continua
  (más con ruido de fondo), sin dato útil, y cada evento hacía 2 escrituras de fichero SÍNCRONAS en el hilo de voz
  → floodeaban el SSE y sumaban latencia; se conservan STT/TTS/LLM/EOU con números. El puente `memory.updated`→SSE
  va **coalescado** (trailing-debounce 400ms, `ZAELAR_MEM_SSE_COALESCE_MS`): una ráfaga de mutaciones de un turno =
  UNA señal (el visor re-fetchea con debounce, no pierde reactividad). **Trazabilidad (V2-044,
  `voice/trace.py`):** cada estímulo (frase del operador voz/chat, kickoff, probe, cron, chispa, tap de UI, peer
  de cluster) nace con un **`trace` id** y TODA su cadena derivada (tools, tags, rails `span=rail:K`, workers
  `span=worker:N`, navegador `span=web:tN`, memoria) llega sellada — ContextVar por `create_task`/`to_thread` +
  costuras explícitas (payload de escalada→`SessionRecord.trace_id`, registro de tareas del navegador, run del
  rail). El visor ◷ pinta un chip por fila (click→filtra la cadena) y el botón **⛓** alterna a la vista
  **Trazas** (árbol frase→actor→eventos). Detalle en `zaelar-observability.md §Trazabilidad` + iniciativa V2-044.
- **Routing de modelos del tester**: DRIVE + juicio barato = **DeepSeek vía AIMLAPI**; juicio competente = **GLM-4.6
  vía Z.AI**. Claves en `.env` + `.meshkore/credentials/tester.env` (gitignored).
- **Docker SÍ se permite AQUÍ** (aislamiento, LiveKit dedicado del tester) — es la ÚNICA parte del proyecto donde
  Docker es aceptable; el CORE de zaelar NUNCA depende de Docker.
- **Limitaciones CONOCIDAS del arnés**: (a) `--goal` SIEMPRE usa canal VOZ; (b) el Deepgram STT del propio tester a
  veces garbla/mezcla idiomas o "oye" el audio de zaelar → ante señal sucia, mirar `timeline-latest.jsonl`.

## Deploy (producción)

Ver `.meshkore/docs/deploy/zaelar-deploy.md` — instrucciones completas para Fly.io + CloudFlare TURN.
Estado actual: **sin deploy en prod** (destruido por ahorro de costes).

## Hard rules

- **COMMITEA PRONTO Y SIEMPRE — cada agente y cada sesión commitea SU propio trabajo.** En cuanto una tarea está
  hecha se commitea, **incluso ANTES de probarla**: si algo sale mal se revierte (`git revert`/`reset`), pero perder
  código NO es reversible. Con varios agentes/sesiones trabajando en paralelo, **un árbol de trabajo sin commitear
  es la causa nº1 de pifostios irreparables** — un agente empieza a trastear encima de los cambios sin commitear de
  otro y se lía un desaguisado que no entiende nadie. Reglas: (1) **trabajo terminado = trabajo commiteado**, con
  mensaje claro de QUÉ y POR QUÉ; (2) **nunca cierres una sesión ni cambies de tarea dejando cambios sin commitear**;
  (3) commitea en incrementos pequeños y coherentes, no un mega-commit al final; (4) si encuentras trabajo de OTRO
  agente sin commitear, NO lo pises: commítealo aparte y atribuido, o pregunta. Tras commitear, **PUSHEA** (ver la
  regla "Commitea Y PUSHEA siempre" más abajo — política del operador 2026-07-16). Barato deshacer un commit;
  carísimo perder código.
- No commitear `.env`, `.venv/`, `logs/`, `config/settings.json`, `config/connectors.json`, `config/v2.json`
  (todos en `.gitignore`).
- No commitear `~/.hermes/memories/USER.md` — es perfil personal (la memoria puede sembrarlo, solo-lectura), no va
  en el repo.
- **Nada que configure el usuario final se pone en `.env`.** Toda activación/credencial de un conector o integración
  se maneja desde la UI (store `config/connectors.json`/`config/v2.json`, escrito por la UI; env solo fallback de
  power-user). Un conector nuevo SIEMPRE trae su flujo de setup guiado en el widget.
- **Commitea Y PUSHEA siempre** (política del operador, 2026-07-16): en cuanto una tarea/incremento está commiteado,
  `git push origin <rama-actual>` para mantener origin al día. (Deroga la regla anterior "no push sin confirmación".)
  Sigue en pie: NUNCA `pull`/`merge`/`reset`/`checkout` para traer una versión remota al local (el árbol local es la
  verdad); nunca pushear `.env`/secretos/config gitignoreada; no mergear a `main` salvo que el operador lo pida.
- **Cerebro de voz = NO-razonador** (regla dura): un razonador no cierra el turno a tiempo → zaelar se queda
  lento/mudo. El FlashBrain (`nucleo/flash/`) usa solo modelos rápidos no-razonadores. **Modelo POR INVOCACIÓN**,
  nunca una env global de modelo (concurrencia de sesiones). El routing (`fast` + `code_agent`) vive en `config/v2.py`
  (gestionado por la UI).
- No crear módulos sin declararlos en `.meshkore/public/cluster.yaml`.
- No editar `.meshkore/roadmap/state.json` a mano — es un artefacto generado.
- No crear carpetas `docs/` ad-hoc — toda la documentación va en `.meshkore/docs/<categoría>/`.
- **El CORE de zaelar NO debe requerir Docker.** El servidor LiveKit corre desde el binario nativo `livekit-server`
  (`make install-livekit`); Docker es solo un fallback opcional. El **sistema de testing (INI-013) SÍ puede usar
  Docker** — esa es la única parte donde Docker es aceptable.
