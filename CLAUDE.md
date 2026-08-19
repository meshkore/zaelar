# zaelar

## Public repository language rule

This repository is public. All source-code comments, docstrings, inline explanations, developer-facing
instructions, and maintenance notes MUST be written in English, recursively throughout `engine/`. Before
finishing a change, search the touched area for Spanish comments and translate every one. Do not introduce
new Spanish comments or developer documentation. Spanish user-facing labels, voice responses, localization
catalogues, and intentional multilingual product content are runtime data and remain subject to the i18n
rules rather than this comment-language rule.

> **`.meshkore/` es una CARPETA REAL de ESTE repo** (2026-07-28, antes era un symlink a `../.meshkore`). engine
> es el repo PÚBLICO OSS y lleva SU propio `.meshkore/` con el contexto MeshKore Standard del MOTOR —
> arquitectura, convenciones, módulos, seguridad, roadmap del motor, roles de agente (`team/`), `public/cluster.yaml`
> y `STANDARD_VERSION`: quien clone el repo dice «carga el estándar MeshKore» y tiene todo el contexto y las tareas.
> Lo que se ignora (`.gitignore`) es solo el estado runtime PRIVADO del self-hoster (`credentials/`, `logs/`,
> `timeline/`, `snapshots/`, `.runtime/`, `agents/`) — sus propias claves/logs, nunca al repo.
> **Lo que NO vive aquí:** la gestión de NEGOCIO/proyecto entero (cloud/GTM, `launch-readiness`, coordinación
> engine+web+cloud) vive en `../.meshkore/` de la RAÍZ del workspace (repo aparte, privado) — ver `../CLAUDE.md`.

> ⚠️ **NI NUESTRO PASADO NI NUESTRO FUTURO SE PUBLICAN** (2026-08-14, norma del operador). Este repo guarda lo
> que ayuda a entender y correr el motor **HOY**. Lo que cuenta cómo llegamos o a dónde vamos existe en local
> pero está **gitignoreado**, así que quien clone el repo NO lo tiene y muchas referencias de estos documentos
> le apuntarán a carpetas vacías. Es deliberado, no un despiste:
>
> | No se publica (existe en local) | Sí se publica |
> |---|---|
> | `.meshkore/roadmap/` — iniciativas y plan | `.meshkore/docs/` — arquitectura, convenciones, módulos, ops, seguridad |
> | `.meshkore/modules/*/tasks/` y `*/logs/` — tareas y bitácoras | `.meshkore/public/cluster.yaml`, `STANDARD_VERSION` |
> | `.meshkore/team/` — roles internos de nuestros agentes | `CLAUDE.md`, `README.md` |
> | `tests/voice/e2e/agent/reports/` — informes de ejecuciones | `tests/README.md`, `tests/TESTMAP.md`, catálogo de escenarios |
>
> El detonante fue una fuga real: los informes de la batería de voz son **transcripciones de sesiones**, y 110
> de 186 llevaban dentro el nombre del operador y las tareas de su agenda. La regla general que deja: el
> CATÁLOGO de qué se prueba es público y útil; el DIARIO de lo que se probó es nuestro. Igual con el roadmap —
> saber cómo está construido el motor le sirve a quien lo clona; saber qué pensamos construir, no.

Asistente personal por voz **multidioma** (**inglés por defecto**, y se pasa SOLO al idioma del operador en
cuanto lo detecta — ver «Arranque idiomático» abajo), siempre activo. Arquitectura: STT →
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
| **¿Por qué ESTOS modelos en la memoria?** (respuesta canónica) | `zaelar-memory.md §Modelos de la memoria` · denso: `zaelar-model-benchmarks.md §12.3/§12.4` · crudo: `tests/memory/e2e/bot/resultados/` |
| **Canal de cluster — algoritmo de punta a punta** | `.meshkore/docs/architecture/zaelar-cluster-channel.md` |
| **Multidioma / i18n (arranque idiomático, generación de bundles)** | `.meshkore/docs/architecture/zaelar-i18n.md` |
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
**Paso 0 = ALINEACIÓN** (comprobar que `tests/voice/e2e/agent/scenarios.py` cubre los módulos principales y los cambios de las
ÚLTIMAS 48 h — `git log --since` + decisiones `V2-0xx` nuevas; si falta, añadir el escenario ANTES de lanzar) →
prioridades (latencia · coste bajo · memoria · búsqueda precisa · **navegación web profunda Wallapop/coches.net con
extracción de datos reales, con/sin login** · robustez · multiidioma) → lanzar (`tests/voice/e2e/agent/run_battery.sh` con settle,
o `cron_tick.sh`) → evaluar con el JUEZ distinguiendo **bug real (trace-confirmado) vs ruido de STT del tester vs
rigidez del juez** (y comparación HUMANA de lo extraído en navegación) → arreglar código si hay bug → **archivar el
informe del día en `tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/`** (histórico consultable). Catálogo legible de escenarios en
`tests/voice/e2e/agent/anexos/catalogo-escenarios.md`. No hay que recordar los pasos: viven en el playbook.

**Contrato obligatorio para agentes de desarrollo:** antes de probar cualquier cambio, leer **`tests/README.md`**.
Es la guía operativa corta compartida por Claude Code, Codex, humanos y CI; `zaelar-testing.md` conserva el
diagnóstico profundo. La entrada preferida es `./.venv/bin/python -m tests run <suite> [--case ID] --no-open`:
mantiene el exit code de terminal y, al mismo tiempo, publica cada ejecución en el **Test Observatory** estable de
loopback **`http://127.0.0.1:8765`**. `--no-open` solo evita abrir una ventana: NO desactiva el visor, de modo que el
operador puede observar mientras el agente trabaja. La aplicación real sigue en `http://127.0.0.1:43917`; no
confundir ambos puertos. No ejecutar dos runs gestionados por el Observatory en paralelo, no probar contra la
memoria real si existe fixture/corpus aislado y no recrear raíces `test/`/`tester/`: todo test nuevo vive bajo
`tests/<suite>/`. Para cambios visuales, `browser` por sí solo cubre contratos deterministas; afirmar E2E visual
requiere conducir Chromium/Playwright contra el Zaelar vivo. Para una capacidad nueva, mapear el caso en
`suite.json`/provider y validar `tests/platform/tests`; cero casos `unmapped` es el objetivo.
Los cambios que crucen memoria + conversación + widgets/workers/conectores se cierran además con
`./.venv/bin/python -m tests run journey --no-open`: son 26 pasos sobre un único engine/DB/workspace aislado y cada
caso posterior reconstruye su prefijo causal. Contrato y fronteras no cubiertas: `tests/journey/README.md`.

> **Diagrama de arquitectura — MOVIDO al sitio público (2026-07-24):** `frontend/pages/architecture.html` y la
> ruta `/architecture` de este repo se **retiraron** — ya no tenía sentido servir un panel interno (con editor de
> modelos ⚙ en vivo) desde el propio motor. Los diagramas (Arquitectura general, FlashBrain, Brain Workers,
> Memoria, Widgets) viven ahora como contenido **público, curado y en inglés** en `web/` bajo `/technology`
> (`web/src/pages/technology/*.astro`), con las rutas de código internas, nombres de variable y detalle de
> incidentes/costes RECORTADOS a propósito (audiencia externa, no engineering interno). **Ya NO es un espejo
> automático del código** — es una foto seleccionada a mano. Si tocas topología/modelo/proveedor de forma
> significativa, actualiza también los diagramas en `web/src/pages/technology/` como paso manual (no lo hace
> ningún workflow todavía); la fuente de verdad DETALLADA sigue siendo `.meshkore/docs/architecture/` y este
> `CLAUDE.md`. **Limpieza HECHA (2026-07-26, con autorización explícita del operador tras la auditoría):** los 5
> workflows (`zaelar-docs-sync.md`, `zaelar-widgets-workflow.md`, `zaelar-memory-workflow.md`,
> `zaelar-alignment-review.md`, `zaelar-audit-workflow.md`) ya apuntan a `web/src/pages/technology/*.astro` +
> `web/src/lib/diagrams/*.ts` en vez del `architecture.html` retirado; las menciones que quedan son notas
> históricas explícitas ("retirado el 2026-07-24"), no punteros activos a editar.

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
  solo durables, `to_thread`) + `nucleo/mem_processor.py` ★ (el CORAZÓN de escritura V2-013:
  **`deepseek/deepseek-v4-flash` DIRECTO** (`api.deepseek.com` desde 2026-08-16; antes vía AIMLAPI) por config
  `§memory` desde 2026-08-09 — bench §12.3: iguala a
  `gpt-4.1-mini` en completeness (98,5 vs 98,9%) y precisión (100%) por **−55% de coste**; `gpt-4o-mini` VETADO
  (mete una alergia en inglés en `slot=operator.diet`, que la borraría al cambiar de dieta); key
  POR ENDPOINT + salud con alerta por racha de fallos [incidente 2026-07-17/19: 2 días caído en silencio];
  escribir puede ser lento, prioriza escribir BIEN — DESTILA cada turno en píldoras curadas — dato+metadatos,
  decide DESCARTAR/ESTADO/CORTO/LARGO + importancia + `slot`; off-hot-path, fail-open a la heurística [que ya NO
  ensucia: degrada a short+TTL]; **GATES de PRECISIÓN deterministas V2-033**:
  descarta peticiones/preguntas/ack reificadas, no deja que un nombre garbleado del STT pise la identidad del `state`
  —cuarentena— y no hace durable una preferencia efímera) + **`nucleo/workers/`** (**Brain Workers V2-038** —
  sustrato AGNÓSTICO: `base.py` [`WorkerBackend`/`WorkerEvent`/`WorkerSpec`], `claude_session.py` [stream-json vivo],
  `generator_session.py` [widgets, envuelve el generador matable], `codex_session.py` [Codex CLI, `exec --json`],
  **`grok_session.py`** [Grok Build; HEREDA de `claude_session` porque su wire format es el MISMO, ver decisión clave],
  `registry.py`
  [`get_backend` por config, mezclable], `session.py` [`WorkerSession` + `SessionRecord`], **`providers.py`**
  [CADENA de endpoints Anthropic-compatible + relevo por cuota agotada, ver decisión clave]) = capa de trabajo async
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
  `nucleo/memllm.py`, **`deepseek-v4-flash` vía AIMLAPI** desde 2026-08-09 — bench §12.4] + higiene con alerta;
  kill-switch `ZAELAR_REM`. ⚠️ Esta fase estuvo MUERTA semanas: `.format()` sobre un prompt con llaves literales
  lanzaba `KeyError` y el `except` lo volvía un warning — ver la decisión «Memoria central») · capa **episódica** (absorbió el
  antiguo `files/`: paste/drop → `memory/server_api.py` → `memory.write_episode`, binario + resumen buscable, carga
  lazy) · fachada + señal `memory.updated` por el bus. `memory/seed_from_hermes.py` = importador one-shot que siembra
  el perfil del operador desde `~/.hermes` si existe (best-effort, solo-lectura). **`memory/vault.py`** ★ (V2-060:
  BÓVEDA de secretos del operador CIFRADOS — cripto asimétrica sealed box vía PyNaCl + sobre passphrase Argon2id +
  passkeys WebAuthn PRF; tablas `vault_meta`/`vault_secrets`), **`memory/secrets.py`** (detección FAIL-CLOSED +
  redacción) y **`memory/vault_api.py`** (`/api/vault/*`, loopback) — ver la decisión clave «Bóveda de secretos».
  Diseño en `zaelar-memory.md`.
- `observability/` — **QUIÉN · CUÁNDO · en qué FLUJO** (V2-090). Completa el registro de eventos (que ya contaba
  QUÉ pasa) con los ejes para ANALIZARLO: `identity.py` (**`user_id`** estable por instalación —UUID4 aleatorio
  en `config/identity.json` gitignored, con **INIT EXPLÍCITO en el lifespan del server** desde 2026-08-16 (antes
  se generaba solo, la primera vez que CUALQUIER código llamara a `user_id()`; ahora queda creado y logueado en
  el arranque, igual de visible que el `ZAELAR_USER_ID` que una Machine de nube ya trae puesto) — en la nube
  MANDA ese `ZAELAR_USER_ID` del provisioner, `user_id()` lo prefiere sobre el fichero local— y **`session_id`**
  por SESIÓN DE TRABAJO del operador: arranca al conectar, se cierra con ⏻ o al cerrar la pestaña, y una
  reconexión NO la parte en dos) · `flows.py` (lectura por **CORRELATION ID**: flujos con duración real de punta
  a punta, familias, actores, tokens y errores; detalle cronológico; sesiones; cobertura) · `api.py`
  (`/api/observability/*`). **El correlation id NO es un id nuevo: es el `trace` de V2-044 PROMOVIDO** de campo
  del JSON a columna indexada (`events.corr_id`) — un segundo id paralelo se habría separado del primero en la
  primera costura cross-loop sin coser. Un flujo nuevo nace con cada petición del operador; lo que continúa un
  flujo vivo hereda el suyo. **A correction spoken while a task is still live MERGES into that task's `corr_id`
  instead of opening a new one** (2026-08-15): `send_to_worker`'s handler (`nucleo.py::_on_tool_call`) already
  resolves its target via `dispatch.resolve_sessions()`; when that resolves to exactly one live session, this
  turn adopts its `trace_id` (`dispatch.trace_of` + `trace.adopt`) instead of keeping the fresh one `trace.begin()`
  opened at turn start. With several live sessions and no unambiguous match, nothing merges — a stray extra flow
  beats guessing which task a correction belongs to. A flow's end is now also EXPLICIT (`kind="flow"`, emitted
  where the worker session that spawned it finishes), not just inferred from silence. **A single utterance split
  across several LiveKit turns also merges (2026-08-15):** LiveKit closes one turn per STT-final segment, so a
  long sentence spoken without pauses used to open a fresh trace per fragment — `_begin_or_adopt_trace()`
  (`nucleo.py`) checks the V2-096 accumulator's `pending()` instead: while a fragment chain is open, the next
  turn ADOPTS its trace rather than opening one, cleared once the chain resolves. Known limit, not solved here: if
  the accumulator judges a sentence complete (a closing period) and the operator keeps talking about the same
  thing right after, that reopens as a NEW chain/trace — a real improvement, not a guarantee of one flow per
  real-world task. **A pending confirmation's answer also merges into the turn that asked** (`widgets/
  confirm.py::request()` captures `trace.current()`, `_resolve_confirm()` adopts it before executing/cancelling)
  — the ask/answer/action of an irreversible confirm-gate now reads as one flow even across a barge-in-cancelled
  reply attempt in between. `flows()`'s SQL exposes `origin` (the `trace.begin(origin=...)` argument: `turno`/
  `kickoff`/`ui`/`cron`/`proactivo`/`cluster`/`probe`) and `title` (that root event's text) per flow — what the
  master's column-board (`cloud/backoffice`, private repo) uses to tell a real task apart from session
  initialization (kickoff greeting, canvas-restore reconciliation within the session's first ~10s) and to label
  each column/rail item with more than a bare corr_id. **A plain conversational flow now closes EXPLICITLY too**
  (2026-08-15): only a worker-spawned flow had an explicit close before this; the master could only guess
  liveness from recency, and guessed wrong the instant a turn finished (reported live: "restarted the system…
  still shows seven active flows"). `_run`'s success path (never the `CancelledError` branch — a barge-in
  cancellation may still get continued by the next fragment) calls `_maybe_close_flow()`, which closes the
  current trace UNLESS the V2-096 accumulator still expects more on it, a confirmation asked on it is still
  pending, or a worker is still running on it (`dispatch.has_live_trace`, the reverse of `trace_of`) — that
  worker owns the close instead. **A confirmation's "sí"/"no" is now resolved BEFORE any slow work, not only
  after** (2026-08-15): the old deterministic backstop (`classify_reply` + resolve) only ran after the model's
  full response streamed — a turn cancelled by barge-in before reaching it lost the answer in total silence,
  leaving the confirmation pending forever with the widget untouched (reproduced live: operator confirmed
  clearing the agenda by voice, the reply's turn got barge-in-cancelled, and the agenda never changed, with zero
  trace of it in the log). A clear yes/no is now resolved right after the hard-interrupt check, before the model
  is even called; ambiguous replies still fall through to the old late-stage backstop. **A widget can opt out of
  the visual Sí/No overlay** (`"confirm_ui": false` in its manifest, `nucleo.py::_confirm_ui_paints`; e.g.
  `widgets/agenda/manifest.json`, per an explicit operator request — "the agenda widget is voice-only"): the
  confirmation itself, and voice resolution, are completely unchanged — only the SSE emit that paints the card
  overlay is skipped. SOLO LECTURA: el único escritor de `events` sigue siendo
  el sink del bus. Fase LOCAL entregada; nube + privacidad en `INI-021` (raíz del workspace).
- `bus/` — **Sistema Nervioso**: pub/sub de señales in-process (asyncio, patrones fnmatch + `emit_sync`
  loop-agnóstico vía `call_soon_threadsafe` para entrega cross-loop job-thread↔uvicorn). `bus/log.py` = log durable
  de eventos en SQLite (`zaelar.db`, tabla `events`, WAL). `bus/sse.py` = puente SSE al frontend (`GET /events`).
  Transporte HÍBRIDO: llamadas directas en la ruta caliente de voz + eventos para lo async/fan-out. **Nada de
  Kafka/broker.**
- `frontend/` — interfaz como app de **módulos ES sin build**, migrable a Solid (core reactivo + services +
  components + widget desktop). Voz vía **cliente LiveKit** (`services/session-lk.js` + SDK vendorizado en
  `frontend/vendor/`). Ver `zaelar-modules.md §Frontend`. **SUPERFICIES NATIVAS del frontend = «widgets de
  SISTEMA», INTOCABLES** (V2-080): su LISTA CANÓNICA ÚNICA vive en **`frontend/app/core/system-surfaces.js`**
  (`SYSTEM_SURFACES` + `isSystemSurface()`) — panal de actividad, cámara/mic, orbe, TopBar, estado de conexión,
  chat (Chat/Procesos/Crons), panel de estado ◉, config ⚙, benchmarks, debug ◷, mapa de memoria 🧠, wizard 🧭,
  bóveda 🔐, banner de aviso y splash de arranque. `main.js` las MONTA desde esa lista (sin duplicar). El
  generador/`lifecycle` NUNCA las tocan (solo tocan `widgets/<id>/`). **Todo lo demás en pantalla son WIDGETS DE
  USUARIO** (catálogo `widgets/<id>/`, full-stack `manifest.json`+`data.py`+`widget.js`), variables y creados
  por/para el usuario **aunque se distribuyan de serie** — como los conectores. Añadir una superficie nativa nueva
  = añadirla a `system-surfaces.js`. **V2-082:** cada superficie dirigible por voz lleva `name` + `aliases` FIJOS
  (hardcodeados en el front, NO editables) — espejados en el backend `widgets/system_surfaces.py` (test de sincronía)
  para que el resolver de nombres las conozca. Cada tarjeta de widget de usuario pinta un HEADER genérico (en
  `desktop.js`, sin tocar su `widget.js`) con el NOMBRE + un ⚙ que despliega sus ALIAS editables.
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
- `tests/agent_headless/harness/` — harness de evaluación conversacional sintética + juez.
- `tests/voice/e2e/mic/` — self-test headless del transporte micrófono→STT por WebRTC.
- `tests/voice/e2e/agent/` — tester de voz (INI-013): 2º participante LiveKit que HABLA con zaelar y un JUEZ que evalúa lo que HACE.

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

- **Las tools, de menos a más (2026-08-02, norma del operador)**: el catálogo de `router.TOOLS` había llegado a
  **31.647 chars, el 70% prosa**, y viaja ENTERO en cada turno — también en el que solo dice «hola». La norma que
  fija el operador: *«un modelo de lenguaje ya sabe lo que es un player de música; dile que tienes un widget de
  música con play/stop y punto»*. Aplicada: cada descripción se reescribió terse dejando solo (a) qué hace, en una
  cláusula, y (b) las **fronteras contra NUESTRAS otras tools** y las reglas duras nacidas de bugs reales — lo
  único que el modelo no puede deducir. Fuera: listas de ejemplos, repeticiones, narrativa histórica. Los
  COMENTARIOS de Python se quedan (no cuestan tokens y guardan el porqué). **31.647 → 18.926 chars (−41%)**, ~7,9k
  → ~4,7k tokens por turno, con techo fijado en `test_router.py::test_tool_catalog_stays_compact` (21.000) para
  que añadir una tool obligue a recortar, no a engordar el turno de todos.
  - **Medido, no supuesto** (`tests/.../prompt_cost/bench_fast_model.py`, nodo 2.13, 3 rondas × 12 casos contra el
    prompt REAL compuesto por `prompt.build_flash_system`): el enrutado **no empeoró, mejoró** — `deepseek-v4-flash`
    35/36 con el catálogo completo, **36/36 con el compacto**; el turno de escalada bajó de ~10 s a ~6,4 s.
  - **NO partir el catálogo en dos peticiones** (idea razonable que la medición tumba): un índice de una línea por
    tool baja el prompt de 9.729 a 1.221 tokens, pero el turno pasa de 1.938 a **6.208 ms**. El tamaño del prompt
    vale ~150 ms; cada ida y vuelta cuesta 1,5-4,5 s. **Peso y latencia son problemas distintos**: compactar
    arregla el primero, un segundo viaje empeora el segundo.
- **El FlashBrain se queda en DeepSeek V4 Flash — y la latencia NO es del prompt (2026-08-02)**: ante turnos de
  6-15 s se barrieron 11 candidatos contra el prompt real (nodo 2.13). **DeepSeek es el ÚNICO que enruta 12/12**;
  los veloces enrutan peor (gpt-4.1-mini 9/12 y confunde escalada con `web_search`, gemini-3.5-flash-lite 2/12,
  mistral-medium 10/12) y cambiar por ellos regala velocidad a cambio de que el agente haga lo que no es. No hay
  cola ni contención: 4 peticiones a la vez no degradan a nadie (×0,9-1,6).
  - **La causa real: DeepSeek V4 Flash RAZONA aunque se le pida que no**, y la VOZ es no-razonadora por invariante
    duro. Medido en el turno de escalada: sin flag, **2.489 chars de razonamiento / 700 tokens de salida / 8,7 s y
    ni siquiera llama a la tool**; con `extra_body={"thinking":{"type":"disabled"}}` (lo que ya manda
    `fast_client.py`) baja a 993 chars / 405 tokens / 4,7 s — **lo reduce, no lo apaga**. `reasoning_effort`
    (none/minimal) lo rechaza AIMLAPI con 400; `enable_thinking`, `chat_template_kwargs` y `reasoning.enabled`
    EMPEORAN (hasta 1.857 tokens / 20 s). Es decir: los segundos son tokens de pensamiento que el broker no deja
    desactivar del todo. **Pendiente**: probar DeepSeek DIRECTO (`api.deepseek.com`, donde el parámetro es nativo)
    — hoy no hay key. Ese es el siguiente paso de latencia, no tocar el catálogo ni el prompt.
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
  Cloud/self-hosted en prod). **Resiliencia a cambios de red (fix 2026-07-29):** `run-livekit.sh` arranca
  `livekit-server --dev --bind 127.0.0.1` **SIN `--node-ip`** — LiveKit/pion re-enumera las interfaces vivas y
  reúne los host-candidates ICE con la IP ACTUAL en CADA conexión nueva, así que moverse de wifi a hotspot o a
  otra casa se auto-sana (la conexión cae, el navegador reconecta, el server ofrece la IP nueva). Fijar `--node-ip`
  al arranque (lo que se hacía) era JUSTO el bug: congelaba una IP que se quedaba obsoleta al cambiar de red →
  `wait_pc_connection timed out` (3 caídas el 2026-07-28 al moverse entre redes). Verificado con headless-Chrome
  (fake-mic) que ambas patas —navegador↔server y agente↔server— conectan sin pin. El caso loopback
  (`--node-ip=127.0.0.1`) SÍ falla y por eso NO se usa (el agente embebido pion no reúne candidato loopback). La
  señalización sigue privada en `--bind 127.0.0.1`. Escape hatch: `ZAELAR_LIVEKIT_NODE_IP=<ip>` restaura el pin.
  **Producción real** (no local): LiveKit Cloud o coturn/Cloudflare TURN → candidato relay con IP estable
  (independiente del nodo y del NAT del cliente); ver `zaelar-deploy.md`.
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
  conservando su contrato+validación, ahora **matable** por token) y **`codex_session`** (Codex CLI, `exec --json`
  → JSONL; ver la decisión «El segundo backend» más abajo); `registry.get_backend`
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
  al (re)conectar → fin de los chips huérfanos. **V2-084:** `reset_all` **deja los PROCESOS en blanco** — además de
  matar los workers vivos, vacía el HISTÓRICO de la pestaña Procesos (`nucleo/workers/ledger.clear`) para «empezar
  de cero», y el frontend limpia chips+histórico al instante con un handler `session/RESET`. El reset **conserva
  estado, memoria, datos de los widgets, config de modelos y credenciales** — solo los checkboxes MEMORIA/CREDENCIALES
  (opt-in, V2-063) borran esas capas. Piezas one-shot **parkeadas** (revertibles): `nucleo/agentes/
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
    zaelar). Testing: dominio `seguridad_datos` (`tests/voice/e2e/agent/scenarios.py`, prioridad nº8 en `zaelar-testing.md`; el
    tester usa PASSPHRASE, la biometría no es testeable). Detalle: `V2-060-boveda-secretos-cifrados.md` +
    `zaelar-security.md` / `zaelar-memory.md` / `zaelar-conventions.md`.
- **«Susurro» — auto-auditoría conversacional y mejora continua** (`nucleo/susurro/`, V2-053, 2026-07-17; diseño
  y plan en `.meshkore/roadmap/initiatives/V2-053-susurro-autoauditoria.md`): el bucle test→fix parchea el routing
  del no-razonador caso a caso (81 fixes/5 días, ~55% clase routing) y NO generaliza — la pieza que faltaba es un
  **auditor interno**: un modelo POTENTE (config `§susurro`, por la UI; FUERA del camino de voz → puede razonar;
  default `openai/gpt-4.1-mini` **vía AIMLAPI** — el 2026-08-09 se movió del endpoint de OpenAI directo al broker
  conservando el modelo exacto: en la nube no hay `OPENAI_API_KEY`, así que allí habría fallado en silencio como
  falló el REM; §12.5) que, ante **FRICCIÓN** (detector determinista es/en: queja/corrección del operador,
  petición repetida, turno degradado, rail `sin_resolver`, `worker.stuck`, **+ turno de RIESGO V2-061:
  `friction.risky_decision` = acción de widget sin escalar, para intervenir ANTES de la queja**), recibe una ventana
  comprimida (conversación verbatim + decisiones por turno + eventos filtrados + ESTADO) y devuelve correcciones de un
  **catálogo CERRADO** — `repair_say` (frase de reparación → `brain_notes` [SISTEMA], hablada en el turno
  siguiente; el probe también drena, paridad V2-053), `finding` (→ `.meshkore/logs/susurro/findings.jsonl` con
  dedup + topic `susurro.finding`, lo consume el dev-loop) y **`worker_action` (F2, V2-061): RE-RUTEA — dispara el
  worker correcto vía `escalate` cuando el rápido dejó sin ejecutar una acción real (dedup vs sesiones vivas)**.
  **Incidente 2026-07-26 y fix:** `worker_action` re-escalaba en cadena vía el widget `ejecuta-accion-real` (un
  turno posterior que solo relataba el progreso de una tarea YA escalada volvía a calificar como riesgo; el dedup
  de texto no siempre lo atrapaba) → load 5.86, ahogó voz/chat. Susurro estuvo OFF hasta añadir un **circuit
  breaker anti-bucle determinista** (`nucleo/susurro/apply.py`, tope de 3 `worker_action`/10min, avisa al operador
  1× si se abre) — reactivado tras el fix, auditoría 2026-07-26.
  **Enchufado SOLO por el bus** (topic semántico
  **`turn.completed`** emitido por `observer.turn_detail`, punto ÚNICO voz+probe — audit de modularidad
  2026-07-17, doc `zaelar-modularity.md`), montado en el lifespan con **kill-switch de 1ª clase**
  (`ZAELAR_SUSURRO` + `susurro.enabled`), cooldown + single-flight, fail-open duro. **Observabilidad TOTAL**
  (regla del operador): eventos kind `susurro` con el payload ENVIADO al LLM, la respuesta CRUDA y cada
  corrección con su ANTES/DESPUÉS → timeline + /debug + bus/log. **INVARIANTE: NUNCA modifica BRAIN
  RULES/prompt de sistema en runtime** — mejora en dos velocidades: runtime corrige la capa MUTABLE (F2/F3:
  user_rules/workers/estado/memoria con gates); los findings cambian la genética por DESARROLLO (git+tests).
  Verificado e2e (suite `tests/agent_headless/e2e/susurro/run_probe_suite.py`, histórico longitudinal + escenario
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
- **ORDEN DE PROVEEDORES — DeepSeek V4 DIRECTO primero, luego el broker, y solo al final OpenAI/Anthropic**
  (norma del operador, 2026-08-19). Para CUALQUIER pieza que llame a un LLM, el orden de preferencia es:
  **(1) DeepSeek V4 directo de su proveedor** (`api.deepseek.com`, `DEEPSEEK_API_KEY`) — es la opción principal;
  **(2) el broker AIMLAPI** como primer fallback; **(3) un modelo de OpenAI o Anthropic** como último recurso.
  Deroga en su parte de ORDEN a la norma del 2026-08-09 («nada sale por OpenAI directo, todo por el broker»), que
  sigue vigente en lo suyo: OpenAI/Anthropic no se llaman por su endpoint propio, se piden al broker — lo que
  cambia es que ahora son el ÚLTIMO escalón, no el segundo. Estado a día de hoy, comprobado contra el código:
  `fast` (voz) y `memory` (CORAZÓN + REM) y las tareas `turn_complete`/`directed` de `nucleo/memllm.py` van
  DeepSeek directo; `susurro` (`openai/gpt-4.1-mini`), `i18n` (`anthropic/claude-haiku-4.5`) y el bucle del
  navegador (`NAVEGADOR_AGENT_MODEL`) siguen en el tercer escalón **con una medición detrás que lo justifica**
  (§12.5 para i18n: DeepSeek acierta pero razona 6-8× los tokens; el navegador necesita VISIÓN). Mover esos tres
  no es aplicar la norma sino contradecir un banco: exige medir antes, no cambiar el default y ver qué pasa.
- **Cerebro de voz = NO-razonador** (regla dura): un modelo de razonamiento añade segundos de "thinking" (5s+ TTFT)
  en el camino de tiempo real → zaelar se queda lento/mudo. El FlashBrain usa SOLO modelos rápidos no-razonadores; el
  razonamiento vive OFF del camino crítico, en el SlowBrain.
- **ORDEN DE PROVEEDOR — DeepSeek V4 DIRECTO primero, broker después, OpenAI/Anthropic el último (NORMA del
  operador, 2026-08-19).** Toda pieza que llame a un LLM resuelve su proveedor en este orden: **(1)
  `api.deepseek.com` DIRECTO** (V4 pro/flash, **el TITULAR**), **(2) el mismo modelo por el broker AIMLAPI**,
  **(3) otro proveedor ya presente** (Z.AI/GLM, xAI) si los dos primeros están inalcanzables. **NO se usan
  modelos de OpenAI** (aclaración del operador el mismo día, después de que la primera formulación de la norma
  los nombrara como último recurso: *«no quiero usar modelos de OpenAI… vamos a usar los más potentes
  disponibles a coste razonable, por lo tanto DeepSeek V4 debe ser el titular»*). Un modelo de Anthropic solo se
  justifica donde una MEDICIÓN lo respalde y esté escrita (hoy: la tarea `i18n` de `memllm`, §12.5 — haiku dio
  100% de cobertura en japonés y árabe donde gemini devolvió 0/50); nunca como defecto cómodo.
  Amplía la norma del 2026-08-09 («nada por OpenAI directo, todo por el broker»): esa fijaba
  que no se abren cuentas por proveedor, esta fija **cuál manda cuando el mismo modelo se sirve por dos sitios**.
  Los tres motivos están medidos y ya estaban en este fichero, cada uno en su decisión: el directo es **~30% más
  barato** que el mismo modelo por el broker (§«el margen del BROKER no se cobraba»), el broker **acepta**
  `thinking:disabled` y razona igual mientras el endpoint propio lo **obedece** (**TTFT p50 4,24 s → 1,01 s**,
  V2-097), y el 2026-08-19 la cuenta del broker se quedó **sin fondos** (403 «You've run out of funds») dejando
  muda a la vez a toda pieza que colgaba de él. Dos trampas al aplicarla, las dos ya pagadas aquí:
  - **El NOMBRE del modelo cambia con el endpoint**: el broker lo prefija (`deepseek/deepseek-v4-pro`), la API
    nativa no (`deepseek-v4-pro`). Mandar el del broker al directo devuelve 400 con la lista de aceptados — así
    se desplegó roto el escalón DeepSeek de los workers (`model="sonnet"`), invisible porque un escalón de
    relevo solo corre cuando el titular ya cayó. **Compatible en el PROTOCOLO no es compatible en el CATÁLOGO.**
  - **El directo RAZONA por defecto y el razonamiento se cobra contra `max_tokens`**: medido, «Di solo OK» con
    `max_tokens=8` gasta los 8 pensando y devuelve `content=""` con `finish_reason=length` — **respuesta vacía
    sin ninguna excepción**. Quien llame al directo con un presupuesto ajustado necesita techo aparte para el
    razonamiento (gratis si no se usa) y tratar el vacío como FALLO, no como respuesta.
- **Routing de modelos — POR INVOCACIÓN** (`config/v2.py`, gestionado por la UI, persiste en `config/v2.json`):
  prioridad = **latencia** sin quedarnos sin inteligencia. Nunca una env global de modelo (concurrencia de sesiones):
  `config/v2.py` guarda los DEFAULTS y el cerebro los pasa en cada invocación. **Réplica visible al usuario
  (V2-077):** `config/model_benchmarks.py` + botón "¿por qué estos modelos?" en Config → Cerebro rápido — toda
  decisión de modelo nueva se documenta AQUÍ, en `zaelar-model-benchmarks.md` Y en ese módulo curado los tres.
  - **FlashBrain** (sección `fast`): **producción actual = `deepseek-v4-pro` DIRECTO** (`api.deepseek.com`,
    NO-razonador con `thinking:disabled` OBEDECIDO — ver la norma de proveedores en «Hard rules» y el banco a
    3 rondas de V2-097). El titular anterior era `deepseek/deepseek-v4-flash` vía AIMLAPI, y antes de ese
    `anthropic/claude-haiku-4.5` por el mismo broker (V2-034, A/B de 2026-07-12) — los dos siguen siendo
    opciones válidas del broker y ninguno es ya el defecto. ⚠️ Esta línea llevaba desde el 2026-08-02
    diciendo Haiku mientras el propio documento explicaba, más abajo, que el titular era DeepSeek: si tocas
    modelos, cambia LOS DOS sitios. (NO-razonador;
    `AIMLAPI_KEY` presente en el store `tester.env` + `.env`). El A/B de V2-034 lo eligió por **fiabilidad de
    routing/introspección**. ⚠️ AIMLAPI va tras Cloudflare y 403/blip-ea intermitente (el cliente spoofa User-Agent);
    un blip puntual puede marcar el ◉ `llm` en rojo hasta el siguiente turno OK (health self-clears). **`grok
    (xAI) está BANEADO en el FlashBrain**: el único rápido (`grok-4.20-0309-non-reasoning`) MIS-RUTEA —contesta
    "Hecho"/`widget_data` a una PREGUNTA de memoria, causa de "conversaciones absurdas"—; los correctos (grok-4.3/4.5)
    son razonadores → violan "voz=no-razonador". **NUNCA grok en la capa de voz** (canónico: `zaelar-model-benchmarks.md
    §9/§13`). **RE-VALIDADO 2026-08-03 con la generación NUEVA** (`§9.1.b`): sí es ultra rápido (1.030 ms de mediana
    y nunca se dispara, peor caso 2,8 s vs los 76 s de DeepSeek), pero repite el fallo exacto —a «dime cuándo es la
    cita de la ITV» llamó `web_search`+`widget_data`— y además enruta «investiga y ponme un informe» a `web_search`
    **3 de 3**, o sea contesta un dato donde toca lanzar un Brain Worker. El veto no es folclore: se vuelve a medir. `nucleo/flash/fast_client.py::resolved_api_key()` resuelve la key **por endpoint** (aimlapi→`AIMLAPI_KEY`,
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
  el **CORAZÓN** (`nucleo/mem_processor.py`, **`deepseek/deepseek-v4-flash` DIRECTO** — `api.deepseek.com` desde
  2026-08-16, tras un cuelgue del broker AIMLAPI para este modelo (12s+ sin respuesta, degradaba cada escritura a
  la heurística con pérdida); el sueño REM se queda en AIMLAPI, ver más abajo — por config `§memory` desde
  2026-08-09 — bench de destilación §12.3 (`zaelar-model-benchmarks.md`): 21 candidatos comerciales × 34 casos ×
  **4 ejes separados** (write-completeness · precisión/no-pollution · capa+slot · $/1k turnos con tokens REALES).
  Empata con el titular anterior `gpt-4.1-mini` en los dos ejes que DESTRUYEN datos —captar el hecho 98,5 vs 98,9%
  y no ensuciar 100% vs 100%— por **$0,68 vs $1,516 los 1.000 turnos (−55%)**; escribir va off-hot-path, así que su
  mayor lentitud no le cuesta nada al turno. **UN solo modelo comercial para self-host y nube** (decisión del
  operador): los TRES sitios que lo fijan van sincronizados — `config/v2.py §memory`, `fly.accounts.toml` y
  `cloud/provisioner/src/machineConfig.js`. ⛔ `gpt-4o-mini` es más barato y está **VETADO**: a una alergia dicha en
  INGLÉS le pone `slot=operator.diet` (3/3 pasadas) y un slot invalida todo lo anterior con ese slot → un futuro
  «ahora soy vegetariano» borraría la alergia. Los **razonadores tampoco valen** (gpt-5-mini/nano: 50-60% de
  precisión — convierten preguntas y órdenes en recuerdos). Esto **DEROGA la directriz «memoria = SIEMPRE OpenAI»**
  de 2026-07-17: el destilador se elige con el bench, no por reputación del proveedor. Cadena de fallback:
  `gemini-2.5-flash` → `gpt-4.1-mini`. **NORMA GENERAL (operador, 2026-08-09): NADA sale por OpenAI directo — todo
  pasa por el broker AIMLAPI, una sola cuenta de API**; Z.AI (workers) y xAI/Groq van aparte, con su credencial, y
  solo donde hacen falta. Que un modelo se llame `openai/gpt-4.1-mini` no implica cuenta de OpenAI: es el broker
  sirviéndolo. Los DOS restos que quedaban apuntando a `api.openai.com` —la tarea `i18n` de `memllm` (traducir el
  UI a un idioma nuevo) y el **Susurro**— se movieron el mismo día: los dos tenían el defecto latente de que en la
  nube no existe `OPENAI_API_KEY` y habrían fallado en silencio. i18n eligió modelo con una sonda al tamaño REAL
  del lote (§12.5): **`anthropic/claude-haiku-4.5`** — 100% de cobertura y placeholders intactos en japonés Y
  árabe, frente a `gemini-2.5-flash` (una pasada de árabe devolvió 0/50) y `deepseek-v4-flash` (acierta pero razona:
  6-8× los tokens que entrega). Sonda de regresión: `grep -rn "api\.openai\.com" --include="*.py" engine/ | grep -v tests/`. El CORAZÓN **reporta su consumo a Energy** desde 2026-08-09 (era la única
  llamada LLM de nube sin metering); key resuelta **POR ENDPOINT** + **SALUD de 1ª clase** (alerta por racha de fallos +
  `status()` — el incidente 2026-07-17/19 lo dejó 2 días caído en silencio) que DESTILA cada turno en **píldoras**
  (dato canónico + metadatos) y decide DESCARTAR/ESTADO/CORTO/LARGO + importancia + `slot` — LENTO a propósito,
  nunca en el turno; fail-open a la heurística regex, que ya NO ensucia (degrada a short+TTL 3d, nunca durable
  crudo). El sueño tiene DOS fases: el consolidador LIGERO (horario) y la **fase REM** (`memory/rem.py`, V2-056,
  diaria): repara vectores + dedup semántico + **INSIGHTS por concepto** + higiene con alerta — detalle en
  `zaelar-memory.md §Sueño PROFUNDO`. Su síntesis usa **`deepseek/deepseek-v4-flash`** (el MISMO modelo que el
  CORAZÓN; bench §12.4, 2026-08-09) — pero ahí el criterio es la CALIDAD, no el precio: REM es **1 llamada al día**
  con la entrada acotada por diseño (`MAX_GROUPS=8` × `pills[:12]`), así que **el coste no escala con el tamaño de
  la memoria** (todo el barrido cabía entre $0,14 y $2,17 AL AÑO) mientras que un insight malo se consolida como
  píldora durable. Los modelos MÁS POTENTES no mejoran (medido: v4-pro 98,1%, reasoner 97,1%, gpt-4.1 96,8% vs
  flash 97,8-99,0%) y `gpt-4.1-mini` cae por no saber CALLARSE (0% de disciplina de `null`: de «se le olvidó dónde
  dejó las llaves» fabricaba un rasgo durable del operador). **⚠️ INCIDENTE 2026-08-09: esta fase llevaba semanas
  sin escribir un solo insight** — `_REM_SYSTEM` acaba con el ejemplo del contrato `[{"concept": …}]` y se
  interpolaba con `.format(lang=…)`, que lee esas llaves como marcadores → `KeyError` en cada llamada → el
  `except` de `synthesize` devolvía 0 con un `logger.warning`. Fail-open silencioso; el síntoma era «la memoria no
  consolida», nunca un error. Arreglado (`.replace`), blindado (`tests/memory/unit/test_rem_prompt.py` PROHÍBE
  volver a `.format` ahí) y el fallo ya marca `health_state` → sale en el ◉. Tercer incidente de la misma familia
  en este módulo: **un fallo de la memoria nunca puede quedarse en un `logger.warning`.** **La lectura NUNCA lleva LLM** — tres velocidades
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
  2026-07-10): el sistema entero se adapta a UN idioma (el de la persona; inglés hasta detectarlo, ver `langs.py`);
  el CORAZÓN destila cada píldora en ese idioma canónico **traduciendo** lo que venga en otro y **nunca descarta un
  dato durable por estar en otro idioma** → la lectura es siempre mismo-idioma (cero gap cross-lingual, sin indexar
  N idiomas). El FlashBrain entiende varias lenguas (STT+modelo) y sus gates son es/en, pero lo que se GUARDA/RECUERDA
  queda en el idioma del operador. Además el FlashBrain **NUNCA expone al operador las capas internas de memoria**
  ("corto/largo plazo", "base de datos"): responde con naturalidad o pide el dato como un humano.
- **Recuperación del recall LARGO = RERANKER model-agnostic, LOCAL por defecto** (`memory/rerank.py` +
  `memory/rerank_local.py`, config `config/v2.py` §`memory`, V2-030, 2026-07-12): a escala (cientos de recuerdos)
  el embedding local bi-encoder ordena "borroso" — la respuesta está en el top-10 (~82%) pero no en el top-1/3. Un
  **cross-encoder** que reordena el top-N del RRF **leyendo query+recuerdo juntos** cierra la mayor parte del hueco:
  medido (`tests/memory/e2e/bot/scale_eval.py`, 442 durables) **recall@1 41.6→56.2%, recall@3 62.3→68.7%** (empata
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
- **Multidioma con catálogo alineado** (`voice/engine/core/langs.py`, single source of truth; default **inglés**):
  al cambiar de idioma (⚙ o por voz), **STT (lang+initial_prompt), voz TTS e idioma de respuesta del cerebro se
  re-alinean juntos**. Invariante: **la voz nunca puede quedar cruzada con el idioma** — las voces Kokoro son
  por-idioma (`ef_dora`=es, `af_bella`=en) y `voices.selected_voice()` rechaza una voz no nativa del idioma activo
  (cae al default); Cartesia es multilingüe (una voz + `language`). Un idioma solo entra al catálogo si tiene voz
  nativa verificada (hoy **es + en**). Los providers leen `langs.current_code()` (lee `ZAELAR_LANGUAGE`, que el ⚙
  escribe en caliente) → el cambio aplica **al reconectar**.
- **UI multilingüe que se adapta a CUALQUIER idioma** (V2-089, subsistema `i18n/`; doc completa
  `.meshkore/docs/architecture/zaelar-i18n.md`): la UI del frontend ya NO está hardcodeada — cada string pasa por
  `t(key)` (reactivo) y sigue el idioma del operador. **Tres ejes:** exterior/clusters = **siempre inglés**;
  operador↔agente = idioma del operador (cualquiera); UI = sigue al operador. **Best of both worlds:** `en` (base/
  manifiesto) + `es` PRESET en `i18n/bundles/*.json`; cualquier OTRO idioma lo **genera un LLM al vuelo** la 1ª vez
  que se habla y se **actualiza** en cada release (una sola función idempotente `i18n.init.prepare(code)` que diffea
  por snapshot de inglés — misma ruta primer-uso y upgrade). **Autodetección** del idioma en el primer arranque
  (`i18n/init/detect.py`: heurística de script no-latino + LLM para latino; STT en modo auto la 1ª vez) → fija
  `ZAELAR_LANGUAGE` + genera bundle + evento SSE `language` → la UI cambia EN VIVO.
  **ARRANQUE IDIOMÁTICO — el contrato completo (norma del operador, endurecido 2026-08-09):** el producto
  arranca en **INGLÉS** (`langs.DEFAULT_LANG="en"` + `SETTINGS.language` + `store.lang()` del frontend: los tres
  alineados; antes la voz arrancaba en castellano y la UI en inglés). Ese defecto solo dura hasta la PRIMERA frase:
  se detecta el idioma real y **todo** —voz, conversación y frontend— pasa a él, generando el bundle de UI con un
  LLM si no es `en`/`es` (los dos PRESET de fábrica). Para que eso pueda ocurrir, mientras no hay idioma elegido
  **el STT transcribe en AUTO**, y eso lo responde UNA sola función, `langs.first_run_auto()`, que cada backend
  traduce a su forma de decir «auto» — Whisper `language=None`, Voxtral OMITE el parámetro, Deepgram exige
  `"multi"` explícito (omitirlo cae a `en-US` en el servidor, que NO es auto). Antes solo lo hacía `whisper_local`:
  en el perfil de NUBE, que es el de producción, el STT arrancaba clavado al idioma por defecto y la
  autodetección **no podía funcionar** — clasificaba la primera frase ya transcrita por el modelo equivocado.
  Tests: `tests/voice/unit/test_language_bootstrap.py` (nodo 1.9). **Principio arquitectónico:
  INICIALIZACIÓN (`i18n/init/`, puede llamar LLM/STT, corre en boot/primer-uso/switch/upgrade) SEPARADA de la
  EJECUCIÓN (`i18n/runtime.py`, hot path, barato, sin LLM).** `active_code()` (UI) lee `ZAELAR_LANGUAGE` crudo
  (cualquier código), DESACOPLADO del catálogo de voz `langs` (es/en). El **matching de voz** (aliases/regex) es
  es/en como ACELERADOR; el **router/resolver LLM es el mecanismo multilingüe** para idiomas no cubiertos.
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
- **Nombres + alias de widgets con CERTEZA de enrutamiento** (V2-082, 2026-08-01; plan en
  `.meshkore/docs/architecture/zaelar-widget-naming-v2082.md`): cada pieza tiene un **NOMBRE canónico + una lista de
  ALIAS** y se resuelve SOLO por ellos. **Invierte el matching difuso** que confundía widgets: `widgets/runtime.py::
  identify` reescrito — la `description`/`whenToUse` ya **NO abre nada** (fin del "abrió por parecido temático", causa
  raíz de la mis-ruta de [[project_v2081_show_vs_build_misroute]]), tolerancia de voz solo sobre tokens de alias, y
  **sin match de nombre/alias → se PREGUNTA** (nunca se abre el más parecido ni se fabrica un widget). La palabra
  **"widget"** en la frase acota a widgets de USUARIO; las **SUPERFICIES DE SISTEMA** (chat/config/debug…, espejo
  backend `widgets/system_surfaces.py` ← front `system-surfaces.js`) viven en el mismo espacio de nombres y devuelven
  `system=<id>`, nunca un widget → "abre el chat" (sistema) y "abre los mensajes" (mensajería) jamás se cruzan. Único
  matiz: sin match pero UN solo widget abierto → se opera sobre él (lo que tiene delante). Alias de widget
  **EDITABLES por voz/texto** (tool `manage_widget_alias` + REST `POST/DELETE /widgets/{id}/aliases`, escritura
  QUIRÚRGICA del manifest en `widgets/aliases.py` con guard de colisión —un alias = una sola pieza— sin regenerar
  código); alias de sistema FIJOS. **Registro unificado** `widgets/registry.py` (`GET /widgets/registry`, proyectado a
  `state.widget_registry`); el frontend pinta el NOMBRE + un ⚙ con los alias editables en el header de cada tarjeta
  (`desktop.js`, evento SSE `widget/alias` refresca en vivo). **Concepto fijado sin mezclar:** WIDGET (catálogo, alias
  editables) · SUPERFICIE DE SISTEMA (nativa, alias fijos) · TOOL (`router.TOOLS`) · ACCIÓN/data-op (≡"skill",
  `manifest.actions`) · EMBEDDING (solo memoria). `keyword ≡ alias` (D1): `keywords` legacy se siembra a `aliases`.
- **CHAT y VOZ, INDEPENDIENTES — el icono es el único dueño del silencio** (V2-088, 2026-08-02): se RETIRA el
  «modo chat = voz off» de V2-054. Partía de una premisa falsa —que abrir el panel significa «prefiero leer»—
  cuando tiene CUATRO pestañas y el operador entra a mirar Procesos/Crons/Clusters sin querer callar a nadie.
  Ahora abrir el chat NO toca el altavoz y silenciar NO toca el chat. **El chat no es un modo, es una VISTA MÁS**:
  la respuesta aparece en el chat, en los subtítulos y en la voz **a la vez** (`pushAgentChat` cuelga del
  transcript, independiente del audio). Silenciar es SIEMPRE decisión del operador con 🔊. Tests: nodo 4.9
  (`test_chat_voice_independent.py`) — prohíben que el ChatWall vuelva a nombrar `toggleBotMute`/`setVoiceOutput`/
  `botMuted`. La etiqueta del evento ya no dice «modo chat» (apuntaba a una causa inexistente y costaba horas).
- **El icono del altavoz MANDA — un solo interruptor para la voz** (V2-087, 2026-08-01): «abro el chat y la voz se
  desactiva, y el icono se bloquea». Tres fallos encadenados detrás. **(a) DOS interruptores para una cosa:** el
  icono movía solo el `<audio>` local, mientras la síntesis del server la gobernaba `chatOpen` por su cuenta →
  con el chat abierto pulsabas 🔊, el icono se ponía en ON, salía «con voz» y no sonaba nada: **el icono mentía**.
  **(b) MÓDULO DUPLICADO** (pre-existente, de alcance amplio): `main.js` importaba `services/session.js?v=3` y los
  SEIS componentes `?v=2` — query distinta = **instancia distinta** en el navegador, y la de `?v=2` tenía
  `room=null`, así que TODO lo que tocara la sala desde la UI (incluido `setVoiceOutput` del ChatWall) era un
  no-op silencioso; el modo-chat-sin-voz funcionaba solo de rebote, por la reconciliación al (re)conectar.
  Unificados los 7 imports. **(c) BUCLE REACTIVO:** el efecto de ChatWall LEÍA `botMuted()` y también lo ESCRIBÍA
  → al desilenciar se re-disparaba y te re-silenciaba al instante (eso es lo que se veía como «bloqueado»). Fix:
  `untrack()` nuevo en `core/reactive.js` (firma de Solid, la migración prevista sigue siendo un cambio de
  import). **Diseño resultante:** el defecto sigue siendo silencio al abrir el chat (ahorra latencia y coste de
  TTS), pero ahora el icono es la ÚNICA fuente de verdad —`toggleBotMute` avisa al server— así que recuperas la
  voz con un clic sin cerrar el chat, y cerrarlo NO deshace tu clic manual. El aviso dice el MOTIVO («modo chat —
  sin voz, pulsa 🔊 para oírlo igualmente»): un «silenciado» a secas costó una sesión entera buscando una avería
  de TTS inexistente. Ver [[project_v2054_chat_mode_voice_off]].
- **La RED es NATIVA, y hay clusters PÚBLICOS** (V2-086, 2026-08-01; detalle en `§3c` de
  `.meshkore/docs/architecture/zaelar-architecture.md`): el operador pegó la invitación oficial de MeshKore a un
  cluster público y no pasó nada. No era UN fallo sino **CUATRO apilados**: (1) `connect_cluster` gateada al widget
  `cluster-registro` abierto → la capacidad era INDESCUBRIBLE (verificado en vivo, turno 766: la tool ni siquiera
  estaba en el set ofrecido); (2) el esquema exigía `token` y Commons es **tokenless** → el caso era inexpresable;
  (3) la descripción rechazaba ese formato de bloque pegado —correctamente, es forma canónica de prompt-injection—;
  (4) el transporte siempre mandaba `token=` y nunca `vis=public`. **La solución de (3) NO es debilitar la guarda
  sino separar ORDEN de PARÁMETROS:** la orden la da el operador, el bloque pegado solo es de dónde se leen los
  datos. Bloque solo → RECONOCERLO y PREGUNTAR («veo una invitación a un cluster público, ¿quieres que entre?»),
  nunca actuar; bloque + petición → actuar. Se conserva la defensa intacta y es el patrón preguntar-ante-la-duda de
  V2-082 aplicado a la red. **Público ≠ privado en el protocolo:** mandar `token=` VACÍO no equivale a omitirlo (el
  servidor lo lee como auth fallida, no como entrada anónima) → `client._url()` tiene dos modos. **El widget
  `cluster-registro` se RETIRÓ** (su último estado queda en git, `ea49962`): la conectividad es infraestructura del
  sistema, no un widget de usuario → ahora es la **4ª pestaña del ChatWall** («Clusters», junto a Chat/Procesos/
  Crons, ruteada por `show_panel`), que lista los clusters con credenciales **estén conectados o no** (antes uno
  caído desaparecía de la lista justo cuando más importaba saber que existe), con peers y contadores. **Sin
  conversación**: los clusters tienen su propio monitor (decisión del operador). Enviar pasa a la tool
  `cluster_send` (gateada por cluster conectado); el confirm Sí/No se pinta en la pestaña y por fin funciona por
  BOTÓN (`/api/meshkore/confirm` — antes `/widgets/{id}/confirm` solo sabía borrar, así que solo cerraba por voz).
  **Guard de colisión de alias** (`store.unique_name`), cazado probando: al conectar a Commons el modelo eligió el
  alias `meshcore`, el del cluster PRIVADO del operador → habría sobrescrito su token. Verificado en vivo contra
  Commons: conectado sin token, peers `greeter/wanderer/zalo`, conviviendo con el privado.
- **Selección PROGRESIVA de capacidades — el prompt es O(K), no O(N)** (V2-085, 2026-08-01; detalle en
  `.meshkore/docs/architecture/zaelar-architecture.md §3b`): **medido antes de tocar nada** (catálogo real, 16
  widgets) `brief.for_prompt()` metía el catálogo ENTERO en CADA turno (2.497 chars) y `GET /widgets` devolvía los 16
  manifests completos (25.639 chars) a un consumidor (`desktop.js::_resolve`) que solo quería los **ids**. Los dos
  O(N): con 1.000 widgets un "¿qué hora es?" arrastraría ~150 KB de catálogo irrelevante; con 10.000 el turno no es
  viable (coste, latencia y sobre todo ruido de decisión para un modelo pequeño). **Regla: lo que ve el modelo es
  O(K)** — ampliar el catálogo NO engorda un turno que no va de widgets. `widgets/selection.py` es el ÚNICO sitio que
  elige, por capas de prioridad (extiende la escalera de V2-078): `open` (lo que tiene DELANTE, nunca se recorta) →
  **`named`** (lo que el operador NOMBRA este turno, vía `runtime.rank()` sobre nombre/alias de V2-082 — **esta es la
  capa que sostiene los miles**: un widget en la posición 9.999 se promociona en cuanto lo nombra) → `recent` (MRU,
  acotado) → `fill` (relleno, lo primero en caerse). Techo `MAX_WIDGETS=20`, elegido para que **hoy no cambie nada**
  (16 widgets → entran todos, prompt idéntico: cero regresión) y a la vez la garantía quede escrita en código; la
  corrección no depende del techo sino de `named`. **Lo que NO hace, deliberado** ([[feedback_no_hardcoded_understand]]):
  NO clasifica la intención con tablas de verbos/keywords — solo RECUPERA candidatos y decide el modelo por
  function-calling. Recuperar ≠ comprender. **Recortar es seguro** porque `show_widget`/`widget_data` resuelven su
  argumento server-side con `runtime.identify()` contra el catálogo COMPLETO: si algo se quedó fuera, basta pasar las
  palabras del operador; y cuando hay recorte el prompt lo DICE con esa instrucción (si no, el modelo negaría
  capacidades que sí existen o se inventaría ids). **Endpoints:** `GET /widgets` devuelve ahora un **índice compacto**
  (25.639 → 5.142 chars, sin `actions`/payload schemas/`usage`), manifests uno a uno por `/widgets/{id}/manifest`, y
  `?full=1` como escotilla ADMINISTRATIVA explícita (nunca el camino caliente); `?q=`/`?limit=` acotan server-side.
  `state.widget_registry` capado a 200 filas + marcador `_truncated` (hoy `compose_state` no lo incluye, pero "hoy no"
  no es garantía). **Tools:** el catálogo de tools es **O(1)** (23 fijas) → no crece con el catálogo de widgets;
  pero O(1) NO quiere decir barato — la constante llegó a 29,7 KB y luego a 31,6 KB, y **se paga entera en cada
  turno** (ver la decisión «Las tools, de menos a más», 2026-08-02: hoy 18,9 KB con techo en test). Aun
  así se poda por estado (V2-035 + 3 gates nuevos por CAPACIDAD REAL: `reply_message`/`reveal_secret`/`play_video`,
  todos fail-OPEN) y se clasifica en `router.FAMILIES` con `tools_report()` en `llm_metrics`. **Invariante DURO del
  gating:** un gate mira **ESTADO, jamás las palabras del turno**. **Medido después** (turno que no va de widgets):
  100 → 2.763 chars · 1.000 → 2.764 · 10.000 → 2.765 (plano); nombrar el último de 10.000 lo encuentra en 4,5 ms.
  Observabilidad por turno en `timings` (`widgets_n_total/_selected/_open/_named/_recent/_fill/_hidden`, `sz_widgets`)
  + `sz_tools`/`tool_families`/`tools_omitted`. Tests: `tests/browser/unit/widgets/test_selection_scale.py`
  (sintéticos 100/1.000/10.000).
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
  el modelo pasa `item` en lenguaje natural ("la tarea de la migración", "el proyecto Atlas") y `widgets/refs.py`
  lo resuelve al **id REAL** contra los items VIVOS del widget (`data.py:ref_index()` → `[{id,label,field}]`), NUNCA
  lo inventa; el campo a rellenar (`taskId`/`projectId`…) se deduce del `payload` declarado en el manifest, así
  "descarta el proyecto Atlas" (→`projectId`) apunta al proyecto y no a la tarea homónima. Fuzzy stdlib
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
- **El navegador es el ÚLTIMO recurso: primero se le pregunta a la RED** (`nucleo/mesh_agents.py` +
  `nucleo/mesh_cli.py`, V2-167, 2026-08-19). Conducir un Chromium por una web de reservas es pelearse con las
  defensas que esas webs despliegan justo contra eso: una corrida entera se quedó en el muro anti-bot de
  Booking (`chal_t=`) y otra en el CAPTCHA de Google, y aun cuando funciona cuesta minutos de conversación. La
  red MeshKore ya tiene agentes que sirven esos mismos dominios por HTTP. **Medido en vivo el 2026-08-19**
  contra el oráculo público: `POST /v1/search` «hotel in Madrid» → `roomrover` (vivo, **gratis**), y un POST a
  su endpoint con fechas explícitas → **10 propiedades reales con enlace de reserva en ~1 s**; «flight from
  Madrid to Rome» → `aerocast` (gratis) → 10 vuelos con precio y compañía.
  - **NO hay catálogo de agentes en ninguna parte, y es el requisito del operador**: nada en el código lista
    proveedores. Se le pregunta al oráculo EN EL MOMENTO en que se planifica la tarea, y lo que esté vivo y
    sea gratis ese día es lo que sale — dar de alta vuelos o entradas no exige tocar una línea. Lo que SÍ se
    recuerda es la RUTA («para este tipo de encargo contestó este agente»), keyeada por el `intent` que
    resuelve el propio oráculo y guardada en `sys_kv` con TTL: misma idea que la genética de
    `nucleo/flash/site_catalog.py` para webs — el primer encargo de una clase paga el descubrimiento, los
    siguientes van directos. Es una CACHÉ, caduca, y `find()` sigue estando ahí.
  - **Solo agentes GRATIS, y se aplica en el código, no en un prompt** (`_is_free`). Un precio que no se puede
    leer cuenta como NO gratis: saltarse un agente gratuito cuesta una vuelta al navegador, llamar a uno de
    pago cuesta dinero que nadie autorizó. Un `402 Payment Required` se devuelve como HECHO al llamante —
    nunca se paga, nunca se reintenta. Cuando los agentes de pago sean una decisión de producto, este es el
    único sitio que cambia.
  - **PREGUNTAR EN INGLÉS, aunque el operador hable español.** La doc del skill dice que se pase la frase del
    operador verbatim porque el oráculo parsea mejor que nosotros; medido, eso solo es cierto en inglés:
    «vuelo de Madrid a Roma» → intent `general`, **0 agentes**, mientras `"flight from Madrid to Rome"` →
    `bookings.flights` → `aerocast`. Traducir dentro del módulo metería una llamada a un LLM en un paso de
    descubrimiento que tiene que costar ~1 s, así que lo redacta el LLAMANTE: el Brain Worker ya es un modelo
    escribiendo la petición, y el inglés no le cuesta nada.
  - **Las FECHAS las resuelve el llamante.** Medido: pedido «esta noche» el 2026-08-19, el agente resolvió el
    check-in al **año anterior** y devolvió cero resultados; con la fecha ISO explícita devolvió diez. Y hay
    que COMPROBAR lo que vuelve: el emparejamiento falla en los bordes (una consulta de restaurante la
    contesta un agente de hoteles), y un agente que contesta de otro dominio es una vuelta al navegador, no un
    resultado.
  - **Dos trampas heredadas de `integrations/openclaw-plugin` que ya estaban pagadas allí**: el campo de texto
    libre que leen los agentes reales es **`prompt`**, no `query` (un `{"query": …}` impecable vuelve `400
    missing_fields`; se mandan los dos); y de la ficha `/.well-known/agent.json` se toma **solo el PATH, jamás
    el host** — un agente anuncia un hostname sin registro DNS mientras el origen que el oráculo verificó
    sirve ese mismo path perfectamente, así que fiarse del host cambia un 404 por un fallo de red.
  - **Cableado**: `hbmesh` es un puente más del worker (`_BRIDGES` de `claude_session`, que Grok hereda; Codex
    tiene shell completo), y `dispatch_prompts._web_prompt` lo pone como **PASO 0**, antes de abrir nada. Todo
    fail-open: red caída, sin agente o agente que no contesta degradan al navegador de siempre — hoy la red
    cubre poco más que hoteles y vuelos, así que ese camino sigue siendo el habitual.

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
- **El SEGUNDO backend de Brain Worker: Codex — y su frontera de seguridad es DISTINTA** (`nucleo/workers/
  codex_session.py`, 2026-08-12). La agnosticidad de V2-038 dejó el punto de extensión con un **stub honesto**, y el
  precio de dejarlo ahí se cobró entero: con el proveedor puesto a `codex` el operador se quedaba SIN workers y el
  síntoma era una tarea que **moría al instante**, no un mensaje de configuración. Ya es un adaptador real:
  `codex exec --json` escribe **JSONL** y se traduce al vocabulario normalizado — `thread.started`→`spawned` (con el
  `thread_id`, que es lo ÚNICO con lo que se reanuda vía `exec resume`), `item.started`→`step`,
  `item.completed`→`step_result` (la EVIDENCIA) o `note` (su narración), `turn.completed.usage`→`result` con los
  tokens REALES (Energy los tariffa en `session.py::_finish`), `error`/`turn.failed`→`error` fatal. El prompt entra
  por stdin (por argv un prompt largo revienta el límite), killpg/SIGSTOP igual que Claude Code, y el CLI se
  localiza bajo nvm (como `claude`, no está en el PATH del server).
  - **La frontera de seguridad NO es la misma, y eso es lo importante.** Claude Code acota `Bash` a nuestros puentes
    (`--allowedTools`), que ES el invariante del ESCRITOR ÚNICO de la memoria. Codex no tiene ese eje: tiene MODOS de
    sandbox, y headless exige `workspace-write` (verificado: en ese modo ejecuta comandos SIN pedir aprobación, que
    en headless nadie daría). O sea que **un worker de Codex corre un shell COMPLETO** — más radio de acción. Nunca
    se usa `--dangerously-bypass-approvals-and-sandbox`. Consecuencia de diseño: `registry.get_backend` es
    **mezclable por CAPACIDAD, no solo por tipo de tarea** — una tarea con `deny_tools` (entrada NO confiable,
    V2-010) o `kind="dev"` (dev worker de un peer de cluster) va a `claude_code` **aunque la config diga Codex**, y
    se dice en el log; `codex_session` conserva además su rechazo fail-closed como defensa en profundidad. Elegir
    Codex para el trabajo normal no puede costar las capacidades del cluster, ni de forma visible (tarea fallida) ni
    invisible (worker con shell abierto).
  - **La RED hay que abrirla a mano** (`-c sandbox_workspace_write.network_access=true`): el sandbox de Codex la
    corta, y TODOS nuestros puentes hablan HTTP con el server vivo. Sin eso el worker arranca, trabaja y entrega…
    **sin memoria y sin poder reportar su fase** — medido en la primera prueba en vivo, donde narró «no puedo
    publicar el progreso en el puente local» y siguió a ciegas. Es todo-o-nada (no hay allowlist de hosts), así que
    abre internet; no es una clase de riesgo nueva (un worker de Claude Code ya tiene WebSearch/WebFetch) pero queda
    escrito. Kill-switch `ZAELAR_CODEX_NETWORK=0`.
  - **`send()` no inyecta en vivo** (`codex exec` no lee turnos por stdin) y no hace falta: la vía PRINCIPAL de
    inyección es el **piggyback** en las respuestas de los puentes (§v2·A), que es HTTP y por tanto agnóstica del
    backend.
  - **El modelo lo decide el PROVEEDOR, no la cadena de relevo** (fix del mismo día en `dispatch._model_for`): la
    cadena de `workers/providers.py` es de Claude Code (escalones `ANTHROPIC_BASE_URL`-compatible) y estaba
    decidiendo también el modelo de Codex → con `base_url` apuntando aún a Z.AI y Z.AI en cooldown, `relayed()` daba
    True, se devolvía el modelo del escalón (vacío) y Codex caía a su propio `config.toml`; el `gpt-5.5` elegido por
    el operador no llegaba nunca. Ahora la cadena solo manda si el backend ES `claude_code`.
  - **Cada proveedor ofrece SOLO sus modelos** (`server/config_api.py`): las listas estaban vacías, la UI pintaba
    campos libres, y al cambiar de proveedor se quedaban los del anterior (`glm-5.2` en Codex) → la tarea moría
    minutos después con «There's an issue with the selected model», que el operador no puede relacionar con lo que
    guardó. Hoy el catálogo declara los modelos por proveedor, el backend RECHAZA al guardar uno que ese proveedor no
    sirve, y se DETECTA si el CLI está instalado y con qué versión. Los de Codex están verificados contra la lista
    que devuelve su propio servidor de modelos.
  - Verificado en vivo de punta a punta: escalada → worker de Codex (`gpt-5.5`) → 13 consultas por el puente de
    memoria + fase y progreso reportados → entrega, `ok=true`. Tests: nodo 2.5 (`test_codex_session.py`).
- **El TERCER backend: Grok Build — y la elección de worker es una TERNA, no una casilla** (`nucleo/workers/
  grok_session.py` + presets de `server/config_api.py`, 2026-08-13). «El proveedor de los Brain Workers» era una sola
  casilla y eso escondía que son **dos decisiones independientes**: quién **CONDUCE** (el CLI headless) y quién
  **RAZONA** (endpoint + modelo). Elegirlas por separado producía desajustes silenciosos —`glm-5.2` pedido a Codex,
  `gpt-5.5` pedido a Z.AI— que no fallan al guardar sino minutos después dentro de una tarea ya muerta. De ahí los
  **presets**, que mueven la terna junta con su coste y su estado (CLI detectado / credencial presente / `blocked_by`).
  - **Grok Build HEREDA de `ClaudeCodeSession`** (`GrokSession`) porque su `--output-format streaming-messages-json`
    emite **el MISMO vocabulario** que el stream-json de Claude Code. Solo se sobrescribe su vocabulario por una
    costura de tres métodos (`_tool_step`/`_tool_phase`/`_result_text`) y la forma de su evidencia. Reimplementar la
    traducción habría sido duplicar el traductor entero para cambiarle los nombres.
  - **Sí puede sostener el invariante del ESCRITOR ÚNICO** (a diferencia de Codex): acepta `--allow 'Bash(cmd:*)'` y
    lo APLICA — verificado contra el CLI, no supuesto. Por eso `registry` NO lo desvía: puede correr tareas con
    `deny_tools`.
  - ⚠️ **Su allowlist es ESTRICTA: en cuanto hay UNA regla `--allow`, `--permission-mode acceptEdits` deja de
    aprobar lo no listado.** Las reglas se generan desde `_TOOL_ALIAS` (que ya es el mapeo a nombres de Claude, y son
    los que las reglas entienden) para que **no existan dos listas** que se desincronicen: una tool sin alias es una
    tool sin permiso, y hay un test que lo impide. Costó tres corridas del banco descubrirlo porque el síntoma no
    dice «permiso»: Grok presenta una denegación como «**User cancelled the execution for tool X**», el modelo lo lee
    como que el humano lo abortó y **PARA con entrega vacía tras haber trabajado bien**. Ese texto lo escribe el CLI
    dentro de su bucle y no pasa por nosotros, así que se desarma por delante con `_BACKEND_NOTE`, que el propio
    backend pega a su prompt (es una rareza de ESTE CLI; no ensucia `dispatch`).
  - **Grok NO tiene `web_fetch`** (catálogo sondeado entero): descubre páginas pero no puede abrirlas — y en el banco
    el `WebFetch` fue quien hizo TODO el trabajo cuando la búsqueda del relay estaba agotada. Esa pata la dan los
    PUENTES (`worker_bridge` → la `web_search` propia, `nav_cli` → el navegador real), no el CLI.
  - ⚠️ **`grok -p -` NO lee stdin** (a diferencia de `codex exec -`): toma el `-` como prompt literal, el nuestro se
    pierde y **no da error** — el modelo se pone a hacer algo razonable por su cuenta. Medido: **447.559 tokens y
    $0,73** explorando el repo cuando se le pidió imprimir una versión; con el prompt entregado por `--prompt-file`,
    $0,005. Un prompt que no llega es la avería más cara y más muda de este backend, y por eso el guard vive en tests.
  - **El banco y sus resultados**: `zaelar-model-benchmarks.md §14` (los tres CLIs comparados por lo que los
    distingue de verdad, la tabla de la corrida real, y los cuatro defectos que solo aparecieron corriéndolo). Estado:
    **Claude Code + Z.AI es la única probada de punta a punta**; DeepSeek es la más interesante por precio y sigue
    **bloqueada por credencial**. Tests: nodo 2.5 (`test_grok_session.py`).
- **Los Brain Workers no dependen de UN proveedor — cadena + relevo automático** (`nucleo/workers/providers.py`,
  2026-08-02; detonante: el plan de Z.AI agotó su cuota SEMANAL en mitad de una búsqueda —«[1310] Weekly/Monthly
  Limit Exhausted. Your limit will reset at 2026-08-04»— y todo se cayó a la vez: el worker murió, al operador se le
  entregó el texto del error donde esperaba su informe, y el **panel de alertas no dijo nada** porque el proveedor de
  los workers no estaba en ningún mapa de servicios). **Quien conduce es SIEMPRE Claude Code**; lo que se releva por
  debajo es el endpoint Anthropic-compatible (`ANTHROPIC_BASE_URL`+`ANTHROPIC_AUTH_TOKEN`). Regla del operador:
  **planes de SUSCRIPCIÓN (forfait), nunca pago por token** — dos suscripciones baratas cubren el hueco semanal de
  una. Piezas: **cadena ordenada** (`chain()`) donde un escalón SOLO existe si su credencial está presente (catálogo
  `KNOWN`: z.ai/GLM, moonshot/Kimi `https://api.moonshot.ai/anthropic`; ampliable con una línea o desde
  `code_agent.providers` sin tocar código) · **agotado ≠ roto** (`classify_failure`: `exhausted` releva y pone
  cooldown **hasta la fecha de reset que da el propio proveedor**; `rate` es pasajero y NO quema el escalón; un fallo
  de la TAREA no es un fallo de proveedor) · cooldown **persistido** (`sys_kv`) para que un reinicio no reintente una
  cuota agotada hasta el jueves (**con SUELO de media hora desde 2026-08-09**: si la fecha de reset que da el
  proveedor ya PASÓ —respuesta cacheada, reloj desfasado, texto de error reutilizado— el cooldown quedaba en el
  pasado, el escalón volvía a estar disponible en el acto y se relevaba a SÍ MISMO → el bucle de 429 que esta pieza
  existe para cortar. Arreglado en los DOS hermanos, `nucleo/workers/providers.py` y `nucleo/flash/provider_chain.py`;
  el commit lleva mensaje de observabilidad, `3552324`, porque otro agente lo barrió con un `git add -A`) · **el modelo va PEGADO al escalón** (`code_agent.model`=`glm-5.2` solo existe en SU
  proveedor: el primer relevo cambió el endpoint pero siguió pidiendo `glm-5.2` y el CLI murió con «There's an issue
  with the selected model» — `providers.relayed()` decide, y sin relevo manda el modelo POR INVOCACIÓN de siempre) ·
  **reintento único** de la tarea con el escalón de relevo (`SessionRecord.provider_down`, `_finish`) · y la
  **ALERTA** por fin en el panel (`balances.worker_providers()` + `summary_with_workers()`, alimentado por
  `health_state`), con una fila propia `worker:sin-relevo` cuando no queda ningún escalón. **La licencia local de
  Claude Code es el ÚLTIMO escalón y SOLO en local** (autorizado por el operador 2026-08-02): un login de navegador
  no corre en un contenedor, así que en **cloud la cobertura la dan dos tokens de suscripción**, nunca la licencia.
  Fail-open: sin config ni credenciales, `env_for_worker()` devuelve {} y todo se comporta como antes.
- **Energy metering — cobertura real, no solo tabla de tarifas** (`nucleo/energy_meter.py`, 2026-08-05;
  detonante: el operador pidió avanzar el sistema de Energy para TODO el consumo real —voz+FlashBrain+Brain
  Workers— porque "sino perderemos dinero"). **Hallazgo antes de tocar nada**: `report_llm_usage()` se llamaba
  desde UN SOLO sitio (`nucleo/flash/fast_client.py`, el turno de voz), y la tabla de tarifas solo cubría
  `"x.ai"`/`"api.openai.com"` — pero el FlashBrain de PRODUCCIÓN corre sobre **AIMLAPI** (`config/v2.json §fast`,
  un broker multi-modelo), que no matcheaba ninguna fila → **el 100% del tráfico real de voz meteraba a CERO
  coste de Energy**, en silencio, sin ningún error. Fix en tres piezas: **(1) tarifa por (base_url,modelo)** —
  AIMLAPI es un broker de decenas de modelos a precios muy distintos, así que un único par `(in,out)` por
  `base_url` (lo que servía para x.ai/openai) es estructuralmente insuficiente; `_AIMLAPI_MODEL_RATES` tariffa
  por MODELO cuando el broker es AIMLAPI. **(2) FALLBACK nunca-silencioso** — un `(base_url,modelo)` no
  mapeado YA NO devuelve `None`/coste-cero: aplica una tarifa de seguridad (logueada 1×) y sigue cobrando.
  Perder dinero por sub-cobrar es peor que sobre-cobrar un poco a un proveedor raro/nuevo — el fallo por
  defecto se invirtió a propósito. **(3) Brain Workers metrados** (`nucleo/workers/session.py::_finish` +
  `claude_session.py`): el CLI de Claude Code YA calculaba `usage`/`total_cost_usd` reales en su mensaje
  `"result"` de stream-json, pero morían en un chip de UI (`voice.observer`), nunca en Energy —
  `report_worker_usage()` los tariffa con la MISMA tabla (no con el `total_cost_usd` del CLI: ese número usa
  precio OFICIAL de Anthropic, que no significa nada una vez el worker se relevó a un plan forfait de Z.AI/
  Moonshot — ver decisión anterior). **Gate = `nucleo/cloud_account.is_cloud_account()`**
  (`ZAELAR_USER_ID`, inyectado por el provisioner en `accountMachineConfig`). El reporte va a
  `POST {CONTROL_PLANE_URL}/usage` con `{user_id,energy,kind}` + `X-Service-Token` (el endpoint YA
  existía en `cloud/control-plane`, solo faltaba que el motor lo llamara — Fase 3 M8 del plan INI-019).
  **2026-08-09 (INI-020):** el sistema demo anónimo efímero (`demo_routing.py`/`demo_limits.py`,
  Machines compartidas de 15 min) se RETIRÓ por completo — toda alta, gratis o de pago, es hoy una
  cuenta real con Machine+Volumen propios; el corte pasa a ser por saldo de Energy
  (`nucleo/account_limits.py`), nunca por turnos/TTL.
  **Precios verificados por web (2026-08-05, re-verificar periódicamente)**: DeepSeek V4 Flash $0.14/$0.28,
  GLM-5.2 $1.40/$4.40, Kimi K2.6 $0.95/$4.00, Claude Haiku 4.5 $1.00/$5.00 (fallback). **Gap cerrado el
  mismo día**: la generación de widgets (`widgets/generator.py::_run_agent`) también lanza `claude -p
  --output-format json` con `usage`/modelo reales en la salida — antes se descartaba el stdout entero sin
  parsearlo (nunca metraba pese a costar tokens reales); ahora se parsea y reporta a
  `report_worker_usage` (best-effort: stdout no-JSON o sin `usage` no rompe una generación que ya
  terminó bien). El reporte de uso ahora también manda `meta:{model,base_url}` — el control-plane
  (`cloud/control-plane`) reutiliza ese MISMO payload (zero-PII por construcción) para alimentar
  `zaelar_user_events`, la observabilidad centralizada por-usuario del backoffice (Cambio A, sin
  endpoint de ingesta nuevo ni redactor nuevo en `engine/` — ver la addenda de INI-019 para el porqué).
  Detalle completo + decisión de negocio: `.meshkore/roadmap/initiatives/INI-019-fase3-backoffice-multitenant.md`
  (raíz del workspace) addenda 2026-08-05.
  - **CUATRO agujeros más, todos cobrando de MENOS (2026-08-13, encontrados corriendo el banco de Brain Workers).**
    El patrón se repite: no fallaba nada, simplemente el número salía bajo y nadie lo comparaba con nada.
    **(a) Matar un worker era GRATIS** — el reporte vivía DENTRO del `if rec.status != "cancelled"` de
    `session.py::_finish`, que existe por una razón de INTERFAZ (no pintar dos filas `end` contradictorias, demo
    2026-07-14) y se llevaba por delante una de FACTURACIÓN sin relación. Y como el supervisor MATA por diseño al
    agotarse el presupuesto (`loop._budget_for`), no era un borde: era el camino normal de toda tarea que se pasa
    de tiempo. Dos preocupaciones en un solo `if`; separadas.
    **(b) Sin `result` no había números** — un proceso matado nunca lo emite. Cada mensaje `assistant` trae SU
    `usage` y el del `result` es solo la suma (verificado sondeando: 61.969+127 = 62.096), así que se acumula
    mensaje a mensaje: **la factura no puede depender de que el proceso tenga la cortesía de despedirse.**
    **(c) El precio es del MODELO, no del endpoint** — `_MODEL_RATES` se consulta ahora PRIMERO para todos los
    proveedores (antes solo si el endpoint era AIMLAPI), con el patrón más específico ganando. La suposición «un
    endpoint = un precio» se había roto ya dos veces: con el broker AIMLAPI y con xAI, donde la fila decía el tramo
    Fast mientras un worker corría un modelo 10× más caro. Un backend que habla con su proveedor DIRECTAMENTE (Grok
    Build) no reporta `base_url`, así que sin fila por modelo caía a la tarifa de seguridad.
    **(d) El input CACHEADO no se cobraba** — `cache_read_input_tokens` es un contador SEPARADO (no va dentro de
    `input_tokens`) y es una línea que el proveedor factura. En una sesión agéntica larga el mismo prefijo se
    relee en cada turno, así que los cacheados acaban siendo VARIAS VECES los frescos. Su tarifa se DERIVÓ
    MIDIENDO —dos llamadas de tamaños muy distintos resuelven ambas al mismo valor contra el coste que reporta el
    CLI del proveedor, mientras que la cifra que circula por la web no encaja en ninguna— y con ella el cálculo
    cuadra al microdólar (0,0% de desvío en las dos muestras). Sigue SIN modelarse el tramo de contexto largo de
    `grok-4.5` y el `cache_creation_input_tokens`.
    **La equivalencia, el margen y el precio de venta son decisiones de NEGOCIO y NO se documentan aquí** (este
    repo es público): viven en `.meshkore/docs/ops/zaelar-energy-accounting.md` de la RAÍZ del workspace, junto a
    la tabla de Energy por millón de tokens y la lista de lo que sigue sin cobrarse. Aquí solo el mecanismo.
  - **QUINTO agujero, misma familia: el turno CANCELADO se cobraba un 16% de menos (2026-08-14).** Un turno cortado
    por barge-in ya se le pidió al proveedor y ya se pagó — en una sesión de dictado son **38 de 54**. Sí se
    factura (el reporte vive en un `finally` y hay un estimado sembrado ANTES de la petición, así que la parte
    difícil ya estaba bien; la afirmación de que «no se facturaban ~400k de input» era MÍA y era falsa). Lo que
    estaba mal es el NÚMERO: el `usage` real del proveedor viaja en el ÚLTIMO chunk del stream y un turno cancelado
    no lo recibe nunca, así que lo factura `est_tokens`… que asumía **4 chars/token**, la regla del pulgar del
    INGLÉS. Medido contra 114 turnos reales que traían el `usage` del proveedor Y sus chars, nuestro input va a
    **3,36 chars/token** (castellano con tildes + el JSON del catálogo de tools), y el sesgo era sistemático, no
    ruido: el ratio cabía entre 0,823 y 0,857 en las 114 muestras. `_CHARS_PER_TOKEN = 3.3` (se redondea hacia
    abajo a propósito: estima de MÁS, el lado seguro, igual que la tarifa de seguridad). Y `turn_perf` emite ahora
    `usage_source`/`prompt_tokens_est`/`prompt_chars`/`tools_chars`, porque **un número que se factura tiene que
    poder compararse con la verdad en su propia fila**: reconstruir este sesgo exigió cruzar campos que solo
    coincidían en 114 de 1.070 eventos. Nodo 2.14, con las dos ramas (cancelado→estimado, completo→verdad del
    proveedor, y que la verdad GANE) — sin la segunda, la primera la aprobaría un medidor que siempre adivina.
  - **SEXTO: la VOZ facturaba a la tarifa de otro proveedor, y el precio dejó de vivir en el código
    (2026-08-16, `nucleo/energy_tariffs.py`).** El STT y el TTS SÍ se metraban desde julio (hook
    `metrics_collected` de `voice/engine/pipeline/agent.py` → `report_stt_usage`/`report_tts_usage`, con las
    métricas que LiveKit ya emite: `audio_duration` y `characters_count`). Lo que fallaba era el precio:
    `_STT_USD_PER_MIN = 0.0048` era **Deepgram Nova-3** y producción corre **Voxtral realtime a $0,006/min**,
    o sea el **80%** del coste. El TTS estaba bien ($0,05/1k = ElevenLabs Flash v2.5), lo que importa decir:
    el impulso al encontrar un fallo es tocar los dos, y tocar el bueno introduce uno nuevo.
    - **El defecto NO era el número sino su forma**: había UNA constante plana por familia y **nada la ataba
      al proveedor que corre**. Es la tercera vez que esta casa paga la misma avería (la tabla por `base_url`
      que metró el 100% de la voz a cero; el mapa de proveedores del master escrito a mano). Ahora la tarifa
      se resuelve **por proveedor** desde `SETTINGS.stt_provider`/`tts_provider`, y el `provider` es un
      argumento OBLIGATORIO sin default — un default sería un segundo sitio donde el precio deja de
      corresponder con lo que corre.
    - **El precio ya no se despliega: se edita.** La autoridad es una tabla del control-plane que el operador
      cambia desde el master, y viaja a cada Machine **piggyback en la respuesta del arriendo** — la única
      llamada periódica que el motor ya hace. Un endpoint propio habría añadido llamada, modo de fallo y reloj
      nuevos para mover unos números que cambian una vez al mes; y el arriendo (ADR-0005) exige **cero red en
      régimen**, así que el cálculo sigue siendo local contra una caché en `sys_kv`. Motivo de fondo: una
      release **no llega sola a las Machines de inquilino**, así que un número que caduca no podía seguir
      viviendo en un artefacto que se despliega a mano.
    - **Las UNIDADES CRUDAS viajan en `meta`** (`audio_seconds`, `characters`, `participant_seconds`) junto al
      Energy. Energy es el precio aplicado a ellas y un precio puede estar mal: sin las unidades, la central
      solo puede decir lo que cobramos, nunca lo que debió costar — ni re-tarifar hacia atrás, ni cuadrar con
      el panel del proveedor. Nunca contenido: un RECUENTO de caracteres, jamás el texto.
    - **El TRANSPORTE (LiveKit) tampoco se cobraba** y ahora sí, al cerrar sesión (`observability/identity.py`),
      por minuto de **participante** × 2 — la sala factura también los silencios entre turnos, que es justo lo
      que ningún hook por-turno vería. Su tarifa es la más propensa a estar mal *por diseño*: con cuota
      incluida el coste marginal real es **cero**, y eso es un hecho del PLAN del operador, no del código —
      por eso `0` es un valor legítimo del tarifario y no un hueco.
    - **Trinquete (nodo 8.1e)**: un test lee `BASE_PROVIDER_ENV` del provisioner y falla si el proveedor que la
      nube declara no tiene tarifa. El defecto se detecta **al cambiar la configuración**, no tres semanas
      después mirando una factura. Verificado rompiéndolo a mano. Y el catch-all cobra la tarifa **más cara**
      conocida avisando una vez: sub-cobrar en silencio pierde dinero, sobre-cobrar se ve y se corrige.
- **Control central de proveedores en el perfil cloud** (`server/config_api.py` + `ConfigPanel.js`,
  2026-08-05, INI-019 "Cambio B"): en self-host el usuario elige proveedor/modelo por pieza
  (`_PROVIDER_CATALOG`: fast/code_agent/memory/triage/susurro); en una cuenta cloud esa elección la fija
  el operador de forma centralizada — sino perdería el control de coste/calidad de una plataforma de
  pago. `GET /api/config` expone `cloud_profile` (= `nucleo.cloud_account.is_cloud_account()`, mismo
  accessor que gatea Energy); `POST /api/config/v2` devuelve 403 para las secciones de proveedor cuando
  `cloud_profile` es verdad (`flags` queda fuera del gate — no es una elección de proveedor).
  `ConfigPanel.js` oculta esas secciones del menú + los selectores STT/TTS de la sección voz en ese
  perfil (idioma/VAD/atención siguen editables). **Self-host queda byte-idéntico** — el gate solo existe
  si `ZAELAR_USER_ID` está puesto, que nunca ocurre fuera de una Machine de cuenta cloud.
  **Deliberadamente sin tocar** `POST /api/config/credential`: mezclaría credenciales de CONECTORES
  propios del usuario (email/WhatsApp/Telegram/Spotify, que deben seguir siendo autoservicio incluso en
  cloud) con claves de proveedor central — bloquearlo bien exige una lista precisa de qué env-var es
  cuál, que no existe hoy; construirla deprisa arriesgaba romper el autoservicio de conectores. Follow-up
  anotado, no bug.
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
  SIN incidente real (funciones puras + watcher + rotación real: `tests/infrastructure/unit/core/test_homeostasis.py`, dominio 9 del mapa de
  tests). La memoria ya se auto-cura (schema/olvido/dedup); esta pieza cubre lo que NO: motor de voz, logs, cápsulas.
  Detalle: `.meshkore/roadmap/initiatives/V2-070-homeostasis-anti-degeneracion.md`.
- **REHIDRATACIÓN — el trabajo que corta un reinicio se recoge, no desaparece** (`nucleo/rehydrate.py`,
  2026-08-12; detonante reconstruido evento a evento del log durable: a las 12:19:46 el operador pidió una búsqueda
  de veleros en Wallapop, el worker abrió su pestaña, y un reinicio a las 12:21:15 se lo llevó por delante **sin
  dejar rastro** — ni evento, ni entrada en el ledger, ni aviso; la pantalla siguió pintando dos tarjetas de un
  navegador que ya no existía y al recargar quedó en blanco). Tres agujeros distintos, no uno: **(1)** el registro
  de sesiones vivas (`dispatch._SESSIONS`) era RAM y NADIE lo leía al arrancar → `dispatch.sync_state()`, que ya
  sabe cuándo la proyección cambia (no añade escrituras en reposo), deja un **rastro durable con marca de tiempo en
  `sys_kv`** y el lifespan lo recoge UNA vez; **(2)** la continuidad web (`_WEB_RESUME`, el `native_sid` con el que
  el worker RETOMA su razonamiento) también era RAM → espejada en `sys_kv` con su TTL, porque sin ella «reanudar»
  sería empezar la búsqueda de cero; **(3)** el escritorio no volvía (ver la decisión siguiente). **Rastro en
  `sys_kv`, NUNCA en el ESTADO raíz**: `memory.api.compose_state` vuelca cada escalar suelto del estado al prompt
  como «Clave: valor.», así que un timestamp ahí viajaría en todos los turnos. **Lo reanudable se re-escala** (en
  diferido: el listener de escaladas tiene que estar suscrito o el evento se publica contra nadie) y **todo lo demás
  queda VISIBLE** — al ledger como `interrumpido`, con evento y MOTIVO. No se reanuda solo, a propósito:
  `kind="code"` (reescribe el código de un widget del operador), lo que él pausó, lo que esperaba su respuesta (la
  pregunta murió con el proceso), ni nada más viejo que `STALE_S`. **Anti-bucle:** el rastro se CONSUME al leerlo +
  contador durable por objetivo (`RESUME_CAP`) + techo por arranque (`MAX_RESUME`). El **reset lo borra**: matar el
  trabajo a mano es una orden, no una caída. Módulo aparte y sin estado propio — circunstancia → función → se
  aparta; **no-op silencioso en todo arranque limpio**. Y dos superficies que mentían: Procesos pintaba con ✓
  cualquier estado desconocido (una tarea muerta a medias se veía terminada con éxito) y `make stop`/`restart`
  mataba trabajo del operador sin decir palabra — ahora lista lo que va a interrumpir antes de tocar nada. Tests:
  nodo 2.5 (`test_rehydrate.py`) + nodo 4.13.
- **El ESCRITORIO se rehidrata — y el `localStorage` es per-ORIGEN** (`desktop.js` + `GET /api/canvas/layout`,
  2026-08-12): la mitad de frontend del incidente anterior. `_persist()` excluía `navegador` **por nombre** — el
  único widget excluido así, y justo el que está en pantalla durante una tarea web → recargar en mitad de una
  búsqueda dejaba el canvas literalmente vacío. Ahora la tarjeta BASE del navegador se guarda; sus tarjetas de
  INSTANCIA (`navegador::tN` = una pestaña/tarea) siguen siendo efímeras a propósito (mueren con su tarea:
  restaurarlas pintaría algo que ya no existe). Y el único almacén era el `localStorage`, que es **per-origen y
  per-navegador**: el mismo zaelar por `http://localhost:43917` y por `https://local.zaelar.com:44317` son **dos
  escritorios distintos**, así que cambiar de puerta de entrada, de navegador o de perfil PARECE pérdida de datos y
  no lo es. El server guarda la geometría como **red de seguridad** (en `sys_kv`: al cerebro no le importan las
  coordenadas de una tarjeta) y `restore()` la usa **solo como fallback** — si este navegador tiene su escritorio,
  manda él (el frontend sigue siendo AUTORITATIVO del canvas). La **época de wipe conserva la última palabra**: tras
  un reset el escritorio queda en blanco y aquí no se resucita.
- **Canal nativo MeshKore** (`connectors/meshkore/`): 3er I/O (voz+chat+cluster), conducido por el **MISMO motor del
  FlashBrain en perfil UNTRUSTED** (V2-069 «una sola mente»): hablar con el operador o con un agente es el MISMO acto.
  **El algoritmo COMPLETO, de punta a punta (ciclo de vida, orden exacto de cada guard, tabla resumen de defensa
  en profundidad) vive en `zaelar-cluster-channel.md`** — esta entrada resume las piezas, esa doc narra el flujo.
  `connectors/meshkore/brain.py` adapta el canal al motor (resuelve el TIER de modelo off-voz, hoy GLM-5.2) y delega en
  `nucleo/flash/cluster.py` (FastClient **no-streaming** `complete()` + `prompt.build_cluster_system` identidad-safe +
  defensas de `dialog`, **tools APAGADAS en código**). Un peer puede hacer que zaelar razone y hable, nunca actuar. El
  estado de la conversación vive en la **cápsula** (`connectors/meshkore/capsule.py`, memoria-de-relación scope-partido)
  — ver la decisión clave «V2-069». El enrutado seguro de input no confiable al `CodeAgent` (deny-tools/sandbox) se
  construyó en V2-076 (dev worker acotado + sandbox), gated por el PERFIL DE PERMISOS del cluster (ver esa decisión).
  **`nucleo/git_cli.py` re-verifica el `origin` REAL del directorio en CADA `commit`/`push`, no solo al `clone`**
  (fix auditoría 2026-07-26 — antes solo comprobaba que existiera `.git`, un dir apuntado a cualquier repo pasaba).
  **Gap conocido, no cerrado:** `nucleo/sandbox.py` (rlimits/env-scrubbed) existe pero NO está cableado al
  subproceso interactivo del dev worker — su jail de Read/Write/Edit sigue siendo convención de prompt, no código;
  tarea P1 en la iniciativa de remediación de la auditoría.
  - **CICLO DE VIDA / RECONEXIÓN — el conector gestiona el estado y REANUDA la conversación solo** (documentado
    2026-07-26, código ya existente): (1) **arranque** → el lifespan **auto-reconecta** a los clusters persistidos
    (`store.load_clusters` → `manager.connect` → `bridge.note_objective`, `server/__init__.py`); (2) **primer contacto**
    con un peer NUEVO → saludo breve (nombre+capacidad) **una sola vez** (`mem_ingest.known_peer` durable) + **propuesta
    de PACTO** (convenciones, V2-072); (3) **estado por-relación PERSISTE** entre reinicios en la **cápsula** (sys_kv:
    objetivo/fase/pacto/greeted/turnos/balance) — no se pierde al reiniciar browser/server; (4) **RECONEXIÓN** de un
    peer YA conocido → **catch-up automático** (`bridge._catch_up_context`, disparado en `presence:online` y en `ready`):
    si su último mensaje quedó SIN contestar (compara `last_in_ts` vs `last_out_ts` del journal durable), zaelar
    **retoma y responde solo** desde donde estaba, con el objetivo/fase de la cápsula presentes — **el operador NO tiene
    que pedirlo a mano**. Dedup `_caught_up` por `(cluster,peer,ts)` para no re-nudge en bucles de reconexión. Nota: el
    catch-up necesita que el peer esté PRESENTE (reconecte); con el peer offline no hay con quién reanudar (espera). El
    OBJETIVO lo fija SIEMPRE el operador y vive en `capsule.objective`; si un peer intenta redirigirlo, se mantiene o se
    para. **Guard de propiedad-de-objetivo para el DEV-WORKER: CONSTRUIDO (auditoría 2026-07-26)** —
    `perms.gate_dev_by_objective` degrada `dev=False` si `capsule.objective` está vacío, aunque el permiso `code`
    esté concedido (antes el permiso bastaba por sí solo — hallazgo P0, nada escribía `objective` nunca). Efecto
    práctico: el dev-worker vía cluster queda INERTE hasta que exista un mecanismo para que el operador FIJE el
    objetivo de una relación (no construido aún, ver iniciativa de remediación). El guard MÁS GENERAL —
    notificar+pedir permiso ante CUALQUIER intento de un peer de redirigir la conversación (no solo hacia
    dev-worker), enganchado al veredicto `off_track` del evaluador V2-075 — sigue PENDIENTE.
- **Una tarea/flujo SOLO nace de CUATRO fuentes — el pulso NUNCA crea trabajo por tener un loop** (norma dura del
  operador, 2026-08-16; detonante: un flujo de cluster («Cluster · T6 · en curso») visible en el master tras
  minutos SIN que el operador pidiera nada — "el agente está totalmente estático"). Las únicas fuentes
  legítimas de una tarea/turno/flujo son: **(1)** una petición del OPERADOR (voz/chat/UI), **(2)** un mensaje
  REAL entrante de un peer de un cluster MeshKore, **(3)** un CRON venciendo (`nucleo/scheduler.py`), **(4)** un
  CONECTOR recibiendo algo (mensaje de WhatsApp/Telegram/email, evento de un widget backed). Cualquier pieza que
  corra con un LOOP propio (el pulso `nucleo/loop.py`, el latido del cluster `bridge.py::_heartbeat`,
  homeostasis) puede **vigilar y actuar sobre trabajo que YA existe** (cerrar un flujo inactivo, reciclar un
  recurso, avisar) pero **JAMÁS abrir un turno de cerebro nuevo solo porque el reloj avanzó**.
  - **El hallazgo real, y por qué NO era ninguna de las cuatro fuentes**: `bridge.py::_heartbeat()` (el latido
    del canal de cluster, cadencia `TICK_SECS`) comprobaba cada cluster "engaged" y, si llevaba `IDLE_SECS`
    (90s) sin actividad CON PEERS ONLINE, lanzaba `_heartbeat_nudge()` → un turno de cerebro COMPLETO (mismo
    `_brain_turn` que un mensaje real) preguntándole al modelo si seguir esperando o concluir — un "¿sigues
    ahí?" humano, pero **disparado por el PULSO, no por nada que el peer dijera**. Ídem
    `_evaluate_and_apply()`'s "hand_back": corre off el mismo latido (`EVAL_SECS`), no de un mensaje nuevo.
    `_brain_turn` etiquetaba AMBOS con `origin="cluster"` — el MISMO origen que un mensaje entrante de verdad —
    así que el master no tenía forma de distinguir "un peer me escribió" de "el reloj decidió comprobar".
  - **Fix, sin apagar la función humana ("¿sigues ahí?" sigue existiendo, sobre una conversación YA real)**:
    `_brain_turn(..., origin=...)` — solo el disparo real desde un mensaje/evento de transporte entrante
    (`t=="message"/"presence"/"ready"`) mantiene `origin="cluster"`; el nudge de idle y el hand-back del
    evaluador pasan `origin="pulso"` (`voice/trace.py::begin` los trata igual que "cluster" para el `cat` de
    sesión — mismo housekeeping, no fabrica sesión — pero ya son distinguibles por `origin`). El master
    (`cloud/backoffice/src/sessionsView.js::flowIsInit`) atenúa `pulso` como NO-tarea (igual que `kickoff`/
    `cron`/`proactivo`) y ya NO atenúa `cluster` — un peer real SÍ es una tarea legítima, no housekeeping.
  - **Segundo agujero, mismo turno**: NINGÚN turno de cluster cerraba su flujo explícitamente — a diferencia
    del `_maybe_close_flow` de la voz (`voice/engine/llm/providers/nucleo.py`), `_brain_turn` nunca emitía
    `flow:end`, así que hasta un turno REAL de cluster dependía enteramente del `_supervise_stale_flows` de 15
    min para desaparecer del master. `_close_cluster_flow(trace_id)` (nuevo, `bridge.py`) cierra al terminar
    CADA turno de cluster —salvo que `escalate_to_slowbrain` haya dejado un worker vivo en ese trace
    (`dispatch.has_live_trace`), que sigue mandando la regla de siempre: **la pelota está en el tejado de
    quien trabaja, nunca se le cierra el flujo debajo**.
  - **Esto NO prohíbe que el latido actúe** — homeostasis recicla el motor, `_supervise_stale_flows` cierra lo
    abandonado, el heartbeat de cluster decide silencio/nudge/concluir: todo eso es **vigilancia y limpieza de
    trabajo existente**, la categoría que SÍ le corresponde al pulso. Lo que no puede hacer es que esa
    vigilancia se disfrace de una tarea nueva en la observabilidad.
- **`voice.trace.active()` — un puntero EXPLÍCITO para eventos que el ContextVar nunca puede ver (2026-08-16,
  norma del operador: "arréglalo en el flash brain... donde se generan los eventos, siempre debemos relacionar
  los eventos con la tarea")**. Auditando una sesión real (una conversación entera sobre conectores WhatsApp/
  Telegram/Gmail) salió que la MAYORÍA de eventos de `voice/engine/pipeline/agent.py` llegaban SIN corr_id: de 17
  `transcript`, 13 sin trace; `vad`, 0 de 14. Causa confirmada contra el código fuente de livekit-agents 1.6.6
  (no una hipótesis): esos handlers (`_on_transcript`, `_on_item`, `on_state_change`, `_on_user_state`,
  `_on_metrics`) corren en tareas de LiveKit que son **HERMANAS**, nunca descendientes, de la tarea donde
  `NucleoLLMStream._run_inner` fija el trace (`nucleo.py::_begin_or_adopt_trace`) — `asyncio.create_task` copia
  el ContextVar solo hacia HIJOS, así que ningún ajuste de propagación arregla esto: es cómo funciona
  `contextvars`, no un fallo.
  - **`voice/trace.py::active()`** (nuevo): un puntero módulo-level, NO ContextVar, que `begin()`/`adopt()`/
    `scope()` mantienen al día y que esos handlers leen EXPLÍCITAMENTE. Caduca solo (3s por defecto) — pasado
    eso cae al trace **GENERAL de la sesión** (`_general`, fijado por el `kickoff`), nunca a "sin traza": es
    literalmente el "se atribuye a la charla general, bienvenida, etc" que pidió el operador para lo que no
    tiene tarea propia, acotado en el tiempo para no reabrir un flujo que ya cerró con actividad fantasma
    (mismo cuidado que `_maybe_close_flow`/`drain_pending_flow_closes`, arreglado el mismo día). `cluster`/
    `pulso` (otro subsistema, mismo proceso) NUNCA tocan `_active` — si lo hicieran, un tick del puente MeshKore
    le colgaría sus eventos al pipeline de voz.
  - **NO todos los emisores son seguros de etiquetar** — la mitad de esta auditoría fue decidir cuáles. Un
    evento es seguro si describe algo sobre un trace que **YA EXISTE** (TTS sonando para texto que el turno ya
    generó, un barge-in que interrumpe una locución en marcha, el item del asistente añadido tras la cadena
    LLM+TTS, los estados `speaking`/`listening`/`interrupted`) — se les pasa `extra={"trace": trace.active()}`.
    Es INSEGURO si el evento **PRECEDE** al trace del turno que va a disparar (el transcript FINAL del operador,
    "voz detectada", "fin de voz", `STTMetrics`, los estados `thinking`/`idle`) — forzar `active()` ahí le
    pegaría el trace de la conversación ANTERIOR más a menudo que el correcto, peor que no llevar ninguno.
    Fijado en `tests/voice/unit/test_agent_trace_source_guards.py` (guardas de fuente, mismo patrón que
    `test_lead_in.py`: montar la sesión real exige media pila de LiveKit).
  - **Lo que esto NO arregla, a propósito**: el transcript del operador y sus primos siguen sin trace de
    escritura. Ahí gana la LECTURA (`cloud/backoffice/src/flowAttribution.js::attributeOrphans`, mismo día): mira
    AMBOS lados de la ventana temporal de cada flujo y atribuye el huérfano al más cercano — más preciso que
    cualquier heurística de escritura que solo puede mirar hacia atrás. Las dos piezas son complementarias, no
    redundantes: escritura para lo que puede saberse bien en el momento, lectura para lo que estructuralmente no.
  - **Derivar una tarea nueva sigue siendo SOLO al abrir un turno real** (norma de arriba): un worker spawneado
    (`nucleo/dispatch.py`) hereda el trace del turno que lo lanzó, nunca mintea uno propio — es la MISMA gestión,
    no una tarea aparte. Si algún día hace falta que una derivada compleja tenga su PROPIO trace (el operador lo
    mencionó como posible), es una decisión de producto pendiente de confirmar con un caso real, no aplicada aquí.
- **El gate de atención en modo `always` (el default, micro SIEMPRE abierto — permanente, NO es algo a revertir
  a wake-word) ahora JUZGA el contenido en vez de dar todo por dirigido** (V2-105, 2026-08-16, norma del operador: "nunca
  vamos a llamar a la gente por su nombre... el ruido de fondo se puede separar de las acciones reales
  dependiendo de la naturaleza de las frases"). Auditando una sesión real con niños de por medio: 5-7 frases de
  ruido de fondo ("Mira donde tú quieras, pero dame el ya...", con "hija" de por medio) corrieron el turno
  COMPLETO cada una —prompt, decisión de tools, y en un caso un `web_search` real que tardó 3,3s y se
  completó— antes de descartarse como superado. Coste real, cero valor, repetido varias veces en menos de 90s.
  - **Por qué "smart" (ventana de 30s tras el último turno dirigido) no basta**: el ruido ocurrió DENTRO de una
    conversación activa, a segundos del último intercambio real — cualquier heurística de ventana temporal lo
    habría dejado pasar igual. Hacía falta juzgar el CONTENIDO, no el reloj.
  - **`voice/attention.py::evaluate_content()`** (nueva, async — `evaluate()` se queda intacta, síncrona, para
    quien no puede pagar un round-trip: tests, probe, accumulator). En modo `always`: atajo gratis si hay
    wake-word (no hace falta preguntarle a nadie lo obvio); si no, pregunta al modelo RÁPIDO (`nucleo/memllm.py`,
    tarea `"directed"`, mismo perfil DeepSeek DIRECTO que `turn_complete`/V2-097 por la misma razón: TTFT ~1s
    contra ~8,6s del broker AIMLAPI) con la frase + un apunte barato de qué se estaba haciendo
    (`brain._last_reply`, no la ventana entera — ver el fix de contaminación por relleno más abajo, V2-109).
    Fail-open SIEMPRE (excepción, timeout, JSON ilegible → tratado
    como dirigido) — un juez roto jamás puede dejar mudo al agente; sesgado a "dirigido" ante la duda por el
    mismo motivo. Juez inyectable (`set_directed_judge`, mismo patrón que `accumulator.py::set_judge`) para
    tests sin red. `smart`/`wakeword`/`ptt` no cambian — su heurístico ya discrimina sin necesitar el modelo.
  - **Dónde corta**: `nucleo.py`'s bloque T134 (línea ~613) ya existía y ya cortaba ANTES del relleno de espera,
    la construcción del prompt y la selección de tools — solo hacía falta que la CLASIFICACIÓN fuera buena. No
    hizo falta tocar ese corte en absoluto, solo lo que decide si dispara.
  - ⚠️ **El relleno de espera CONTAMINABA ese contexto, tirando abajo el propio juez que esto construyó (V2-109,
    2026-08-17)**: `context` se pasaba como `brain._last_spoken`, el campo de anti-eco (V2-093) que se actualiza
    con CUALQUIER salida de voz — incluido el relleno ("Pues…", "Mmm…", "Espera…"). Auditado en vivo
    (`sid=0db9bf42-...`): 4 preguntas de seguimiento reales, cada una dicha justo tras un relleno, se
    clasificaron `🙉 ambiente` con contexto `"Se estaba haciendo: Pues…"` — CERO tema para el juez. Una de las
    cuatro era la propia queja del operador por haber sido ignorado ("te acabo de hacer preguntas ahora"),
    también ignorada. Fix: nuevo `brain._last_reply`, escrito SOLO desde `send()` (respuesta real), nunca desde
    `_lead_in_filler` — `_last_spoken` sigue sirviendo al anti-eco sin cambios. Detalle:
    `V2-109-directed-context-filler-contamination.md`.
- **Fusionar dos flujos que resultan ser la MISMA tarea — la capacidad existe, el disparo automático NO (pass 2
  pendiente)** (V2-105, 2026-08-16, norma del operador: "por la segunda o tercera frase nos demos cuenta que los dos
  turnos son el mismo... dejaría esa feature disponible").
  - **`voice/trace.py::merge(a, b)`**: el MÁS ANTIGUO (seq más bajo del propio id — nace secuencial, sin
    necesidad de comparar timestamps) se queda como TITULAR siempre, sea cual sea el orden de los argumentos; el
    más nuevo se funde EN él. No reescribe nada ya escrito (el archivo es append-only a propósito) — emite un
    MARCADOR (`kind="trace", label="merge"`, sellado con el trace NUEVO, `extra={"merge_into": <titular>}`) que
    el lector resuelve.
  - **Lectura**: `cloud/backoffice/src/flowAttribution.js::resolveMerges()` (sigue cadenas de fusión
    transitivamente, protegido contra ciclos) integrado en `attributeOrphans()` — un evento de un flujo ya
    fundido se lee como del titular, huérfanos incluidos. `handleFlowDetail` (server.js) resuelve también el
    `corrId` de la URL: visitar el id viejo redirige al contenido combinado, no a una tabla vacía. **Pendiente,
    a propósito**: la RAIL/tablero en vivo (`flows_detail`, vista de resumen) todavía no oculta un flujo ya
    fundido como columna separada — solo el DETALLE (clic dentro) queda correcto; y el lado nube
    (`observability/flows.py`) no tiene el equivalente todavía, solo el local.
  - **Lo que falta A PROPÓSITO — el disparo automático**: qué decide fusionar y cuándo es la mitad que NO se
    construyó esta pasada. El diseño recomendado para la siguiente: extender el ÚNICO tool-call real del turno
    (`nucleo.py`'s stream, ver la entrada de `voice.trace.active()` arriba para el mapa completo de esa
    llamada) con un campo booleano tipo `continues_previous_task` que el modelo declare — el motor, no el
    modelo, resuelve A QUÉ trace concreto se refiere (el inmediatamente anterior de la sesión, un puntero
    sencillo análogo a `_active`/`_general`), así el modelo nunca necesita ver ids internos. Coherente con la
    norma de este repo de "no hardcoded, enseña al modelo" en vez de heurísticas de similitud de texto escritas
    a mano.
- **El motor no arrancaba NUNCA en frío — deadlock de reentrancia en `memory/db.py::get_db()`** (V2-106,
  2026-08-16, encontrado cerrando V2-105: cinco reinicios seguidos colgados, proceso vivo a 0% CPU, sin
  traceback). En el PRIMER `get_db()` de un proceso, `Database.__init__` → `_migrate()` → `embeddings.dim()` →
  `_resolve_backend()` → `_ollama_embed()` registra perf vía `voice.observer.perf()`, que atraviesa `emit()` →
  `stamp_identity()` → `nucleo.runstate.stopped()` → `kv_get()` → **`get_db()` otra vez, mismo hilo**, antes de
  que la primera llamada terminara. `_DB_LOCK` era un `threading.Lock()` plano sostenido durante TODA la
  construcción → se autobloquea para siempre. Invisible en tests porque `_DB` es singleton de proceso: solo el
  PRIMER `get_db()` de un arranque real dispara la rama de construcción; ningún test reutiliza ese estado.
  Fix mínimo: `RLock()`, el mismo patrón que `Database._lock` ya usaba en el mismo fichero. Regresión:
  `tests/memory/unit/test_db.py::test_get_db_survives_reentrant_call_from_inside_migrate` (verificado que falla
  sin el fix). Diagnosticado con `faulthandler.dump_traceback_later()` tras descartar red/Ollama/puertos —
  `py-spy`/`lldb` no disponibles sin sudo interactivo en esta máquina.
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
    siempre activo, snippet pequeño pasa; desde la auditoría 2026-07-26 **acumula por-destino** en una ventana
    corta —`accum_key`, `MESHKORE_CODE_ACCUM_WINDOW_S`— para que fragmentar el volcado en varios mensajes pequeños
    ya no esquive el umbral) + aviso al operador 1× en explotación + evento observer `resource` (la
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
  este patrón. **V2-083 — Config en 3 pestañas + conectores 100% dinámicos:** el área ⚙ (`ConfigPanel.js`,
  superficie de sistema) se organiza en **Ajustes · Conectores · Widgets**. **Conectores** lista TODOS desde un
  **registro único** `connectors/registry.py` (`GET /api/connectors`: mensajería/música/infra con familia, método de
  auth, estado y config redactada) y permite **conectar/revocar desde ahí** (además del widget de mensajería, en los
  dos sitios) — WhatsApp/Telegram QR, Email app-password, Spotify OAuth, **Architect (token) y MeshKore (cluster_id+
  token) DINÁMICOS**: el token de Architect vive ahora en `config/connectors.json` (NO en `.env`; `client.token()`
  store-first), visible/revocable desde la UI — invariante del operador: NADA de credenciales en archivos de entorno,
  todo dinámico y revocable desde el frontend. **Widgets** = una sola lista alfabética con badge «de serie»/«tuyo»
  (`origin` de `registry.origin_of`: lista curada `_BUILTINS` + el generador estampa `origin:"user"`), solo lectura.
  Conectar por voz = follow-up (aparte).
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
- **LA PILA de Energy — el saldo se VE antes de agotarse** (`frontend/app/components/EnergyGauge.js` +
  `nucleo/energy_meter.py::snapshot`, `GET /api/energy`, 2026-08-13): el agente se quedó sin Energy a mitad de una
  sesión real y el operador se enteró **por un cartel**, sin haber visto nunca cuánta le quedaba. El corte
  funcionaba; faltaba la parte de antes — misma clase de fallo que un agente caído que se pinta vivo. Pila de
  rayitas verticales a la IZQUIERDA del 👤, **SOLO con cuenta de nube** (en self-host `/api/energy` dice
  `cloud:false` y no se pinta nada: allí el usuario paga sus propias APIs).
  - **La escala son DOS ejes, no uno.** Un saldo crece sin techo y una barra no: la pila tiene un número FIJO de
    huecos y lo que cambia es **cuánto vale cada rayita**, con el color diciéndolo. `valor = techo(capacidad/50)`
    acotado a una escalera; encendidas = `saldo/valor`; los huecos dibujados son los que había al empezar y **lo
    gastado se queda en gris pálido** — sin eso no es una pila, es un número de rayitas variable.
  - **La CAPACIDAD fija el valor y el color, NUNCA el saldo.** Si dependiera del saldo, el color cambiaría mientras
    gastas y la pila se leería como un tramo bajando de categoría. Y la capacidad tampoco se pregunta: **una
    recarga es, por definición, un saldo que SUBE** → un salto hacia arriba la refija, gastar no la toca. Persiste
    en `sys_kv`, NUNCA en el estado raíz (`compose_state` vuelca cada escalar del estado al prompt de CADA turno —
    misma razón que en `nucleo/rehydrate.py`).
  - **No hizo falta endpoint nuevo en la nube**: el saldo YA venía en la respuesta de cada reporte de consumo y
    solo se usaba para decidir el corte; bastó dejar de tirarlo. Se empuja por SSE (`kind:"energy"`, familia
    `system`) con cada gasto, así la pila baja EN VIVO sin polling.
  - **«No lo sé» y «se te acabó» no pueden verse igual**: mientras no haya llegado ningún saldo la pila se pinta
    APAGADA con su aviso, no vacía. Vacía de verdad = late en rojo.
  - El servidor devuelve HECHOS (saldo, capacidad, si hay cuenta de nube) y **no la escala**: huecos, valor y color
    son PRESENTACIÓN y viven en el frontend, así se cambian sin tocar Python. Los tramos y sus precios se
    documentan en el repo PRIVADO (`../.meshkore/docs/ops/zaelar-energy-gauge.md`) — aquí el mecanismo, allí el
    producto. Tests: nodo 4.14 (la escala es pura y se prueba en Node, sin navegador).
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

- **ADMISIÓN — cuando el proceso NO es la frontera, sin sesión verificada no se sirve nada**
  (`server/ingress.py`, 2026-08-13; doc: `.meshkore/docs/security/zaelar-security.md §Request admission`):
  una instalación de un solo proceso sirve a quien llegue, y está bien — la máquina donde corre ES la frontera.
  Esa premisa se cae en UNA forma concreta: **varios procesos detrás de UN hostname, cada uno con los datos de
  una persona distinta**. Ahí «contestó el proceso que el borde eligió» no es un detalle de routing, es el
  proceso equivocado contestando.
  - `nucleo/account_routing.is_account_routing_machine()` dice si este proceso está en esa forma (dos lecturas
    de entorno, default falso). Si lo está, `server/ingress.py` solo admite una petición **después** de
    establecer que su sesión es de ESTE proceso; todo lo demás se rechaza (401 sin credencial, 503 si no se
    puede verificar, entrega al proceso dueño si es de otro).
  - **La respuesta del resolver es de TRES valores** (`RESOLVED`/`NO_SESSION`/`UNAVAILABLE`), nunca un
    `Optional`. Antes un `None` significaba a la vez «no es una sesión» y «no pude preguntar», y el llamante
    leía las dos como permiso: **un timeout no es una autorización**. Y un rechazo de NUESTRA credencial no es
    un veredicto sobre el visitante — tratarlo como «no es sesión» convertiría un error de credencial en un
    cierre de sesión masivo y mudo en vez de en una avería visible.
  - **Lo público es una ALLOWLIST** (shell, `/static/*`, `/favicon.ico`, `/healthz`): una ruta nueva nace
    cerrada. El diseño anterior protegía las rutas cuyo autor se acordó de protegerlas.
  - **`/` se queda pública**, y no por comodidad: es el shell (idéntico en todo proceso, de nadie) y la ruta que
    busca el health-check de la plataforma. Un probe que falla saca al proceso de rotación — «seguro pero sin
    tráfico» no es una victoria. `/healthz` existe para cuando toda la flota lleve la imagen nueva.
  - La decisión está aislada en una función PURA (`decide`, cinco entradas) → se prueba sin servidor, sin red y
    sin reloj. Nodo 7.11. Sustituye a un middleware que servía en **las cuatro** ramas de rechazo, las cuatro
    comentadas como fail-open deliberado.

- **PARAR ES PARAR — el interruptor global vive en el SERVIDOR, y un widget DECLARA lo que produce** (V2-092,
  `nucleo/runstate.py` + `widgets/producers.py`, iniciativa `V2-092-parar-es-parar.md`; fallo real del operador
  2026-08-13): el ⏻ paraba la voz (V2-039) y congelaba los Brain Workers (V2-065, SIGSTOP), pero su estado vivía en
  `localStorage.hb_power_off` — **el backend no tenía a quién preguntar**. Con el agente parado seguía sonando un
  vídeo, **recargar la página lo volvía a arrancar** (su store decía «reproduciendo» y el `<iframe>` nace con
  `autoplay=1`), sonaba encima de la música, y los `tick()` de background seguían sondeando conectores.
  - **`nucleo/runstate.py`** es la verdad única: `running|stopped` persistido en `sys_kv` (una parada es una
    INTENCIÓN del operador, así que sobrevive a un reinicio), `GET /api/run`, `POST /api/run/stop|start`, y evento
    SSE `run` (familia `system`) para que **todas las pestañas converjan**. `stopped()` cachea en proceso: lo
    consultan caminos calientes.
  - **Contrato DECLARABLE, no casos especiales** (`"runtime": {output, produce[], suspend, active_when}` en el
    manifest). Los widgets los genera el agente: dos `if` para `youtube`/`musica` habrían dejado al widget de
    podcast de la semana que viene sonando sobre un agente parado. De la declaración salen gratis la **parada
    global**, la **exclusividad de canal** (el altavoz tiene UN dueño) y la **puerta** (`agent_stopped`) para
    cualquier widget presente o futuro. `active_when` se evalúa contra `view_data()`, admite rutas con punto y una
    LISTA de condiciones (la música suena por Spotify o por YouTube-audio: dos estados distintos).
  - **Embudo único** en `widgets/server_api._dispatch` (mismo camino para la UI y para el cerebro): puerta → acción →
    exclusividad, en ese orden. Suspender va por `dispatch_raw` (sin puerta), o parar con el agente ya parado se
    rechazaría a sí mismo.
  - **ASIMETRÍA deliberada** (decisión del operador): parar es total; **arrancar NO reanuda la reproducción** —
    «que sea el usuario a mano el que decide si quiere volver a seguir escuchando música». Lo que SÍ continúa es el
    TRABAJO: SIGCONT y el worker sigue exactamente donde estaba. La diferencia es de quién es la intención.
  - **Y todo lo demás que podía estar en marcha**: sin ticks de background (el bucle no se cancela, solo no ejecuta),
    sin crons (se sale ANTES de `mark_fired` → el job sigue vencido y salta al arrancar: parar no pierde el
    recordatorio, lo aplaza), sin trabajo NUEVO (`task/blocked`, visible). En el frontend el ⏻ ORDENA al servidor y
    el arranque RECONCILIA en la dirección segura (nunca se enciende solo), y cada widget recibe `ctx.running`.
  - **El `autoplay` se apaga en el propio `src` del `<iframe>`**, no con una pausa posterior: esa llega tarde y el
    primer instante se oye.
  - Contrato para widgets nuevos en `widgets/AGENTS.md` + el prompt del generador, junto a la decisión hermana de
    background: son la misma pregunta — ¿esto sigue haciendo algo cuando el operador deja de mirar?

- **PARAR ES PARAR, de verdad: ni sesión fantasma con el agente parado, ni turno cortado a medias** (V2-092
  addenda, 2026-08-15, dos fallos reales del operador probando en vivo):
  - **Gap real: "parado" nunca gateaba la conexión de voz.** `runstate.stopped()` se consultaba en workers/
    background/crons/widgets pero NUNCA en `server/livekit_api.py::token()` — una ventana nueva (perfil sin su
    propio `hb_power_off` en `localStorage`) siempre podía levantar sala LiveKit + kickoff aunque el servidor
    tuviera el agente parado, y el master la veía "EN CURSO". `token()` ahora responde 409 `engine_stopped` en
    vez de un JWT; `session-lk.js::start()` pregunta la verdad del servidor (`api.runState()`) ANTES de tocar el
    micro (no después, como hacía la reconciliación de `main.js` — sin esto había una ventana de carrera real
    donde el micro y la sesión de observabilidad ya se habían abierto antes de que la reconciliación los tumbara).
  - **Parada DIFERIDA para un turno con el modelo REALMENTE en vuelo.** Cortar `FastClient.stream()` a media
    respuesta no es aceptable, pero tampoco vale un temporizador (petición explícita del operador: la finalización
    la dispara una ACCIÓN CONCRETA — el turno terminando de verdad — nunca un reloj). `nucleo/runstate.py` lleva
    ahora un contador de turnos en vuelo (`enter_inflight`/`exit_inflight`, incrementado/decrementado por un
    envoltorio fino de `stream()` — la lógica de streaming real vive intacta en `_stream_inner()`): con el
    contador > 0, `stop()` NO congela nada todavía (estado `"pausing"`, nada se persiste ni se suspende), y
    `exit_inflight()` completa la parada real en el momento exacto en que el ÚLTIMO turno en vuelo termina.
    Pulsar ⏻ otra vez durante `"pausing"` CANCELA (nada se había tocado, no hay nada que deshacer) — y como el
    clic del frontend en ese momento en realidad llama a `start()` (ve `powerOff` ya en `true` desde el primer
    clic), `start()` también sabe cancelar una parada pendiente. El Orb gana un QUINTO estado (`pausing`,
    parpadeo ámbar con `--hb-warn-ink`, deliberadamente distinto del rojo/alerta de `stalled`: por dentro el
    agente sigue funcionando de verdad, no es una avería).
  - **Una sesión resucitándose a sí misma al cerrar.** `voice/observer.py::stamp_identity()` estampaba `sid` con
    `identity.session_id()` (que se ABRE sola) para CUALQUIER evento, incluido el propio evento `"end"` que
    `end_session()` emite al cerrar — así que cerrar una sesión reabría una nueva en el acto, y lo mismo con
    cualquier evento `run` (stop/start/pausing/resumed) disparado con el agente ya parado. Ahora los eventos de
    categoría `system`/`pulse` leen `session_info()` (que SOLO LEE, nunca abre) en vez de `session_id()`; la
    actividad real (flash/worker/memory/widget) se sigue abriendo sola, sin cambios.
  - **Heartbeat hacia el control-plane** (propuesta del operador): `identity.begin_session()` repite el mismo
    aviso de "start" cada ~15s (`ZAELAR_SESSION_HEARTBEAT_S`) mientras la sesión siga abierta — cero verbo nuevo,
    `userSessions.touch()` ya era idempotente. No-op total sin `CONTROL_PLANE_URL`/`ZAELAR_USER_ID` configurados
    (local puro). El backoffice (`cloud/backoffice`, repo privado) ahora prefiere ese latido —fresco (< 45s)—
    sobre la recencia-por-ruido-de-fondo de `flyQuery.js` (contaminada por homeostasis/cron), solo para SUMAR
    certeza de "viva", nunca para quitarla.

- **La ESPERA se oye, y el veredicto de latencia ya puede culpar al proveedor** (V2-093, `voice/proactive.py`
  + `nucleo/flash/turn_perf.py`, iniciativa `V2-093-la-espera-se-oye.md`; sesión b70a45d0):
  - **El relleno de espera llevaba desde julio SIN SONAR.** Viajaba como `ChatChunk` por el stream de la respuesta,
    y el tokenizador de frases de LiveKit **solo entrega un segmento cuando tiene DOS**; un relleno suelto no llega
    ni a ser segmento (acaba en «…», que no está en `[.!?。！？]`, y ninguno pasa de `min_sentence_len=20`), así que
    se quedaba en el buffer y salía PEGADO a la respuesta. 48 generados, 0 oídos a tiempo, 50 s de `bot_speech:idle`
    con tres pendientes mientras el operador decía «parece que te has quedado tonto». Ahora sale FUERA DE BANDA por
    `session.say` (costura `proactive.speaker()`). **No baja el TTFT: cambia que la espera se viva como «pensando»
    en vez de como «muerto»**, que es el síntoma que reportó el operador.
  - **`turn_perf` no PODÍA culpar al proveedor en voz.** El orden era frío → prompt → proveedor y `prompt` gana con
    `>=6000` tok; el prompt de voz es SIEMPRE 9-10k → rama inalcanzable POR CONSTRUCCIÓN. Diez turnos lentos
    culpando al prompt con el prompt CONSTANTE (±9%) y el TTFT de 0 a 25.703 ms. Nuevas causas **`pre_token`** (≥70%
    del turno antes del 1er token: razonamiento oculto o cola, y lo dice) y **`reparto`** (lento sin causa
    dominante: los números en vez de un culpable por descarte). `ttft_frac` viaja en el evento.
  - Regla que sale de aquí: **un diagnóstico que siempre acierta con el mismo culpable hay que sospecharlo.**
- **RELEVO por latencia del cerebro de voz** (V2-094, `nucleo/flash/provider_chain.py`, iniciativa
  `V2-094-relevo-por-latencia.md`): la cadena existía desde el 2026-08-03 pero solo servía al cerebro de CLUSTER y
  solo relevaba por proveedor ROTO (429/cuota). Ahora `chain(role)`/`pick(role)` sirven a los dos —**el cooldown
  sigue compartido a propósito**: un proveedor sin cuota lo está para todos— y `note_slow(verdict)` releva por
  LENTITUD comiéndose el veredicto de `turn_perf` (no re-mide nada). El spec de voz se resuelve POR TURNO.
  - **Tres protecciones de coste**, porque un relevo por latencia salta justo en los turnos difíciles, que son los
    que más gastan: 2 turnos lentos SEGUIDOS (un pico no releva), cooldown de 5 min (no la media hora del de cuota)
    y **TECHO de 40 turnos** en el escalón de relevo → se vuelve al titular aunque siga lento.
  - Cadenas: **self-host `['titular']` SIN relevo** (quien se autohospeda paga sus APIs y no puede llevarse la
    sorpresa; lo activa con `fast.providers`), nube `deepseek-v4-flash → grok-4-fast → groq`, cluster sin cambios.
    El orden es por (rapidez al 1er token, precio de ENTRADA): el input domina **14:1** en este cerebro, así que
    `grok-4-fast` está a 1,4× y **`grok-4.5` a 14,3× — fuera del defecto** (la sesión de 11 min habría pasado de
    ~31 a ~460 Energy). Precios en `energy_meter.py`; el producto, en la raíz privada.
  - **Esto NO cura el TTFT**: es razonamiento oculto del modelo, no cola. La cura era `api.deepseek.com` directo
    — **desbloqueada el 2026-08-14, ver V2-097 justo abajo**.
- **DeepSeek DIRECTO cura el TTFT, y por eso es RELEVO y no titular** (V2-097, 2026-08-14; iniciativa
  `V2-097-catalogo-modelos-agosto.md`). Con la credencial que faltaba desde el 2026-08-02, medido con el prompt REAL
  de voz (13.630 chars, 23 tools), 6 turnos por brazo:

  | brazo | TTFT p50 | peor caso | razonamiento | enrutado (nodo 2.13) |
  |---|---|---|---|---|
  | AIMLAPI `thinking:disabled` | 4,24 s | **14,71 s** | **2.138 tok** | **14/14** |
  | `api.deepseek.com` directo | **1,01 s** | **1,30 s** | **0** | 12/14 |

  - **El broker ACEPTA el parámetro de no-razonar y razona igual; el endpoint propio lo OBEDECE.** Y ya no se
    infiere del tiempo: `usage.completion_tokens_details.reasoning_tokens` lo LEE — el instrumento que faltaba para
    cerrar el diagnóstico de agosto («lo reduce, no lo apaga»). Medido además: `reasoning_effort:"minimal"` NO lo
    apaga y `enable_thinking:false` se ignora; solo valen `thinking:{"type":"disabled"}` y `reasoning_effort:"none"`.
  - **NO es el titular aunque la latencia sea el síntoma nº1**, porque bajó el enrutado 2 casos y la regla escrita
    es «si el nodo 2.13 baja, no se despliega». Ser rápido haciendo lo que no es fue justo lo que el operador llamó
    «conversaciones absurdas». Entra como **primer escalón de relevo por latencia** (V2-094): un relevo solo actúa
    con el titular ya lento, y ahí el canje «enrutado algo peor» vs «el turno llega» sí compensa — además no
    encarece (misma tarifa, sin el ×1,4 de Grok Fast). Promoverlo exige el banco a 3 rondas.
  - **El banco a 3 rondas NO EXISTÍA cuando esto se escribió** (corregido el 2026-08-15): `exp_routing` ignoraba
    `--reps` y corría cada caso UNA vez, así que «12/14 contra 14/14» eran dos muestras sueltas y la decisión que
    colgaba de ellas no era medible. Ahora `--reps` llega al enrutado, los fallos se reportan con su FRECUENCIA
    (`caso→tools (2/3)` — fallar 3 de 3 es un defecto, 1 de 3 es ruido, y la diferencia es la que decide) y hay
    `--models` para medir DOS brazos: los 20 candidatos a 3 rondas son 840 llamadas y los proveedores devuelven
    429 a media tabla, o sea números contaminados. Medido de verdad (42 turnos por brazo):

    | brazo | enrutado | graves | TTFT p50 |
    |---|---|---|---|
    | AIMLAPI `deepseek-v4-flash` (titular) | **41/42** | **0** | 8.659 ms |
    | DIRECTO `deepseek-v4-pro` | **41/42** | 1 | **1.158 ms** |
    | DIRECTO `deepseek-v4-flash` | 38/42 | 1 | 934 ms |
    | AIMLAPI `haiku-4.5` | 31/42 | 0 | 1.297 ms |

    **El escalón de relevo pasa a V4 PRO**: Flash directo fallaba `mostrar widget` **3 de 3**, y un relevo salta
    justo en los turnos difíciles — «total, es solo el relevo» es como se acepta un defecto reproducible. Pro
    iguala el enrutado del titular por 224 ms más de TTFT, así que el relevo deja de costar precisión.
    **El titular no se toca**: el broker marca 0 graves en 42 y los directos 1, y ese grave es
    `pregunta memoria → widget_data`, el fallo exacto que baneó a grok. Apagar el razonamiento parece costar justo
    la discriminación pregunta/orden. Lo que falta para promover Pro **no es otra medición sino una decisión de
    tarifa**: dobla el coste del turno de voz (~0,5 → ~1 Energy) a cambio de 8,6 s → 1,2 s al primer token.
  - ⚠️ **El escalón DeepSeek de los WORKERS estaba ROTO y era imposible saberlo**: escrito el 2026-08-13, solo se
    activa con la credencial puesta → nunca se ejecutó. Declaraba `model="sonnet"` sobre la creencia de que su
    gateway mapea alias de Claude, y **no los mapea** (400: «supported API model names are deepseek-v4-pro or
    deepseek-v4-flash»). Habría dado 400 en cada petición desde que entrara la clave, **y solo se usa cuando el
    titular ya cayó** → caída parcial convertida en total. Regla: **un relevo sin probar es peor que no tener
    relevo**; compatible en el PROTOCOLO no es compatible en el CATÁLOGO. Guarda estático, nodo 2.5.
  - **GLM-5.3** (workers): pedir `glm-5.2` ya devolvía `glm-5.3` — Z.ai subió el alias por debajo y la config
    documentaba un modelo que no corría. Solo el endpoint **Anthropic** lo tiene (su API OpenAI-compat sigue en 5.2),
    y **es RAZONADOR** → workers sí, voz jamás. **Gemini 3.7 Flash**: en el catálogo del broker como CANDIDATO sin
    avalar — su familia siempre fue rápida y siempre enrutó peor aquí (3.6-flash 6/14, 3.5-flash 8/14).
  - **Energy — los dos contadores de caché tienen aritmética OPUESTA**, y confundirlos cobra dos veces:
    `cache_read_input_tokens` (Anthropic) va FUERA de `prompt_tokens` → se SUMA; `prompt_cache_hit_tokens`
    (OpenAI/DeepSeek) va DENTRO (verificado: `pt = hit + miss`) → se DESCUENTA. Son parámetros distintos a propósito.
    Importa aquí más que en ningún sitio: el prompt de voz son ~10k tokens CONSTANTES, así que en conversación real
    casi todo el input es un hit y el input domina 14:1. Con tokens ESTIMADOS no se aplica el descuento (rebajar la
    factura con un dato inventado va en el sentido peligroso). ⚠️ Pendientes del operador: el pico/valle de DeepSeek
    del 2026-08-17 (hoy se factura siempre a PICO — sobre-cobra hasta 2× en valle, acotado y en el lado seguro) y el
    precio de cache-hit de V4.
  - **Energy — el margen del BROKER no se cobraba: ~30% de sub-cobranza en la llamada más frecuente del producto**
    (2026-08-15). Las tablas de `energy_meter` son tarifas del proveedor NATIVO, y tienen que serlo: es lo que hace
    comparables a los candidatos en los benchmarks. Pero producción no le compra al proveedor —el titular va por
    AIMLAPI, que revende con margen— y las dos rutas caían en la MISMA fila, así que `deepseek-v4-flash` facturaba
    $0,14 viniera de `api.deepseek.com` o del broker que cobra $0,182 por él. Invisible porque el test lo afirmaba
    como correcto. Arreglado con `_broker_markup()`, y con tres detalles que son la decisión: el margen es **por
    modelo** (medido: flash ×1,30, haiku ×1,30, grok-4-fast ×1,05, gemini-2.5-flash **×1,00** — un ×1,3 plano
    sobre-cobraría un 30% a gemini), un modelo del broker sin medir toma el **peor** margen visto, y **el fallback
    NO se multiplica** porque apilar dos rellenos de seguridad deja de ser «un poco por el lado seguro». De paso
    responde a la pregunta de si el directo sale más caro: es ~30% **más barato** que el mismo modelo por el broker.
- **El turno se cierra cuando la frase ACABA, no cuando hay silencio** (V2-095, `nucleo/flash/segmenter.py` +
  `voice/engine/speech/turn/semantic.py`, iniciativa `V2-095-turnos-por-sentido.md`): el límite era solo acústico,
  así que quien piensa en voz alta abría un turno por pausa y el siguiente fragmento lo cancelaba — **22 prompts,
  18 cancelados y CERO respuestas en 161 s** de dictado, sobre trozos como «del» o «para que».
  - **No es la doble pasada descartada el 2026-08-02** (prompt 9.729→1.221 tok pero turno 1.938→6.208 ms): aquello
    ponía dos llamadas en el camino crítico DESPUÉS de que el operador callara. Esto decide dónde acaba la frase
    MIENTRAS habla, en tiempo que ya estamos esperando.
  - **Y no hizo falta modelo para la mayoría**: mirando los 89 fragmentos reales, los que van a medias acaban en
    palabra función o en coma. Regla léxica → **43/89 = 48% de llamadas evitadas** a coste y latencia cero. La
    capa de modelo para lo genuinamente ambiguo se declaró aquí (`ZAELAR_SEGMENTER_MODEL`) pero no se cableó a
    nada — **superseded by V2-102** (más abajo), que la construye de verdad y ON por defecto, no opt-in.
  - **Se cablea como detector de turno de LiveKit** (`turn_provider=semantic`, **el DEFECTO desde 2026-08-14**), no
    en el proveedor, y eso es lo que lo hace seguro: devuelve una PROBABILIDAD y `max_delay` es el tope duro → puede
    RETRASAR un turno, nunca perderlo. El ONNX de LiveKit sería un segundo veto (se toma la probabilidad más baja)
    pero está **opt-in y apagado** (`ZAELAR_TURN_ONNX=1`): exige registrar su `InferenceRunner` en el hilo
    PRINCIPAL y el job corre en un HILO (INI-012), así que aquí no puede cargar — verificado, revienta con
    «InferenceRunner must be registered on the main thread». La capa léxica es Python puro y corre donde él no.
  - ⚠️ **NACIÓ MUERTA y hubo que arreglarlo**: se entregó con el detector registrado y `turn_provider` en
    `disabled`, o sea **nada lo seleccionaba** — la capa léxica no corría en ninguna sesión. El mismo fallo que
    Susurro leyendo claves inexistentes, repetido dos commits después de documentarlo. La regla que deja: **una
    capacidad cuyo defecto está apagado es una capacidad que nadie tiene**, y el guarda va sobre el DEFECTO, no
    sobre el valor del entorno de la máquina.
  - **Tres falsos positivos, los tres cazados MIDIENDO** (los dos últimos solo aparecieron al replicar contra las
    **195 sesiones** del registro local, 804 transcripciones — una regla afinada sobre UNA sesión está ajustada a
    esa sesión): (a) la regla «corta y sin cerrar» retenía TODAS las órdenes cortas («pon música», «abre la
    agenda»); (b) **«Y que lo pares todo.» se RETENÍA** por acabar en «todo» — retrasar una orden de parar es
    justo lo que prohíbe V2-092; (c) «sí»/«si» y **«estás»/«estas»** colapsan al quitar acentos, con «Sí, te
    autorizo a borrar toda la agenda» y «¿Cómo estás?» del lado equivocado. Arreglado partiendo las palabras
    función en **`_HARD`** (no cierran frase NUNCA, con punto o sin él: «de.» sigue siendo un fragmento) y
    **`_SOFT`** (sí pueden cerrarla, así que solo delatan si el STT no cerró). La puntuación final es señal medida:
    la llevan el **74%** de los enunciados completos y el **29%** de los fragmentos.
  - **Lo que la medición NO puede afirmar, dicho en voz alta**: la etiqueta de producción está contaminada por los
    dos lados (que el agente contestara un fragmento ES el bug; y 79 de 275 «incompletos» acaban en punto porque
    son frases ACABADAS con otra detrás — dictado multi-frase, otro problema). El número honesto es sobre la clase
    que esta regla gobierna: **196 fragmentos sin puntuación final, recall 79%**. Un recall mezclado habría sonado
    mejor y habría acreditado a la regla por una clase que no alcanza.
  - **El corpus NO se commitea** (son grabaciones verbatim del operador con planes de viaje y citas; este repo es
    público): el guarda lee el registro en RUNTIME y se SALTA donde no hay, como `test_roadmap_closure.py`.
  - **Techo conocido**: `max_delay` son 2,2 s, así que el veto añade ~1 s como mucho; subirlo
    (`ZAELAR_ENDPOINT_MAX_S`) retrasa TODOS los turnos y se deja al operador.
  - **Pendiente de la misma petición**: la selección DETERMINISTA de tools/widgets por turno (el catálogo son 17.335
    de 31.772 chars = 55% del input). Pieza propia, con el nodo 2.13 como puerta (hoy 12/12). Diseño en V2-096 §Fase 2.
- **Una frase en DOS TIEMPOS es UNA petición — y el fragmento no genera nada** (V2-096,
  `nucleo/flash/accumulator.py`, iniciativa `V2-096-conversacion-progresiva.md`): V2-095 resolvía esto RETRASANDO el
  turno, y el operador señaló el defecto antes de que lo midiéramos — *«no podemos tener un tiempo fijo esperando que
  todas las conversaciones y todas las personas van a actuar igual»*. Medido sobre **372 pausas reales** del registro:
  p50 **2,3 s** · p75 3,5 s · p90 **4,9 s** · max 19,5 s, así que el `max_delay` de 2,2 s cubría **48,7%** — menos de
  la mitad, por construcción. Y subirlo retrasa TODOS los turnos, también los ya completos.
  - **La solución no es esperar mejor, es NO esperar.** El turno acústico se cierra cuando quiera; lo que cambia es
    que un fragmento **no GENERA nada** (ni voz, ni tool, ni widget, ni worker, ni memoria) y se GUARDA. Al llegar el
    trozo siguiente se juzgan JUNTOS → la pausa sale de la ecuación. **156 frases recompuestas** en las 79 cadenas
    multi-fragmento reales. Va tras `hard_interrupt` y el gate de atención, y **antes de `ingest_utterance`**.
  - **Sin flush por tiempo, a propósito**: callar ante un fragmento abandonado es la conducta CORRECTA, no un efecto
    que compensar con un temporizador (norma del operador, con su ejemplo: *«ahora vamos a…» y me paro ahí → no debe
    generar nada*). Las válvulas (hueco 25 s / 6 trozos / 1200 chars) solo evitan que el buffer crezca o contamine
    una petición posterior.
  - ⚠️ **Fallo de seguridad cazado por su propio test**: «ciérralo todo» SIN punto final se RETENÍA («todo» es
    función blanda y el léxico solo la absuelve si el STT cerró la frase — y el STT pone el punto cuando le parece).
    **Un invariante de seguridad no puede depender de la puntuación del STT**: el predicado consulta ahora
    `attention.hard_interrupt`, la lista CANÓNICA, en vez de mantener una copia que estaba garantizado que divergiera.
  - **El número grande de coste, y no lo consigue ningún rediseño de prompt**: de los 471 prompts al FlashBrain del
    registro, **192 (41%) eran fragmentos a medias** → ~1,8M de tokens de input que dejan de enviarse, con una regla
    léxica de coste CERO.
  - **Límite conocido, escrito como test** (nodo 3.9) en vez de descubrirse en una sesión: el léxico ve si la frase
    CUELGA, no si hay **acción/pregunta/petición clara** — «quiero que busques» cierra sintácticamente sin decir qué.
    Esa capa PRAGMÁTICA entra por `accumulator.set_predicate()` (ya construido) y corre MIENTRAS el operador habla,
    que es lo que la separa de la doble pasada descartada el 2026-08-02.
- **SELECCIÓN PROGRESIVA de tools — el turno lleva su RUMBO, no el catálogo entero** (V2-096 Fase 2,
  `nucleo/flash/tool_selection.py`, nodo 3.10): *«cuando alguien dice "hola, ¿qué tal?" no le vamos a mandar todos
  los widgets, todas las tools… ir encaminando la dirección»* (operador). Pasa su propia puerta —el nodo 2.13 con
  el prompt y el titular reales—: **14/14 de enrutado, 0 graves, −28% de tokens de input** (−51% de chars de
  catálogo), latencia idéntica y **cero segundos viajes** sobre los 14 casos.
  - **NO es una segunda llamada al modelo.** Esa idea se midió y perdió el 2026-08-02 (prompt 9.729→1.221 tok pero
    turno 1.938→**6.208 ms**). El «abanico de posibilidades» se resuelve sin viaje extra porque de sus tres piezas
    solo una necesita modelo: la completitud es LÉXICA (F1), la selección de tools es RECUPERACIÓN O(K) —esto—, y
    la única que querría modelo («¿hay petición clara?») sigue declarada como hueco enchufable.
  - **Recuperar no es comprender, y por eso hay ESCOTILLA.** V2-085 fija que un GATE mira ESTADO y jamás las
    palabras del turno; esto **no es un gate**: es la misma recuperación que `widgets/selection.py` ya hace con su
    capa `named`. La distinción es la que autoriza usar palabras aquí — un gate DECIDE que algo no existe, una
    recuperación PROPONE y tiene que degradar bien. `need_capability` (tool minúscula, añadida SOLO si se recortó)
    deja al modelo pedir la familia que le falta → **un segundo viaje MEDIBLE** en vez de una capacidad negada en
    silencio, que es el fallo que de verdad rompe una conversación. El reintento va **después** del stream (ese
    bucle tiene tarea bomba, cola y plazo de silencio) y **una sola vez**.
  - **`core`/`web`/`memory` no se recortan NUNCA**: sirven turnos que no se anuncian ni en el estado ni en las
    palabras («¿cuánto cuesta la entrada?», «¿cuándo es la cita de la ITV»). Cambiar coste por contestar mal es el
    intercambio equivocado. Capas: ALWAYS → estado (lo que tiene DELANTE) → forzado → nombrado → reciente (MRU, para
    que una charla que iba de música no la pierda al decir «la siguiente»).
  - **Kill-switch `ZAELAR_TOOL_SELECTION=0`** — un cambio que toca el ENRUTADO tiene que poder apagarse sin
    desplegar código. Y un guarda de deuda silenciosa: toda tool debe tener familia en `router.FAMILIES`, porque una
    sin familia se colaría siempre y no se podría recortar jamás.
- **Architecture/modularization pass — real duplication killed, three god-files split, one deliberately NOT split**
  (V2-098, 2026-08-16; full audit + rationale in `.meshkore/roadmap/initiatives/V2-098-arquitectura-modular.md`,
  gitignored/local). Baseline tagged `v3.06` first (1924 tests green) as the pre-refactor starting point.
  - **Killed, not just renamed — each was a real, already-diverging bug risk, not a style complaint**: (1) two
    secret-redaction predicates (`config/v2.py` vs `config/credentials.py`) that would have let a future `*_token`
    config key leak unredacted — now one shared suffix list; (2) API-key-per-endpoint resolution reimplemented in
    5 places, two of which (`susurro/client.py`, `memllm.py`) only knew 4 of ~9 endpoints — pointing either at
    gemini/mistral/z.ai/deepseek/moonshot silently resolved an empty key — now `nucleo/provider_keys.py`, one
    resolver; (3) two independent cooldown/circuit-breaker implementations (`nucleo/flash/provider_chain.py`,
    `nucleo/workers/providers.py`) — now share `nucleo/provider_health.CooldownStore` mechanics while keeping
    separate KV state (a model tier down says nothing about a worker CLI endpoint); (4) OAuth PKCE math and the
    atomic-JSON-plus-chmod-600 secret store, each copy-pasted across `spotify/auth.py`/`email/oauth.py`/
    `meshkore/store.py` — the last of which wrote its file with no tmp+replace step, a real truncation risk on a
    crash mid-write, now fixed as a side effect of sharing `connectors/secure_json_store.py`.
  - **Three god-files split where the boundary was actually clean**: `widgets/generator.py` (job orchestration)
    → `widgets/validator.py` (static+runtime contract checks, zero shared mutable state); `nucleo/flash/probe.py`
    (core `run_turn`) → `probe_api.py` (FastAPI router) + `probe_cli.py` (talks to the running server over plain
    HTTP, needs none of the core's state); `nucleo/dispatch.py` (session/pool lifecycle) → `dispatch_prompts.py`
    (pure prompt-string builders, no `SessionRecord`/pool state touched). Each kept the old call sites working via
    re-exports — but the `dispatch.py` split still had a hidden reverse dependency (`nucleo/research.py` importing
    a private name straight from `dispatch`) that only the FULL test suite caught, at runtime, not at import time
    or by `grep`: a lesson for the next split, not just this one.
  - **`voice/engine/llm/providers/nucleo.py` (the 2374-line `_run_inner`, THE voice hot path) was investigated
    and deliberately NOT split this session.** It mixes turn-gating, tool-call dispatch, provider failover,
    vault interception, and the streaming loop, with 110 bare `except Exception` blocks — genuinely the highest-
    value target, and genuinely the highest-risk: unlike `dispatch.py` (async workers, doesn't block voice), a
    mistake here shows up in every conversation, and the `dispatch.py` split's own near-miss argues for doing
    this one as its own dedicated, extraction-by-extraction effort with the full suite green between each step —
    not the last stretch of an already-long session. A concrete extraction plan is left in the initiative doc.
  - **`config/` importing upward into `voice`/`server`/`nucleo`** (`config/settings.py`, `config/balances.py`) was
    investigated and left alone on purpose: fixing it needs a registry-pattern inversion (a real design change,
    not an extraction) since `config/balances.py` calls the full `.status()` of the provider chains, not a
    liftable function. Documented as deliberate debt rather than forced into a bad shape.
  - **Docs refreshed to match**: `zaelar-modules.md` gained the `observability` row it was missing;
    `zaelar-architecture.md`'s model-routing section (§6) was rewritten off a stale 2026-07-15 snapshot naming a
    now-banned model, and its voice-engine row picked up the turn-segmentation (V2-095) and fragment-accumulator
    (V2-096) behavior it never mentioned. The two web diagram files (`architecture.ts`/`widgets.ts`, hand-tuned
    SVG coordinates on zaelar.com/technology) were investigated but left untouched — no browser/screenshot tool
    was available this session to verify a coordinate edit on a real public page, and an unverified visual change
    there is worse than a diagram that's merely missing one recent feature.
  - Full suite green after every step (1924 passed, 2 skipped) — never one big commit at the end.
- **V2-098 follow-up: FlashBrain modularization, 9 splits executed** (V2-112, 2026-08-17, operator request: "quiero
  saber si hay scripts largos, piezas que podamos descomponer... para seguir creciendo"). Three parallel audits
  (FlashBrain's 4 largest files, `nucleo/`'s core orchestration, and the two largest files repo-wide) produced a
  concrete, risk-ranked plan; executed the safe/mechanical tier end to end, full suite green after every single
  step (2043→2051→2060 tests), never a batch commit.
  - **Splits, all via the same pattern**: move the separable slice to a new file, **re-export it from the
    original** so every existing call site — whole-module (`router.looks_like_close(...)`) AND direct-name
    (`from nucleo.worker_api import deny_reason`, confirmed by grepping actual importers before moving anything,
    not assuming) — keeps working unchanged. `nucleo/flash/router.py` (1221→895) → `router_guards.py` (~340
    lines of deterministic guards, zero shared state with the tool catalog). `nucleo/flash/fast_client.py`
    (770→666) → `model_spec.py` (`ModelSpec`/`spec_from_config`/`available`; added to the Energy-coverage
    guard's `_EXENTOS` — it resolves config text, `fast_client.py::stream()` still does the metered call).
    `nucleo/research.py` (591→415) → `research_prompts.py` (`_SYSTEM` + the 140-line `to_prompt_block()`
    formatter) — built as a LEAF module (`min_candidates_floor` passed as a parameter instead of importing
    research.py's constant) specifically to avoid a circular import, since research.py needs the prompt text
    re-exported back. `nucleo/worker_api.py` (452→373) → `worker_policy.py` (pure ALLOW/CONFIRM/DENY decision
    logic). `nucleo/flash/prompt.py` (641→458) → `recall_heuristics.py` (`needs_recall`/`needs_recent`/
    `compose_recent_block`, no dependency on the ESTADO-composition code). `nucleo/dispatch.py` (1352→~1330) →
    `dispatch_devworker.py` (V2-076's confined dev worker — deliberately NOT touching `_WEB_RESUME`, which 4
    other files reach into by private name and needs its own pass).
  - **`voice/engine/llm/providers/nucleo.py`'s extraction plan, step 1 of 7 executed**: `vault_intercept.py` —
    the security-config-command + spoken-secret intercept (~50 lines), the smallest, most self-contained slice
    of the ~1600-line closure-heavy `_run_inner` body, done first to prove the "extract a slice into a callable
    with explicit params" pattern on this specific hot-path file before touching anything riskier. Returns a
    bool the caller checks (`if await try_vault_intercept(...): return`) instead of the original bare `return`.
    First unit coverage for this path (6 cases) — previously reachable only through a live LiveKit session. The
    remaining, riskier steps (a `TurnState` object design, then `tool_dispatch.py`) are explicitly left for
    their own dedicated session, per V2-098's own stated principle.
  - **`widgets/navegador/owner.py`: dead code found and deleted BEFORE the audit's own claim was trusted.**
    `snapshot_for_agent`/`screenshot_b64`/`agent_act` (module-level, 79 lines) looked like they had one caller
    (`agent.py` references `owner.snapshot_for_agent()` textually) — verified with `git log` that `agent.py` is
    actually LIVE (called from `owner.py:602`, contradicting an older CLAUDE.md note calling it "parked"), but
    its `run_task(goal, owner, ...)` parameter is a generic name that always receives a `TaskBrowser` INSTANCE
    at the one real call site — so those references always resolved to TaskBrowser's own methods (which also
    carry a danger-confirm gate the module-level twins lacked), never the module-level functions. Confirmed
    zero real callers before deleting anything, not just trusting a subagent's grep. This unblocked a second
    split: `dom.py` (`_describe_el`/`_bulk_metas`/`_snapshot_lines`/`_human_move`/`_human_click_handle`/
    `_human_type_handle`/`_human_click_at`) — these took `mouse: dict | None = None`, falling back to a
    module-level `_mouse`, a fallback only the now-deleted dead code ever used. With it gone, every surviving
    caller (`TaskBrowser.agent_act`) already passes `self.mouse` explicitly, so `mouse` became a REQUIRED
    parameter and the module has zero dependency on `owner.py`. First unit coverage for this path too (8 cases).
  - **A real gap found and fixed along the way**: `tests/run_testmap.py`'s `deterministic_paths()` (consumed by
    `python -m tests run <suite>`) runs an EXPLICIT list of file paths per node — it does not glob a directory.
    Two brand-new test files created earlier the same session (`test_nucleo_directed_context.py`, V2-109's
    directed-context fix, and this pass's own `test_vault_intercept.py`) had been running only when invoked with
    pytest directly, silently absent from every `all`/`voice` suite run, no error. Registered both (plus this
    pass's `test_dom.py`) in the testmap. Lesson: a new test FILE needs a testmap line even inside an
    already-covered directory — only adding a test to an EXISTING file is exempt.
  - **Left alone, deliberately**: `probe.py` (deliberate twin of `nucleo.py`'s hot-path body — splitting one
    without the other breaks the voice/probe parity the channel exists for), the ~1600-line closure cluster
    inside `_run_inner` (13 turn-state dicts shared by closure — needs a `TurnState` object designed first, not
    a mechanical move), `owner.py`'s login/auth subsystem (same verdict as V2-098, reinforced by an open,
    unrelated investigation — V2-108 — in its exact neighborhood), `dispatch.py`'s `_WEB_RESUME` (4 external
    files reach into it by private name, needs all 4 updated in the same commit), and `nucleo/memory_agent.py`/
    `nucleo/mem_processor.py` (memory-domain work, handed off to the session running that initiative instead).
  - Full suite green after every step, never a batch commit (2043 passed → 2051 → 2060; 1 skipped throughout).
    Detail: `V2-112-modularizacion-flashbrain-audit.md`.
- **Floating feedback widget — a self-hosted engine's first outbound call, and the control-plane's first
  PUBLIC route that accepts real data** (V2-100, 2026-08-16; full detail in
  `.meshkore/roadmap/initiatives/V2-100-feedback-widget.md`, local; the cloud/business side is INI-023 in
  the workspace root's private repo). One native surface (`frontend/app/components/FeedbackWidget.js`,
  registered in `system-surfaces.js` + mirrored in `widgets/system_surfaces.py`): a draggable launcher
  (default bottom-right, `lib/draggable.js` mode `"bl"` — same call as the Orb, no new snap logic) opening
  a two-tab panel (New: textarea + mic dictation + opt-in session-evidence checkbox, default OFF; Sent: a
  static, read-only status list — never chat-shaped).
  - **Dictation is the browser's native `SpeechRecognition`**, not a new backend endpoint: no reusable
    one-shot "transcribe this audio" primitive exists anywhere in this codebase (every STT provider is
    wired into LiveKit's streaming `AgentSession`), so a server-side alternative would have meant new
    plumbing plus per-use provider cost for a convenience feature. Degrades safely (the mic button hides)
    where unsupported, mainly Firefox. Deliberately not `services/stt.js` — an unwired, dead sketch whose
    header comment claims a `ClientSTTInjector` that does not exist anywhere in the Python code.
  - **The local↔cloud branch in `server/feedback_api.py` reuses the exact call shape already proven by
    `energy_meter.py::_post_usage_cloud_account`**: a cloud engine posts with
    `X-Service-Token: {CONTROL_PLANE_SERVICE_TOKEN}` (that env var's value on a cloud Machine is actually
    the per-workload MACHINE credential, despite the legacy name); a self-hosted engine has neither
    `CONTROL_PLANE_URL` nor a credential, so this is the first "phone home" call self-host makes at all —
    every other one is gated on env vars only a cloud Machine has. It carries only the already-existing
    per-install UUID (`observability.identity.user_id()` — no new "keypair on first boot" needed) to a
    new, separate endpoint default (`ZAELAR_FEEDBACK_URL`), kept distinct from `CONTROL_PLANE_URL` on
    purpose so an account-specific billing endpoint and a "everyone can reach this" endpoint never share
    one env var's meaning.
  - **The opt-in session-evidence bundle is built by calling `observability.flows` directly, in-process —
    never over `/api/observability/*`.** That HTTP surface is loopback/token-guarded
    (`_allowed()` requires `ZAELAR_OBS_TOKEN` + a header the frontend never sends), so a browser call to
    it would silently 403 on a cloud deployment; running server-side sidesteps the guard entirely. Capped
    to the current session only, last 200 events, fails open to no evidence on any error.
  - Tests: `tests/infrastructure/unit/core/test_feedback_api.py` (self-host vs cloud branch, evidence
    opt-in/fail-open, empty-message guard, network fail-open — 9 cases). Full suite green: 1943 passed,
    2 skipped.
- **First-run language onboarding — a blocking ceremony, and the alias-pack extension point finally built**
  (V2-101, 2026-08-16; full detail in
  `.meshkore/roadmap/initiatives/V2-101-language-onboarding.md`). Before this, a brand-new install silently
  guessed the operator's language from whatever they said first, with no gate on the UI. Now the first boot
  blocks the whole interface behind `frontend/app/components/LanguageOnboarding.js` (above the boot veil,
  z-index 100020 > `.boot-ovl`'s 100010) while zaelar asks, in forced English, what language to use — the
  kickoff branch in `voice/engine/pipeline/agent.py` checks `i18n.init.detect.should_detect()` before
  building its greeting. The modal also offers two non-voice escape hatches
  (`POST /api/i18n/choose/{code}` for a quick-pick chip, `POST /api/i18n/detect-text` for typed free text) —
  a purely voice-gated first-run blocker is a real usability trap (mic denied, noisy room, hard of hearing).
  - **Solved the loader-text chicken-and-egg by reusing the SAME translation pipeline, not a new one.** The
    loading line has to already be in the target language, but the full 564-key bundle can take up to ~2
    minutes to generate. `i18n.init.detect._priority_translate_loading` translates JUST the new
    `onboarding.loading` manifest key first (~1-2s) and pushes it inline in the SSE `phase:"detected"`
    payload, persisting it into the generated store immediately so the full `ensure_language` diff that
    follows doesn't re-translate the same key with possibly different phrasing.
  - **Built the alias-pack extension point `.meshkore/docs/architecture/zaelar-i18n.md` had documented as
    deliberately deferred.** `i18n/init/aliases.py::ensure_aliases(code)` — one batched LLM call generates
    4-6 natural voice-command words per system surface for a non-preset language, persisted to
    `i18n/generated/<code>.aliases.json`; `widgets/system_surfaces.py::surfaces()` consults it ADDITIVELY
    (the hardcoded es/en list is extended, never replaced) so the resolver's matching logic itself
    (`widgets/runtime.py::identify`) needed zero changes. Scoped to `lock(..., onboarding=True)` only — a
    plain ⚙ language switch stays exactly as cheap as it always was, no new LLM call as a side effect.
  - **Deliberately NOT localized: `voice/attention.py`'s hard-interrupt vocabulary and
    `nucleo/flash/router.py`'s `looks_like_*` backstop regex.** Both are safety/precision-critical
    deterministic guards with real incident history (the anti-garble identity gates, the
    hard-stop-must-never-be-buried invariant) — auto-translating a regex that decides "does this utterance
    mean STOP RIGHT NOW" via LLM is a materially different, higher-risk effort than translating a widget's
    voice aliases, and deserves its own dedicated initiative. Non-preset languages already fall back
    correctly to the LLM router for these — just a bit slower, the same accepted tradeoff as before.
    `nucleo/rails.py`/`music_flow.py` needed no work: confirmed they route by tool-calling, not hardcoded
    phrase lists.
  - **The confirmation is spoken via `voice.proactive.notify()`, not a raw `session.say`** — respects the
    existing "never talk over the operator" quiet-wait gate. Its TEXT is correctly translated
    (`onboarding.confirmSpoken`, generated as part of the normal bundle batch); the TTS VOICE itself stays
    whatever the session started with, since that's fixed for the whole LiveKit session and only realigns on
    the next reconnect — a pre-existing architecture limitation, not new here.
  - Tests: `tests/infrastructure/unit/core/test_language_onboarding.py` (12 cases — onboarding vs plain
    `lock()` sequencing, the PRESET fast path, alias-pack idempotency + fail-open, `surfaces()`'s additive
    extension, both new endpoints). The kickoff branch and fail-open valve inside `agent.py`'s
    `_maybe_detect_language` closure are deliberately not unit-tested — no extracted importable unit exists
    there, same coverage shape as the rest of that file.
- **Turn-completeness judge — real intelligence replaces "hold forever"** (V2-102, 2026-08-16; full detail in
  `.meshkore/roadmap/initiatives/V2-102-turn-completeness-judge.md`). Live bug: "dame los datos personales
  que conoces de mi" was silently swallowed three times — `nucleo/flash/accumulator.py` (V2-096) held it as
  incomplete because it ends in unaccented "mi" (the possessive determiner reading), and the accumulator has
  **no time-based flush by design** — a lexical misclassification meant a real request vanished forever, not
  just late. That one word is fixed (`segmenter.py::_ENDING_PRONOUN_HOMOPHONE`); this closes the class of bug.
  - **`nucleo/flash/segmenter.py::judge(text) -> (verdict, extra)`** — async, calls a fast LLM
    (`nucleo/memllm.chat_sync`, new `"turn_complete"` task, **DeepSeek DIRECT** per the V2-097 TTFT finding —
    the AIMLAPI broker doesn't honor `thinking:disabled` for this model, the direct endpoint does) judging by
    MEANING in any language, never a per-language word list. Three verdicts: `complete` (act), `ask` (speak a
    clarifying question NOW instead of waiting on something that may never come — `extra` carries the
    question, in the operator's language), `incomplete` (agrees with layer 1, keep accumulating). Fails open
    to `("incomplete", "")` on ANY error — strictly an extra chance, never worse than before. **Replaces the
    dead `ZAELAR_SEGMENTER_MODEL`/`model_enabled()` stub** — declared in the V2-095 docstring, zero real
    callers ever wired to it. Default **ON**, not opt-in (this codebase has hit "a capability whose default
    is off is a capability nobody has" three times already — Susurro, REM, this very module); kill-switch
    `ZAELAR_TURN_JUDGE=0`.
  - **`Accumulator.offer()` → async, new `"ask"` action.** Layer 1 (lexical, sync, `_complete`) still decides
    the fast path ALONE and unchanged — the judge (`_judge`, injectable via `set_judge`, mirroring
    `set_predicate`) is only `await`ed when layer 1 says incomplete, so the common case pays nothing extra.
    `"ask"` clears the buffer and returns the question for the caller to speak; no FlashBrain dispatch for
    that turn — the question IS the response.
  - **The 25s gap valve gets one LLM check before discarding anything.** `voice/engine/llm/providers/
    nucleo.py::_speak_acc_drop` used to always speak the same generic "sorry, I missed that" when a stale
    chain got dropped — an ACKNOWLEDGED loss of intent, still a loss. Now: `ask` speaks the clarifying
    question directly; `complete` still speaks the generic notice (immediate signal) but ALSO pushes a
    `[SISTEMA]` note (`voice/brain_notes.py`) so the content surfaces on the NEXT turn — never spoken
    unprompted, and deliberately NOT a synthetic re-dispatch from this out-of-band path (no live turn context
    to safely re-enter the pipeline from); `incomplete` keeps the plain behavior.
  - **Deliberate scope decision, asked explicitly rather than assumed**: keep the BOUNDED wait (8s nudge, 25s
    gap resolution) for a genuine `incomplete` verdict, rather than always resolving to ACT/ASK on the first
    ambiguous read. 141/160 real multi-fragment pauses in the corpus resolve themselves when the next
    fragment arrives (V2-096's own measurement) — always-resolve-immediately would reintroduce the
    over-eager-interruption problem V2-096 fixed, now as a spoken question instead of a wrong action. "Never
    retained forever" is still literally true: every fragment ends in ACT, ASK, or an LLM-confirmed
    acknowledged discard — never silence with zero signal — it just doesn't have to happen on the very first
    ambiguous read.
  - **Fixed an adjacent Energy-metering gap found while tracing the call path.** `memllm.chat_sync` is
    documented to run inside `asyncio.to_thread`, but `energy_meter._fire_and_forget` required a running loop
    in the CURRENT thread — a `to_thread` worker has none, so the control-plane usage POST silently never
    fired (the local lease deduction still happened; only billing visibility was lost). Already affected i18n
    bundle generation and nightly REM synthesis. Fixed at the root with the SAME `set_loop()`/
    `run_coroutine_threadsafe` bridge `nucleo/browser_search.py` already uses for the identical problem,
    called once from `server/__init__.py`'s lifespan, rather than working around it per-caller.
  - **Cheap first filter, small addition**: `voice/endpointing.py::is_backchannel` (already existed, es/en,
    free) gained "uh", "uhh", "oops", "wow", "damn", "shit", "fuck", "good" — named explicitly when scoping
    this. Deliberately NOT a broad multilingual profanity dictionary: an interjection in an uncovered language
    just costs one `judge()` call and gets classified correctly by meaning — that fallback is the point of
    this whole feature, not a gap to patch with more hardcoded lists.
  - Tests: `test_segmenter.py` (judge + parse + default-on/kill-switch), `test_accumulator.py` (3-way verdict,
    injection, fail-open, cost — judge never called when layer 1 already says complete),
    `test_energy_meter.py` (the bridge, both branches), `test_nucleo_accumulator_notice.py` (the `"ask"`
    action's pure logic), new `test_nucleo_speak_acc_drop.py` (the gap-valve's upgraded behavior, all three
    verdicts). Also fixed three now-broken synchronous `.offer()` calls in
    `tests/voice/unit/providers/test_nucleo_trace_merge.py` (a concurrent session's uncommitted work) —
    `offer()` becoming async broke them structurally; fixed alongside, nothing else in that file touched.
- **RESET left stale rows on screen and never touched the chat wall** (2026-08-16, operator report with a live
  screenshot: debug panel still showing pre-reset ticks, chat wall still showing the pre-reset conversation).
  Both server-side pieces were already correct — `reset_hard`/`reset_full` (`server/voice_api.py`) already call
  `rotate_session("reset")` (new session id, observability zeroed). The gap was entirely CLIENT-side, in
  `frontend/app/services/session-lk.js::_clearCanvasAndLog()` — the optimistic, deterministic reset path added
  2026-07-23 to avoid depending on an SSE round-trip through a connection `stop()` is about to kill (see that
  function's own comment). It called `clearDebugBuffer()` directly (empties `debugbus.js`'s ring) but never
  `store.newSession()` — and `DebugPanel.js`'s RENDERED rows only clear via its OWN reactive effect on
  `store.sessionEpoch()` (its "SESIÓN NUEVA" comment, 2026-08-10), which that bare buffer-clear never triggers.
  Two different things both called "clearing the log", and only one of them was wired to the optimistic path.
  Separately, `store.chatMsgs` (the chat wall's history) was never cleared by ANY reset path — checked all
  three (`/reset`, `/reset/hard`, `/api/reset/full`) end to end. Fixed by having `_clearCanvasAndLog()` also
  call `store.newSession()` and `store.setChatMsgs([])` — it already owns "clear everything the operator can
  still see" for the canvas; the debug panel and chat wall are exactly that, just two more instances of it.
  Frontend-only fix (no Python test harness reaches DOM-level assertions for this file); not live-verified
  this session (no browser tool), flagged for a manual check.
- **Memory — write-path self-healing, and REM stops being purely additive** (V2-103, 2026-08-16; live audit
  against the operator's real `zaelar.db` found duplicated pills, not the weather-note clutter suspected —
  slot-based supersede was already flawless, 28/28 slots at exactly 1 valid row each). Root cause of the
  duplicates and of 51.6% of valid memory carrying no embedding vector, TRACED TO ONE BUG:
  `memory/embeddings.py::_resolve_backend()` resolved the backend ONCE per process and cached it forever — one
  transient Ollama hiccup at boot locked the whole process into a degraded backend (`fastembed`/`hash`) even
  after Ollama recovered seconds later, which silently turned off BOTH the semantic-dedup gate
  (`writer.py::_semantic_dedup_on()`, calibrated only for `ollama`) AND `rem.py::repair_embeddings()` (self-
  excludes on embed-signature mismatch) for that process's whole lifetime. Fixed with a TTL re-check
  (`ZAELAR_EMBED_RECHECK_S`, def 300s) that only fires for an AUTO-detected, DEGRADED backend — never overrides
  an explicit `embed_provider`/`ZAELAR_EMBED_BACKEND`, never re-pings a healthy one. Three more pieces closed
  the same audit: (1) a synchronous EXACT-text dedup in `writer.insert_memory()` (new `idx_mem_text_lower`
  index) — the hourly `consolidator.dedup()` window let two turns seconds apart both stay `valid=1` for the
  literal same sentence; (2) `rem.py::synthesize()` now calls new `writer.demote_summarized()` after writing a
  concept's insight — multiplies the source pills' `weight` (floor 0.05, never touches `pinned`) and stamps
  `meta.summarized_by`, **never invalidates/deletes** (history stays intact) — REM was pure ADDITION before,
  never retiring what it just summarized; (3) `repair_embeddings()`'s daily budget raised from a flat 200 to a
  configurable 1000 (`§memory.rem_repair_limit`) — a zero-cost local job with no documented reason to be that
  low. Deliberately left alone: no hard importance-threshold discard at write time (this session's failure mode
  was over-writing, not data loss), no slot-registry expansion (the 4 separate pills about one relative's
  hospitalization are genuinely distinct facts, not the exact-duplicate bug), no per-kind decay tuning (the
  50k-row evict threshold isn't even close to firing yet), no hard-delete of superseded `note` rows (would
  reopen the 2026-07-19 P2-6 "never delete history" invariant). Tests: `test_writer_dedup.py` (new),
  `test_embeddings.py`/`test_rem.py`/`test_memory_agent.py` extended — 322 passed via
  `pytest tests/memory/ nucleo/`, 312 passed via `python -m tests run memory --no-open`.
- **REM — gate de fidelidad antes de escribir/demotar un insight** (V2-104, 2026-08-16, mismo día que V2-103):
  `rem.py::synthesize()` nunca verificaba que un insight fuera FIEL a las píldoras que resume — solo longitud
  ≥12 chars. El prompt pide "no inventes nada" pero sin backstop. Importa MÁS desde el propio V2-103: ahora un
  insight demota el peso de sus fuentes, así que uno inventado ya no compite con los hechos correctos, los
  DESPLAZA. `nucleo/memllm.verify_insight_grounded()` — segunda opinión por LLM en una llamada FRESCA e
  independiente de la que generó el insight (el autocriterio en el mismo turno es más débil) — es el ÁRBITRO
  cuando está cableada (por el loop, como `verify_fn` opcional de `rem.run()` — la memoria sigue sin importar
  cerebros); `_grounded()` (backstop determinista gratis: toda cifra/nombre propio del insight debe aparecer en
  las píldoras fuente) solo decide cuando NO hay `verify_fn` disponible. **Fail-CLOSED** (al revés que el resto
  de tareas de memoria): sin respuesta clara, se trata como no fiable. Rechazo SIEMPRE visible
  (`health_state.record`, nunca un warning silencioso), sin coste para el concepto (se reintenta el próximo
  sueño). Más un tope de longitud (`MAX_INSIGHT_CHARS=400`, antes solo había mínimo).
  ⚠️ **Corregido el MISMO día tras validación REAL** (norma del operador: "todas las validaciones tienen que
  ser reales... no nos importa el coste"): el diseño ORIGINAL dejaba `_grounded()` vetar SIEMPRE, antes del
  LLM. Probado contra DeepSeek V4 Flash de verdad (`tests/memory/e2e/bot/live_rem_faithfulness.py`, nuevo
  script de validación con coste real): el modelo convierte de forma CONSISTENTE una cantidad en palabras de
  la fuente ("las nueve") a dígito en el insight ("las 9") — paráfrasis fiel — y `_grounded()` la rechazaba
  SIEMPRE (comparación substring sin normalizar dígito↔palabra) mientras el verificador LLM real la aceptaba
  correctamente 3/3 veces cuando se le preguntó directamente. El backstop "de seguridad" bloqueaba el camino
  feliz normal de REM. Mismo principio que V2-075 ya fijó en otro módulo: el juicio semántico lo decide un
  MODELO, no un patrón hardcodeado. Verificado que los tests nuevos fallan sin el gate (`git stash` temporal) Y
  que el escenario real corregido pasa 3/3 pruebas reales tras el fix. Tests: `test_rem.py` — 339 passed.
- **Corpus longitudinal con contradicciones + REM real end-to-end (V2-107)** (2026-08-17): el corpus de 966
  ops/180 días (`tests/memory/e2e/timeline/`) era 100% fijo y determinista, sin ninguna semilla aleatoria —
  perfecto para regresión, ciego a la PRÓXIMA clase de bug (contradicciones a destiempo, paráfrasis semanas
  después, hechos casi-simultáneos en competencia). Extendido 180→270 días
  (`cases.py::_real_tramo()`): 90 días más generados con `random.Random(SEED)` — reproducible para una seed
  dada, variedad real si se cambia. Reutiliza el vocabulario `write`/`slot`/`recall` YA existente, cero ramas
  nuevas en `_execute()`. `runner.py` gana `--real` (hooks de REM REALES contra DeepSeek en vez del hook Python
  puro), norma del operador ("todas las pruebas tienen que ser reales... no nos importa el coste"). Verificado
  en vivo (`--target 20 --real`): 21/21 operaciones, REM real backfillando paráfrasis de verdad. **Dos bugs
  reales cazados en la primera corrida**: (1) una resolución diferida (`gap`/`offset`) sin acotar podía caer
  fuera del rango del bucle → la escritura quedaba sin su checkpoint, en silencio; (2) un checkpoint `slot` sin
  `not_marker` falla SIEMPRE (`"" in text` es cierto para cualquier texto en Python) — el bug estaba en MI
  código de generación, no en `_execute()`, pero el síntoma parecía un fallo del sistema bajo prueba. Ambos
  fijados como regresión pura (`tests/memory/unit/test_timeline_cases.py`, 7 tests, sin tocar la BD del
  timeline). No se corrió `--all --real` de punta a punta (270 días × REM real, potencialmente horas) —
  verificado en una porción representativa; la corrida completa queda periódica/manual, mismo patrón que
  `distiller_bench.py`/`scale_eval.py`. Suite: 356 passed, 1 skipped (subido de 349). Detalle:
  `V2-107-corpus-longitudinal-contradicciones.md`.
- **Susurro's friction window had no recency boundary — an 11-hour-old exchange got escalated as "now" (V2-108)**
  (2026-08-17): audited against `memory/_data/zaelar.db` directly (operator, sid `55783a7c-...`) found Susurro
  escalating a worker_action for a football's price under today's test trace — but that request was the real
  operator's conversation from **11 hours earlier** (a different session entirely), not anything from the test.
  Root cause: `memory.recent_window()` is a single GLOBAL conversational buffer (no session_id, no per-line
  trace, deliberate 2-day TTL for the FlashBrain's own reconnect continuity) — the probe/test channel correctly
  never WRITES to it (`ingest=False`), but nothing gated what Susurro READS from it, so an unrelated stale
  exchange got presented to the auditor with zero age signal. `nucleo/susurro/engine.py::_audit()` already had a
  `recency_window_s` cutoff for `turn_ring`/`event_ring`, added for the identical prior incident ("a scenario
  diagnosed a different EARLIER one's failure") — `conversation_block` was the one section that gap didn't
  cover. Fixed by extending the SAME cutoff to it: `memory.recent_window()` now carries `ts` per entry;
  `window.conversation_block/has_conversation/compose_audit_window` accept `since_ts` (fail-open on missing
  `ts`, e.g. existing test mocks); `_audit()` passes its existing `cut` through. Considered the trace-merge
  design the operator's report proposed (`voice.trace.merge()`, LLM declares the original trace) — rejected for
  THIS incident: even correct attribution would have merged today's work into an 11-hour-old, closed, unrelated
  trace, no less confusing than the original bug. That design stays valid for its intended case (a request from
  a couple of turns ago, same session, different trace) — just wasn't what this specific failure needed. Test:
  `test_conversation_block_drops_entries_older_than_since_ts` (real contract, no mocking — backdates a written
  entry 11h via direct SQL, same gap as the real incident). Suite: `agent-headless`, 547 passed. Detail:
  `V2-108-flujos-board-audit.md`.
- **A worker-dispatched browser task's own trace was empty for its whole lifetime — TaskBrowser used ambient
  context that was never active (V2-108, cont.)** (2026-08-17): same audit found `widgets/navegador/owner.py`'s
  `TaskBrowser._emit()` (via `tasks.trace_of(task_id)`) reporting no trace for a task's ENTIRE run — not a
  startup race that settles, confirmed with an event 12 minutes into a task's life still showing none. Root
  cause: `widgets/navegador/tasks.py::create()` stamped `trace` from `voice.trace.current()` (ambient context)
  at creation time, but the task is created inside `nucleo/dispatch.py::_prepare_web()` — the worker's own async
  execution, which never has that scope active. Nothing rewrites `trace` after `create()`, so an empty read
  there is empty forever. `_prepare_web` has the correct value the whole time (`rec.trace_id`, reliably set —
  proven by the same worker's own tool-call events carrying it correctly) — `create()` now accepts an explicit
  `trace` param that wins over the ambient fallback; `_prepare_web` passes `rec.trace_id`. A SECOND, distinct
  source of the same corr_id=NULL symptom (`widgets/navegador/act_api.py::_emit_nav` via
  `dispatch.record_by_nav_task`, labels 🧭 página/resultados/vista) was investigated and NOT fixed: ruled out
  id-space mismatch, session-registration ordering, and a silently-swallowed attribute-assignment failure, but
  didn't isolate the actual cause — left open, flagged for a live repro with temporary instrumentation rather
  than an unverified fix. A third source (`owner.py`'s module-level `_emit()`, the `browse_web` singleton flow)
  was confirmed CORRECT by design — no task_id to look up, left untouched. Tests:
  `test_create_with_explicit_trace_does_not_depend_on_ambient_context` +
  `test_create_without_explicit_trace_still_falls_back_to_ambient`. Suites: `browser` (354 passed),
  `agent-headless` (547 passed, 1 skipped). Detail: `V2-108-flujos-board-audit.md`.
- **La query de recall llevaba pegada la nota `[SISTEMA]` del turno — el modelo alucinó un familiar (V2-110)**
  (2026-08-17): auditoría en vivo encontró que zaelar respondió *"tienes un hijo o familiar que se llama
  Ricart"* — ninguna píldora dice eso. Causa: `voice/engine/llm/providers/nucleo.py::_run_inner` antepone las
  notas `[SISTEMA]` (bandeja `voice/brain_notes.py`) sobre `text` ANTES de usar esa misma variable como query de
  `needs_recall`/`compose_recall` — una nota de Telegram sobre trading dominaba el vector semántico y enterraba
  los hechos de familia que SÍ existían (`valid=1`, largo plazo). Con la búsqueda vacía, el modelo inventó. Fix:
  se captura `operator_text` ANTES de anteponer las notas y se usa SOLO eso para el recall — el `text` con notas
  sigue yendo íntegro al prompt del modelo (necesita verlas como contexto), pero deja de contaminar la búsqueda.
  Mismo fix espejado en `nucleo/flash/probe.py::run_turn` (impl paralela, misma bandeja). Investigado también si
  `memory/slots.py::state_field` (car/hardware/proyecto) no llegaba a `state` — **descartado con evidencia**: la
  fila `state` real YA tenía esos campos correctos, escritos horas ANTES del turno auditado (por eso "tienes un
  Range Rover" no era la parte alucinada). Sí se confirmó que NO existía slot para familiares — solo píldoras
  sueltas `slot=None`, alcanzables nada más que por el mismo recall que acababa de fallar; añadido
  `operator.family` a `memory/slots.py` (mismo trato que `operator.car`/`hardware`: texto que se restablece por
  reformulación) — cero código nuevo de proyección, reutiliza la mecánica slot+value ya existente. Detalle:
  `V2-110-recall-query-contaminada-slot-familia.md`.
- **Grafo multi-hop (PPR) + bi-temporal explícito — dos piezas de V2-111 §9, construidas por delante de las
  fases de entidades (2026-08-17)**: comparando con Engraphis (memoria local-first de terceros para agentes de
  código) salieron dos técnicas medidas por ellos que no dependen de que exista la capa de entidades/relaciones
  de V2-111 — operan sobre el sustrato de hoy (`edges`, `memories`).
  - **`memory/graph_ppr.py`**: `retriever.graph_expand()` solo hacía UN salto (pill→concepto→píldoras
    hermanas). Personalized PageRank añade un canal MÁS, acotado (BFS desde los mismos parents hasta
    `MAX_HOPS=3`/`MAX_NODES=400`, power iteration pura en Python, sin numpy/scipy nuevos), con su propio
    descuento y sin duplicar lo que el 1-hop ya trajo. Fail-open total (grafo vacío/roto → `{}`, cero impacto).
    Kill-switch `ZAELAR_GRAPH_PPR` (default ON — la lección ya escrita en este mismo fichero sobre capacidades
    que nacen apagadas y nadie las enciende, V2-095/V2-102).
  - **`valid_at`/`invalidated_at` (SCHEMA_VERSION 4→5)**: investigado ANTES de asumir que ya lo teníamos —
    `memories.updated` NO sirve como "cuándo se invalidó" porque también lo toca el refuerzo
    (`writer.py::reinforce`) y la promoción de nivel del consolidador, así que ninguna columna existente podía
    responder "¿qué creíamos cierto en la fecha X?" de forma fiable. Dos columnas nuevas (ALTER idempotente,
    mismo patrón que `slot`/`meta` v1→v2; `valid_at` se backfillea a `created` en filas existentes,
    `invalidated_at` se queda NULL — no se inventa una fecha que no se puede reconstruir) enhebradas en los 8
    sitios de escritura/invalidación/restauración (`writer.insert_memory` ×2, `writer.supersede()`,
    `consolidator.heal_slots`, `consolidator.expire_ttl`, `rem.py` dedup semántico, `api.forget()`,
    `api.unforget()` — este último limpia `invalidated_at` de vuelta a NULL al restaurar). Nueva
    `memory/api.py::as_of(slot, ts)` reconstruye el valor vigente de un slot en un instante pasado — sin
    inferencia de retroactividad todavía (una corrección dicha hoy se fecha hoy).
  - Ambas piezas son aditivas, cero cambio de comportamiento en las rutas de lectura existentes (`compose_state`,
    `search()`, `recent_*`). Tests nuevos: `tests/memory/unit/test_graph_ppr.py`,
    `tests/memory/unit/test_bitemporal.py` (registrados en el testmap, nodos 1.1/1.2). Suite completa
    `pytest tests/memory/ nucleo/`: 380 passed, 1 skipped (subido de 364). Detalle:
    `V2-111-memoria-entidades-relaciones.md §9` (las fases 0-3 de entidades/relaciones SIGUEN en diseño, sin
    construir).
- **An escalated flow closed itself seconds after opening — a structural race, not an occasional one (V2-113,
  2026-08-17)**: confirmed with millisecond-level trace evidence (session dd64a1a7-..., trace T5·d232) — a flow
  escalated to a Brain Worker got its explicit `flow/end` at +184ms while the worker itself didn't start until
  19s later. `nucleo/flash/escalate.py::escalate_to_slowbrain()` is synchronous and only publishes
  `bus.emit_sync("escalate.requested", ...)`; `nucleo/dispatch.py::run_listener` registers the `SessionRecord`
  that `has_live_trace()` checks for ASYNCHRONOUSLY, on its own task. `voice/engine/llm/providers/
  nucleo.py::_close_flow_now()` checked `has_live_trace(tid)` moments later, still inside the SAME synchronous
  turn — before the event loop had given the listener a single scheduler turn to react. Not a timing bug that
  usually works: the producer never yields before checking, so the consumer literally cannot have run yet.
  - **Fix carries the signal in the SAME turn, no new cross-module state.** Two designs were weighed: a shared
    "pending worker" registry between `escalate.py` and `dispatch.py` (new coupling between two modules
    deliberately decoupled today) vs. the call site that just decided to escalate passing that fact straight to
    `_flow_should_close` as one more boolean, same priority as `has_live_worker` — chosen for zero new shared
    state, consistent with that function's existing pure-decision contract. `NucleoLLM._escalated_trace_id`
    (same ownership pattern as `_acc_trace_id`) is set right before publishing; `_flow_should_close` gains
    `just_escalated: bool = False`.
  - **The guard had to be BOUNDED, not indefinite, or it traded one bug for a worse one.** `run_listener` has two
    outcomes that never create a `SessionRecord` at all: rejected while the agent is halted (⏻), or absorbed as
    a dedup refinement into an already-live session. Left unguarded, `just_escalated` would have blocked
    `_flow_should_close` from EVER closing those flows — permanently stuck open beats the original premature
    close for wrongness. `nucleo/dispatch.py::_close_escalated_flow(ctx, *, ok, status)` emits the same explicit
    `flow/end` `_run_session`'s finally block emits for a real spawn, wired into both `run_listener` branches.
  - Tests: `tests/voice/unit/providers/test_nucleo_trace_merge.py` (pure-decision guard + `_close_flow_now`
    reading `_escalated_trace_id`), `tests/agent_headless/unit/test_dispatch.py` (both `run_listener` branches
    against the real bus, confirming no `SessionRecord` is ever created for the escalated trace in either case).
    Full suite: 2076 passed, 7 skipped, no regressions. Detail:
    `V2-113-flujo-escalada-cierre-prematuro.md`.
- **Lead-in filler leaked into the chat wall AFTER the real reply — now its own module, and structurally unable
  to touch chat at all (V2-122, 2026-08-17)**: live report with a real chat transcript — "¡Hola! ¿Cómo va
  todo?…" followed by "Déjame que mire…", a neutral wait-filler trailing a reply that no longer needed covering
  anything. Confirmed against `zaelar.db`: both lines were generated correctly with real text — this was a
  TRANSPORT bug, not a generation one. The filler spoke through `voice.proactive.speaker()`, which in LiveKit is
  `session.say(text, add_to_chat_ctx=True)` (the default) — that registers a conversation item, which fires
  `conversation_item_added` → `agent.py::_on_item` → SSE `kind=transcript role=assistant` → the chat wall.
  `speaker()`'s own docstring already said the intent since 2026-08-14 ("not a message worth keeping") — nothing
  enforced it.
  - **Two separate speaker registrations, not one flag on the existing one.** `voice/proactive.py` gains
    `ephemeral_speaker()`/`register_ephemeral_speaker()`, sibling to `speaker()` but backed by
    `session.say(..., add_to_chat_ctx=False)` (`agent.py::_speak_ephemeral`). `clear_speaker()` releases both
    together (the same session registers them at the same point). NOT applied to `speaker()` itself: `_speak_
    acc_drop` (V2-096/V2-102's dropped-fragment notice / clarifying question) and `_schedule_acc_nudge`
    ("still here") also go through it, and THOSE are real content the operator may want in their history — only
    the neutral filler is inherently ephemeral.
  - **Extracted to its own module** (`voice/engine/llm/providers/lead_in_filler.py`, operator's explicit
    request — keep this concern isolated from the turn manager, modular): `LeadInFiller`, four verbs (`start()`,
    `mark_real_started()`, `cancel_for_barge_in()`, `stop()`) the turn manager calls at its three real
    integration points (first real token, barge-in, stream end). Replaces 5 loose pieces of state
    (`_real_started`/`_filler_spoken`/`_filler_task`/`_filler_say`/the inline coroutine) that used to live mixed
    into `nucleo.py::_run_inner` with one instance with an explicit lifecycle.
  - Tests: `tests/voice/unit/test_lead_in.py` (the two registrations are decoupled; `clear_speaker` doesn't
    steal a NEW session's speaker on an OLD session's teardown; the module uses `ephemeral_speaker()` and NEVER
    `speaker()`; `agent.py` passes `add_to_chat_ctx=False`) + `tests/voice/unit/providers/
    test_nucleo_directed_context.py` (repointed at the new file). Full suite: 2079 passed, 7 skipped.
  - **Two architecture questions raised in the same thread, resolved with the operator (AskUserQuestion)**:
    (1) whether non-preset languages should get their own generated filler phrases now — found the ENTIRE
    voice pipeline (STT + TTS + the model's reply-language directive, not just fillers) is hard-limited to
    es/en today (`langs.py::current_code()` falls back to English for any code outside its 2-entry catalog)
    even though onboarding already accepts and persists any language and generates its UI bundle + alias pack
    (V2-101) — **operator chose to let fillers degrade gracefully for now**, matching the rest of the pipeline,
    not build the full multi-language voice expansion in this pass; (2) whether filler/prompt/language data
    should live in `memory/` — operator clarified the real ask was a general "one stable place to look for any
    data, static or dynamic" principle, not literally the SQLite operator-facts store, and authorized a concrete
    call for this case. **Applied**: `pick_filler()` now checks a per-language GENERATED store
    (`i18n/init/fillers.py`, `i18n/generated/<code>.fillers.json` — same shape as V2-101's alias pack) before
    falling back to the hardcoded `LangSpec.fillers` pool; with nothing generated (today, always) behavior is
    byte-identical for es/en, only the lookup ORDER changed. Deliberately NOT wired to LLM generation yet
    (matches decision (1)) — `save()` exists and is tested, ready for a future generation step. Kept OUT of
    `memory/`'s SQLite on purpose: this is per-installation config, not operator facts, and `i18n/generated/`
    is already the established "stable path" for exactly this class of data (same home as the UI bundle and
    alias pack) — no new mechanism needed, and no encroaching on the memory-domain session's territory. Tests:
    `tests/voice/unit/test_lang_fillers_store.py` (7 cases, testmap node 3.7). Full suite: 2086 passed, 7
    skipped. Detail: `V2-122-relleno-modulo-aislado-y-fuga-al-chat.md`.
  - **V2-122 addenda (2026-08-18): "structurally unable to touch chat" over-corrected — the filler DOES belong
    in the chat wall, just explicitly and marked.** Operator's own words: "son frases que acaba de decir el
    agente" (they're phrases the agent just said) — making the filler invisible to fix its ORDERING bug threw
    out real, user-visible content along with the bug. The audio-side fix stands unchanged
    (`ephemeral_speaker()`, `add_to_chat_ctx=False` — that mechanism is what caused the ORIGINAL bug, LiveKit
    deciding `conversation_item_added`'s firing order, not us). What's new: `LeadInFiller._run()` now ALSO
    pushes its own dedicated, synchronous `emit("filler", "relleno", text=_ph, role="assistant", extra=
    {"cat":"flash"})` — a NEW `kind` (added to `voice/observer.py`'s `_CAT` as `"flash"` family, caught by the
    kind-classification ratchet test if forgotten) so the frontend can mark it distinctly from a real
    LLM-generated reply, never as `kind="transcript"`. `frontend/app/services/sse.js` gains a
    `kind==="filler"` branch → `store.pushAgentChat("💬 " + d.text)` (same prefixed-marker pattern as
    `notify()`'s "🔔 "). Ordering is guaranteed WITHOUT depending on LiveKit at all: this emit fires
    synchronously the instant the filler is decided, which by construction is always before any real reply
    text exists (`mark_real_started()` cancels this exact code path the moment the model's first real token
    arrives) — so the filler bubble always lands before the reply's, deterministically, regardless of TTS/
    audio timing. Test: `tests/voice/unit/test_lead_in.py::test_leadinfiller_empuja_su_propio_evento_de_
    chat_marcado` (behavioral, not source-grep — instantiates `LeadInFiller` directly and asserts both the
    `filler` and `brain` events fire).
- **Showing data is the generic sheet's job, not a reason to write a component — and a created widget was never
  opened (V2-115, 2026-08-18)**: "muéstrame una ficha técnica y una foto" of a car spent three minutes in the
  WIDGET GENERATOR writing a single-use `investiga-ferrari-f80` with the car's specs hardcoded from model
  knowledge, then announced "He creado el widget «X»" to a screen where **nothing appeared**. Three independent
  failures, none of which raised an error. Detail: `V2-115-hoja-generica-por-defecto-y-widget-nuevo-sin-probar.md`.
  - **(1) The indefinite article.** The FlashBrain's own reformulation ended in "Monta el resultado en **un**
    widget del canvas", and `_WIDGET_DEST_RE` — the guard that exists precisely to neutralize a widget named as a
    DESTINATION (V2-098, incident 2026-08-13, "Entrega el resultado MONTADO en el widget results" hijacking a
    travel investigation) — listed only `el|la|los|las`. **`un|una` was missing**, and that's the most natural
    phrasing. Reproduced before touching anything. Fixed by accepting any article (plus `a|an`), with one
    lookahead carve-out: **"en un widget NUEVO" really does ask for a new one** — there destination and create
    coexist and create wins; without it, widening the list would have swapped a false positive for a false
    negative. Verified both directions.
  - **…and the rail, which is the root the operator asked to fix.** The guard is the backstop; the reason the
    sentence got phrased that way was **the tool catalog itself** — `escalate_to_slowbrain`'s description said, in
    so many words, "búscala de verdad y **móntala en un widget**". We were teaching the model the phrasing the
    guard then has to undo. Operator's rule: *"cuando vamos a visualizar datos… el widget genérico de
    visualización debería ser el primero a utilizar por defecto… crear un widget solo está justificado cuando
    queremos hacer algo que no existe"* (his examples of what DOES justify one: the Snake game, an expense
    tracker, a daily-weight app — "cualquier cosa customizada que tenga que gestionar interacción con el
    usuario"). Applied in the two places the decision is read: `router.py`'s escalate description (findings —
    data, report, a product's spec sheet, a listing, photos — go to the results sheet; a NEW widget is only for
    functionality that doesn't exist and that the operator operates; catalog 19,466→19,759 chars, cap 21,000) and
    `dispatch_prompts.py`'s `_METHOD_BLOCK` step 4b, which covered only "un CONJUNTO DE RESULTADOS… una lista" —
    a worker asked for ONE spec sheet reasonably concludes it doesn't apply, **which is exactly what happened**.
    It now covers both: a list AND a single thing (spec sheet, report, photo, summary), the latter as one item
    with its `facts`/`images`/`blocks` opened via `data results detail` — the "hoja en blanco con título, foto,
    precio, características y enlaces" the operator described.
  - **On raw HTML in the sheet, deliberately NOT built**: the operator framed it as "enchufarle la HTML ahí". The
    `results` sheet already does what he wants (list mode AND single-ficha `view=detail`, with `facts`, `images`,
    `score`, `parts`, and custom `blocks`) but **rejects HTML on purpose** — closed vocabulary
    (`text·facts·chips·gallery·meter·table·link·section`), everything rendered via `textContent`. That content is
    written by a worker from arbitrary web pages, so accepting markup would be direct injection into the canvas.
    What was missing was never expressiveness — it was the sheet getting used. Recorded for a decision in the
    open, not silently resolved either way.
  - **(2) A created widget was opened by nobody.** `GeneratorBackend._drive()` emitted `result` with
    `data={"widget": wid}` and **nothing read it** — `session.py::_handle` keeps `summary`/`ok`/`usage` and drops
    `data`; the only path that ever opened a worker's widget was the browser's (`dispatch._prepare_web`). In the
    `existed` branch the copy literally says *"ya existía, te lo muestro"* over an unchanged screen: the same bug
    with the worst of the two wordings. Fixed by emitting `widget/show` **in the backend**, where the action is
    known — `delete` returns before it (opening what you just deleted is absurd) and `session.py` stays the
    AGNOSTIC stream pump that doesn't know what a widget is. Four cases tested, verified failing without the fix.
  - **(3) PROCESOS ↔ FLUJOS were misaligned** (operator: *"los procesos no dejan de ser flujos y deberían estar
    alineados"* — the flows board said "ningún flujo activo" while Procesos still showed "creando un widget… en
    curso"). `dispatch.active_sessions()` was **the only one of the three projections with no status filter**,
    under a docstring saying "sesiones vivas" — `has_active()` and `pending_summaries()` both carry it right
    below, and `sync_state()` re-applies it by hand to `_SESSIONS` rather than trusting the function, which is the
    clearest possible signal it was missing. Every consumer reads it as live: `loop.py` dumps it into a set named
    `live_ids`, `susurro/apply.py` dedups against it (a FINISHED task suppressing a legitimate re-run), and
    `/api/tasks` feeds the Procesos chips, which paint **every row they receive** as in-progress. Fixed on both
    sides of the seam: the filter in `active_sessions()`, and `reconcileTasks()` (frontend) now honors `status`
    instead of assuming everything it receives is live — a `done` row that slips through doesn't just resurrect
    the phantom chip, it also **hides its own ✓ history row** (`ChatWall` drops live ids from history).
  - **Left open, deliberately**: `fetchTasks()` only fires on `es.onopen`, on a tab CHANGE, and on ⏻ clicks — so
    nothing reconciles while Procesos sits open, and **one lost `task/end` pins the chip forever** (already
    described in-code at `Orb.js:150-156`; likely what the operator watched for 30 minutes). The obvious cure, a
    `setInterval`, collides head-on with the widget system's "refresco por SSE, nunca polling" rule — choosing
    between that, a `visibilitychange` hook, or a reconcile on tab re-render is a design decision, not a fix.
  - **The real gap this exposes, and the operator's explicit ask**: *"tenemos que probar la creación de un widget
    y su visualización… que el proceso de un nuevo widget esté operativo al 100%"*. **Creating a new widget has no
    end-to-end test at all** — that's what let failure (2) live indefinitely. The generator is covered
    (`make test-widgets`, action/background/CSS validation) and now the `show` is, but **nothing walks the whole
    chain**: escalation → `kind=code` → `GeneratorBackend` → `generate_widget` → validation → catalog →
    `widget/show` → a card painted on the canvas with data in it. Every link is tested in isolation; the chain
    isn't. Tracked as the primary open task in V2-115, together with the reverse case (ask for a spec sheet and
    assert that NO widget is created and the result lands in `results`).

- **One sentence must be ONE flow — and flow continuity can no longer hang on getting completeness right; plus the
  chat wall stopped waiting for the voice (V2-116, 2026-08-18)**: live report — *"mientras yo estaba hablando,
  encima se iban abriendo flujos diferentes… se han abierto cuatro flujos"* plus *"el agente me está hablando, no
  aparece el texto en el chat de su respuesta"*. Session `b403c979`. Operator's framing of the stakes: **flows are
  the system's skeleton** — any continuous action lasting minutes must be attachable to one corr_id — under the
  standing rule *"NECESITO QUE CUANDO ALGO FUNCIONA YA NO SE JODA MÁS"*. Detail:
  `V2-116-flujo-por-frase-y-muro-de-chat-sin-esperar-la-voz.md`.
  - **NOT a regression of V2-096/V2-090's merge — that works.** The defect: flow continuity depended ENTIRELY on
    the LEXICAL layer judging completeness correctly, because adoption was gated on `brain._acc.pending()`. Measured
    on the real STT finals: `looks_incomplete("Mira, lo que quiero es")` → **False**. It's a clause dangling off
    the copula «es» (demanding a complement not yet spoken) but it ends in a VERB, not a function word, so layer 1
    calls it closed → the accumulator RELEASES it → the `"act"` branch cleared `_acc_trace_id` → the next fragment
    opened a fresh flow. **One false "complete" splits the sentence.** And there is no second opinion: V2-102's LLM
    judge only runs when layer 1 says *incomplete* — the asymmetry is deliberate (keeps the fast path free) but
    makes a false "complete" final. Production cost: 4 corr_ids, two full ~5,800-token prompts thrown away, each
    turn cancelled by the next.
  - **Fix: separate the two questions.** A resolved chain's trace is no longer discarded — it stays in GRACE
    (`_CHAIN_GRACE_S`, 3s, `ZAELAR_CHAIN_GRACE_S`) and a turn arriving inside that window ADOPTS it. Structural and
    cheap: no word lists, no LLM, no added latency. The 3s comes from V2-096's own measurement (p50 pause WITHIN a
    sentence = 2.3s), and it fails on the safe side — at worst it merges two sentences said back-to-back into one
    flow, far less harmful than splitting one hesitant sentence into four. The counterweight is a test: past the
    grace window, a new topic gets a new flow. The caller's bookkeeping was extracted to
    **`_resolve_acc_chain(brain)`** on purpose so the test exercises the SAME code production runs — a test that
    reimplements the fix can pass while production does something else, which is exactly the failure mode here.
  - **Deliberately NOT fixed, and it costs more than the split flow (open task #1)**: the false "complete" itself
    still burns a full prompt and leaves a cancelled turn per stray fragment. Not touched because V2-095 recorded —
    measured against **195 sessions / 804 transcriptions** — that hand-tuning `_HARD`/`_SOFT` produced **three false
    positives** only visible on the full corpus, one of which RETAINED "Y que lo pares todo" (delaying a STOP
    order). Adding «es» to a list because one sentence failed today is precisely the patch that measurement exists
    to prevent. Correct route: run the corpus, and consider detecting the dangling copula as a grammatical CLASS
    («lo que quiero es», «la idea es», «el caso es») rather than another word.
  - **The chat wall was fed ONLY by LiveKit's `transcript`**, which isn't emitted until the conversation item
    closes — i.e. until TTS finishes speaking the WHOLE reply. Measured: reply→wall of **5.4s** and **12.2s** in
    this session; the longer the answer, the later the text, which the operator experienced as "a minute". Now the
    reply is pushed the moment the model generates it (`brain`/`reply` already carries the full text and
    `role=assistant`), and `pushAgentChat` dedupes by **PREFIX** instead of exact equality — which also fixes the
    barge-in case, where the later transcript arrives TRUNCATED and exact-equality would have left two bubbles (a
    complete one and a half one); the complete text wins. **Subtitles untouched**: they still come from the
    audio-synced transcription (`session-lk.js`), correct for something that accompanies the voice. The operator
    also reported subtitles missing — not reproducible without a browser, most likely independent; open task #2.
  - **On "quizás hay que empezar a quitar Python de ciertos lugares"**: this turn took **22.7s** and the engine's
    own diagnosis says "TODO ANTES DEL 1er TOKEN". That is not Python — it's ~10s of `web_search` plus provider
    TTFT (V2-097's finding that the broker ignores `thinking:disabled`). The headline model choice is still
    pending a TARIFF decision, not a language rewrite. Worth its own conversation with the numbers in view.
  - Use case (operator's explicit ask — *"crea un use case y simúlalo empezando con una instancia de agente
    vacía"*): `tests/voice/unit/providers/test_nucleo_trace_merge.py::test_use_case_una_frase_titubeante_es_UN_solo_flujo`
    replays the five REAL STT finals from a clean agent instance; verified failing without the fix
    (`ZAELAR_CHAIN_GRACE_S=0` → 2 flows). It also asserts the PREMISE (that fragment 1 is still judged "complete"),
    so it announces itself if it ever stops testing what it thinks. Chat wall: node 4.17,
    `tests/browser/unit/chat/test_chat_wall_promptness.mjs` (6 cases), also verified failing without the fix.

- **A worker started with the engine's own developer manual inside it, and its raw provider error was delivered as
  the report (V2-117, 2026-08-18)**: the operator asked for a left-handed child's guitar and got
  «API Error: The model has reached its context window limit.» read out loud, 4m48s and $2.27 in, with zero results.
  The message was wrong on three counts and the real cause was in a line that did not exist. Detail:
  `V2-117-contexto-del-worker-y-un-solo-hilo.md`.
  - **It was not the context window, and it was not Opus.** From the worker's own native transcript: the real
    `apiError` was **`max_output_tokens`** (the provider rejects once accumulated input PLUS the requested output
    reservation no longer fit — which is why it died at 138,492 and not at 200,000); that sentence is the CLI's
    **synthetic** message, not the provider's. The model that actually ran was **`glm-4.7`**, while the record said
    `claude-opus-4-8[1m]` because `self._model = spec.model` keeps the requested ALIAS and `spawned` only overwrites
    it when the spec came empty — so the panel lied about the model AND the $2.2696 was priced at Opus rates for a
    GLM run.
  - **The real cause: it started 62% full.** The FIRST API call already carried **122,833 input tokens before the
    worker did any work**; the 14 browser round-trips only added ~15k. The spec carried no `cwd`, so the backend fell
    back to the ENGINE ROOT and the headless agent loaded `engine/CLAUDE.md` (304,893 bytes ≈ **76k tokens**) plus
    the parent `CLAUDE.md` on EVERY request. Measured head-to-head afterwards against the real CLI, same trivial
    prompt: **167,242 tokens with the repo as cwd vs 25,352 in a scratch dir (−84.8%)**, and the spawn's fixed cost
    ÷24. Today a worker would have 33k of 200k left — it cannot even begin. The number is HIGHER than the incident's
    because `CLAUDE.md` has grown since: the fault was getting worse on its own.
  - **Three faults collapse into that one `cwd`**, and `nucleo/workers/workdir.py` (one private directory per task,
    `PYTHONPATH` to the engine root — the pattern `dispatch_devworker.py` already used) removes all three:
    the CONTEXT above; the COLLISION (the delivery recipe tells every worker to write `informe.json` to a RELATIVE
    path, so a shared root means a shared file — the guitar worker started with the PREVIOUS day's report attached);
    and PRIVACY (walking up from `engine/` also loads the ROOT `CLAUDE.md`, the private business/cloud one, and ships
    it to whichever provider serves the worker). Applied to `web`/`research`/`generic`/`memory`; `code`/`dev` keep
    the repo because their job IS the repo.
    ⚠️ Bug caught while testing it: the module lives one level deeper than the file whose pattern it copied, so two
    `dirname` calls pointed `PYTHONPATH` at `nucleo/` and `-m nucleo.nav_cli` stopped resolving — a worker with NO
    bridges at all, the very fault the module exists to prevent.
  - **`WorkerSpec.read_dirs`** — a genuinely agnostic field (declare the intent, each backend translates it to its
    own flag; `claude_session` → `--add-dir`). `extra_args` could not carry it: all three backends splice that in
    VERBATIM, so a Claude-only flag there would have broken Codex and Grok. Born with the confined cwd, because the
    browser's vision path hands over its screenshot as an ABSOLUTE path outside the working directory.
    ⚠️ A claim of mine, corrected the same session: I wrote that without this the worker would be BLIND. Tested live
    against the real CLI with production flags (`--print --permission-mode acceptEdits --allowedTools Read`, from a
    scratch cwd) — an absolute read outside the cwd is ALREADY permitted, so `--add-dir` is not what keeps the vision
    path working. Kept as defence in depth (it states the read dependency explicitly instead of resting on a
    permission default that could tighten silently), but the rationale was wrong and it was wrong in five places.
  - **A blown context gets its OWN failure family** (`providers.is_context_overflow`), deliberately NOT inside
    `classify_failure`: it is not a sick provider. Folding it into `exhausted` would put a healthy tier on cooldown
    and migrate the fault to the next one, which would blow up identically. The right answer is COMPACT AND CONTINUE,
    not relay. Until now `classify_failure` returned `""` for it → no `provider_down` → the one-shot relay retry that
    ALREADY existed (`provider_retried`) never fired: the same hole closed for quota on 2026-08-10, still open for
    everything else.
  - **The number that predicts death was already flowing past us.** `session.py`'s `usage` branch accumulated tokens
    for the post-mortem bill; nothing watched the context SIZE. They are different quantities and conflating them is
    what left us blind: spend is SUMMED message by message, but the context is the TOTAL OF THE LAST message
    (`_ctx_size`: fresh + cache read + cache written) — `input_tokens` alone said «956» when the real context was
    138,492. Now a watchdog (`ZAELAR_WORKER_CTX_BUDGET`, def 110,000) injects ONE turn asking the worker to deliver
    what it has. It is TALKED to rather than killed because the session is still alive and its own reasoning is the
    cheapest summary of its progress — same stdin channel `send_to_worker` already uses, no new machinery.
  - **Compact and continue** (`context_handoff` + a branch in `_finish`): re-escalated ONCE carrying plan, steps
    already taken, last narrated note and reported breadth. No LLM call — compacting must not depend on a model being
    reachable at the exact moment one just failed. It deliberately does NOT carry the dead worker's
    `result_summary`: on that path the field holds the provider's error, and pasting it would tell the fresh worker
    its predecessor's error message was a finding.
  - **A raw provider error is NEVER the report** (`operator_safe_summary`, at the delivery point): the specific
    branches each replace the text for the failures we anticipated; this one covers the next one we did not. It is a
    translation, never a silence — the operator always learns the task did not finish; only the internal wording
    disappears, and the full text stays in the log.
  - **`self._tier` went blind whenever the endpoint arrived PRE-SET in `spec.env`** — it was only assigned inside
    `if "ANTHROPIC_BASE_URL" not in env`, so on that path every piece of provider attribution reported an empty
    `base_url` and a failure could not name who served the session. Choosing the endpoint and KNOWING which one is in
    play are two different jobs; only the first belonged in that `if`.
  - **A flow is ONE chronological thread, and the board now shows it that way** (operator: *«todos los mensajes,
    ejecuciones, eventos… todo tiene que ir en un mismo hilo cronológico, y así se tiene que ver en el master»*). The
    DETAIL already complied since V2-105, but the board and rail read `flows_detail` grouped by RAW `corr_id`, so a
    merged task painted TWO columns and counted twice in «N active». `flows_detail` now exposes `merge_into` in BOTH
    places — `observability/flows.py` (local) and `cloud/backoffice/src/flyQuery.js` (cloud), per the two-surfaces
    rule: a column added on one side only does not fail with noise, it fails coming out EMPTY. `foldMergedFlows()`
    folds absorbed rows into their titular (combined window, `t_ms` RECALCULATED — summing two durations would exceed
    the real elapsed time, since the halves of a hesitant sentence overlap), and the board paints a **+N** chip
    because a flow that vanishes with no explanation is silent state. `handleFlowDetail` now orders by `ts_ms` and
    takes `lastId` as the MAXIMUM: with two merged traces the events INTERLEAVE, so the newest in time is not
    necessarily the highest id.
    ⚠️ **This is LATENT, and saying so matters**: checked rather than assumed — `voice/trace.py::merge()` has ZERO
    callers in the tree and `SELECT COUNT(*) FROM events WHERE kind='trace' AND label='merge'` returns **0**. The
    folding is correct, tested plumbing with nothing yet to fold; the trigger is the half V2-105 left unbuilt ON
    PURPOSE. It also corrects the operator's reading that a vanishing column meant a merge: the board only paints
    ACTIVE flows (60s window), so a finished turn leaves the view by itself, and the ~350ms no-reply flows were
    stillborn columns, never merges. Nor does the `ts_ms` ordering change anything VISIBLE today — with a single
    trace, id order and time order coincide because the sink writes in order; it is a correctness guard for the
    merged case, not an observable improvement.
  - Tests: `tests/agent_headless/unit/workers/test_context_budget.py` (node 2.5, 41 cases, the use case rebuilt from
    the real evidence) + `cloud/backoffice/test/flowAttribution.test.js` (+12). **Sensitivity verified** — with the
    classifier disabled the failure goes invisible again (0 events), without the delivery gate the operator receives
    the `API Error` verbatim, and with the watchdog at 0 the worker sails past the ceiling in silence. **NOT verified
    live**: the engine was not restarted in this pass, so a real task running with the confined cwd (bridges +
    reading its own screenshot) is still unexercised — that is the first thing to try.

- **The flow-merge TRIGGER, built at last — and neither of the two resolvers we already had could do it (V2-123,
  2026-08-18)**: V2-117 left the master able to paint ONE chronological thread for a merged task and nothing to
  paint, because the trigger is the half V2-105 left unbuilt ON PURPOSE (`voice/trace.py::merge()` had zero callers
  and the DB held zero merge markers — checked, not assumed). Detail:
  `V2-123-disparador-de-fusion-de-flujos.md`.
  - **The gap, from the operator's own screenshot**: while a worker searched for a guitar, "sí, muéstramelo todo en
    tiempo real" and the agent's reply to it opened a SEPARATE flow. V2-090's merge only fires when the model calls
    `send_to_worker` — its handler is where `resolve_sessions` gets consulted — so a follow-up the model answers
    CONVERSATIONALLY, the most natural thing an operator says while waiting, matched nothing and split the thread.
  - **`_merge_target()`** (`nucleo.py`, pure decision, wired into `_close_flow_now`): a finished turn is absorbed
    into the ONE live task's flow. **Deliberately not text matching**, and that was the load-bearing choice: both
    resolvers this codebase already has are wrong for attribution, from OPPOSITE ends. `dispatch.resolve_sessions`
    is loose ON PURPOSE ("mejor parar de más que dejar zombies") so with one live task it returns it for ANY
    wording — precision it does not actually have; `find_duplicate` is strict (Jaccard ≥ 0.60 of content words) and
    "muéstramelo en tiempo real" shares ZERO words with "busca una guitarra zurda", so it would reject the very
    case this exists for. What IS solid is state we already hold: exactly one task running, and this turn started
    nothing else. Guards: `just_escalated` (this turn launched its own task — V2-113's signal reused), `tid` already
    being a live task, **exactly one** candidate (with several running, which one a bare "¿cómo va?" refers to is a
    guess, and since V2-090 a stray extra flow beats guessing), and any tool outside `_WORKER_CONTROL_TOOLS`
    (putting on music is a turn about something else, whatever is running).
  - **The absorbed trace does NOT emit its own `flow/end`**, and this is not a detail: the reader counts a close for
    the FOLDED row (`_absorb` sums `ended_events` — "closed if EITHER closed", correct when both halves are
    fragments of one sentence), so closing here would mark a still-working task as finished and drop it off the
    board. Losing sight of live work is worse than the stray open flow the close exists to prevent. Same rule as
    everywhere: the flow belongs to whoever is still working.
  - **Second trigger, pure proof rather than evidence**: `dispatch._merge_dedup_flow()` in `run_listener`'s dedup
    branch. When `find_duplicate` matches, the 60% overlap was already demanded — they ARE the same task, learned
    AFTER the turn opened its trace, which is exactly what `merge()`'s append-only marker exists for.
  - **Accepted false positive, stated rather than hidden**: a purely conversational request using no tool while one
    task runs lands in that task's thread. The trade is deliberate (the operator asked for a COMPLETE thread,
    splitting is the reported bug, the mis-attribution is bounded to one task's lifetime and stays VISIBLE via the
    board's `+N` chip). The upgrade that removes the guesswork is the model DECLARING continuation (V2-105's
    recommended design) — a tool-schema change with its own measurement, not a reason to keep splitting meanwhile.
  - **Verified live, and it closed V2-117's open item**: engine restarted, a REAL Wallapop investigation ran with
    `cwd=/private/var/…/T/zaelar-workers/1` (not the repo root) and `PYTHONPATH` at the engine — and from that
    confined directory the memory bridge answered both ways, the phase report worked, and the worker READ ITS OWN
    SCREENSHOT (`📄 archivo ↩ [imagen]`), which was the concrete doubt behind `read_dirs`/`--add-dir`. **Not
    verified live**: `_merge_target` lives in the VOICE provider and the probe channel doesn't close flows, so that
    half is test-covered (sensitivity checked by disarming each half) but unexercised by a real voice session.
  - ⚠️ **Side finding, real money**: trying to provoke a live merge, two escalations of the SAME search did NOT
    dedup and both workers ran, doing the job twice. Measured Jaccard **0.556** against the 0.60 threshold — and
    among the tokens separating them, `zurdo` vs `zurdo,` and `guitarra` vs `(guitarra`. `_content_words` split on
    whitespace over a `_norm` that only strips accents and lowercases, so **punctuation stayed glued to the word**.
    The bias was one-directional (punctuation can only push the ratio DOWN: it shrinks the intersection and grows
    the union), so it always failed towards letting duplicates through. Fixed with `\w+`, paired with a test that
    demands the duplicate now match AND one that demands two genuinely different tasks still DON'T — without the
    second, "fixing" dedup is indistinguishable from loosening it. Corrected an overclaim of mine in that same
    comment: `\w+` does not save CJK (2-3 character tokens, already dropped by the `len(w) >= 4` filter before this
    change) — a pre-existing limit, written down as one.
  - ⚠️ **STILL OPEN after that fix, and it still costs money: the dedup cannot see a PARAPHRASE.** Repeated live with
    the fix loaded — two escalations of the same guitar search, **two workers ran again**, Jaccard **0.471** vs the
    0.60 threshold. The separating words say it: `busca`/`infantil`/`tamano` on one side, `lanza`/`investigacion`/
    `precios`/`enlaces` on the other — the SAME task said two ways (one is the FlashBrain's reformulation, the other
    the raw text). Lowering the threshold is not the fix: 0.60 is strict on purpose so it does not absorb genuinely
    different tasks, and loosening it trades a costly failure for one that mixes up unrelated work. The route this
    repo already has written for this exact class is V2-075: **a MODEL judges semantics, not a pattern.** Recorded
    as an open defect with its measured number, not as fixed. Nuance worth keeping: in NORMAL use the FlashBrain
    REFUSES to re-escalate (first attempt it just replied conversationally, V2-029) and only did so when explicitly
    told "lanza TAMBIÉN" — so today's real protection is the FlashBrain itself, `find_duplicate` is the backstop,
    and the backstop is weak. Which is also why the dedup trigger is RARE in practice and `_merge_target` is the one
    actually holding the thread together.

- **A SECOND SHELL over one engine — the mobile PWA, and the two contracts that made it cheap (V2-124, 2026-08-18,
  operator request: «una progressive web app… que no lo tenga que conectar a nada ni meter en la store», with the
  design already specified — full-screen widgets, two-finger paging, «el orbe y todas las opciones abajo del todo»,
  chat, an on/off switch, a menu for feedback/account/profile, «una carpeta separada… piezas nuevas lo más separadas
  posibles para no interferir»)**. `frontend/mobile/` is installable on an Android or iOS home screen and drives the
  SAME engine: no mobile backend, no mobile API, not one new data route. Anatomy + design rules:
  `.meshkore/docs/modules/zaelar-mobile-shell.md`. Product/cloud side (origin, paid tier, the home-computer bridge)
  in the workspace root's private repo — this repo is public.
  - **The finding that governs the whole thing: the frontend was ALREADY split by two contracts, and neither
    mentions the DOM.** (1) `services/sse.js` touches no DOM at all — the only thing it does with its argument is
    call **13 methods** (`show`/`close`/`closeAll`/`createWidget`/`modifyWidget`/`onDeleted`/`showConfirm`/
    `hideConfirm`/`move`/`resize`/`fullscreen`/`refreshData`/`refreshRegistry`), plus `setRunning` (main.js) and
    `_reportOpen` (session-lk.js). (2) every widget is mounted with a **4-member `ctx`**
    (`action`/`close`/`top`/`running`). So the work was never "adapt the widgets": it was writing a SECOND host of
    those two contracts with another idea of screen. The whole widget catalog — including widgets the agent
    generates tomorrow — works on the phone with zero changes to `sse.js`, zero to any widget, zero to the backend.
  - **Media queries on `app/styles.css` were rejected on measurement, not taste**: that file is ~89 KB written
    around a 3-column desk with a docking chat, and `widgets/desktop.js` is 859 lines whose SUBJECT is a pointer (drag
    by the grip, 8 resize handles, free-space tiling, z-order on click). Retrofitting puts every mobile regression
    inside the desktop's blast radius permanently. The mobile stylesheet is ~11 KB and imports nothing from it.
  - **Two things the contract means differently in a deck, said out loud instead of faked**: `move(id, where)` has no
    spatial meaning when one card fills the screen → it REORDERS the card; `resize` is refused explicitly
    (`{ok:false, reason}`), because a silent no-op in a contract method is how a shell starts lying about what it did.
  - **Paging is TWO-finger and one finger is the widget's.** If one finger also paged, every scrollable widget would
    be unusable — you could not scroll without changing cards. And a card is HIDDEN while paging, never unmounted: a
    video that keeps playing behind another card is correct; re-mounting would cut it off. V2-092's global stop is
    what silences it.
  - **SHARED by import, never forked**: `core/store.js` (one truth about power/energy/chat/tasks — two stores would
    be two truths, the failure this codebase has paid for repeatedly), `core/reactive.js`/`dom.js`/`i18n.js`, all of
    `services/`, and — extracted this pass — **`app/core/palette.css`** (the `--hb-*` contract both shells AND every
    widget read) and **`app/core/shared-surfaces.css`** (the CSS of `BootOverlay`/`LanguageOnboarding`/`Alert`, the
    three components both shells mount verbatim). Those two extractions are the point: a second copy of the tokens
    would NOT fail loudly — it would make a widget paint wrong colors in one shell only, and forking a first-run
    gate is how two shells end up disagreeing about whether onboarding happened.
  - **The service worker is almost empty ON PURPOSE, and there is a test to keep it that way.** A cached module is a
    stale agent — `server/pages.py` serves the shells `no-store` precisely so a reload cannot run yesterday's JS. So
    `sw.js` intercepts ONLY navigations, touches nothing else (`/api/*`, `/events`, `/widgets/*`, `/static/*` never
    pass through it) and **never calls `cache.put`**. Its only jobs are Android installability (Chrome demands a
    manifest plus a fetch handler) and an offline card instead of the dinosaur. iOS needs no worker, only
    `apple-mobile-web-app-capable` + `apple-touch-icon`.
  - **THE VOICE LOCK is the real hole the brief did not see.** The operator's framing was «desde dos frontends se
    conectan al mismo server, y ya está» — almost: `server/livekit_api.py` allows exactly ONE live voice session per
    machine (two open mics break the pipeline). Until now the two contenders were two tabs on one computer, so
    "close the other one" was actionable in a second; a phone and a laptop in another room are not two tabs. The
    automatic behaviour is RIGHT and untouched (`micBlocked` + 3s self-retry: when the desktop closes, the phone
    takes the voice on its own). What was missing is that `micBlocked` paints a 🚫 ring on the desktop orb —
    legible when the other tab is visible, meaningless between rooms. New `POST /api/session/steal` (EXPLICIT
    operator gesture only; the previous holder's ~4s heartbeat already knows how to stand down, so the handover
    needs no new machinery on the loser's side) + a surface that NAMES the situation. The loser drops to chat +
    observer, which has worked since V2-088.
  - **Which shell a device lands in** is decided by a picker in `frontend/index.html` that runs BEFORE any ES module
    loads (so a phone never downloads the desktop stylesheet just to be redirected away from it): explicit choice
    sticks → stored choice → narrow viewport **AND** coarse pointer. Both conditions deliberately: a narrow desktop
    window is still a mouse, and erring permissively would strand a laptop user in a one-card shell. `/` keeps
    answering 200 HTML because the platform health check fetches it — the redirect is client-side, never a 302. The
    escape hatch appears in two places and is not optional: a shell you cannot leave is a trap.
  - **Three routes added to `server/ingress.py`'s allowlist** (`/m`, `/manifest.webmanifest`, `/sw.js`) — all build
    constants, identical in every process. `/sw.js` must come from the ROOT with `Service-Worker-Allowed: /`,
    because a worker only controls its own directory downwards and one under `/static/mobile/` could never see a
    navigation to `/m`.
  - **THREE REAL BUGS found by rendering it in a phone-sized Chromium, none of which reading the source would have
    caught**: (a) `t()` returns the KEY when a string is missing — which is TRUTHY — so every `t("x") || "fallback"`
    was dead code that READ like a working fallback, and the shell showed a literal `mobile.empty_title` on screen;
    fixed by putting the 29 strings in `i18n/bundles/{en,es}.json` (the base bundle is also what makes a GENERATED
    language get them, since init diffs against English) and deleting all 36 fake fallbacks. (b) A
    `textContent = t(...)` at construction time freezes whatever the bundle had before its async fetch landed — the
    empty state and four menu rows were permanently stuck on their keys; they are reactive bindings now. (c) The
    chat sheet BURIED the dock (78vh from `bottom:0` on a 390×844 screen), which would have meant the operator
    cannot mute the mic or press ⏻ while the chat is open — the sheets now stop ON TOP of the dock. My own CSS
    comment had claimed a sheet "never covers the dock"; the layout was fixed, not the comment.
  - Test node **4.18** (`tests/browser/unit/mobile/test_mobile_host_contract.mjs`): every assertion DERIVED from a
    source of truth — the methods `sse.js` actually calls, the routes the Python decorators actually declare — never
    a hand-copied list, because a hand-copied list keeps passing while the phone silently ignores the brain.
    Sensitivity verified by breaking each one (dropping a Deck method, inventing an endpoint, linking the desktop
    stylesheet). Full deterministic testmap green (74 nodes).
  - **NOT verified live, and it is the first thing to try**: the engine was not restarted this pass (it was serving
    an older build from a concurrent session), so `/m` has never been loaded against a REAL backend — voice,
    SSE-driven widget opens, the two-finger gesture on real hardware and the PWA install prompt are all unexercised.
    What IS verified: the three routes serve with the right headers and content types, the module graph resolves with
    zero page errors in a 390×844 Chromium, and the dock/sheets/deck render with the intended geometry.
  - **THE ORB MOVED TO THE CENTRE OF THE DOCK, AND IT IS THE SWITCH** (2026-08-18, operator: «un orbe también en
    el centro del footer… y en los laterales del orbe, el resto de botones», plus «podría ser el mismo orbe que le
    podamos apretar encima: cuando está parado solo está el botón de on/off»). Six controls in three zones —
    `mic · speaker · captions | ORB | chat · menu`. Stopped, the centre slot is a ⏻ and nothing else; running, it is
    zaelar's face and tapping it stops. Both faces go through ONE handler, the same `api.runStop()`/`runStart()` +
    `markPowerCommand()` seam as the desktop ⏻ (V2-092: the switch is the SERVER's state). Cycling the TTS voice
    moved off the orb into a menu row — on a phone in a pocket, the gesture that changes what the agent sounds like
    must be deliberate. Glyphs are the desktop's BYTE FOR BYTE from `app/components/Orb.js`, and the test DERIVES
    them from that file so the two shells cannot drift apart unnoticed.
    - **TWO REAL BUGS, both only visible by RENDERING it** — the deterministic node was green through both:
      (a) the orb sat **8px off centre**, because `1fr` is `minmax(AUTO, 1fr)` and the three-button side grows its
      own track past its fair share (fixed with a 0 floor + 48px icons: 3×48+4 = 148 ≤ 152 of fair share);
      (b) **the orb never painted at all** — an empty hole in the middle of the bar with no error anywhere. I wrote
      the centre as `() => state === "off" ? h(⏻) : h(button, OrbMini())`, which is the natural shape and the wrong
      one: a reactive child function re-runs on every state change and returns a NEW tree, so each transition minted
      a fresh `OrbMini` with a fresh `<canvas>`, while `main.js` had handed `$("#orb")` to the visualiser once at
      boot. After the first re-render that handle is a DETACHED node: the loop kept running (measured 741 frames)
      painting where nobody can see, and the canvas on screen was never drawn to. **0 painted pixels of 9216, versus
      10490 for the desktop under the SAME preview** — which is what ruled out the headless environment. Both faces
      are now built once and swapped by `display:none`.
    - **A LATENT bug in the SHARED visualiser that the new design exposes**: `_orbFrozenAt` was recorded even on
      frames with zero width, and a hidden orb (stopped) produces exactly those — so coming back from stopped the
      latch was still set and it never repainted. Verified both ways: with the guard, tapping ⏻ paints 1704px;
      without it, 0 and the canvas is not even resized. The desktop never hid its orb, so it never hit this. My
      first comment there blamed this latch for the boot-time hole and that was **false** — it only breaks the
      stopped→starting path; corrected in place.
    - **The PWA icons are a SILHOUETTE on flat black** (operator: «super limpios, fondo uniforme, idealmente negro,
      solo siluetas, los más parecidos a los que ya existen en el frontend»): the mark is THE EYE, already fixed in
      this file as zaelar's identity (the orb is the iris), with the real eyelid ratios (±2.16·R, ±1.24·R) solved to
      a circular arc. The maskable variant fits the 80% safe CIRCLE by its bounding-box CORNER (2.49·R ≤ 0.4·S).
    - **Test node 4.19 exists because 4.18 could not see any of this** (`tests/browser/e2e/mobile/render_dock.py`):
      it RENDERS the shell at 390×844 and measures it — the orb centred within 1.5px and actually PAINTED (>200px),
      the visualiser owning the canvas that is on screen (attached AND resized), no label rendered as its own i18n
      key, the chat sheet stopping ON TOP of the dock with the mic still reachable, and the stopped → ⏻ → painted
      cycle. Self-contained (starts its own preview, needs no `make run`) and non-destructive by design: the
      interesting assertions tap the power switch, which against a live engine would stop the operator's agent.
      Sensitivity verified by reintroducing all three bugs; a fourth mutation that did NOT reproduce anything was
      discarded rather than counted as coverage.
  - **Deliberately out of F1**: `MemoryMap` (the component would import fine; its ~200-line panel CSS is keyed to a
    wide window and re-fitting it is its own work), the 35 KB ConfigPanel (delegated to the desktop with a row that
    says so — a phone is for USING an installation, not setting one up), and the Processes/Crons/Clusters tabs.

## Testing y rueda de mejora (INI-013)

zaelar se prueba **solo, sin micrófono humano**, con un agente tester independiente que HABLA con zaelar y un
JUEZ que evalúa lo que zaelar HACE (no lo que dice). **El PLAYBOOK autocontenido de "cómo se prueba" (trigger "lanza
un test del bot", Paso 0 de alineación, prioridades, evaluación, archivado) vive en
`.meshkore/docs/ops/zaelar-testing.md`**; el catálogo legible de escenarios en `tests/voice/e2e/agent/anexos/catalogo-escenarios.md`
y el histórico de informes por día en `tests/voice/e2e/agent/reports/<YYYYMMDD>-<desc>/`. Docs canónicas:
**«¿funciona todo bien?» → `./.venv/bin/python tests/run_testmap.py`**: el MAPA DE TESTS navegable — todo el testing
ordenado por **DOMINIO → CASO DE USO → CANAL** (9 dominios, nodos `N.M`), responde con el árbol numerado
"1.1 ✅, 1.2 ✅, 2.1 ✅…" y marca aparte los nodos VIVOS (exigen `make run`). Es la fuente de verdad de qué fichero
cubre cada caso; la narrativa/segunda-opinión (cobertura, huecos, duplicación) en `tests/TESTMAP.md`. Se extiende
1000→10000 por hojas (añadir ficheros a un nodo o un nodo nuevo), sin reescribir la espina. Docs canónicas:
`.meshkore/roadmap/initiatives/INI-013-voice-tester.md` (registro de pruebas + oleadas),
`.meshkore/docs/ops/zaelar-observability.md` (cómo depurar por logs), `.meshkore/docs/ops/zaelar-model-benchmarks.md`
(modelos/latencias). Cómo funciona:

> **TRES formas de testing** (el DETALLE completo — cómo lanzar, formatos, evaluación — vive en
> **`.meshkore/docs/ops/zaelar-testing.md`**, no aquí): (1) **MEMORIA** (`tests/memory/e2e/bot/`, taxonomía A–X);
> (2) **VOZ e2e** (INI-013, `tests/voice/e2e/agent/`) — realista, lento, con ruido de STT; (3) **canal de PRUEBA del FlashBrain por
> TEXTO** (V2-032, el más RÁPIDO, headless) — **úsalo siempre que toques cerebro rápido / conversación / prompt /
> memoria-estado / tools**: `make reset` → `make flash-serve` → `make flash T="…"` (ver el playbook para el resto).

Cómo funciona (canal de VOZ e2e, INI-013):

- **El tester** (`tests/voice/e2e/agent/`, `python -m tests.voice.e2e.agent.run`): se une a la MISMA sala LiveKit de zaelar como un **2º
  participante**, **habla por TTS** y **escucha+transcribe con Deepgram STT**. Un cerebro **DRIVE** (DeepSeek vía
  AIMLAPI) conduce el escenario/objetivo turno a turno. Uso: `./.venv/bin/python -m tests.voice.e2e.agent.run --scenario <id>` o
  `--goal "..." --turns N`, `--no-open` para no abrir navegador. **Requiere zaelar ya arrancado** (`make run`). Bucle
  nocturno: `tests/voice/e2e/agent/overnight.sh` + `tests/voice/e2e/agent/guard.sh`.
- **El juez** (`tests/voice/e2e/agent/judge/`, GLM-4.6 vía Z.AI, fallback DeepSeek): se suscribe a `GET /events` (el bus del
  observer) y evalúa el **comportamiento OBSERVABLE**: acciones de frontend (widgets `show`/`close`, navegador), tags
  del cerebro, escalados, latencias reales. Escribe un informe por sesión en `tests/runs/agent/report_*.md` (+ `.json`,
  versionados; los `.wav`/`.log` se ignoran).
- **El prompt de iteración — el loop autónomo** (`/loop 20m <prompt>`, skill `loop`): re-invoca SIEMPRE el mismo
  ciclo: **(1) guarda** (`curl /api/brain`; si no responde, `make run` y esperar) → **(2) prueba** la siguiente
  oleada → **(3) arregla** en código si hay hallazgo → **(4) re-verifica** (reinicia si tocó `.py`) → **(5)
  documenta** una entrada FECHADA nueva al final de INI-013 → **(6) repite**.
- **Cron test→fix (cada 15 min) — el PROCEDIMIENTO ESTÁNDAR** (`tests/voice/e2e/agent/cron_tick.sh`, doc en INI-013 §Cron test→fix
  loop): cada disparo prueba **UN caso de uso COMPLETO** (no saludos triviales) rotando por `tests/voice/e2e/agent/scenarios.py`
  (mensajería · widgets · navegador/moto · conectores · memoria · búsqueda V2-022 · agenda · idea compleja…), el
  JUEZ lo puntúa (`overall>=4` = PASS, `dispatch_dead`/null = INFRA), y el agente **arregla el código si falla**,
  reinicia si tocó `.py`, **re-corre ese mismo escenario** y documenta. `cron_tick.sh` asegura zaelar UP, SALTA si el
  operador está en vivo, rota con cursor y aplica watchdog. Se prueba contra la **cuenta viva del operador**
  (autorizado: admin/pruebas; añadir/quitar datos reales OK, NUNCA crear perfiles ni romper).
- **Oleadas de prueba (A-L)**, en INI-013: A=fiabilidad de escalada, B=directiva de estilo, C=memoria de arranque,
  D=widgets, E/F=WhatsApp/Telegram, G=paste/ficheros, H=multilenguaje, I=latencia, J=regresión, K=widgets nuevos,
  L=cron/proactividad.
- **Evaluación A FONDO de la MEMORIA** (bot dedicado `tests/memory/e2e/bot/`): taxonomía de **24 dimensiones (A–X)**
  anclada a los benchmarks del estado del arte (LongMemEval/LoCoMo/MemBench/MemoryAgentBench/MemConflict/BEAM/STALE/
  Mem2ActBench) — alimenta la memoria incremental por el CAMINO REAL (`_brain_view`, sin LLM en la lectura) + pytest
  de regresión + tester en vivo para lo que es del LLM. **Teoría canónica** en `zaelar-memory.md §Evaluación de la
  memoria`; **mapa/cobertura** en `TAXONOMY.md`; **control de calidad cada 50 casos** en `EXIGENCIA.md`; oleadas
  fechadas en INI-013. Fronteras abiertas (T175/T177/T178/T179/T181/T182/T183) y mejoras aplicadas en `V2-021`.
- **Entrada primaria de memoria para agentes**: ejecutar
  `./.venv/bin/python -m tests run memory --case memory::group::1.4::v4 --no-open`. Son 15 turnos naturales por el
  gateway real CORAZÓN con extracción, descarte, slots/correcciones y recall; el operador los ve en `127.0.0.1:8765`.
  Para aging/TTL/REM usar después `memory::group::1.4::timeline-6m` (966 pasos, 180 días, REM diario). Ninguna de
  estas pruebas toca la memoria real del operador; todo caso tardío reconstruye su prefijo causal en una BD aislada.
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
  **Filtro del visor = las PIEZAS del sistema, con inventario CERRADO (2026-08-09):** las familias son
  **FlashBrain · Brain Workers · Memoria · Widgets · Sistema/Código · Pulso** (fuera «Principal», que era un cajón
  de sastre), y **TODO `kind` emitido pertenece a una** — lo garantiza un test que recorre el código y falla si
  alguien estrena un kind sin clasificarlo (`tests/infrastructure/unit/core/test_observer_categories.py`, nodo
  7.6); antes caían filas que ningún chip gobernaba. Regla: **la familia dice QUÉ pasó, el `span`/`trace` dice
  QUIÉN lo hizo** — la lectura de memoria de un worker es `memory`, no «worker»; para aislar por ACTOR está la
  vista Trazas. **UN SOLO eje de filtro, el `kind`** (panel plegable «Filtros (N)» con el mapa COMPLETO de lo
  filtrable —una fila por familia, su rótulo enciende/apaga la familia entera—, shift+click = solo ese) + cabecera
  FIJA de columnas. **El último evento va ARRIBA (2026-08-10, decisión del operador): la lista crece por PREPEND y
  el scroll es 100% manual** — eso RETIRA el «seguir el fondo» y toda su maquinaria (estado de seguimiento, ventana
  de gesto, rAF, indicador): un estado que puede mentir sobre lo que estás viendo se elimina, no se blinda (falló
  dos veces). Tabla completa en `zaelar-observability.md §El visor`. **Cada evento lleva
  además `corr` (el FLUJO), `sid` (sesión de trabajo) y `uid` (instalación)**, y `bus/log.py` los sube a COLUMNAS
  indexadas de `events` junto a `cat`/`kind`/`ms`/`model`/tokens → la observabilidad se CONSULTA por flujos en
  vez de escanearse. Ver el módulo `observability/` y la iniciativa V2-090.
- **Routing de modelos del tester**: DRIVE + juicio barato = **DeepSeek vía AIMLAPI**; juicio competente = **GLM-4.6
  vía Z.AI**. Claves en `.env` + `.meshkore/credentials/tester.env` (gitignored).
- **Docker SÍ se permite AQUÍ** (aislamiento, LiveKit dedicado del tester) — es la ÚNICA parte del proyecto donde
  Docker es aceptable; el CORE de zaelar NUNCA depende de Docker.
- **Limitaciones CONOCIDAS del arnés**: (a) `--goal` SIEMPRE usa canal VOZ; (b) el Deepgram STT del propio tester a
  veces garbla/mezcla idiomas o "oye" el audio de zaelar → ante señal sucia, mirar `timeline-latest.jsonl`.

## Deploy (producción)

Ver `.meshkore/docs/deploy/zaelar-deploy.md` — instrucciones completas para Fly.io + CloudFlare TURN.
Estado actual: **sin deploy en prod** (destruido por ahorro de costes).

## Frontera PÚBLICO/PRIVADO — este repo es OSS y se lee desde fuera

**`engine/` es el repo PÚBLICO.** Su código y su `.meshkore/` los lee cualquiera que clone zaelar. Por eso:

- **NUNCA se documenta aquí nada de la NUBE ni del NEGOCIO**: control-plane, provisioner, facturación, backoffice,
  tablas de la base central, precios, políticas de las cuentas de pago, decisiones de privacidad del producto
  comercial. Eso vive en el `.meshkore/` de la RAÍZ del workspace (repo privado aparte) — ver `../CLAUDE.md`.
- **El código puede tener costuras que un despliegue use y otro no** (una URL de servicio en una variable de
  entorno, un id de usuario que venga del entorno). Lo que NO puede es NARRAR para qué sirven en un producto de
  pago. La regla práctica: describe el MECANISMO («si `X_URL` está configurada, avisa a ese servicio; sin ella es
  un no-op»), nunca el PRODUCTO («el provisioner inyecta esto en la Machine de cada cliente»).
- Ante la duda, la pregunta es: *¿esto le sirve a alguien que se auto-hospeda?* Si la respuesta es no, no va aquí.

⚠️ **Deuda conocida (2026-08-09):** este `CLAUDE.md` y varios docs de `.meshkore/` arrastran menciones a
`INI-019`/`INI-020`, control-plane, provisioner y backoffice de ANTES de fijar esta regla, y el repo **ya está
publicado**, así que el historial de git las conserva aunque se limpien hoy. Limpiar lo que queda es una tarea
abierta (`V2-091`); a partir de ahora, no añadir más.

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
