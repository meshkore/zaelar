# zaelar

## Working language: English, everywhere inside `engine/`

`engine/` is the PUBLIC repository. Anyone who clones it reads what is written here, so **everything a
developer reads is English** — there is no half of this rule that is optional:

- source-code comments and docstrings;
- **test function names** and test docstrings (`def test_the_repair_says_when_it_could_not`, not `def
  test_una_reparacion_que_no_pudo_lo_DICE`);
- log, warning and exception messages;
- technical documentation under `.meshkore/` — architecture, modules, ops playbooks, `V2-xxx`
  initiatives — and this file;
- **commit messages** of any commit that touches `engine/`.

**This rule beats "write code that reads like the code around it".** Measured 2026-08-29: 777 of the
1139 tracked `.py` files still carry Spanish comments — 16126 blocks, 68% of the repo. That is a
**backlog under translation**, not the house register, and reading it as the local idiom is precisely
how this rule kept losing to it. Do not translate your neighbours either: a separate pass owns that
corpus and editing the same files concurrently only makes conflicts. Write **your** lines in English,
leave the rest alone.

Spanish that is **product data** is untouched by this rule and must stay Spanish: user-facing labels,
voice replies, `i18n/bundles/*.json`, prompt text the operator's agent speaks, and the Spanish
vocabulary inside detectors and regexes. Those answer to the i18n rules (`voice/engine/core/langs.py`,
V2-089), not to this one. Our customers speaking Spanish has nothing to do with what language we
develop in.

The boundary stops at `engine/`: the workspace root `../.meshkore/` is the operator's private business
context and stays in Spanish on purpose.

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

## ⭐ Cómo se orienta CUALQUIER arreglo del agente (norma del operador, 2026-08-20)

El agente debe ser capaz de resolver **cualquier** encargo: reservar un hotel o un restaurante, montar una
investigación sobre la cultura griega del siglo II a.C., sacar los planos o la lista de tareas para construir un
cohete, inventar un libro, buscar un vehículo en Wallapop, o buscar casas en la zona de Los Ángeles usando las
webs que sean populares **allí**, empezando por la más popular. **No hay lista de encargos soportados y no puede
haberla.**

De ahí sale la regla que gobierna todo cambio en el lado del worker, y son DOS MITADES con tratamientos opuestos:

- **RECURSOS (el core) → clavados, completos y probados.** El manejo del navegador, que el worker reciba EN
  TIEMPO REAL todo lo que tiene que recibir, el parseo de los datos, las capturas de pantalla cuando hagan falta,
  los puentes, la evidencia y la entrega. Aquí un fallo es un bug.
- **RAZONAMIENTO (el encargo) → abierto y general.** La lógica, la investigación y la ejecución no se cablean:
  se construye un sistema capaz de **encontrar la fórmula** que llega al resultado que espera el operador. Los
  prompts de los Brain Workers llevan **fórmulas, recursos y maneras de resolver**, nunca un guion.

**Lo prohibido es adaptarse al caso de uso.** Un arreglo que hace pasar ESE escenario y se cae cuando cambian un
dato, una coma o una condición no es un arreglo: es andamio. La prueba, antes de escribir nada: *cambia una
palabra del encargo —hotel→restaurante, Sevilla→Los Ángeles, «4 estrellas»→«menos de 80 €»— ¿sigue en pie?* Y:
*¿sirve para un encargo que nadie ha escrito todavía?* Si la respuesta es no, está apuntando a la mitad
equivocada.

Un conocimiento cableado del mundo (el catálogo de sitios) puede decir **«empieza por aquí»**; nunca **«solo
aquí»**. En cuanto un encargo fuera del catálogo tiene MENOS capacidad que uno de dentro, el catálogo dejó de ser
un atajo y es una valla.

**Duda razonable → es un problema de RECURSOS hasta que se demuestre lo contrario.** Ha sido cierto todas las
veces hasta hoy: el worker muriendo aprendiendo su propio CLI a tientas (V2-219), el compositor que leía la
cadena de proveedores y nunca la escribía —y dejaba a ciegas TODA investigación— (V2-225), lo que el navegador
encontraba sin llegar a nadie (V2-223), y la nota empujada 3/3 contra la línea de prompt 0/13 (V2-222). Ninguno
tenía forma de escenario, y el arreglo con forma de escenario los habría tapado a los cuatro.

Doctrina completa, con el contrato de recursos y el procedimiento al recibir una ronda fallida:
**`.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md`**.

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
| **Red MeshKore — agentes vivos (oráculo) + clusters, y en qué estado está cada pieza** | `.meshkore/docs/architecture/zaelar-meshkore-network.md` |
| **⭐ Doctrina de los Brain Workers — endurecer los RECURSOS, abrir el RAZONAMIENTO (orienta CUALQUIER fix)** | `.meshkore/docs/architecture/zaelar-brain-worker-doctrine.md` |
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
| **⭐ Widget o conector NUEVO — el workflow completo** | `.meshkore/docs/ops/zaelar-new-widget-or-connector-workflow.md` |
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

**Widget o conector NUEVO ("añade un conector de X" / "haz un widget de Y" / "pasa el workflow de widget
nuevo"):** ejecutar `zaelar-new-widget-or-connector-workflow.md` — TODAS las acciones, en orden, para que una
pieza nueva quede construida, cableada, probada, documentada y en el contexto. Es DISTINTO de
`zaelar-widgets-workflow.md`, que gobierna cambios del SISTEMA de widgets; este gobierna piezas nuevas. Trae
las cuatro decisiones previas (¿widget o conector? · ¿hace falta una tool nueva? casi siempre NO, las acciones
declaradas SON las skills · ¿background? · ¿produce?), **la lista de los 8 puntos de cableado que fallan
VACÍOS** (registro, routers, `_BUILTINS`, tarjeta Y familia del ⚙, `api.js`, i18n en+es, exención stdlib,
testmap), el set de tests en sus cuatro clases —incluida la VIVA, que se construye entera aunque no haya
credencial y SALTA con los pasos para habilitarla—, las fronteras que no se cruzan (la voz transporta
intención y nunca una credencial; `widget.js` no toca la red; los widgets no se hablan entre sí) y una tabla
de **diez traps medidos**. Nació del build de V2-557 y su razón de ser es que el siguiente sea corto.

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
- `connectors/` — conectores externos; **`connectors/files/` = archivos en la NUBE** (Google Drive +
  OneDrive, V2-557: registro tipado de proveedores + PKCE compartido + un cliente por proveedor tras la
  **fachada agnóstica** `service.py`, que devuelve UNA forma normalizada — un tercer proveedor no toca el
  widget; doc `zaelar-cloud-files.md`); `connectors/meshkore/` = canal nativo de clusters (3er I/O junto a voz+chat),
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

> **Compaction policy (V2-601 T-18, 2026-09-06).** This log holds recent decisions VERBATIM and a one-line
> citation index for everything older. The full text of every archived entry lives, untouched and in its
> original order, in `.meshkore/docs/decisions-archive.md`; the dense per-decision source is each entry's
> initiative under `.meshkore/roadmap/initiatives/`. When closing work, keep writing full entries here — and
> when the size ratchet (`tests/infrastructure/unit/test_claude_md_ratchet.py`) trips, move the oldest
> full entries to the archive and leave their index line, exactly as this pass did. Never delete a citation:
> the closure trinquete requires every delivered initiative to stay cited in this file.

- **La agenda no inventa, y el aviso por defecto es SUYO (V2-473, 2026-08-29)**: el caso
  `dentist-appointment-into-agenda` (ES PASS 4/5 en 6 rondas de defecto-por-ronda; US 5/5 a la primera)
  dejó estas reglas en `widgets/agenda/data.py` + `nucleo/flash/{router,prompt}.py`. (1) **La escritura no
  inventa**: un `add_meeting` sin title/date/hora es un ERROR que enseña la forma del reintento — los
  defaults fabricaban «Cita, hoy, 17:00» con cara de éxito. (2) **La forma natural no cuesta el hecho**
  (V2-341): la hora pegada en `date` («2026-09-08 15:00») y el alias `time` se leen; el `startTime`
  explícito manda. (3) **El aviso por defecto lo crea la AGENDA al escribir la cita** (~2h antes, prompt
  RESUELTO, `reminder_id`/`remindAt` en la cita, jamás para el pasado) — la ronda 2 midió la alternativa:
  el modelo escaló a un worker que murió en el login de Google con «Hecho» encima. (4) **`set_reminder` es
  vocabulario** (la lección de `clear_all`): mover el aviso es una acción declarada, y las alarmas viajan
  con sus citas al borrar (`cancel_meeting`/`clear_all`) — una alarma huérfana dispara una cita fantasma.
  (5) La lista de «Próximos días» del prompt DECLARA que es un traductor de días nombrados, no el límite
  del calendario (el modelo rechazó una cita válida a 10 días por leerla como tope). (6) La doctrina ya no
  se contradice: la tool decía «el recordatorio es un [[cron.create]] aparte» contra el mecanismo nuevo
  (familia V2-222) — el cron queda para avisos SUELTOS sin cita. (7) El dedup de citas entiende reintentos
  retitulados y títulos contenidos a la misma fecha+hora (los sustantivos de categoría del widget son
  ruido, no identidad). Los errores del widget sobreviven a ser HABLADOS (el modelo los lorea). Tests en
  `tests/browser/unit/agenda/` (+13 esta tanda).

- **La acción que ES el propósito de un widget es la que se salta el censo (V2-547, 2026-09-02)**: el operador
  —«review last session, not working a simple request»—. La observabilidad del 2026-09-01 23:21 lo cierra:
  «Enséñame la foto de un Ferrari F cuarenta» → `🪟 'abrir/mostrar' puro → show · imagenes (descartada show)`,
  dos turnos seguidos, visor abierto y **vacío**, «No sale la foto», y de ahí una escalada a un agente de
  CÓDIGO que se pasó minutos conduciendo un navegador por Wikimedia para traer una foto.
  - **El guarda de V2-545 es correcto; lo que falló es el CENSO.** La pasada que marcó las acciones de
    solo-vista llegó a `imagenes` y marcó `select`, `next`, `previous` y `local` —todas las formas de MOVERSE
    entre fotos ya puestas— y se saltó `show` y `add`, **las dos únicas que PONEN una foto ahí**. El widget cuya
    función entera es enseñar fotos tenía su acción principal descartada por la forma normal de pedir una.
  - **La lección no es sobre `imagenes`**: una marca opt-in es una lista que alguien recorre, y la acción más
    fácil de saltarse es la que ES el propósito del widget, porque no parece ni una lente ni un paso. La primera
    pregunta al marcar un widget no es «cuáles son lentes» sino «cuál contesta la frase para la que existe».
    Está escrito en el contrato de `is_view`, que es donde el próximo lo hará.

- **El catálogo enrutaba con la frase cortada a mitad de palabra (V2-547, 2026-09-02)**: la segunda causa de la
  misma sesión, y la más cara. `widgets/brief.py` recortaba `whenToUse` a 80 caracteres sin mirar dónde caía —
  **los once widgets truncados**, y varios perdiendo justo la cláusula que los desambigua: `clock` su «NO para
  el tiempo meteorológico», `search` su «FRONTERA con `result‹CORTE›»», `mensajeria` su «WhatsApp/Telegram/
  correo» y `contactos` su «o por sus favoritos («mi restaurante favorito en Barcelona»)».
  - Por eso «Enséñame mis restaurantes favoritos» —**la frase que ese manifest nombra literalmente**, con
    `show_view` ya declarada `view` para contestarla— escaló a un agente de código y respondió «Sigo con ello».
  - ⚠️ El corte de `mensajeria` es el mismo widget al que V2-545 dedicó una iniciativa entera: «ábreme el
    Telegram» llegando a un modelo cuyo catálogo **no menciona Telegram**.
  - **Ese texto lo escribimos nosotros PARA enrutar.** Cortarlo a mitad de palabra corta lo único para lo que
    existe el bloque, y el fragmento que queda no pierde un significado: **inventa otro**. Sigue acotado
    (V2-526) — tope generoso, corte en frontera de FRASE, y el número de widgets ya lo acota `selection`, así
    que se acota la prosa POR widget, no el bloque. Medido 586 → 907 tokens por turno.
  - Misma forma de fallo que el aviso de V2-027 que vive diez líneas más abajo en ese fichero: recortar el
    `usage` hizo que un modelo pequeño **escalara en vez de deducir**. Segunda vez de la misma causa.
  - ⚠️ Un segundo test —«todo widget de mirar declara alguna acción de vista»— **pasaba en verde con el defecto
    puesto**, porque a `imagenes` le quedaban `select`/`next`/`previous`. Retirado en vez de dejar un guarda que
    da falsa tranquilidad; la lección se guardó en el contrato, que es donde sí sirve.
  - Nodos **2.1** (fichero existente) y **4.100**. Dos desarmes: 1 y 3 rojos.

- **Un fallo de RECUPERACIÓN es invisible cuando sobrevive un vecino plausible (V2-548, 2026-09-02)**: la causa
  de fondo de lo que el operador reportó como «not working a simple request», y de la que V2-547 solo arregló
  los síntomas. Sus tres turnos de foto de esa noche —dos en castellano y el último, ya en inglés por el chat,
  «show me a ferrari f40 picture» → *«Te lo abro, aunque de momento está vacío»*— llegaron al modelo **sin
  `show_images` en la lista de herramientas**. La única tool que pone una foto en pantalla se había podado.
  - **Las fotos viven en la familia `media`** (`show_images`, V2-457, el tercer hermano de música y vídeo) y las
    pistas léxicas de esa familia tenían solo vocabulario de música y de vídeo: ni «foto», ni «imagen», ni
    «picture». Así que «enséñame» recuperaba `widgets` y nadie recuperaba `media`. Medido: pedir MÚSICA
    conservaba `show_images`; pedir una FOTO no.
  - **La escotilla no podía absorberlo.** `need_capability` funciona cuando el modelo NOTA que le falta algo, y
    aquí le quedaban `show_widget` y `widget_data` sobre la tarjeta `imagenes` — tools que PARECEN hacer el
    trabajo. Las usó, abrió el visor vacío y dijo «Aquí lo tienes». Nadie rompió nada: la familia GANÓ una tool
    y la lista de semillas se quedó atrás sola.
  - **Trinquete de la CLASE**: las palabras del NOMBRE de una tool deben aparecer en las pistas de su familia —
    el mínimo, que la familia sepa nombrar lo que contiene. Añadir una tool sin semilla es rojo en el mismo
    commit. Al escribirlo encontró un segundo agujero: `reply_message` con pistas **solo en castellano**,
    perdida por «reply to the message from Claudia».
  - ⚠️ **El canal `probe` NO recorta herramientas** — no importa `tool_selection` en ningún sitio. Sondeando la
    frase del operador para verificar el arreglo, el probe eligió `show_images` bien: **verde falso sobre el
    defecto que estaba diagnosticando**. Y como la plataforma de casos de uso conduce el probe, **ningún caso de
    uso podía cazar esto**. Espejarlo mueve los números de todos los casos a la vez: queda ABIERTO.
  - Nodo **3.10**, dos desarmes. ⚠️ Uno **no llegó a aplicarse** por comillas anidadas en un `python -c` y sus
    15 verdes no significaban nada: los desarmes van a FICHERO y con la mutación AFIRMADA antes de medir.

- **LA HOJA EN BLANCO: una sola cosa para leer, y el borde que la mantiene pequeña (V2-549, 2026-09-02)**: encargo
  del operador — «un widget que sea como una hoja en blanco, genérico, para enseñar otras cosas: un PDF, un HTML,
  una receta, un informe que hagamos… el cuadrado y lo rellenamos con el contenido», con el código y sus
  herramientas LIGEROS, «sin sobrecargar los prompts con skills, tools ni otras cosas».
  - **La frontera con `results` la dictó él mismo**: aquella hoja contesta «búscame las opciones» (un CONJUNTO
    que se compara, con fichas, fuentes y criterios); ésta contesta «dame la receta» — UNA cosa, ya elegida, que
    se lee. «Pedí una receta y el sistema trajo una lista de recetas, y yo solo pedí una, y me fío de su
    criterio». Un documento suelto en una superficie de comparación se lee como una lista de enlaces (la queja
    que creó el visor de fotos, V2-457); una comparación aquí pierde sus columnas.
  - **Tres tipos y ningún cuarto** (`markdown` por defecto —el texto llano ES markdown sin marcas—, `html`, `pdf`):
    un cuarto tipo es un cuarto renderizador dentro de un widget cuyo valor entero es ser pequeño, y todo lo que
    pudiera pedirse ya está en un sitio mejor — fotos → `imagenes`, una web en vivo → `navegador`, un conjunto a
    comparar → `results`. Nombrar esos bordes cuesta una línea cada uno y evita que esto se convierta en todos.
  - **Tres acciones declaradas y NINGUNA tool nueva** — la conduce el `widget_data` genérico; en el prompt son
    nombres, ~5 tokens. Era una condición del encargo, no un detalle de implementación.
  - **`show` y `append` nacen `view: true`** — la lección de V2-547 aplicada de nacimiento: la acción que ES el
    propósito del widget es justo la que una pasada opt-in se salta, y sin marcar deja «enséñame la receta» en una
    tarjeta vacía.
  - **`prompt_digest` es por lo que esto gana a una captura**: con la hoja abierta, «¿cuánta harina lleva?» es una
    pregunta sobre texto que ya tenemos. Solo se pide con la tarjeta ABIERTA. El PDF es la excepción honesta: le
    damos el fichero al navegador y no lo leemos, así que el digest dice el título y dice que su interior no es
    nuestro para citarlo.
  - **NINGÚN `innerHTML`**: el trabajo entero de este widget es enseñar texto llegado de la web, de un worker o de
    un modelo — justo el que jamás puede ejecutarse. El html se parsea INERTE (DOMParser: no corre ni carga nada) y
    pasa una whitelist; los envoltorios desconocidos pero inocuos se vuelven `div` para no perder su CONTENIDO, y
    los que llevan conducta se tiran enteros. Se le quitan `class` y `style` al entrar, y eso no es una limitación
    sino el punto: venga de la página que venga, aterriza en la tipografía de ESTA hoja y sigue el tema vivo.
  - **Un `show` vacío NUNCA borra una hoja que se está leyendo** (la regla de `imagenes`), y **`append` se niega
    ENTERO en vez de recortar** — un corte silencioso cae a mitad de frase y se lee como un documento que
    simplemente acaba: ni el llamante ni el operador pueden saber que se cortó. Lo cazó un test que afirmaba la
    conducta correcta mientras el código crecía un carácter y reportaba éxito.
  - **El `src` de un PDF es una URL http(s) o el nombre de un fichero que ya tenemos; una RUTA se rechaza aunque
    nombre un fichero real** — un widget lee dentro de su directorio o en ningún sitio. La negativa NOMBRA lo que
    hay (V2-463) y `state.json` queda fuera de esa lista: es el almacén del propio widget.
  - **Medido DESPUÉS del primer commit, y cambió el manifest**: la línea de enrutado se corta a 300 chars y el
    `whenToUse` medía **426**, así que la FRONTERA con `results`/`imagenes`/`navegador` —la mitad que enruta— no
    llegaba al modelo. Cortaba en frontera de FRASE, así que el guarda de V2-547 callaba: no se perdía nada a mitad
    de palabra, solo la parte que decide a dónde va una petición. Reescrito a 295 y clavado por un test que le
    pregunta a `brief._purpose` en vez de copiar el número. **La regla que deja: la línea de enrutado de un widget
    nuevo se escribe para CABER, y eso se comprueba contra el presupuesto real.**
  - Nodo **4.101**, 18 casos, **siete desarmes con la mutación AFIRMADA antes de correr**. Verificado en vivo
    (`3.16+fc8bf83`): en el catálogo, receta real conducida por la ruta de acción y renderizada, las dos negativas
    devueltas literales, e `identify` resolviendo «el documento»/«la receta»/«el pdf»/«el papel» sin robarle «la
    agenda». **Pendiente: el ojo del operador sobre la tarjeta.**

- **Lo que se perdía del chat no era la posición, era estar ABIERTO (V2-550, 2026-09-02)**: el operador —«si
  estaba abierto, no lo deja donde estaba»—. El muro guarda su rectángulo flotante y su lado acoplado
  desde que se hizo movible y acoplable; lo que nunca guardó es estar abierto, porque `store.chatOpen` es una señal que nace `false`. Una
  recarga lo devolvía cerrado y al reabrirlo la geometría se restauraba bien, que es exactamente lo que «no lo
  deja donde estaba» parece desde fuera. **Su reporte era preciso y leerlo literalmente habría hecho perder la
  mañana arreglando una geometría que funcionaba.**
  - Abierto + pestaña viven en `localStorage` **junto a la geometría a la que pertenecen**, no en el layout del
    canvas: es un panel nativo, no una tarjeta, y repartir el estado de una ventana entre dos almacenes es como
    se descuelgan. Se restaura en la CONSTRUCCIÓN (cambiar la señal después enseña el escritorio un fotograma y
    le deja caer un panel encima) y se guarda en cada cambio, **incluidos los del MOTOR** — un aviso proactivo
    que abre el muro por SSE es tanto «donde lo dejó» como un clic suyo. Un wipe de servidor lo alcanza.
  - **Una primera visita sigue encontrándolo CERRADO**, con su propia comprobación: recordar no puede
    significar abrirse por defecto a quien nunca lo abrió. Nodo **4.102**.

- **Media tarjeta no es una tarjeta más pequeña (V2-551, 2026-09-02)**: «se abre un widget de imagen y medio
  widget está en el área visible y medio aparece como si estuviera fuera de la pantalla». `_place` reserva el
  tile por defecto de 400×340 mientras la tarjeta CARGA, y luego el widget pinta doce fotos: nada la volvía a
  meter. Había un re-encaje, pero **solo dentro de `_applyPreferred`**, o sea solo para los widgets que DECLARAN
  tamaño; y el fallback de «no cabe» cascadeaba con `Math.max` en los dos ejes y **sin cota superior**.
  - El encaje deja de ser un momento y pasa a ser una **garantía permanente** (`ResizeObserver`), y una tarjeta
    demasiado grande se **ENCOGE, no se recorta**. Nunca pelea con el operador: solo se toca la que se sale, y
    una maximizada se respeta.
  - **Rejilla de 5px en colocación, arrastre Y redimensión** — cuadricular solo algunas deja bordes que *casi*
    se alinean, que se lee peor que no tener rejilla. **El origen del barrido también se cuadricula**: arrancar
    en el borde del raíl y avanzar de 5 en 5 arrastra el desfase para siempre.
  - **Barrido por COLUMNAS**, y ese orden es la funcionalidad que pidió («pegados unos a otros»): por filas se
    llena de izquierda a derecha y desparrama la sesión por arriba. Sin sitio → **el hueco más grande**, al
    frente: la que puedes ver es la que puedes mover.
  - ⚠️ **Dos guardas míos no medían nada.** El de «una tarjeta que crece sigue entera» pasaba con el arreglo
    quitado, porque el registro falso declaraba tamaño para TODOS los widgets y la tarjeta **nunca llegaba a
    crecer**; ahora una comprobación aparte exige que haya crecido ANTES de preguntar si cabe. Y un
    `_bringFront` que añadí en `_place` no medía nada porque todos sus llamantes ya lo hacen: quitado, en vez de
    dejarlo haciendo parecer que un guarda probaba esa rama. Nodo **4.92**, cuatro desarmes.

- **Un glifo que cambia de significado bajo la mano hay que leerlo antes de usarlo (V2-552, 2026-09-02)**: la
  barra izquierda queda con los **iconos de los widgets abiertos arriba** (con su scroll) y **cuatro controles
  anclados abajo** — un control que se desplaza según se abren tarjetas es un control que hay que buscar.
  - Son cuatro porque él nombró cuatro gestos y la barra los tenía en dos: **⊟ esconder todo** (MINIMIZA, nunca
    cierra: los chips se quedan y cada uno vuelve por su cuenta), **⊞ restaurar todo**, **▦ recolocar**
    cerrando huecos y **manteniendo tamaños** (`compact`, nuevo) y **⤢ meter todo en pantalla** encogiendo en
    celdas (`arrange`, el de antes). Esconder y restaurar son dos botones, no un conmutador; cada uno se
    deshabilita cuando no haría nada, que dice lo mismo sin moverse.
  - **Recolocar y ajustar eran el MISMO botón** y no son el mismo gesto: `arrange` reparte en celdas iguales, o
    sea que redimensiona — y «optimiza los huecos» acababa aplastando una hoja que él había agrandado aposta.
  - **En `compact` los tamaños se asientan ANTES de empaquetar**: si `_fit` encoge una tarjeta después, la
    garantía de V2-551 la devuelve a la esquina y la deja encima de las recién ordenadas. Y se empaqueta **de
    mayor a menor**, porque colocar la grande al final la deja sin sitio y acaba enterrando a las ordenadas.
  - ⚠️ **Escribí una comprobación que pedía un imposible** («tras recolocar nada solapa»): con una tarjeta que
    ocupa 1178×656 de 1280×800 no existe colocación de cuatro sin solape, y el botón por diseño no redimensiona.
    Lo exigible —y lo que se exige— es que queden **enteras y dentro del lienzo**. ⚠️ Y un desarme **mató la
    corrida en vez de ponerla roja** (`null.click()`): la comprobación de que los cuatro controles existen se
    movió ANTES de tocarlos. *Un fallo que revienta el instrumento es peor señal que el mismo fallo contado.*

- **Un número de versión no sabe si el navegador tiene que recargar (V2-553, 2026-09-02)**: el canal de
  actualización publica **DOS** campos porque su encargo tiene dos mitades opuestas — barra cuando llega una
  versión nueva, y **nada** cuando lo único que cambió está en el backend. Un número solo no las distingue:
  sube en TODA release, incluidas las que no tocan un byte de lo que el navegador ejecuta.
  - **`build`** = un entero pelado, la ÚNICA versión que ve un usuario («la 1, la 2, la 25»). `version.VERSION`
    no vale de sustituto: es semántica y no contesta «¿voy más nuevo que tú?» de un vistazo. **`ui_rev`** =
    digest de los bytes de `frontend/**` que un navegador pide. La pregunta de recargar se **mide**.
  - **El número vive en un FICHERO (`update/BUILD`) porque en la nube no hay git**: el `Dockerfile` no copia
    `.git`, así que `version.sha()` es `"nogit"` dentro de cada Machine — lleva siéndolo siempre. Lo único que
    sobrevive a la imagen es un fichero de texto. Y el gate del tag **rechaza una release cuyo número no se
    movió**: olvidar `python -m update bump` deja a todo el mundo en «v24» tras recargar, en silencio.
  - **El digest es de CONTENIDO, jamás de fechas**: un `COPY` de Docker y un `clone` recién hecho se INVENTAN
    los mtimes → anuncio fantasma en cada despliegue, y silencio ante uno real escrito con fecha vieja. Cuesta
    **8,1 ms una vez** (74 ficheros, ~2 MB) y luego 25 µs. Un árbol ilegible devuelve `"unknown"` y el cliente
    se **niega a actuar** sobre él: un digest vacío es un valor estable contra el que todos comparan tan
    tranquilos, y el canal se queda mudo para siempre sin que nadie lo note.
  - **La pestaña sabe lo que ejecuta ELLA por la PRIMERA respuesta**: la sirvió ese mismo proceso segundos
    antes. Así no hace falta inyectar la revisión en `index.html` en tiempo de build, que metería un paso de
    compilación entre él y un fichero que edita a mano. ⚠️ Queda una carrera de ~0 s (reinicio entre servir la
    página y la primera comprobación); por eso la primera se dispara al cargar el módulo, no en el intervalo.
  - **Poll y no SSE, con el motivo**: un proceso nuevo rompe todo SSE abierto, así que «reconectó» ya sería la
    noticia — pero el número tiene que seguir subiendo con el navegador abierto tres días y con la PWA de
    fondo, y eso solo lo sostiene un poll. ~200 bytes contra un dict cacheado; pestaña oculta = **cero**.
  - **`--banner-h` ya existía en `palette.css`** documentada como *«height of the update banner… top controls
    shift down by this»*, con `.tr` y `.me` consumiéndola y su transición puesta: una costura construida para
    esta barra que **nunca había tenido escritor**. Las tarjetas no se mueven porque la colocación ya reserva
    70 px arriba (`tile.top`) > los 36 de la barra: la garantía de V2-551 sigue en pie.
  - **La insignia no vive dentro de `WidgetRail.js`** aunque sea su columna: el raíl se esconde solo con el
    lienzo vacío, y un número que solo se lee habiendo un widget abierto no es un número que se pueda leer.
    Se aparta con el raíl **plegado** por `body:has(#wrail.folded)`, CSS puro y sin referencia al raíl.
  - **Descartar dura UNA versión y no se persiste**: el arreglo de estar desactualizado es recargar, y recargar
    ya lo limpia; un descarte recordado entre recargas esconde una actualización real para siempre.
  - **Dos puntos de contacto y un test que los cuenta**: `server/__init__.py` monta el router y el `Dockerfile`
    embarca el paquete. `git grep` de `import update` en `nucleo/ voice/ memory/ widgets/ connectors/ bus/
    observability/` tiene que salir **vacío** — su restricción («que no ensucie el código del agente») escrita
    como guarda, no como intención.

- **Un `COPY` no significa que el directorio viaje (V2-554, 2026-09-02)**: `.dockerignore` se aplica al
  contexto de build **ANTES** de que corra ningún `COPY`, así que un patrón puede vaciar en silencio un
  directorio que se copia entero — y la imagen construye perfectamente, porque en build no hay nada que
  resolver. Encontrado auditando la release: `config/*.json` estaba tirando `config/models.default.json`, la
  tabla única de modelos (V2-500), que leen al arrancar `config/models.py`, `provider_chain`,
  `workers/providers` y `memory/embeddings`.
  - ⚠️ **Y no reventaba el arranque, que es lo que lo hacía peligroso.** Reproducido: la app se crea,
    `/healthz` contesta 200, y el `FileNotFoundError` cae dentro del `try/except Exception` del bloque
    «Colmena» de `create_app()`, que se traga **CUATRO routers** (probe, reporte CC, plano de workers, puente
    del navegador) tras UNA línea de WARNING. El smoke del pipeline mira BOOT + ADMISSION: las dos habrían
    pasado. **`success` en verde sobre un producto sin brain workers ni navegador.**
  - **La regla que cierra la clase** (no el fichero): *lo que git VERSIONA dentro de una ruta que el
    `Dockerfile` copia tiene que llegar a la imagen*. El estado por instalación que `.dockerignore` existe
    para excluir no está versionado, así que la regla no lo roza. Medido: de todo lo tracked bajo rutas
    copiadas, **exactamente uno** se caía. Guarda en el nodo 7.16, con el orden real de `.dockerignore`
    (gana el ÚLTIMO patrón que casa; `!` re-incluye) y lista de exenciones **vacía**.
  - **El gate de sintaxis del release es ahora la lista de `COPY`**: no compilaba `observability` ni `i18n`,
    ambos importados a nivel de módulo por `server/__init__.py`.
  - **Queda abierto y NO se tocó en la release**: ese `try/except Exception` convierte una mala configuración
    FATAL en un warning. Lo correcto es distinguir «no hay cerebro configurado» de «hay cerebro y no montó»,
    y que el segundo tumbe el arranque para que el smoke lo vea. Cambiar el manejo de excepciones del
    arranque en el mismo commit que se corta una release es justo lo que provoca incidentes.

- **Mover código «byte por byte» cambia sus GLOBALS (V2-555, 2026-09-02)**: el trinquete de arquitectura queda
  CERRADO con cuatro extracciones y ningún techo subido — `reminder_guards.py` (26 guardas que forman un
  conjunto cerrado y que nada de lo que se queda usa), `text_norm.py` (los tres ayudantes que ambas mitades
  necesitan, para que ninguna importe a la otra de vuelta), `probe_scheduling.py` (una rodaja de `run_turn`,
  que era 1136 de 1248 líneas) y `confirm_gate.py` (el único par del proveedor de voz que no necesita NADA
  de él). Techos: 3493→**3470**, 1374/15→**789/7**, 1226→**1163**.
  - **La costura se MIDE, no se elige por tamaño**: en los cuatro casos la pregunta fue «¿qué necesita este
    bloque de lo que se queda, y qué necesita lo que se queda de él?». Y lo movido se comparó por **AST contra
    HEAD**: mismo conjunto de nombres y cada definición `ast.dump`-idéntica. *Nada cambió, se mudó.*
  - ⚠️ **Y aun así rompió dos cosas, las dos por globals.** `safe_reminder_schedule` leía `_sched` como global
    del módulo; al quedarse ese import atrás lanzaba `NameError`, **que su propio `except` fail-soft se tragó**
    devolviendo la entrada tal cual — nueve tests en rojo con valores plausibles, no con un error. Misma forma
    que V2-554 y que el `_re` de v3.16. Y un `monkeypatch.setattr(router_guards, "_longest_pending_min", …)`
    dejó de tener efecto: **un stub va donde la función MIRA, no donde el llamante importa**.
  - **El guarda 7.30 NO caza esto** y conviene saberlo: solo mira nombres usados mientras el módulo se
    IMPORTA. Un global leído dentro de una función lo caza la suite, no él.
  - **Una guarda de cableado se apunta al CANAL, no al fichero**: cuatro guardas de «impl PARALELA — cablear en
    AMBOS» leían el fuente de `probe.py`; el canal son ahora dos módulos y leen los dos. Desarmado para
    comprobar que siguen mordiendo — si no, la siguiente extracción convierte la guarda en falsa alarma y la
    tentación sería debilitarla.
  - **Abierto**: `NucleoLLMStream` (2713 líneas) es la deuda que queda, y partirla es su propia tanda.

- **BUSCAR ANUNCIOS es UNA tool, y el MÓDULO decide si sirve el turno o escala (V2-556, 2026-09-02)**: el
  FlashBrain llama a `search_listings` y nunca elige entre rápido y profundo — `nucleo/flash/listing_turn.py`
  lanza la pasada rápida con presupuesto de segundos, y o entrega filas REALES en la hoja o **se auto-escala**
  a un Brain Worker que **HEREDA esa misma hoja** (`ctx={"sheet": …}`, la costura de relevo de V2-117: el
  operador mira UNA caja desde el primer hallazgo hasta el informe final). La hoja se acuña en la pasada
  rápida, no desde el encargo, precisamente para que la escalada la herede en vez de abrir otra.
  - **Lo que YA se encontró se NOMBRA, no se cuenta.** La cara de escalada decía «hay 4 anuncios
    provisionales» como HECHO al lado de un imperativo que solo ordenaba «di que sigues buscando»: el modelo
    obedeció el imperativo y tiró el hecho — cuatro coches reales en la hoja contestados con «en cuanto tenga
    resultados específicos te los digo». Y el bloque de TAREAS DE FONDO tenía el mismo defecto un nivel más
    abajo: con «YA ENTREGADO (de su hoja): AUDI A3 — 10.990 EUR; AUDI Q5 — 9.590; BMW X3 — 9.980» EN EL PROMPT,
    «¿tienes ya algo?» se contestó «Sigo sin tener anuncios concretos… puede haberse atascado» — negando una
    entrega **e inventando una avería a los 37 s**. La rama anti-negación de V2-222 existía, quince líneas más
    abajo. **La bifurcación va DENTRO del imperativo**, tercera vez que esta familia cuesta una ronda. Un
    atasco solo puede afirmarse si el bloque pone ENCALLADA o SIN AVANZAR con esas letras. Nodos **2.44** y
    **2.45**.
  - **Una página de CATEGORÍA no es un anuncio, y lo dice su propio JSON-LD**: `AggregateOffer`, `offerCount`
    o un `lowPrice` sin `price` es la colección poniéndose precio a sí misma («desde 300 EUR») — se rechaza, y
    `lowPrice` no vale nunca de precio de repuesto. Medido: los 5 primeros de 12 «entregados» eran categorías de
    coches.net y OcasionPlus, y el juez lo llamó inventar. Es V2-510 un nivel más abajo.
  - **Una búsqueda cortada por tiempo NO se cachea** (`deadline_s` → `exhausted: False`): guardarla sirve una
    truncación durante media hora.
  - **El trinquete de arquitectura se puso rojo el día que nació la funcionalidad** —cayó sobre tres ficheros
    que estaban EXACTAMENTE en su techo (3469/3470, 1162/1163, 928/930)— y siguió rojo un día porque corrí las
    suites de mi barrio mientras ese guarda vive en `infrastructure`: **la misma lección ya escrita en ese
    fichero**, pagada otra vez. Extraído, no subido: `router.py` **964→326** (el CATÁLOGO de tools es dato
    puro → `router_catalog.py`), el proveedor de voz **3495→3327** (los lectores deterministas de intención de
    widget → `widget_intent.py`) y `probe.py` **1180→1147**. Y tres copias de la propia forma de V2-556 se
    colapsaron en su módulo: la DEFINICIÓN de la tool (el router solo la coloca), `request_from` y `voice_turn`
    —la secuencia entera pasada rápida→cara→stream, que estaba escrita dos veces y ya había derivado un
    párrafo—. Bench 2.13: **43/45**, sin caída.
  - **Abierto**: los 27 casos restantes de la tanda de 30 están sin correr; se pararon a propósito para no
    tasar un defecto ya diagnosticado. La nube no autentica en sitios, así que los casos son sin credencial a
    propósito (paridad local↔nube), y falta el token de Bright Data del operador para probar el escalón de
    desbloqueo.

- **ARCHIVOS EN LA NUBE: el tramo de permiso es el DISEÑO, y un permiso que no puede listar no es un disco
  vacío (V2-557, 2026-09-02)**: encargo del operador — un conector a sus archivos (Drive/OneDrive) y «un widget
  de navegación lo más parecido posible a los que existen», conducible con el ratón y por voz, **genérico** para
  los conectores que vengan. `connectors/files/` (registro tipado + PKCE compartido + un cliente por proveedor)
  tras la **fachada agnóstica** `service.py`, que devuelve UNA forma normalizada — el widget `archivos` no sabe
  con quién habla, y un tercer proveedor es un módulo cliente y una fila del registro, **cero líneas del
  widget** (hay test de que los dos clientes emiten las mismas claves; sin él la fachada es una ilusión).
  Detalle: `.meshkore/docs/modules/zaelar-cloud-files.md`.
  - **El TRAMO no es una constante y por eso es un campo.** `drive.file` solo ve lo que la app creó o el
    usuario eligió a mano → **no hay árbol que navegar**, y no es ámbito restringido; `drive.readonly` navega y
    **sí** lo es (Google pide CASA para una app PUBLICADA — quien usa su propio cliente OAuth no está
    publicando nada); Graph no pide nada equivalente para OneDrive personal. Elección por instalación, viaja
    pegada al token, y el asistente la enseña **antes** del consentimiento.
  - **La consecuencia es el arreglo de verdad**: el tramo estrecho contesta **200 con lista vacía**,
    indistinguible de «esta carpeta está vacía», así que `service.py` devuelve `ok` + un **`reason`** y la
    tarjeta imprime el motivo. Colapsarlos es cómo se le enseña «tu Drive está vacío» a quien lo tiene lleno —
    y cómo el defecto se diagnostica como conector roto en vez de como permiso estrecho. Misma familia que
    V2-507 (una negativa que no puede decir qué es se diagnostica mal).
  - **NINGUNA tool nueva del FlashBrain**: las **13 acciones declaradas SON las skills**, ejecutadas con
    `widget_data`. Es V2-526 aplicado — una entrada de catálogo cuesta UNA línea de prompt, no una plaza de
    tool en cada turno. Las de navegación llevan `"view": true` o «ábreme el Drive» levantaría la tarjeta sin
    listarla (V2-545), y `search_files` **devuelve** sus coincidencias porque «¿tengo un contrato de Axa?» es
    una pregunta (V2-541).
  - **Las fronteras que sostienen esto, todas con test**: la voz transporta INTENCIÓN y nunca una credencial
    (V2-520 — ningún payload admite un `client_secret`; la app se registra una vez en ⚙); `widget.js` no toca
    la red, así que el consentimiento lo arranca una acción declarada que devuelve la URL; nada de llamadas
    entre widgets — `open_file` devuelve metadatos y `web_url` y decide el CEREBRO; y todo nombre de fichero es
    texto UNTRUSTED (el test RENDERIZA uno llamado `<img src=x onerror=…>` y exige que no naciera ningún
    elemento).
  - **`data.py` importa el conector**, lo que normalmente está prohibido, porque este widget ES un conector y
    no hay equivalente de stdlib para un token que se refresca en el credential store: entra en la lista
    curada `_STDLIB_EXEMPT` junto a `musica`, con el import DIFERIDO para que el catálogo no pague `httpx` en
    cada turno. De paso **`agenda` vuelve a verde**: V2-540 metió su import sin la exención y dejó
    `make test-widgets` en rojo para todo el mundo, lo que hacía indistinguible el fallo del widget siguiente.
  - **Tres errores míos, que son la parte reutilizable** y están en el workflow nuevo: (1) un consumidor
    leyendo un campo que su productor no manda, **tres veces seguidas** — no falla con ruido, la superficie sale
    VACÍA; (2) verifiqué el montaje del router leyendo `app.routes`, que devolvió `[]` **con las rutas
    perfectamente montadas** (esta versión de FastAPI las guarda envueltas) y estuve a un paso de «arreglar»
    algo que funcionaba — las rutas se comprueban con una PETICIÓN; (3) un `git add` en el árbol compartido y
    otra sesión se llevó mis ficheros nuevos en SU commit (`7b24a91`): no se perdió código, ya estaba pusheado,
    **no se reescribe `main`** por una atribución.
  - `/api/cloudfiles/*` y **no** `/api/files/*`, que ya es de `server/memory_routes.py`; comprobado con una
    petición real que las dos siguen vivas. 59 tests deterministas (conector · contrato · **renderizado**) con
    cinco desarmes y la mutación afirmada antes de medir.
  - **ABIERTO**: la ida y vuelta contra una cuenta REAL está construida entera (nodo **5.8**, `live`) y
    **SALTA** hasta que el operador registre su app OAuth y conecte una cuenta — nada del camino HTTP está
    probado contra el proveedor de verdad, y la tarjeta no se ha visto en su motor vivo. Es **solo lectura**:
    escribir en el disco de alguien son acciones irreversibles y quieren su propia decisión.

- **A refusal has to name what you PASTED, and a retry has to move something (V2-559, 2026-09-03)**: the
  operator followed the guide, created the app password at Google, and the card answered «usa una CONTRASEÑA
  DE APLICACIÓN» over a password he had just created. What was stored was **47 characters starting with
  `https://`** — the LINK of the page where he had created it. The product held the evidence (a URL cannot be
  a 16-letter app password) and threw it away to print a generic reason. FOUR faults, each measured before
  touching anything, and none of them fails loudly:
  - **The form accepted any string.** The rule now lives ONCE (`connectors/email/credentials`) and is read by
    the three seams that need the same verdict: the shared connect door (`control.validate_connect`, which the
    HTTP API and the supervisor both go through), `config.password()`, and the message after IMAP says no.
    **Narrow on purpose**: the shape check only fires where the provider publishes a fixed format (Google and
    Apple, 16 letters) and NEVER for Outlook/Yahoo/IMAP, whose formats vary — a false «that is not a password»
    locks someone out of a mailbox that works, which is worse than the generic error it replaces.
  - **The supervisor dropped `{ok:False,error}` on the floor.** `apply_connect` refused and nobody published a
    status, so the widget kept painting «Conectando…» forever: **a refusal the user cannot see is
    indistinguishable from a hang**, and it is the half he can act on.
  - **«Corregir y reintentar» was `_expandConnect.add(pl)` on a set that already had it** — on the error path
    the form is ALREADY expanded below, so the click repainted an identical card. From outside that is a dead
    button, and it was reported as one. It now always moves something and lands the cursor on the field to fix.
  - **The draft was wiped on submit**, so the form under the error banner came back EMPTY and «retry» meant
    retyping the address and sixteen letters. It survives a REFUSAL and is cleared on CONNECTED — a connected
    account has no reason to keep its app password in a form field.
  - **The redesign** (his words: «que sea más de tipo asistente… respeto por los márgenes, crea las cajas, pon
    el paso 1, paso 2, paso 3»): three numbered boxes, the middle one being the step he has to LEAVE for, with
    a real link to the provider's page instead of a sentence buried between two inputs. Same visual language
    for Telegram. Spaces are stripped where the provider PRINTS them (Google shows four groups of four; those
    spaces are presentation and IMAP AUTH does not want them, and `.trim()` only removes the ends).
  - ⚠️ **And the mobile half is mostly a NON-finding, which is the honest answer**: rendered at 375px in six
    states (connect panel with three failures, both wizards, the QR, the chat list, a thread with media),
    **nothing was clipped and nothing left the viewport** — `min(480px,92vw)` was already doing the job. The
    wrap rules drafted for the channel row were DELETED after measuring: they made every row twice as tall for
    a defect that does not exist (the long statuses and the action button never co-occur). What survived is the
    part that IS an improvement on a phone — let the container decide the width instead of reserving 8vw, and
    let a received photo use the whole card instead of a 220px thumbnail taken from the desktop.
  - Nodes **5.9** (24 cases) and **4.106** (14 RENDERED). **Nine disarms, each mutation ASSERTED before
    measuring — and two came back GREEN**: the phone checks passed with the whole media query removed (they
    were a ratchet, not proof of a fix, and now say so), and `config.password()`'s normalization was never
    exercised end-to-end because the fixture mocked it — an install that already saved the password WITH the
    spaces would have kept failing at every reconnect. Both closed.
  - ⚠️ A backtick inside a CSS comment CLOSES the widget's template literal — the trap this very file warns
    about, paid again by writing `width:min(...)` in prose.

- **Two screens, ONE widget (V2-574, 2026-09-04)**: nobody had ever rendered a widget at phone width — 4.18
  checks the shell's contract, 4.19 the dock's pixels, 4.87 the deck's navigation, and the CONTENTS of the cards
  were never looked at. Worse, the house style every widget is built against (`widgets/AGENTS.md`, quoted into
  every generation by `generator.py::_CONTRACT`) was pushing the wrong way: «prefer horizontal / grid layouts»,
  «NEVER a tall single broken column», `width:min(620px,90vw)` — desktop advice written before the phone shell
  existed, so an agent following it built for a desk. Measured across all 14 at 390px with real data: **widths
  were fine** (no overflow, nothing off-screen) and the break was TOUCH — six widgets with 20-34px controls,
  three with inputs at 11.5-13px (**below 16px iOS Safari zooms the page on focus and never recovers**). Fixed
  in THREE layers: the guide + contract now say fluid sizing and that a single column is the right answer on a
  phone; `validator.py` REJECTS a `min-width` over 360px (the one declaration no scroll container can absorb —
  a wide `width` inside `overflow-x:auto` stays legal on purpose); and a HOST touch floor in
  `frontend/mobile/app/styles.css` (44px controls, 16px inputs, scoped to `.zm-scroll` so the desktop is
  untouched and widgets that do not exist yet are covered — checkbox/radio/range excepted, and
  `.zm-scroll.zm-scroll` doubled instead of `!important` so a widget can still out-specify the floor).
  ⚠️ **Two lessons paid**: the floor itself broke `archivos` (six icon buttons at 44px = 414px in a 366px card),
  fixed with a wrap + `max-width:100%` on any box holding controls — after `:has(> button + button)` failed to
  fire (a search box sits between them) and wrapping alone changed nothing (`flex:0 0 auto` means its width IS
  its content). And **an empty widget cannot overflow**: nine of fourteen rendered their empty state, so the
  first green run measured almost nothing — filled fixtures were added and `archivos` failed the moment it had
  content. Node 4.111 prints which widgets were measured thin, so the claim never covers more than it measured.
- **The voice SEES the open directory — a widget the operator is looking at publishes its truth (V2-576,
  2026-09-04)**: session 0a93de06, favourites. Asked «¿cuántos restaurantes favoritos tenemos?» the brain
  answered from stale memory pills («one») while the open contactos card showed FOUR — then, confronted,
  CONFABULATED «la vista actual no lo muestra», and 18 s after a worker fixed the store to five it still said
  «de los cuatro». The model had labels (`ref_index` → items line) but no meaning: nothing said «these ARE all
  the favourites, four in total», and no tool reads the directory. Fixed with `contactos/data.py::
  prompt_digest()` through the EXISTING `refs.prompt_digest` seam (open cards only): authoritative counts, the
  current view filter, every row compact — and the block declares it outranks memory for counting/listing what
  is stored, which is what kills the confabulation branch. Empty says EMPTY. Node 4.96 (+5, incl. end-to-end
  through `brief.for_prompt`), disarm 5 red. **The chain behind it, measured and still partly open**: the
  memory pills asserting widget-owned state (a favourite «in your list», an errand «still pending», a DELETED
  widget's description) are never invalidated by widget events — yesterday that same stale pill made the add
  flow SKIP El Fogón («que ya tenías») right after its real entry was deleted, and today it misled the fix
  worker into trying the deleted widget first. That half is memory-domain work; the four measured pills were
  manually superseded. Also open: the fast lane firing `show_view`+«Hecho.» on complaints/questions (x3), and
  repair whispers hardcoding counts that anchor later turns.
- **A widget event reaches the pills it outdates — the lifecycle chain (V2-577, 2026-09-04)**: closes V2-576
  cause B for the class with a deterministic anchor. Lifecycle pills carry `[widget:<id>]` in their text (only
  `widgets/lifecycle.py` writes them), and each new lifecycle write (created/deleted/restored) now passes the
  widget's PRIOR anchored pills as `supersedes` — V2-565's plumbing applied at the writer chokepoint, so only
  the newest chapter of a widget's story stays valid and recall stops serving a birth announcement next to its
  own tombstone (measured: pill 1165's «was CREATED» sent the fix worker to a DELETED widget first). Targets
  come from the new read-only door `memory.api.widget_trace_ids(wid)` (valid, slotless, `LIKE` with `_`
  escaped — a legal slug char and a LIKE wildcard); the hook lives in `_mem_write(wid=...)`. The superseded
  chain keeps created-at/deleted-at for auditing — history is never deleted, it is just no longer VALID. Pills
  without the anchor (worker notes, distiller prose) are out of reach ON PURPOSE: matching by content invents
  targets; the write-side rule (workers prefix their widget notes; a completion note supersedes its order pill
  via the V2-565 offer) is proposed in the initiative, unbuilt. Node 1.3, three disarms (1/2/4 red). ⚠️ Three
  `_mem_write` test doubles needed the new signature — and the first disarm round restored the UNCOMMITTED fix
  with `git checkout`, wiping it: re-apply the edit, never checkout (V2-531's lesson, paid again).
- **The sleep circuit review — five silent integrity holes in the REM process (V2-578, 2026-09-05)**: full
  review of deep sleep (`rem.py`), light sleep (`consolidator.py`) and their writer/api seams, measured
  against a copy of the live DB first. The healthy half stated (daily cadence holding, 8 valid insights,
  0% heuristic writes); the five holes, none of which failed loudly: (1) a stale `embed_pending` marker on a
  row that already CARRIES a vector was unclearable by construction (repair only selects vector-less rows) —
  `hygiene()` counted it forever; the repair entrance clears them now. (2) **«unforget = flip the flag, no
  reindexing» stopped being true the day `prune_invalid` was built**: a shell pruned >2d ago lost FTS +
  vector + paraphrases, so revival produced a row no search could surface, with `meta.pruned=1` lying —
  unforget re-adds the FTS row itself (recall works at once through the keyword half), drops the stamp, and
  marks `embed_pending` so the nightly repair restores the vector. Only rows the pruner touched: FTS5
  external-content has no upsert, re-inserting a still-indexed row would duplicate its entries. (3) pinned
  invalid shells were never de-indexed (`pinned=0` filter) — pinned protects from DELETION, not de-indexing;
  measured live, a superseded pinned profile shell held its vector 4 days and counting. (4) **the trust
  boundary did not reach any dedup door**: exact dedup (writer + consolidator) and semantic dedup (writer
  neighbor + rem cosine merge) all matched across trust classes — an untrusted verbatim echo could reinforce
  a trusted pill, and worse, a trusted write could fold INTO a quarantined row where synthesis never sees it
  again. Trust class is part of a fact's identity in all four doors now; slots stay `remember_external`'s
  job. (5) `semantic_dedup`'s pair scan was pure Python holding the GIL — measured 24 µs/pair, **~28 s at
  cap 1500** against a comment claiming "ms"; one numpy float32 matmul now (~70 ms, releases the GIL), with a
  tested pure-Python fallback. Six disarms, mutations asserted, backups BEFORE the first mutation — and one
  came back green because the retriever's LIKE rescue channel masked the missing FTS re-index: the sharpened
  test asks the FTS INDEX itself (`MATCH` walks the index; a plain SELECT on external-content FTS5 returns
  the content table's rows regardless, a measurement trap worth remembering). Suite: 646 passed.
- **A voice fullscreen order must change the screen — requestFullscreen is gesture-gated and rejects in
  SILENCE (V2-583, 2026-09-05)**: «Maximiza el video» routed perfectly twice (tool → `fullscreen` tag → SSE →
  `desktop.fullscreen`) and nothing moved. `youtube` declares `fullscreen:"native"`, and the browser gates
  `requestFullscreen()` on transient user activation — a voice order over SSE has none, so the call rejects
  as a Promise AFTER the method returned true: the try/catch never saw it, no error anywhere, and the model
  confabulated on top. Voice-driven native fullscreen never worked since its birth (2026-07-23). Fix in
  `nativeFullscreen`: no activation → in-app `maximize()` (canvas filled, voice reachable, toggle restores);
  no API or rejected promise → same fallback. Native stays for gesture-driven callers; exit needs no gesture.
  ⚠️ **Why no test ever saw it**: Playwright's evaluate runs with CDP `userGesture:true` — the harness GRANTS
  the activation a voice order never has, so the first version of the test passed `requestFullscreen` without
  any gesture. Both refusal signals are simulated explicitly now (node 4.92, +3 checks; disarm 3 red, incl.
  the unhandled rejection finally surfacing as a page error). Mobile Deck immune (its fullscreen just
  navigates). Frontend-only: a page reload picks it up.
- **The video widget gets an ACCOUNT — the video connector family, and the interior anchors to the parent
  (V2-597, 2026-09-05)**: the operator's direction — replicate the MESSAGING pattern in the video widget
  (platform icons in the header, a guided wizard when someone asks to connect, per-platform results never
  mixed) and the HOME fed by his subscriptions under HIS filters. `connectors/video/` is the V2-557 family
  shape (typed registry · PKCE oauth forked from photos · Data API v3 client · fail-safe facade ·
  `/api/video/*`), one provider (YouTube, tier `readonly` ONLY — the write tier is deliberately not declared
  until subscription management ships) but a FAMILY by design: adding a provider touches the registry + one
  client, zero widget lines.
  - **Quota facts that shaped the client**: `subscriptions.list` and `playlistItems.list` cost 1 unit/page;
    a channel's uploads playlist is DERIVED (`UC…` → `UU…`), saving one `channels.list` per channel — a full
    suggestions pull is ~26 of 10,000 free daily units.
  - **The widget follows archivos, not mensajeria, for state**: youtube is PASSIVE, so every `apply_action`
    branch must be declared — which is why credentials go through the ⚙ panel (`video-connect` card) and the
    declared actions carry INTENT only (`open_connectors` the voice door with a timestamped `connect_focus`;
    `connect_account` returns the consent URL, window opened synchronously on the click; `suggest` fills the
    home band). `view_data` stays connector-free: platform rows are CACHED (`platforms_stale` computed from
    age, the `needs_refresh` pattern) and the card asks for one `sync_platforms` when stale.
  - **No background refresh, decided in writing** (V2-034 forces the decision): the operator's standing rule
    is absolute control — the suggestions band fills when ASKED, never on a timer. `block_channel` sweeps
    the band too, and a disconnect empties it.
  - ⚠️ **Trap T3 found LIVED while wiring the ⚙ card**: the `fotos` family (V2-564) had registry rows and
    NOBODY rendered them — no fams entry, no api.js helper, so there was nowhere to paste the Photos
    client_id. Closed in the same seam (generic OAuth card for `fotos` + `video`).
  - **The interior anchors to the parent card** (operator, live, with his screenshot: a maximized card kept
    the widget at a fixed 680px hugging the left edge): `.hb-yt` is `width:100%` + `border-box` — the CARD
    decides in every state — and the default footprint moved to `manifest.size` (680). And `maximize()` now
    resolves a MISSING catalog meta lazily: a card restored on reload and maximized before the catalog fetch
    answered never got its cinema class, so full-bleed silently depended on WHICH road opened the card.
  - Nodes 5.13/5.14 (connector unit + LIVE roundtrip, skips with enable steps) and 4.4/4.53 additions; five
    disarms, mutations asserted, all red; mural 4.92 green after the desktop.js change. **NOT verified live
    against a real Google account** — the LIVE node is built whole and waits for the operator's OAuth client.
    Doc: `.meshkore/docs/modules/zaelar-video-widget-and-account-connector.md`.

- **A fullscreen order is about a SCREEN STATE, never a close — and cinema goes above everything (V2-600,
  2026-09-05)**: the operator asked the video OUT of fullscreen and the widget CLOSED; reopening came back
  «a pantalla completa pero dentro del escritorio». Read from his own observability (session `3050e623`),
  three defects: (1) the STT rendered «cierra la pantalla completa» as «…completamente» — the hard-interrupt's
  fullscreen guard demanded the exact bigram, missed, and «cierra»+«pantalla» fired close-ALL, once per glued
  fragment; (2) the generic close backstop's only fullscreen guard was `fullscreen_widget in _tool_fired`, so
  his complaint ABOUT the close («no que cerraras el widget del vídeo» — close verb + widget name, model called
  nothing) closed `youtube` twice more; (3) the reopen looked «inside the desktop» because a voice order has no
  user activation → V2-583's fallback gives in-app maximize+cinema, while his FIRST attempt rode a recent
  click's activation window into true fullscreen — same order, two looks, a gesture RACE he cannot see.
  - Fixes: `_FULLSCREEN_RE` tolerates «completamente» (a false veto hands the turn to the model; a miss
    destroys the canvas); **`attention.mentions_fullscreen()` is the ONE copy** both close backstops (voice +
    probe mirror) veto on — a turn mentioning fullscreen is never a whole-widget close for a backstop to
    guess; **cinema covers the WHOLE viewport** (`position:fixed`+`!important` over maximize's inline
    geometry, and `.hb-stage:has(.hb-cinema)` lifts the stage — its own z-index is a stacking context, so the
    card alone could never beat the rail/chat); and **`_layout()` persists a maximized card at its `_restore`
    geometry** — the full-canvas footprint was being saved as the card's normal size, so a close-while-maximized
    reopened filling the desk.
  - NOT seeded into the actionmap on purpose: `fullscreen` is a toggle and the map cannot see state; the exit
    phrases name no widget. Nodes 3.x (+ wiring guard, comment-stripped, anchored on the backstop conditional)
    and 4.92 (2 RENDERED checks). Five disarms, mutations asserted, all red. **Not verified live** — needs a
    reload (frontend halves) and an engine restart (guard + vetoes).

- **A stale connector error never greets a fresh open — and the state line OUTRANKS the window (V2-582,
  2026-09-05)**: the operator opened the email connect screen days after a refused attempt and «No se pudo
  conectar. Eso es un ENLACE…» was already on it; in the same session the agent claimed the email was
  connected against `Email: error.` in its OWN prompt, and after the operator connected it live
  (`Email: conectado.` from the next turn on) kept answering «no me ha quedado conectado», anchored on its
  earlier sentences — the window beating the state line, both directions in five minutes (session
  `e32b00f1`, read turn by turn before touching anything).
  - **The banner belongs to the ATTEMPT, the status to the store.** `widgets/mensajeria/widget.js` keeps
    module-lived `_attempted[platform]`: the error card renders only for a failure of THIS page session's
    own connect attempt, and the connector list shows a stale-errored platform as plain «Sin conectar». The
    store keeps `status:"error"` durably on purpose — the brain must keep knowing it is NOT connected.
  - **A refusal ENDS the attempt** — found by RENDERING: `_busy` was only cleared on non-error advances, so
    after a refusal the primary button sat disabled on «Conectando…» forever, with the banner's retry as the
    only way out.
  - **The state line speaks and RULES** (`connectors/messaging/brief.py`): `error` gets words («NO conectado
    — el último intento falló») instead of the raw status the model filled in both directions, and the block
    declares itself this turn's LIVE state that wins over the whole prior conversation, the model's own
    claims named explicitly (V2-221: without the phrase inside, nothing to check itself against).
  - **The worker knows the door** (`nucleo/dispatch_prompts.py`): the escalated worker invented
    `nucleo.gmail_cli`, was denied a «gmail» tool, concluded — falsely — «no hay conector directo» and drove
    the browser to webmail. The generic prompt now says messaging/email is read with
    `widget_cli read mensajeria`, no gmail CLI or tool exists, and webmail-by-browser is the last resort.
  - Design pass on the wizard (operator's ask): «Paso N de 3» into the step header, roomier boxes/inputs/
    buttons, and outside-work steps label their own advance («Ya la tengo — continuar»). Nodes 4.106 (+3
    cases incl. the exact incident and the counterweight: a THIS-session refusal stays visible) and 5.12;
    five disarms, mutations asserted, all red. Open, named in the initiative: the bare «Hecho.» that
    swallowed half a compound order (V2-567 family), and «cuántos SIN LEER» having no exact answer while the
    widget holds triaged items, not a mailbox count.
- **The daemon is the piece that reads somebody's disk, so it gets an attacker with a name (V2-575 P0 security
  pass + P4, 2026-09-06)**: audited, split into `security/` (WHETHER: never-served names · a PURE admission
  decision over headers · a refusal throttle) · `fs/` (WHAT: the one permission circuit · a TOCTOU-safe open ·
  one module per capability, READ ONLY) · `http/` (the plumbing that joins them), with `permissions.py`,
  `files.py` and `server.py` as re-export shims. Threat model and stated limits:
  `.meshkore/docs/security/zaelar-daemon-security.md`; build/install/release:
  `.meshkore/docs/ops/zaelar-daemon-build.md`.
  - **The hole that mattered: the Origin check CANNOT SEE A REBIND.** A page on `evil.example` re-resolved to
    127.0.0.1 makes a SAME-ORIGIN request, which carries no `Origin` header at all — so the guard rested
    entirely on `Sec-Fetch-Site`, one header away from nothing. `Host` betrays it (the browser still names the
    site it THINKS it is on), exact match against the loopback names AND this daemon's port — `startswith` is
    satisfied by `127.0.0.1.evil.example`. Same class the engine already paid for in V2-601 T-14.
  - **A body must be declared JSON**, which closes the browser vector ON ITS OWN: `text/plain`,
    `x-www-form-urlencoded` and `multipart/form-data` are the only shapes a browser sends cross-origin with no
    preflight, so requiring JSON forces a preflight that never succeeds.
  - **Unauthorized attempts are AUDITED** — the old shape answered 401 before recording anything, so the single
    most security-relevant signal there is left no trace in a log whose own docstring says refusals earn the
    file — and COLLAPSED by a throttle, so a flood cannot push the interesting line off the end of a rotated
    one. No lockout: every process here already runs as the user, so a ban is resettable by an attacker and
    permanent for the person who mistyped their own token.
  - **Every guard answers with the SAME 401 and sentence.** Naming which one fired turns «try things until
    something works» into «read the error and adapt». The precise reason goes to the log.
  - Also: a 500 no longer narrates its exception text (absolute paths, internal names) to the caller who most
    wants it; `S_ISREG` + `O_NOFOLLOW` + the descriptor's OWN path re-checked against the boundary (`F_GETPATH`
    / `/proc`, which catches a directory swapped MID-path — **Windows is a stated limit, not a solved
    problem**); the never-served list grew what is actually on a disk (browser cookie stores, `.env.*`,
    `.git/config`, shell history), normalized for case AND Unicode form because macOS stores names decomposed;
    granting `$HOME` or a system folder is refused (a name list is not a boundary — home is the machine minus a
    list); numbers off the wire are clamped instead of `int()`-ed into a 500; concurrency, body size and
    connection lifetime are bounded.
  - ⚠️ **The split cost a boot**: `fs/__init__.py` re-exported the FUNCTION `roots` over the SUBMODULE of the
    same name, so `from ..fs import roots` handed a function to code that wanted the module — no import error,
    a failure on the first attribute access, in whichever file wrote the shorter import. Guarded (7.40).
  - **P4 — two artifacts, no administrator, and no self-updater.** A 50 KB stdlib `zipapp` (always buildable,
    reproducible, zero build deps) beside a PyInstaller onefile; per-user LaunchAgent / scheduled task, so an
    install never needs elevation — **a security property first**: a per-user daemon that needed it could then
    reach every account. **Re-running the installer IS the upgrade path.** No auto-update on purpose: an update
    channel that downloads and executes without a signed artifact is remote code execution by design, and this
    is the worst possible daemon to put one on.
  - **Verified where, because it is not everywhere.** macOS by hand end to end (built → installed into a temp
    HOME → launchd ACCEPTED and ran the agent → it deferred to the already-running instance without
    restart-looping → uninstalled, job gone). **The Windows half was written with no Windows and no PowerShell
    on the machine**; `.github/workflows/daemon-artifacts.yml` is what turns that into a measurement, parse-
    checking the scripts, building the .exe, and asserting a `Host: evil.example` request still gets a 401 —
    the one regression that would ship a daemon which starts and defends nothing.
  - Nodes **7.40** (hostile local process, seven disarms with each mutation ASSERTED before measuring) and
    **7.41** (built, run from the artifact, installers name what the build produces, no elevation).

- **The controls exist; a ROBOT runs them now — the audit remediation tier (V2-601 T-01..T-14, 2026-09-05/06)**:
  the full-system audit's verdict on «this looks vibe-coded» was that the engineering controls were real and
  UNOPERATED — the architecture ratchet sat RED on clean main and nobody saw, because nothing ran it. The
  operator ordered the safe tier executed whole. What changed, one commit per task (`c95d8ee..217ac55`, each
  with tests + verified disarms; full deterministic run 7473 green on the release tree, tagged v3.26/build 11):
  · **CI on every push/PR** (`.github/workflows/ci.yml`): syntax sweep + ruff F/E9 + `tests/infrastructure`
    (every ratchet). Its FIRST three runs caught a non-hermetic daemon e2e (it read the REAL `$HOME`) and then
    caught the very session that created it (dispatch over its ceiling + a duplicate testmap id) — a robot
    sees what a person running «their neighbourhood's suites» does not, which was the audit's whole point.
  · **The red ratchet paid by extraction, never a ceiling**: `surface_ack.py`, `results/sheet_names.py`,
    `probe_actionmap.py`, `providers/flow_lifecycle.py` — AST-identical moves with re-exports; the actionmap
    wiring guards follow the CHANNEL (both files), per V2-555.
  · **ruff F+E9 at the door** (no formatter — N agents share the tree; `tests/use_cases/` excluded whole,
    arnés territory). Its first run found a REAL dead branch in the voice hot path: the V2-090
    «a correction merges into the live task's flow» adopt call used `_trace` with the name never in scope —
    it died as a NameError inside its own `except: pass` on EVERY firing since it shipped. The lint gate is
    that class's regression guard now (the third paid instance after V2-348/V2-555).
  · **A lockfile** (`constraints.txt` from the venv that runs the operator's engine — pinning to it is zero
    behavior change by construction), the livekit-plugins stack pinned, a Python floor at the door.
  · **Security seams closed, each with a reproduced test**: a peer's text can no longer ride the cluster
    SYNTHESIS past the fence (neutralized at the write AND at the read, covering already-poisoned installs);
    the originless same-origin GET from a DNS-rebound page is refused by the Host header (live-verified);
    the widget generator runs from a SCRATCH cwd (the repo-root cwd shipped `engine/CLAUDE.md` AND the
    private parent `CLAUDE.md` to the external provider on EVERY generation) with the dev-worker PreToolUse
    jail reused as a MECHANICAL write-jail — probed first: acceptEdits happily writes an absolute path
    outside the cwd, and path-scoped `Write(<dir>/**)` rules deny even matching paths, so cwd alone was
    never confinement (la capacidad se MIDE, no se lee); the dev worker's jail fails CLOSED (no settings
    file → ZERO tools, never unjailed) and its env is an ALLOWLIST (the process env carries every key
    `.env` loads, and a peer-driven worker reads none of them now).
  · **Correctness**: `create_app`'s broad except is gone — a configured brain whose routers fail to mount
    RAISES where the release smoke can see it (V2-554's own prescription; the old shape booted «green» with
    no probe, no worker plane, no browser bridge); `/api/cron` mounts only under the brain whose loop fires
    the jobs (the V2-121 silent-alarm class); memory ingestion marshals to ONE home loop (its serializing
    `asyncio.Lock` cannot span the engine's two loops — contended cross-loop it poisoned itself and lost
    writes in silence); the client's close-all copy learned V2-600's fullscreen veto (the third handle);
    `make test-widgets` is GREEN 14/14 (the results sheet's identity rides the payload instead of a fetch,
    `results` sits in the curated `_STDLIB_EXEMPT` with its reason written, navegador's phantom golden
    drift seeded away) — while it sat red, a NEW violation in any widget was invisible.
  Still the operator's: the LICENSE (T-03 — the repo declares itself open source with no license file) and
  this very file's compaction policy (T-18). The P2/P3 structural tier stays in V2-601.

- **A catch-all category must not outrank a specific match (V2-599, 2026-09-05)**: `domain_of` asked the
  site catalog first and returned whatever it said. Right for the categories that name a vertical, wrong for
  `local_business`, which is «some business near you» — measured, it swallowed **six of ten** Spanish errands
  (doctor, dentist, physio, hairdresser, vet, gym) into the single key `local`, so the specific patterns
  never got a turn. Two costs: `pedir cita con el médico` keyed `local` while `book a doctor appointment`
  keyed `health`, defeating the exact thing `_EXTRA` is bilingual to prevent — the two halves of one errand
  writing to two rows that never help each other; and six unrelated needs sharing one cache row, where a
  negative learned from the vet silences the doctor for the three days the row lives, answering «no hay
  agente» for verticals it never asked about. Now `_WEAK_FROM_CATALOG` holds the catch-all back as a
  FALLBACK, not an answer: specifics get their turn first, and `local` still serves what nothing else
  matches (a better key than `""`, which writes no row). Ten of ten ES/EN pairs now key identically. **The
  shape:** neither classifier was wrong about what it saw — the ORDER was, and it was written when every
  catalog category happened to be specific. A generic bucket added later inherits a priority nobody meant to
  give it.

- **A broken upstream is not a request for fields (V2-598, 2026-09-05)**: measured live, `aerocast` fails on
  roughly half of the free-text flight errands — it forwards a relative date to Duffel, which answers `422
  validation_error`. That is the agent's bug. Ours was what `serve` did with it: `_HINT_KEYS` held `need` /
  `missing` / `required` (*«give me these fields»*, actionable) in the same tuple as `error` / `detail` /
  `message` / `hint` (*«something broke»*, not actionable), and the branch fired on the tuple as a whole. So
  every upstream failure was reported as *«the agent says what it needs: ask again with `--field key=value`»*
  — advice that cannot work, because the fields were never missing, and that loops the caller instead of
  letting it fall through to the browser. Now `_names_missing_fields` gates that advice; anything else
  returns `agent_failed: True` and says so. A diagnostic is truncated at 300 chars — the measured Duffel body
  was 400+ characters of upstream JSON walking into the worker's context. **What let it live: nothing tested
  `asks` at all.** V2-487 built the actionable half, verified it by hand against an agent that happened to
  answer `missing_fields`, and left the other half unpinned.

- **The workflow table: what serves this kind of errand (V2-594, 2026-09-05)**: operator directive — *«if
  today I look for a restaurant and there is no agent, what cannot happen is that tomorrow I ask the Oracle
  again»*, and *«if the Oracle says zero, we do not need a language model to tell us that»*. Both were real:
  `mesh_agents` remembered only SUCCESS, and only under an intent it would key on, so the two most expensive
  cases were the un-cacheable ones — «nobody does wellness» thrown away every time, and everything the Oracle
  called `general` (events, shopping, wellness). New table `workflows` (`memory/schema.py`, facade in
  `memory/api.py`, runtime in `nucleo/workflows/`): one row per `(domain, channel)` with `status`, `ttl_s`,
  `source`, `evidence`. **It is not a second `action_map`** — that maps a PHRASE to a LOCAL widget action and
  never leaves the machine; this maps a DOMAIN to the ORDER of EXTERNAL channels, and when a phrase is a local
  action the action map wins and this is never consulted. **It is not a third opinion on what «reservar mesa»
  means** either: `domain_of` asks `site_catalog.category_of` FIRST (the shared classifier behind `errand_kind`
  and `router_guards`, whose comment warns that two components deciding the same thing end up disagreeing) and
  only adds the verticals the catalogue cannot name, named after the ORACLE's own intents so both sides share
  the key. **It is never carried in a prompt** — one regex sweep plus one indexed SELECT, zero tokens. Wired
  into `serve`: a known-empty domain answers BEFORE the Oracle is called. **The live run caught the bug the
  unit test could not**: the first version cached only `coverage == "none"`, which the test MOCKED, while a
  real uncovered vertical returns an EMPTY coverage — so the saving never fired where it mattered. Fixing it
  exposed that `find` flattened «answered with nobody» and «did not answer» into one empty list (the same
  fault V2-487 fixed a layer down), so `find` now returns **`reached`** and **an outage is never cached** —
  that would turn one bad minute into three bad days. TTL 7 days positive / 3 negative, shorter because a
  negative is likeliest to stop being true (two agents arrived the same afternoon). Measured live: a plumber
  errand went **1.02 s → 0.0002 s**, no network and no model. Node 2.5 (+3 and a new file, 49 green;
  agent-headless 2667, memory 646). Disarm verified. **F2, same day**: the `browser` channel is now DERIVED from the site catalogue (never copied — a second
  inventory of trusted sites is what drifted apart once), and the worker prompt is data-backed: its last line
  used to hand-write «hoy hay agentes vivos de hoteles, vuelos y entradas/eventos», which went stale the same
  day restaurants and wellness went live — a prompt claiming LESS coverage than exists sends the worker to the
  browser for something an agent solves in two seconds. It now names the proven agent, or says the mesh is
  known empty, and **writes nothing when nothing is known**, which is what keeps it free. `connector` and
  `worker` stay declared and unwritten.
- **A free tier arrives as one entry in a LIST (V2-593, 2026-09-05)**: the operator ruled that every agent
  Zaelar can use must have a free tier, the mesh side complied — and **the three agents it unblocked were
  still invisible here**. `_is_free` read `pricing` as a single dict and did `if not isinstance(pricing,
  dict): continue`, so a **list of tiers** — the natural way to publish «free tier + paid tiers» — was
  skipped entirely and returned False. Measured: `foodlens` republished a plain dict and passed, while
  `lucid` and `ybana` published `amount: 0` as the FIRST entry of a list and both still counted as paid.
  The reader was blind to exactly the thing it was looking for. `_tier_is_free` now judges one entry
  (True / False / «did not say») and `_is_free` accepts a list when ANY tier is unambiguously zero. **This
  is not a loosening**: a list of priced tiers with no free one is still a NO, and an empty or unreadable
  list is still paid — unknown counts as paid, as before. What keeps it safe was never this function:
  **the motor never pays**; a 402 is reported as a fact and never paid or retried, so the worst case of
  calling a tiered agent past its quota is a fallback to the browser, never a charge. Verified live: `lucid`
  and `foodlens` now come back from `find`. Node 2.5 (+4, 31 green; agent-headless 2649). Disarm 2 red.
- **Zero agents beats a wrong one (V2-581, 2026-09-05)**: V2-580's measurements were sent to the mesh side,
  who deployed — and the fixes were **re-measured with the original queries instead of taken on trust**. The
  Oracle now puts `category`/`pricing`/`free`/`domain_match` in each row and `coverage` (`full|partial|none`)
  on the envelope, honours **`strict: true`** server-side, and returns real intents (`transport.train`,
  `events`, `wellness`, `health`…). The killer case is dead: the train errand returns `count: 0`,
  `coverage: none`, and **`aerocast` no longer appears**; `ebay-finder` is discoverable with the query that
  found nothing before; `events` is finally cacheable. Across the 16 verticals, wrong-domain matches went
  **from 5 to 1**. Here: `find` sends `strict: true`, drops a row whose `domain_match` is explicitly `false`
  — belt and braces, and **a MISSING key is not a mismatch**, since reading silence as `false` would empty
  the mesh the day the field is rolled back (there is a fence test for that) — and returns `coverage`, so
  `serve` can say the two emptinesses differently: «todavía no hay ningún agente en la red para esto»
  (genuinely uncovered vertical) versus «no hay ningún agente libre». **The survivor proves the caller's own
  check stays mandatory**: with strict ON, «find a flat to rent in Madrid under 1200 EUR» comes back
  `coverage: full`, `domain_match: true`, agent `ebay-finder` — which answers `ok: true` with nine listings
  topped by a ***«PISO EN ALQUILER» banner sign* for €81**. Ask for a flat, get a for-rent SIGN, and this
  time the row asserts the match, which makes the lie more credible. That is what V2-580's `serves` is for.
  Two other loose matches (`dinner delivery`, `track a parcel` → `ebay-finder`) were left alone on purpose:
  they answer `count: 0` with an honest hint, and a failure that is visible is not worth spending on. Node
  2.5 (+4, 27 green; agent-headless 2645). Also measured and smaller than feared: Spanish errands are not
  systematically classified worse — of six ES/EN pairs only the events one differs.
- **The answer says what the agent claims to be (V2-580, 2026-09-05)**: sweeping the 16 verticals of the
  action-connector backlog against the Oracle, the mesh serves 3 (events, hotels, flights) — but five of the
  gaps do not come back empty, they come back **wrong and confident**. Measured: asked for a TRAIN
  Madrid→Barcelona the Oracle ranked `aerocast` (FLIGHTS) first, and `aerocast` answered `ok: true` with ten
  flight offers (`IB3179`, an aviasales link). Also `rent a car` → `roomrover` (hotels), `parcel shipping` →
  `foodlens` (food *vision*). **The failure arrives GREEN** — not a 404, not an empty list, a 200 with ten
  plausible, well-formed, wrong results — and it does not fail once: `compute` is not in `_UNCACHEABLE`, so
  that single probe LEARNED `compute → aerocast` into the real route store, where it would skip discovery for
  seven days (found because a unit test read the live store and got answered by the real route instead of its
  fixture; the entry was cleaned by hand). The module docstring and the worker's PASO 0 both order the caller
  to check the domain of what came back — but `serve` returned an opaque `agent` id and the payload, and **a
  wrong-domain payload looks exactly like a right one**, so the check was ordered against nothing. `serve` now
  returns `serves` (the agent's declared capabilities) and `describes_itself_as` beside the data: no taxonomy,
  no domain table, no verb list — it just stops discarding a claim the agent already publishes, and judging
  stays the caller's job. Trimmed (12 caps / 240 chars) so a chatty card cannot eat a worker's context;
  absence stays absent (an agent that declares nothing adds no keys — `serves: []` would assert something
  false); and it **never buys a network round-trip**, using the card only when already memoised. The first
  version fetched unconditionally and the autouse network trap reddened two unrelated tests, which is what
  caught it. Node 2.5 (+4, 23 green). The other half is not ours: the Oracle must carry the agent's domain or
  stop ranking a category-mismatched agent first — **zero agents is better than a wrong one**, because zero
  falls back to the browser and a false positive hands the user a lie. Requested from meshkore-master, with
  the two Oracle gaps now 17 days open (no `pricing` in the row; `general` for events/shopping/wellness).
- **A mesh agent can gate its skills behind a bearer of its own issue (V2-579, 2026-09-05)**: the mesh caller
  (`nucleo/mesh_agents.py`) only ever spoke to FREE, anonymous agents — right for `roomrover`/`aerocast`, wrong
  for the coming `zaelar-connectors` service agent, whose skills (Places/Yelp/Ticketmaster/eBay) are gated NOT
  by licence but by COST CONTROL: those providers bill per call, so open-to-the-mesh is an open invoice, and
  meshkore-master issues a per-zaelar-agent bearer it can revoke. `_bearer_for(agent, endpoint)` reads it from
  the credential store under `MESH_BEARER_<AGENT_ID>` (id uppercased, non-alphanumerics collapsed to `_`), the
  endpoint HOST as fallback key; `_post` grows an optional `bearer=` that sets the `Authorization` header only
  when one exists. **The keyword is passed only when the store holds a token**, so every existing caller and
  test double keeps its `(url, body)` shape unchanged — one test hands `ask()` a legacy `_post` with no `bearer`
  parameter as the regression fence. No entry, no header, no behaviour change: a public free agent is called
  exactly as before, and the token never appears in code, a prompt or a log. Node 2.5 (+4), disarm 2 red. This
  is the motor half of INI-030's `zaelar-connectors` contract (the business/cloud half lives in the workspace
  root's private repo); the agent and the provider keys are meshkore-master's to build and hold.
- **The phone is HEARD, and the dock is the operator's (V2-573, 2026-09-04)**: «i couldnt listen to the voice
  in mobile» had TWO independent causes, both silent. (1) **Playback was never unlocked**: every mobile browser
  refuses a remote audio track until the page has had a user gesture, this shell connects at LOAD by design
  (`ensureVoice()` before any tap), and `room.startAudio()` — the SDK's own way out, reported by
  `room.canPlaybackAudio` — was called **nowhere in this repo, on either shell**; the only recovery was a banner
  whose action was a bare `play()` that a suspended context rejects again. (2) **Silence was inherited**:
  `hb_bot_muted` is written by `togglePower()` too, so stopping on the phone and starting later from the
  computer reopened the app live and muted. Now: `unlockAudio()` (gated on `canPlaybackAudio` → `startAudio()`
  → `play()`), an `AudioPlaybackStatusChanged` subscription that also clears the warning when playback is
  RESTORED, `store.audioBlocked` painted as an amber ring **on the orb** (where someone who cannot hear looks,
  and tapping it is the gesture the unlock needs), the unlock on the shell's global `pointerdown` and on the
  power tap, and a mobile boot that never inherits a mute — the desktop keeps its preference on purpose.
  Dock restyled to the operator's layout (`chat · dashboards | ORB 74px with the mic INSIDE | mic · config`),
  captions button AND band removed, deck paging widened to two OR three fingers, card content top-aligned in a
  uniform box. ⚠️ **Two traps paid here**: removing the speaker button while the settings sheet still declared
  that a speaker row would be «clutter» would have left NO way to mute — the row was added and a guard asserts
  the control exists somewhere; and node 4.110 was green with the real `startAudio()` call deleted, because the
  regex matched the COMMENT explaining it — every source read in that test is comment-stripped now. Nodes 4.110
  (new) + 4.18/4.19/4.87 (the composition assertions now derive from the dock instead of hardcoding it).
- **The mouth matches the order (V2-572, 2026-09-03)**: three shapes of the same incoherence, all measured in
  ONE session (20:10-20:52): the action-map fast lane executed «in silence» (by design — the operator asked
  for the opposite: *«he has to say 'ok, done'»*); a close order that reached the model got covered with
  «Déjame ver…»; and two information questions were answered with a bare «Hecho.» until he protested («Te he
  hecho una pregunta», «Respóndeme a la pregunta»). Fixes, node **2.50**: (1) `langs` ships ACTION fillers
  («Voy…») + spoken ACKS («Hecho.», varied, anti-repetition), and `filler_audio.arm(brain, text)` classifies
  the utterance deterministically (`filler_kind`: imperative action verb up front → action pool; «?» vetoes);
  (2) the fast lane speaks the ack AFTER the mutation (never on a decline) — the lane moved whole to
  `providers/fast_lane.py` paying the ratchet (3245→3218), probe reply carries the same ack for parity;
  (3) `answer_guards.a_bare_ack_answers_a_question` (narrow: information question, no action verb, bare ack —
  «¿puedes cerrar…?» + «Hecho.» stays legitimate) triggers `second_pass.bare_ack_repair` in BOTH channels: the
  probe re-composes, the VOICE speaks the missing answer as a follow-up. That voice follow-up deliberately
  diverges from V2-210's «hablar dos veces» doctrine and says why where it lives: «Hecho.» carried zero
  information, so the follow-up is the answer said once, late — the operator's own manual recovery, automated.
  `second_pass.py` also folds probe's triplicated stream-collect shape (recall compose moved there;
  `sanitize` is passed IN by the caller — the dependency-direction ratchet (7.32) caught this module reaching
  for `voice.engine.core.speech` on its second day of life, working exactly as designed).
- **Dependency directions are a ratchet, like sizes (V2-569, 2026-09-03)**: the modularity doc had declared
  since July that `voice/engine/` is not a facade, and §5 row 6 even wrote «new code adds no sites» for
  `langs` — nothing measured it, and the ~10 sites became **30**. A rule each caller has to remember is not a
  rule, so the directions now have teeth: `test_dependency_directions_only_improve.py` (node **7.32**, sibling
  of 7.22) freezes the 42 (file→module) pairs that reach `voice.engine.*` from outside voice/ (shrink-only,
  stale rows are ALSO red so the table cannot loosen silently) and allowlists the exactly ONE private `_x`
  name that crosses a domain boundary in the whole engine. Named debt with the honest exit recorded in
  `zaelar-modularity.md` §7: extract `langs` to a low layer behind a re-export shim (the `text_norm.py`
  precedent), then retire rows. Growth doctrine, operator's directive: the size ratchet enforces the PIECES,
  this one the JOINTS — what two domains both need is extracted DOWN, never imported ACROSS.
- **The stop record declares its own lifespan (V2-568, 2026-09-03)**: `abandon_work`'s «[PARADO]» card
  (short-term, «the next greeting must not resume») was written WITHOUT a ttl, and `consolidator.promote` is
  age-based and never looks at ttl — so a stop order climbed short→mid→long and became permanent memory.
  Measured live: **411 `[RESET]` pills alive in mid** (132 on Aug 28 alone — lab bursts), 55 `[PARADO]` behind
  them, and 2 FALSE ones a test suite wrote to the live desk attributing the operator an order he never gave
  (V2-567 incident). Unique texts (live counters inside) → immune to exact dedup. Fix: `ttl_days=2.0` declared
  at the write — `expire_ttl` kills by `created+ttl` at ANY level, so promotion can climb all it wants, the
  grave wins. Cure, reversible: 442 invalidated, 25 recent stamped with the ttl, zero eternal stop records
  left. Lifecycle test walks promote+expire a week out (disarm = 1 red). ⚠️ The general lesson stays open: any
  ephemeral system write without a ttl becomes biography by promotion — sweep pending.
- **A spoken correction reaches the SLOTLESS pill it corrects (V2-565, 2026-09-03)**: measured on «reserva
  Soria» — STT heard «Elfo On» for «El Fogón», the heart stored two long prefs with the false name, the operator
  corrected himself in the SAME conversation, and nothing could reach the false pills: every supersede path keys
  on `slot`, and additive facts are slotless BY DESIGN (V2-498 — a slot would make one favourite destroy
  another). A worker later paid the bill: 15 min and $2.25 searching a restaurant that does not exist. And the
  distiller alone can never fix this: it sees ONE turn, so it cannot correct what it never sees. Mechanism —
  offer → answer → whitelist → chokepoint: `api.correction_targets()` (recent durable slotless pills, `created`
  not `updated`, 45 min/6 cap) feeds a «GUARDADO HACE POCO» block in `_render`'s DYNAMIC tail (stable prefix
  untouched, V2-536 cache safe; empty memory costs zero tokens); the contract gains `supersedes:[ids]` valid
  ONLY with `change:"correction"` (few-shot 9); ingest intersects the answer with the SAME function — the model
  can only aim at what it was shown; `writer._apply_correction_supersedes` applies it at EVERY `insert_memory`
  exit (dedup collapses included: the SURVIVOR becomes the successor), slotless-and-valid targets only,
  reversibly (`valid=0` + `superseded_by`). None of the deterministic correction regexes matches a re-statement
  («he dicho X») — V1 deliberately relies on the model; the offer is what makes that possible. Two disarms in
  two directions: writer stops applying → 2 red; render stops offering → 1 red; the other 4 cases assert
  absence and stay green on purpose. Node 1.3 + bot dim AD (BATCH_170) — **VERIFIED LIVE 3/3 with the real heart**: it stored the garble as TWO pills, exactly production's shape, and the correction named both (`#435→#437`, `#436→#437`); recall serves the corrected name in 23 ms.
  Operator data cured the same day, reversibly: #1149/#1150 → superseded by #1461, and three «prefs» that were
  fragments of a spoken STOP order («Para todos los procesos…») invalidated.
- **A screen belongs to ONE connector, and a picker is a grid you can already see (V2-561, 2026-09-03)**:
  the operator's follow-up on V2-559's redesign, with the two screenshots still fresh — the wizard's three
  steps were stacked in one scrolling card, the email provider was a `<select>` you had to open to see the
  options, and the connector list and the connect form shared one screen (his own worry: "if we ever have
  20 connectors I'll be four scrolls away from the wizard"). None of it needed new mechanism — `connect_focus`,
  the per-provider guide table and the numbered-box shell all already existed, this rewires how the client
  navigates and paints them.
  - **`_screen = {view:"list"|"wizard", platform}`** replaces the flat `_connectorsOpen`/`_expandConnect`
    pair. The list is now an **icon grid** (`.igrid`/`.ibox`), and clicking ANY box — connected or not —
    enters that connector's OWN screen: a step wizard if it needs one, a status/disconnect card if it's
    already linked. One screen per connector, never two concepts for the same box.
  - **Only ONE step renders at a time**, with a breadcrumb back to the list and a `Paso N de 3` caption —
    the operator's literal ask ("show step 1, and only when he continues does step 2 appear"). The email
    provider step is the icon grid he asked for by name ("put the mail providers in a box with the icon in
    the middle so he sees all of them"); no per-provider brand icons exist, so it's an avatar with the
    provider's initial, same honesty as the header's plain envelope for the email CHANNEL.
  - **`connect_focus` now jumps straight into that connector's screen**, never the list — "connect Gmail"
    lands on the Gmail wizard directly, matching the manifest's updated `open_connectors` description
    ("entra DIRECTAMENTE en la pantalla de ESE conector").
  - **Retry got simpler because the redesign removed the reason it looked broken**: a submit only ever
    happens from the wizard's LAST step, so "Corregir y reintentar" has nothing left to "expand" — it just
    clears busy and refocuses the field, already on the right step by construction.
  - Consolidated the three drifted button classes (`.btn`/`.cbtn`/`.dbtn`) into one `.bt`/`.bt-primary`/
    `.bt-ghost`/`.bt-danger` scale, and deleted the now-dead `.chan`-scoped CSS for the stacked rows rather
    than leaving it unused.
  - Node 4.106 rewritten end to end for the new DOM (23 render cases: grid-not-rows, click-enters-own-screen,
    one-step-visible, provider-grid-not-a-select, header-button-toggles-vs-opens-list depending on state,
    refusal keeps the draft, retry moves focus, phone width for all three wizards). Node 4.89's live harness
    updated to the same assertions. Disarm verified: reverting the `connect_focus` jump makes the new render
    test fail on a real pixel/DOM check, not a source grep.
  - **Phase 2, same pass: the global connector catalog (a 5th `ChatWall` tab, "Conectores"), implementing
    the already-approved `V2-526-the-connector-catalog-costs-nothing-until-it-is-connected.md` design.**
    `connectors/catalog.py` + `connectors/catalog/*.json` (declaration is DATA — a stdlib-only lexical
    index over label/family/capabilities, no model call, no network) split the directory into what is
    LIVE (`connectors/registry.py`, unchanged) and what is merely LISTED (`state:"planned"`/
    `"not-possible"`, new `GET /api/connectors/catalog`). The tab groups both by family, offers "Conectar"
    for a built-disconnected row (hands off to `ConfigPanel`'s own "conectores" tab via a new
    `store.configInitialTab` signal — this surface browses and asks, it never holds a credential form,
    same boundary V2-520 already pins) and "Lo quiero" for a planned row.
    - **Family scoping needed zero code**: `registry.py` already tags every descriptor with `family`, and
      each widget only ever queries its own — the operator's "a video widget should only show video
      connectors" ask was already true by construction.
    - **A real scoped compromise, not silently dropped**: the design asked for a request to carry
      "a structured subject — the manifest id, never prose". The feedback pipeline's schema
      (`server/feedback_api.py` → the `cloud/control-plane` deployment, a **separate repo** outside this
      pass) has no such field, and guessing at extending its wire format blind risked breaking every
      feedback submission for an uncertain payoff. The id travels instead as a fixed, CODE-WRITTEN prefix
      in `message` (`"[conector:<id>] Lo quiero: <label>"`) — never anything the operator typed. Extending
      that schema for a real field is noted as follow-up, not silently forgotten.
    - **Deliberately NOT built**: voice-reachability of the tab (`show_panel` opening "conectores" the way
      it already opens "clusters") — that touches five files in the FlashBrain's tool-routing core
      (`router.py`, `router_catalog.py`, `nucleo.py` AND `probe.py` — the "wire both channels" lesson this
      file has paid for repeatedly — plus `nucleo/actionmap/executor.py`), each with existing tests. A
      self-contained UI feature earned its own pass instead of also touching a sensitive, well-tested
      part of the system in the same commit.
    - Tests: `tests/connectors/unit/catalog/` (13), `tests/infrastructure/unit/core/
      test_connector_catalog_route.py` (3), `tests/browser/unit/widgets/test_connectors_tab.py` (14,
      contract-level like `test_clusters_tab.py` — this repo's established pattern for native ChatWall
      surfaces, no full Playwright mount of the whole app shell). Three disarms verified red. Full sweep
      `tests/browser/ tests/connectors/ tests/infrastructure/unit/core/`: 1752 passed, 1 xfailed.
    - Detail and both phases: `V2-561-messaging-wizard-redesign-and-connector-catalog-plan.md`.

- **A fresh Volume has no directories, and a session born LAZILY told nobody (V2-562, 2026-09-03)**: two
  defects measured on a real account Machine, same class — the code was right and the thing it wrote into did
  not exist, and neither failed loudly.
  - **`workspace.root()` only ever answered WHERE a path lives, never whether it EXISTS.** On a self-host
    clone the answer was free: git ships `config/`, `credentials/` and `i18n/`, so no writer ever needed a
    `mkdir`. A cloud Machine mounts an EMPTY Volume — measured, `/data` held only `memory/` and `widgets/`,
    the two writers that happen to `makedirs`, and the other three were simply ABSENT. Every write into them
    raised inside code that treats persistence as best-effort, so it was caught, logged at WARNING and stepped
    over. **The visible symptom was the language onboarding running again on EVERY cold boot**, because
    `settings.json` could never be written — one WARNING among two hundred INFO lines.
  - `SUBDIRS` is the SINGLE declaration of that tree and `ensure()` runs at boot **before the app import**
    (`server/__init__` loads `settings.json` at import time, so a FastAPI startup hook would be too late for
    the very write this exists for). The three `config/` writers that lacked one create their own parent too:
    a directory can be removed while the process lives. Corrected while measuring — only those three were
    genuinely unguarded; the rest use `os.makedirs`, which a `grep` for `mkdir` had hidden.
  - **The guard is what keeps it closed**: it READS the real call sites out of the source and fails if a
    module resolves a workspace path whose root is not declared. A hand-copied list would keep passing while a
    new persistent path silently reopened the hole — and it asserts the scan MATCHED something, or a pattern
    that stopped matching would guard nothing while staying green.
  - **The other half: `zaelar_user_sessions` held ZERO rows for every account, ever.** A work session has two
    doors — the explicit `begin_session()` and the lazy self-open inside `session_id()`, which is how one is
    usually born (the first event opens it) — and only the first announced itself. So the central registry only
    ever received `event="end"`, and closing a row nothing opened is an UPDATE matching nothing, returning 200.
    The registry that exists precisely to survive a Machine being destroyed was recording nobody. The
    announcement moves into `_announce()` so a session **cannot be born without it**.
  - ⚠️ **And the report was being dropped exactly where it mattered**: `_report_to_control_plane` needs a
    running loop, and a lazily-born session comes from whatever thread emitted the first event — the voice
    thread, a `to_thread` worker — none of which has one. Same cross-thread bridge `energy_meter` already uses
    (V2-102). The heartbeat takes `call_soon_threadsafe` rather than `run_coroutine_threadsafe` so the task
    HANDLE still lands in `_heartbeat` and `_stop_heartbeat` can cancel it.
  - ⚠️ **A test of mine leaked its own workspace and broke an unrelated i18n test several files away.**
    `importlib.reload(config.settings)` was the obvious way to re-resolve an import-time path and is a trap
    twice over: the root `conftest.py` aims `SETTINGS_FILE` at a temp file for the WHOLE session, and a reload
    silently reinstates the REAL repo path — so it both pointed at the operator's own file and left every later
    test reading it. Patch the attribute; never reload a module the suite has isolated.
  - Four disarms verified red, each mutation ASSERTED before measuring. **Verified live on the shipped v3.20
    image**: an empty root goes from `[]` to `config · credentials · i18n · memory · widgets` and
    `settings.json` writes — the exact operation that failed. ⚠️ **A release does NOT reach Machines that
    already exist**: an account created before the tag keeps its old image, so the truest test of this work is
    a NEW signup, the only one that exercises a freshly mounted Volume.

- **The picture was never missing, only OUR COPY of it (V2-563, 2026-09-03)**: the operator asked for motocross
  photos, got twelve thumbnails in the strip and an empty stage saying «esta imagen ya no carga desde su origen».
  Probed his own set: **photo 1 of 12 is a 404 at enduro21.com and its thumbnail is a live 37 KB JPEG** — the
  other eleven originals answer 200. An image index hands over TWO addresses for the SAME photograph (the file at
  the publisher, and the index's own copy), the strip painted the second while the stage only ever asked for the
  first, and item 1 — the one `show` selects — happened to be the dead one.
  - The stage asks for the original, falls back to the same photo from the index, and only then admits defeat.
    **The swap is NAMED** («· vista previa») and **the marker is taken back if the fallback dies too**: claiming a
    preview beside «this no longer loads» is worse than either message alone — a flaw in my own first version,
    caught by the existing both-dead test, not by reading.
  - **Not auto-advance**, deliberately: the index lives on the server and every mutation goes through
    `ctx.action` (this file's own opening rule), so skipping locally would desync the big picture from the
    highlighted thumbnail — the one bug a viewer cannot have — and would race the voice. The fallback shows the
    picture the operator was told about; advancing shows a different one.
  - **`parse_yandex_rows` stops publishing the TILE's dimensions as the photo's**: the DOM reports the
    thumbnail's size and the source line prints it next to the picture as if it described it («480×290» over a
    404; «213×320» over a 2.2 MB PNG). Zero, like the Bing leg. Google's parser reads the real record and is
    untouched.
  - **Upstream context, reported and NOT «fixed»**: the evidence row says `blocked: true · degraded_from:
    "google" · degraded_because: "blocked"` — Google Images captcha'd and the chain degraded to Yandex, which is
    the design working and honestly reported (V2-466). Yandex's `img_url` is a hotlink to somebody else's server;
    that it dies is a fact about the world, not a defect to chase.
  - Nodes 4.83 and 2.1, four disarms verified red with each mutation ASSERTED before measuring. **Verified over
    the REAL network against the failing set**: the stage paints a 480×290 bike, no notice, 12/12 thumbnails
    alive, zero page errors. ⚠️ Sets already stored keep the `w`/`h` they were saved with — the parser fix only
    reaches new searches.

- **Google Photos via the PICKER, and a real gallery has to VIRTUALIZE its grid (V2-564, 2026-09-03)**:
  operator's ask — a Google-Photos-style gallery, mixing whichever photo service is connected, browsable by
  year and searchable by voice ("last year's Morocco trip photos"). Checked before designing anything: the
  premise "Google Photos is the easy one" is false since March 2025 — third-party apps can no longer read a
  user's *existing* library at all (`photoslibrary.readonly` → 403 for everyone); the only surface left is
  the **Picker API** (the user hand-selects items in Google's own UI, per session). Apple Photos has NO
  public third-party API (same CloudKit wall as iCloud Drive) and Amazon Photos has no official API at all
  (only an unofficial, ToS-violating scraper). Decided with the operator: v1 ships **Google Photos only**;
  Apple/Amazon go into the catalog as `not-possible`, same shape as `icloud-drive.json`.
  - `connectors/photos/` follows `connectors/files/`'s shape (providers/oauth/client/service), with one
    structural difference: **`store.py` is the source of truth for browsing, not Google** — once a picker
    session's items are imported, they live in a durable LOCAL index
    (`widgets/store.data_dir("fotos")`, same "reach a widget's storage from inside a connector" pattern
    `connectors/telegram/`/`connectors/email/`/`connectors/whatsapp/` already use) forever, because there is
    no way to re-derive them from Google later. A thumbnail is downloaded and cached AT IMPORT TIME, while
    the session's signed `baseUrl` is still valid (~an hour) — the widget's `<img>` tags point at our own
    `/api/photos/thumb/{id}`, never Google's ephemeral URL.
  - **A separate, PAST-oriented date parser** (`service._parse_date_hint`) — deliberately NOT
    `nucleo/scheduler.py::parse_when`, which is future-only (reminders: "tomorrow", "next Thursday") and
    returns a single point, the wrong shape for "last year" or "in June". ⚠️ Caught while writing its own
    tests, not before: the phrase is matched against an ACCENT-STRIPPED copy of the text ("año"→"ano"), and
    removing the matched string from the ORIGINAL accented text by substitution silently fails — "año" never
    matches "ano". Fixed by capturing match SPANS on the stripped copy and blanking those index ranges
    directly in the original (accent-folding a single Spanish letter is always one-codepoint-in,
    one-codepoint-out, so the indices stay aligned).
  - ⚠️ **Second bug caught by its own test, not by reading**: `store.all_items()`'s sort put undated items
    FIRST instead of last — `sort(key=..., reverse=True)` on a `(has_date, date)` tuple reverses BOTH fields
    at once. Fixed by splitting into two lists (dated sorted descending, undated appended after) instead of
    one clever sort key.
  - **The gallery grid is genuinely virtualized** (`widgets/fotos/widget.js`): a pure layout function
    (`buildRows`) computes year-header and item rows from the sorted list, and only rows within one
    viewport-height of buffer get mounted DOM nodes — scrolling recycles rather than accumulates. This is the
    direct answer to the operator's own worry ("if I scroll through a thousand photos, that shouldn't eat
    memory"), and it is the one claim no source-level test could check: `tests/browser/e2e/widgets/
    test_fotos_render.py` renders a 300-item fixture and measures the mounted `.fts-tile` count stays under
    100, both before and after scrolling to the bottom.
  - Trip labels are OUR OWN concept: the Picker never hands back an album name for a mixed selection, so a
    batch gets labeled by the operator (voice or UI) after import, and `search` matches that label plus
    `taken_at` — never photo CONTENT. Stated in the manifest's `usage` so the FlashBrain never narrates a
    capability ("finds the Morocco photos by what's in them") that does not exist (V2-547's lesson, applied
    in the opposite direction here).
  - Nodes 4.107 (contract + render) and 5.10 (connector: session lifecycle, date parser, store). Full sweep
    `tests/browser/ tests/connectors/` green (1535 passed, 1 xfailed). **Not verified live**: needs a real
    Google Cloud OAuth client with the Photos Picker API enabled and a connected account — nothing here was
    run against the real API.

- **A follow-up is not a new errand, and an alias fragment is not a name (V2-566, 2026-09-03)**: the Soria
  reservation session, read event by event. One errand — book a lunch table — produced two tasks with two
  `results` sheets, and a final exchange where the operator shouted «ciérrame la reserva… hazlo ya» and the
  engine CLOSED THE TIMER WIDGET, cancelling the escalation the model had (correctly, on retry) just produced.
  Each link verified against `events` before touching anything; the memory half (a same-conversation correction
  never invalidated the «Elfo On» long-term pills, so task 1 burned $2.25 chasing a restaurant that does not
  exist) is **V2-565** (memoria-dev).
  - **`runtime.identify()` fuzzy-matched «restaurante» ≈ «restante» (0.842)** — an INNER token of the timer's
    multi-word alias «tiempo restante» — and reached the certainty bar (2.0) on that alone. Voice tolerance now
    only lands on a COMPLETE single-word alias (`watsap`≈`wasap` still resolves); an alias finds the piece, its
    fragments name nothing. With that, `looks_like_close`'s «ciérrame» resolves no widget, the close backstop
    stays quiet, and the escalation survives. Guard: the literal operator sentence in
    `test_resolver_certainty.py`.
  - **`dedup.continues_ended`**: the live dedup was RIGHT to miss (task 1 had ended 3.5 min earlier — nothing
    live), so the relaunch minted a second sheet. The relay's rule («a relay is not a new errand», sheets.py)
    now applies one step out: a new escalation matching a JUST-ENDED errand (same strict containment matcher,
    `_ENDED_SESSIONS`, 5-min window) inherits its sheet — `_sheet_open` already knew not to wipe an inherited
    box. Emits `task/sheet_inherited` with the evidence.
  - **A dropped tool call names WHICH failure it was**: the escalation's «argumentos ilegibles» was actually a
    stream cut by the operator's own barge-in (turn RETAINED, no finish_reason) — a correct discard wearing the
    label of a model defect, which is where the diagnosis went first. Three labels now (token cap / unfinished
    stream / genuinely illegible), and the parse retries `strict=False` before dropping (a complete object with
    a literal newline inside a string — a class DeepSeek emits — is readable; the salvage is recorded).
  - **The es restaurant-booking escape route is real now**: the «ElTenedor (app web)» alt was the SAME company
    and the SAME wall as TheFork (403 twice that session), surviving `alternatives_for`'s host filter precisely
    because the hostname differs. Replaced with the measured route — Google Maps to pick, the restaurant's own
    site's booking engine to book (the CoverManager pages loaded fine while every aggregator walled), commit to
    ONE candidate instead of touring informational pages.
  - Nodes 2.47 (new) + 2.1/2.4/2.5 files; four disarms, each mutation ASSERTED before measuring, all red.
    **Not verified live** — the operator's engine needs a restart to load any of it. Open: no MeshKore agent
    exists for `bookings.restaurants` (confirmed live: `mesh_cli fin` → `agents: []`) — a network gap, not a
    bug; and small-town restaurants largely have no online booking at all, which no catalog entry fixes.

- **One widget order, ONE mutation — and the boring ones never wait for a model (V2-567, 2026-09-03)**: the
  operator's minimal session (19:01-19:03) measured the whole answer to «why can't widgets behave linearly»:
  «Cierra los mensajes» hit the action map in 0.08 ms, while «Cierra los contactos» five seconds later had no
  entry, fell to the model (3.4 s + a trimmed-family retry) and the model answered the CLOSE order with
  `show_widget(mensajeria)` — contactos only closed because the close backstop rescued it. One order, two
  mutations.
  - **Seed packs v3**: open AND close VERB×OBJECT grids for EVERY card (close covered 2 of 14 widgets; that
    asymmetry — five phrasings for mensajería, zero for contactos — was the whole defect class). A coverage
    ratchet walks the widget catalog: a new widget cannot ship without deterministic open/close phrases, in
    both languages. «abre las fotos» retargeted from the `imagenes` viewer to the V2-564 `fotos` gallery,
    which it predates. The favourite-restaurant phrases open the contactos CARD; the view filter stays with
    the model on purpose — the live rows carry `favorite=true` with empty `groups`, so a deterministic group
    filter would answer ZERO (measured before seeding, not after).
  - **`show_contradicts_the_order` (router_guards, both channels)**: a CLOSE order licenses no show — with a
    close verb and no un-negated open verb, the model's `show_widget` is DISCARDED and the close backstop does
    the closing. The probe had carried this exact rule in prose («un canvas:show ESPURIO en un turno de cerrar
    SÍ debe corregirse») while the voice channel executed the spurious show: the V2-539 parallel-channel trap,
    again. A guard now asserts both channels call the shared function.
  - **The fast close declines over live work**: closing navegador cancels its tab and closing results orphans
    the errand delivering into it — richer than «hide a card», so the actionmap executor returns False (whole,
    no emit) and the model gets the turn. Fail-CLOSED when liveness is unreadable: the wrong default is a
    0.08 ms kill of a five-minute errand.
  - The architecture ratchet fired on three files sitting AT their ceilings and was paid by extracting, never
    raising: accumulator notices → `providers/acc_notices.py` (3335→3244), the V2-210 answer-source family →
    `flash/answer_guards.py` (811→762), probe's alias classification → `show_target.py` (1152→1144).
  - Node 2.49; three disarms (coverage grid gutted / voice guard dropped / executor gate removed), each
    mutation ASSERTED before measuring, all red. Deliberately NOT done: widening `search_listings`' mouth to
    restaurants (a places lane is a sibling module, V2-526's budget rule), and the operator's process-tab
    redesign (results tab LAST, browser embedded in the process view) — frontend, recorded in V2-567.

- **A DELIVERED hunt is not re-hunted in parallel — the linear gate (V2-570, 2026-09-03)**: the operator
  watched it live (session 9dcff6f5, the catamarans): the listing fast pass delivered 20 rows into a sheet,
  and seven seconds later — his sentence now complete — the model escalated the SAME hunt to a Brain Worker,
  which opened a SECOND sheet and navigated nautal.com for minutes. His doctrine, now encoded: **a search
  resolves LINEARLY** — the fast delivery IS the answer; deeper machinery runs only when the module judges
  it insufficient or the operator pushes again. Never two parallel processes for one errand.
  - **The dedup could not see it BY CONSTRUCTION**: `dedup_miss` said `live: 0` — a fast pass is not a
    session, and `continues_ended` (V2-566) only saw worker snapshots. Verified in dry-run BEFORE writing
    anything: the existing matcher, unchanged, links that escalation to that delivery (containment 0.6 >
    0.45); it only lacked the snapshot. So a delivery is a recorded FACT now
    (`workers/ended.note_listing_delivery`, TTL `JUST_ENDED_S`) — a SIBLING store, never a row in
    `_ENDED_SESSIONS`: that dict feeds the death-notice machinery, and a synthetic row would announce
    «FALLÓ» about something that never was a session.
  - **The gate lives in `nucleo/errand_continuity.py`** (NEW — dispatch sat ONE line under its ratchet
    ceiling, so the whole V2-566 inheritance block moved out and dispatch SHRANK 1769→1756): a same-hunt
    escalation inherits the delivery's sheet, and the FIRST one is not spawned at all — the fast pass
    re-runs with the escalation's full request as the refined query, INTO the inherited box, and the module
    keeps the verdict (V2-556's principle extended to cover the model's stray escalation): delivered →
    pushed note naming the rows (the route that arrives 3/3, V2-222); insufficient → `run()` escalates by
    itself carrying the same sheet, let through by the consumed refinement mark. One redirect per delivery,
    bounded like a provider retry; cost asymmetry stated: a wrong redirect costs ≤10 s, a wrong spawn costs
    minutes, dollars and the second box. The gate never redirects `web`/`code`/`dev`/`memory` kinds —
    booking or acting on a site goes to the worker (still in the same box); `_classify_kind` already draws
    that line, no new phrase lists.
  - **`listing_turn.run(sheet=…)` reuses an inherited box**: found rows REPLACE the earlier less-specified
    delivery; an empty refined pass NEVER wipes it (`rename_task` only — «estrenar = borrar», V2-259).
  - **The prompt carries the fact WITH the rule** (V2-453): while a delivery is fresh, the live tail says
    «BÚSQUEDA DE ANUNCIOS YA HECHA … llama a search_listings OTRA VEZ con todos los filtros — NUNCA
    escalate_to_slowbrain para la misma caza». The only instruction that used to sit next to the delivered
    rows covered «si te pide el ENLACE» — so the model's escalation was almost reasonable from its seat.
  - **And the fragment that started it**: «…catamaranes en plan» was judged COMPLETE (the connector's last
    word is a noun), so a full turn ran on half his sentence and the fast query lost the size and the zone.
    Trailing colloquial connector BIGRAMS («en plan», «o sea», «es decir») are HARD-incomplete now —
    measured against the registry first (V2-095 protocol): 617 raw transcripts, ZERO complete ones end in
    any of them. Bigrams and never single words: «cancela el plan» is an order.
  - Node 2.5 (`test_a_delivered_hunt_is_not_rehunted_in_parallel.py`, through the real bus→`run_listener`
    path per V2-199) + listing_turn and segmenter cases; six disarms, each mutation ASSERTED, all red.
    **NOT verified live yet** — the engine needs a restart; first check is the catamaran errand giving ONE
    box, and «busca más a fondo» putting the worker into that same box.

- **ONE widget per errand — the browser lives INSIDE the sheet's process tab (V2-571, 2026-09-03)**: the
  operator, with both cards on screen: «no tiene sentido abrir un browser que solo muestra capturas y un widget
  de Result en paralelo — ambas cosas son parte de la misma tarea y el mismo flujo». So the `navegador::tN`
  monitor card is RETIRED for any errand with a sheet, and the sheet's PROCESS tab embeds the browser: capture
  top-left, the search FILTERS (criteria.hard + changes) beside it, the event feed below in REVERSE
  chronological order (newest first — the first line is what happens NOW, nobody scrolls a growing list to its
  bottom), and the browser's own needs — wall, pending question, the «Ya he iniciado sesión» button.
  - **`sheet_browser` is the third sibling of `sheet_progress`/`sheet_harvest`**, same division: the task
    registry owns the facts, the sheet READS them per render. `data["browser"]` is derived and never persisted
    (`{}` once the errand ends — a frozen capture pretending to be a live browser lies; the tab keeps only its
    persisted history). The tab is found under BOTH names an errand can give it (`rec.nav_task`, else its own
    `task_id` — the same two-name rule `sheet_for_nav_task` already applies), and with several live tabs the
    most recently MOVING one wins.
  - **The refresh had to travel or the embed was stillborn**: `tasks._notify` now also emits `widget/data`
    for the sheet's card when the task carries a sheet stamp — captures change far more often than phases, and
    the sheet only repaints on ITS id. `_announce_wall` raises the SHEET (the capture is the evidence and now
    lives there); a task with NO sheet keeps its monitor card and its wall show — there it is the only surface.
  - **The login handoff forwards, never writes**: `results.apply_action("auth_done")` enqueues into the
    navegador owner's mailbox (`widgets/supervisor.enqueue`) — the owner stays the only writer of its state.
    Without a `task_id` it resolves the live browser of ITS OWN sheet only (guessing another sheet's would
    confirm a stranger's login); a dead owner is a spoken refusal, and the button SHOWS a refusal (V2-540).
    The pending question stays voice-answered (`answer_from_turn`, V2-202) — only login gets a button, because
    its gesture happens outside, in the real Chrome window.
  - **A REUSED tab is re-stamped** (`tasks.set_sheet`, called from `_prepare_web`'s continuation branch): the
    sheet stamp is written once at the tab's birth, and a tab serving a NEW errand with the old stamp routes
    findings and refreshes to the predecessor's box — the V2-434 «sello rancio», now closed on the writer's
    side for this path. A stamp is never blanked.
  - ⚠️ **A disarm came back GREEN because the mutation hit the WRONG function**: muting `sheet_browser` via a
    source prefix shared with `sheet_harvest` disarmed harvest instead (`str.replace(…,1)` took the first
    occurrence) — a disarm's mutation anchors on something UNIQUE to the function it claims to disarm. The
    presentation ratchet also collected: a raw `padding:8px` in the new login button went to the scale.
  - Nodes **4.109** (17 cases through the REAL paths — `_prepare_web` actually run, `_notify` fired by a
    registry write; five disarms red) and **4.29** rewritten (14 RENDERED checks: newest-first order, the
    capture painted at real size with the asset route-intercepted, filters measured to the RIGHT by geometry,
    the login click firing `auth_done` with the task id). **NOT verified live** — the engine was not restarted;
    first check is a real web errand showing ONE card with its capture moving inside the process tab.
  - Pre-existing and left alone: `widgets.harness` was already red for two unrelated things (results'
    `fetch(` from the V2-538 identity strip; navegador's golden expecting an `updated` key nobody emits).
  - ⚠️ **Found by this pass's full sweep and fixed, unrelated to the redesign**: `Settings.language` FREEZES
    `env("ZAELAR_LANGUAGE")` at the first import of `voice.engine.core.config`, and the V2-539 actionmap tests
    reached that first import lazily from inside a test that had monkeypatched the env to «es» — the reverted
    patch left `langs.current_code()` answering «es» for the rest of the process, and the suite-isolation
    guards went red in whatever file ran later. New face of the V2-562 lesson (there, a reload reinstated the
    real path; here, a lazy first import froze a patched env): **a module the suite isolates must be imported
    BEFORE any env monkeypatch that its defaults read** — the actionmap test file now imports it at collection
    time, with the suite's clean env. And a SECOND door, same symptom (V2-562's own `test_workspace_tree`):
    `settings.update()` writes `os.environ["ZAELAR_LANGUAGE"]` ITSELF, a mutation monkeypatch never saw and
    nothing reverted — the key is registered in monkeypatch's ledger FIRST now, so teardown restores the
    pre-test state whatever the code under test writes into it. Full sweep after both: 4423 passed, 0 failed.

- **The engine is licensed: Sustainable Use License 1.0, fair-code (V2-601 T-03, 2026-09-06)**: operator
  decision, checked against the competition per-artefact — Hermes Agent and OpenClaw both ship MIT, which
  grants everyone the right to sell and sublicense, the opposite of the intent (use it and modify it for
  yourself; don't commercialize it; commercial exploitation stays with Zaelar). `LICENSE.md` carries the SUL
  1.0 verbatim (the n8n fair-code license) with the third-party carve-out named; the vendored WhatsApp bridge
  finally has its upstream MIT text in `connectors/whatsapp/bridge/LICENSE` (Copyright 2025 Nous Research) —
  the frame INI-027 §9 asked for, provenance untouched. This is source-available, NOT OSI open source: every
  "open source" claim in README and on zaelar.com was corrected the same day (live-verified). Never
  reintroduce "open source" or "MIT" wording for this repo.
- **This file compacts by ARCHIVING, never by deleting (V2-601 T-18, 2026-09-06)**: at 869KB/~210k tokens no
  agent could load the whole log, so every reader got a nondeterministic slice. Now recent decisions stay
  verbatim, everything older moved — byte-for-byte, order preserved — to
  `.meshkore/docs/decisions-archive.md`, leaving a one-line citation per entry in the index below (the
  closure trinquete requires every delivered initiative to stay CITED here; verified: zero citations lost,
  all 363 entries verbatim in one of the two files). The size ratchet
  (`tests/infrastructure/unit/test_claude_md_ratchet.py`, ceiling 400KB) trips when the log regrows; the
  procedure to pay it is written in the policy note at the top of this section.

### Archived decisions — index (full text: `.meshkore/docs/decisions-archive.md`)

- **El worker escribe lo natural y el CLI le cobraba el turno — tres formas más (V2-341, 2026-08-26)** (2026-08-26; V2-123, V2-248, V2-253, V2-306, V2-341)
- **Las dos puertas del motor le decían cosas opuestas al mismo worker (V2-350, 2026-08-26)** (2026-08-26; V2-350)
- **Un contratiempo también se cuenta: solo las buenas noticias llevaban un «cuéntalo» (V2-348, 2026-08-26)** (2026-08-26; V2-131, V2-133, V2-222, V2-276, V2-348)
- **Un nombre que comparten todas las filas no nombra a ninguna (V2-346, 2026-08-26)** (2026-08-26; V2-334, V2-345, V2-346, V2-347)
- **Una ruta que comparten decenas de anclas no es la ficha de nada (V2-334, 2026-08-26)** (2026-08-26; V2-320, V2-334)
- **Sin filas no se puede pedir que las cuente (V2-330, 2026-08-25)** (2026-08-25; V2-298, V2-330)
- **El informe dice qué nombró ZAELAR él mismo (V2-329, 2026-08-25)** (2026-08-25; V2-329)
- **Un SUPERÍNDICE no es parte del número (V2-326, 2026-08-25)** (2026-08-25; V2-326)
- **Pedir ayuda no es equivocarse (V2-325, 2026-08-25)** (2026-08-25; V2-325)
- **Cuando dos anclas apuntan al mismo anuncio, gana la que lo NOMBRA (V2-324, 2026-08-25)** (2026-08-25; V2-234, V2-324)
- **«Cero filas» no es «sin resultados» (V2-323, 2026-08-25)** (2026-08-25; V2-294, V2-323)
- **Verificar el ARREGLO no es verificar el CASO (V2-322, 2026-08-25)** (2026-08-25; V2-321, V2-322)
- **Una FECHA no es un teléfono, y la diferencia costaba la hoja entera (V2-321, 2026-08-25)** (2026-08-25; V2-321)
- **Las tools, de menos a más (2026-08-02, norma del operador)** (2026-08-02; no refs)
- **El FlashBrain se queda en DeepSeek V4 Flash — y la latencia NO es del prompt (2026-08-02)** (2026-08-02; no refs)
- **Dominios públicos → motor local (CERRADO 2026-07-22)** (2026-07-22; no refs)
- **Motor de voz = LiveKit Agents** (2026-07-29; INI-012)
- **Cerebro propio «Colmena» — FlashBrain ORQUESTADOR + workers Claude Code** (2026-07-13; V2-036)
- **Workers Claude Code = memoria serial + reporte por el bus + pool** (2026-07-16; V2-036)
- **Brain Workers INTERACTIVOS — sesiones vivas, bidireccionales y AGNÓSTICAS del motor** (2026-07-14; V2-029, V2-038, V2-063, V2-084)
- **UN BRAIN WORKER HACE CASI DE TODO — la seguridad es un FILTRO, no una lista corta de permisos** (2026-08-21; V2-117, V2-236)
- **Gate de ATENCIÓN — el micro abierto no actúa sobre voz ambiente** (2026-07-09; V2-015)
- **Latencia del turno — la memoria FUERA del camino caliente** (sin fecha; V2-011)
- **Circuito de CORTO PLAZO de interacción con el operador** (2026-07-14; V2-035)
- **El canvas es AUTORITATIVO — reconciliar al (re)conectar** (2026-07-14; V2-035)
- **ESTADO = contexto VARIABLE con UI vivo — el cerebro sabe lo que el operador tiene DELANTE** (sin fecha; V2-011)
- **RAILS — comportamientos comunes CONDUCIDOS** (sin fecha; V2-042, V2-047)
- **- **«Sistema arena» — rails/widgets/tools auto-generados, BRAIN RULES + USER RULES, genética (V2-046, DISEÑO** (2026-07-16; V2-042, V2-045, V2-046)
- **- **Bóveda de secretos del operador — cifrado E2E + passkeys (V2-060, CONSTRUIDO 2026-07-21, rama** (2026-07-21; V2-046, V2-060)
- **«Susurro» — auto-auditoría conversacional y mejora continua** (2026-08-09; V2-053, V2-061)
- **Acciones ENCADENADAS realidad↔widgets↔memoria + inteligencia asertiva de DOS velocidades** (2026-07-21; V2-061)
- **Búsqueda web = capacidad COMPARTIDA por los dos cerebros, model-agnóstica** (sin fecha; V2-011, V2-022, V2-024)
- **Prewarm del camino caliente en el ARRANQUE** (sin fecha; V2-024)
- **Prompt del FlashBrain = ESTADO compuesto + petición, ~30 líneas (no ~280)** (2026-07-11; V2-011, V2-027, V2-028, V2-029)
- **ORDEN DE PROVEEDORES — DeepSeek V4 DIRECTO primero, luego el broker, y solo al final OpenAI/Anthropic** (2026-08-19; no refs)
- **Cerebro de voz = NO-razonador** (sin fecha; no refs)
- **- **ORDEN DE PROVEEDOR — DeepSeek V4 DIRECTO primero, broker después, OpenAI/Anthropic el último (NORMA del** (2026-08-19; V2-097)
- **Routing de modelos — POR INVOCACIÓN** (2026-08-19; V2-034, V2-077, V2-097)
- **Memoria central** (2026-08-16; V2-013, V2-056)
- **Recuperación del recall LARGO = RERANKER model-agnostic, LOCAL por defecto** (2026-07-12; V2-030, V2-031)
- **Sistema Nervioso** (sin fecha; no refs)
- **Perfiles remote/local** (sin fecha; no refs)
- **Multidioma con catálogo alineado** (sin fecha; no refs)
- **UI multilingüe que se adapta a CUALQUIER idioma** (2026-08-09; V2-089)
- **La autodetección de idioma colgaba SOLO de la voz — un canal de texto se quedaba en inglés para siempre** (2026-08-20; V2-101, V2-170)
- **TTS local por hardware (Metal)** (sin fecha; no refs)
- **TTS cloud FIABLE — ElevenLabs** (2026-07-13; V2-035)
- **STT local por hardware** (2026-07-12; no refs)
- **Sistema de widgets** (sin fecha; V2-017, V2-025)
- **Nombres + alias de widgets con CERTEZA de enrutamiento** (2026-08-01; V2-082)
- **CHAT y VOZ, INDEPENDIENTES — el icono es el único dueño del silencio** (2026-08-02; V2-054, V2-088)
- **El icono del altavoz MANDA — un solo interruptor para la voz** (2026-08-01; V2-087)
- **La RED es NATIVA, y hay clusters PÚBLICOS** (2026-08-01; V2-082, V2-086)
- **Selección PROGRESIVA de capacidades — el prompt es O(K), no O(N)** (2026-08-02; V2-035, V2-078, V2-082, V2-085)
- **Acciones de widget = FRONTERA datos/código + gate de irreversibilidad (NO de escalado)** (2026-07-11; V2-025)
- **Data-ops por FUNCTION-CALLING + resolución de referencias a items** (2026-07-11; V2-025, V2-026)
- **Widgets en BACKGROUND — ejecución OFF-SCREEN con ciclo declarado** (2026-07-12; V2-034)
- **Ciclo de vida de widgets + memoria — CREAR/MODIFICAR = SlowBrain; BORRAR = FlashBrain con confirmación** (2026-07-09; V2-017)
- **Widgets "backed" + supervisor** (sin fecha; INI-016)
- **navegador — navegador web REAL + agente de tareas web** (sin fecha; INI-016)
- **navegador — TAREAS: una tarea = una tarjeta = una pestaña** (sin fecha; INI-016)
- **El navegador es el ÚLTIMO recurso: primero se le pregunta a la RED** (2026-08-19; V2-167, V2-169)
- **Un código de idioma inventado no falla: es un idioma** (2026-08-21; V2-171, V2-248, V2-249, V2-251)
- **Un informe de lo que ya pasó no es una orden** (2026-08-21; V2-039, V2-047, V2-259, V2-261)
- **Dos búsquedas son dos hojas, y estrenar deja de significar borrar** (2026-08-21; V2-242, V2-257, V2-259)
- **El navegador MUESTRA y la hoja GUARDA** (2026-08-21; V2-192, V2-200, V2-223, V2-240, V2-257)
- **Un formulario que calla no se distingue de uno que funciona** (2026-08-21; V2-124, V2-256)
- **Para vigilar el ARTEFACTO, el artefacto tiene que contener lo que se comprueba** (2026-08-21; V2-171, V2-195, V2-253, V2-254, V2-255)
- **La regla estaba escrita en TRES sitios y aplicada en UNO** (2026-08-21; V2-242, V2-252, V2-253, V2-254)
- **Unos argumentos ILEGIBLES no son una acción sin argumentos** (2026-08-21; V2-171, V2-253)
- **El canal de TEXTO no relevaba — y era la TERCERA vez que `probe.py` se separaba del provider de voz** (2026-08-21; V2-252)
- **Un solo reloj para el «hoy» que se le DICE al worker** (2026-08-21; V2-250)
- **La píldora que se auto-avala: un aviso PROGRAMADO existe de verdad, o no se dice** (2026-08-21; V2-219, V2-249)
- **Un `ref` caducado decía QUÉ pasaba y no CÓMO salir** (2026-08-21; V2-203, V2-212, V2-236, V2-241, V2-247, V2-248)
- **Traer el elemento a la vista es una CORTESÍA, no el clic** (2026-08-21; V2-236, V2-247)
- **Un escalón que se atasca SIEMPRE no se penalizaba nunca** (2026-08-21; V2-244, V2-246)
- **Callar un escalón es legítimo; callar QUE LO CALLAS, no** (2026-08-21; V2-244)
- **246 tests verdes que ninguna suite ejecutaba, y TRES formas de desaparecer** (2026-08-21; V2-098, V2-243, V2-245)
- **Un SALDO agotado no es una cuota, y quedarse sin proveedor no es un tropiezo** (2026-08-21; V2-098, V2-158, V2-243)
- **Una píldora de fondo no es un hecho sobre la persona** (2026-08-21; V2-242)
- **La puerta avisaba UNA vez y el worker chocó TRES** (2026-08-21; V2-211, V2-236, V2-241)
- **El extractor exigía PRECIO, así que un fontanero devolvía CERO filas** (2026-08-21; V2-236, V2-240)
- **Un RELEVO no es una muerte** (2026-08-21; V2-198, V2-222, V2-237, V2-238, V2-239)
- **Un `native_sid` que MATÓ a un worker no se vuelve a armar** (2026-08-21; V2-237, V2-239)
- **La búsqueda dio la respuesta perfecta y MURIÓ dentro del worker** (2026-08-21; V2-199, V2-223, V2-226, V2-236)
- **El extractor PARTÍA el precio y no cogía el nombre** (2026-08-21; V2-234, V2-235)
- **La nota llevaba delante el CROMO DE NAVEGACIÓN, y el turno describió eso** (2026-08-20; V2-223, V2-234)
- **UN ENCARGO, UNA SUPERFICIE: el panal de hexágonos se RETIRA** (2026-08-20; V2-233)
- **El contrato de pantalla estaba en verde y el operador seguía sin ver nada** (2026-08-20; V2-199, V2-227, V2-233)
- **La nota del hallazgo llevaba TRES órdenes, y el turno obedeció la del medio** (2026-08-20; V2-223, V2-224, V2-226)
- **Decirlo una vez no es olvidarlo** (2026-08-20; V2-189, V2-221, V2-224)
- **El compositor de investigación LEÍA la cadena de proveedores y nunca la ESCRIBÍA** (2026-08-25; V2-225)
- **El prompt se contradecía a sí mismo, y el turno elegía la mitad cierta** (2026-08-20; V2-199, V2-221, V2-222)
- **Lo que el navegador ENCUENTRA no llegaba a nadie** (2026-08-20; V2-215, V2-220, V2-223)
- **Una tarea de fondo MUERTA no es una pregunta pendiente** (2026-08-20; V2-185, V2-189, V2-193, V2-196, V2-198, V2-213, V2-220, V2-221)
- **El aviso proactivo existía y no tenía dónde llegar** (2026-08-20; V2-073, V2-214, V2-215, V2-220)
- **El worker dejaba de trabajar en la aridad de NUESTRO propio CLI** (2026-08-20; V2-117, V2-153, V2-219)
- **Un hecho recogido en TODAS partes y dicho en NINGUNA** (2026-08-20; V2-185, V2-193, V2-197, V2-202, V2-207, V2-211, V2-212, V2-215)
- **El aviso existía y su CONTENIDO estaba roto** (2026-08-20; V2-214)
- **DOS REGRESIONES MÍAS, medidas el mismo día y en el único caso 5/5 del tablero** (2026-08-20; V2-176, V2-202, V2-209, V2-210)
- **«Prueba otro sitio» sin decir CUÁL es un deseo, no una instrucción** (2026-08-20; V2-176, V2-185, V2-186, V2-213)
- **Un `usage` dice la FORMA, no el ERROR** (2026-08-20; V2-203, V2-212)
- **La puerta es NUESTRA: el worker se muere en ella y en silencio** (2026-08-20; V2-117, V2-202, V2-211)
- **Un dato del mundo, dicho con una cifra y sin consultar nada** (2026-08-20; V2-022, V2-135, V2-210)
- **Desde fuera del proceso, «el muro no se anotó» y «se anotó y el turno lo ignoró» se veían IDÉNTICOS** (2026-08-20; V2-176, V2-207)
- **La MISMA cita dos veces, ahora por la data-op del modelo** (2026-08-27; V2-194, V2-208)
- **«Aquí lo tienes» sobre una tarjeta vacía — y la frase es NUESTRA** (2026-08-20; V2-176, V2-209)
- **Le decíamos al worker que mirara una captura que no estaba en disco** (2026-08-20; V2-117, V2-203, V2-205)
- **El puente del payload contestaba con el OSError pelado, y el worker lo leía como un callejón sin salida** (2026-08-20; V2-117, V2-186, V2-203)
- **El confirm-gate paró un clic irreversible y no preguntó a NADIE** (2026-08-20; V2-126, V2-153, V2-202)
- **Una tarea de verificación se cuelga del CASO, no del arreglo** (2026-08-20; V2-133, V2-199, V2-200, V2-201)
- **Cada cara del bloque del navegador tiene que poder DISPARARSE** (2026-08-20; V2-176, V2-199, V2-200, V2-201)
- **El arreglo anterior no estaba roto: estaba MUERTO** (2026-08-20; V2-185, V2-192, V2-199, V2-200)
- **Un test que no recorre el camino real prueba que el código compila, no que funciona** (2026-08-20; V2-126, V2-190, V2-198, V2-199)
- **Una sesión de WORKER que acaba desaparecía del estado** (2026-08-20; V2-150, V2-197, V2-198)
- **Dos listas de estados que había que mantener sincronizadas — y `open` llevaba en el hueco desde siempre** (2026-08-20; V2-196, V2-197)
- **Una tarea CANCELADA no estaba ni viva ni terminada** (2026-08-20; V2-150, V2-176, V2-190, V2-195, V2-196)
- **La captura forense de un turno guardaba la persona y tiraba el ESTADO** (2026-08-20; V2-195)
- **La suite escribía en la agenda REAL del operador: 328 citas de prueba** (2026-08-20; V2-194)
- **La cita se apuntaba DOS veces** (sin fecha; V2-153, V2-186, V2-189, V2-194)
- **Con varias tareas vivas, el estado MANDABA entregar una y no decía cuál** (2026-08-20; V2-189, V2-192, V2-193)
- **REGRESIÓN PROPIA: pasé de demasiado optimista a demasiado pesimista** (2026-08-20; V2-185, V2-192)
- **«Sí, adelante» → «Hecho.» → «¿Ya está cancelada del todo?»** (2026-08-20; V2-176, V2-189)
- **Una tarea parada esperando a que el operador ENTRE decía «te dará el resultado sola»** (2026-08-20; INI-016, V2-167, V2-176, V2-185)
- **Un hecho que solo vive un turno es un hecho que la conversación pierde** (2026-08-20; V2-150, V2-171, V2-176, V2-190)
- **Una confirmación que CADUCA borraba el hecho de que existió** (2026-08-20; V2-138, V2-150, V2-190)
- **El relleno de espera decía CUATRO veces la misma frase, y no lo decía el modelo** (2026-08-20; V2-038, V2-133, V2-189)
- **El muro más silencioso: la página de error del PROPIO sitio** (2026-08-20; V2-187, V2-188)
- **Un hecho que no se puede decir en voz alta es un hecho que no llega** (2026-08-20; V2-145, V2-150, V2-185, V2-187)
- **El operador pidió el aviso en SUBJUNTIVO y el backstop no lo reconoció** (2026-08-20; V2-151, V2-167)
- **Una respuesta que aún PREGUNTA archivaba una cita hecha con su propia pregunta** (2026-08-20; V2-167)
- **El muro del cuerpo DISPARÓ, y el hecho se borró al re-enrutarse** (2026-08-20; V2-167, V2-176)
- **«¿Hay algo corriendo?» era la pregunta equivocada** (2026-08-20; V2-132, V2-176, V2-196)
- **Una búsqueda vacía y una búsqueda IMPOSIBLE eran el mismo dato** (2026-08-30; V2-176)
- **El traspaso de inicio de sesión no estaba cableado en el canal de TEXTO** (2026-08-20; V2-153, V2-176)
- **El día del aviso podía estar SOLO en la frase del operador** (2026-08-20; V2-121, V2-167)
- **Una fecha sola no es un compromiso** (2026-08-20; V2-167)
- **El muro y el atasco NUNCA llegaron al worker** (2026-08-20; V2-167, V2-186)
- **«No me habías pedido eso» era VERDAD** (2026-08-20; V2-176)
- **Un proveedor roto no se le decía a NADIE en el canal de texto** (2026-08-20; V2-176)
- **Un muro puede estar en el CUERPO de la página, con URL normal y status 200** (2026-08-20; V2-167)
- **El atasco llegaba al TURNO y no al WORKER** (2026-08-20; V2-167, V2-186)
- **- **Una salvedad no compite con una promesa: el estado PROMETÍA que la tarea iba a terminar sola, también** (2026-08-20; V2-152, V2-167, V2-185)
- **El turno que fija la FECHA no es el que dice el QUÉ** (2026-08-20; V2-075, V2-132, V2-151, V2-176)
- **El turno corría con un tope que NO cabía la tool más importante del sistema** (2026-08-20; V2-171)
- **Una ruta de FastAPI no sabe qué función viene detrás del decorador** (2026-08-19; V2-169)
- **navegador — AUTENTICACIÓN = abrir un navegador REAL** (2026-07-10; INI-016)
- **«Una sola mente» — el FlashBrain conduce TODA conversación** (2026-07-25; V2-069)
- **El SEGUNDO backend de Brain Worker: Codex — y su frontera de seguridad es DISTINTA** (2026-08-12; V2-010, V2-038)
- **El TERCER backend: Grok Build — y la elección de worker es una TERNA, no una casilla** (2026-08-13; no refs)
- **Los Brain Workers no dependen de UN proveedor — cadena + relevo automático** (2026-08-09; no refs)
- **Energy metering — cobertura real, no solo tabla de tarifas** (2026-08-16; INI-019, INI-020)
- **Control central de proveedores en el perfil cloud** (2026-08-05; INI-019)
- **«Homeostasis» — el LATIDO AUTÓNOMO del sistema** (2026-07-25; V2-070)
- **REHIDRATACIÓN — el trabajo que corta un reinicio se recoge, no desaparece** (2026-08-12; no refs)
- **El ESCRITORIO se rehidrata — y el `localStorage` es per-ORIGEN** (2026-08-12; no refs)
- **Canal nativo MeshKore** (2026-07-26; V2-069, V2-072, V2-075, V2-076)
- **Una tarea/flujo SOLO nace de CUATRO fuentes — el pulso NUNCA crea trabajo por tener un loop** (2026-08-16; no refs)
- **- **`voice.trace.active()` — un puntero EXPLÍCITO para eventos que el ContextVar nunca puede ver (2026-08-16,** (2026-08-16; no refs)
- **- **El gate de atención en modo `always` (el default, micro SIEMPRE abierto — permanente, NO es algo a reverti** (2026-08-17; V2-093, V2-097, V2-105, V2-109)
- **- **Fusionar dos flujos que resultan ser la MISMA tarea — la capacidad existe, el disparo automático NO (pass** (2026-08-16; V2-105)
- **El motor no arrancaba NUNCA en frío — deadlock de reentrancia en `memory/db.py::get_db()`** (2026-08-16; V2-105, V2-106)
- **Seguridad del canal de cluster** (2026-07-26; V2-021, V2-069, V2-071)
- **Reglas en TRES niveles + PACTO de conversación agente-agente** (2026-07-25; V2-046, V2-067, V2-071, V2-072)
- **Criterio de conversación por INTELIGENCIA — parar/ceder el turno cuando no fluye** (2026-07-26; V2-010, V2-073, V2-075)
- **Sello de VERSIÓN — saber qué código corre y qué versión generó cada línea** (2026-07-26; V2-074)
- **Proveedor Architect** (sin fecha; no refs)
- **Mensajería personal UNIFICADA con triaje** (sin fecha; V2-051, V2-052)
- **Configuración MANEJADA POR LA INTERFAZ — "instala una vez, todo lo demás desde la UI"** (sin fecha; V2-083)
- **Tema dark/light** (sin fecha; no refs)
- **- **Controles del orbe = «EL OJO» — 7 iconos como párpado superior + ECG como párpado inferior (el orbe = iris** (2026-07-22; V2-014, V2-016, V2-039)
- **LA PILA de Energy — el saldo se VE antes de agotarse** (2026-08-13; no refs)
- **Visor de memoria (🧠 «mapa de la memoria») — DOS VISTAS** (2026-07-10; V2-014)
- **ADMISIÓN — cuando el proceso NO es la frontera, sin sesión verificada no se sirve nada** (2026-08-13; no refs)
- **PARAR ES PARAR — el interruptor global vive en el SERVIDOR, y un widget DECLARA lo que produce** (2026-08-13; V2-039, V2-065, V2-092)
- **PARAR ES PARAR, de verdad: ni sesión fantasma con el agente parado, ni turno cortado a medias** (2026-08-15; V2-092)
- **La ESPERA se oye, y el veredicto de latencia ya puede culpar al proveedor** (sin fecha; V2-093)
- **RELEVO por latencia del cerebro de voz** (2026-08-14; V2-094, V2-097)
- **DeepSeek DIRECTO cura el TTFT, y por eso es RELEVO y no titular** (2026-08-17; V2-094, V2-097)
- **El turno se cierra cuando la frase ACABA, no cuando hay silencio** (2026-08-14; INI-012, V2-092, V2-095, V2-096, V2-102)
- **Una frase en DOS TIEMPOS es UNA petición — y el fragmento no genera nada** (2026-08-02; V2-095, V2-096)
- **SELECCIÓN PROGRESIVA de tools — el turno lleva su RUMBO, no el catálogo entero** (2026-08-02; V2-085, V2-096)
- **Architecture/modularization pass — real duplication killed, three god-files split, one deliberately NOT split** (2026-08-16; V2-095, V2-096, V2-098)
- **V2-098 follow-up: FlashBrain modularization, 9 splits executed** (2026-08-17; V2-076, V2-098, V2-108, V2-109, V2-112)
- **- **Floating feedback widget — a self-hosted engine's first outbound call, and the control-plane's first** (2026-08-16; INI-023, V2-100, V2-256)
- **First-run language onboarding — a blocking ceremony, and the alias-pack extension point finally built** (2026-08-16; V2-101)
- **Turn-completeness judge — real intelligence replaces "hold forever"** (2026-08-16; V2-095, V2-096, V2-097, V2-102)
- **RESET left stale rows on screen and never touched the chat wall** (2026-08-16; no refs)
- **Memory — write-path self-healing, and REM stops being purely additive** (2026-08-16; V2-103)
- **REM — gate de fidelidad antes de escribir/demotar un insight** (2026-08-16; V2-075, V2-103, V2-104)
- **Corpus longitudinal con contradicciones + REM real end-to-end (V2-107)** (2026-08-17; V2-107)
- **Susurro's friction window had no recency boundary — an 11-hour-old exchange got escalated as "now" (V2-108)** (2026-08-17; V2-108)
- **- **A worker-dispatched browser task's own trace was empty for its whole lifetime — TaskBrowser used ambient** (2026-08-17; V2-108)
- **La query de recall llevaba pegada la nota `[SISTEMA]` del turno — el modelo alucinó un familiar (V2-110)** (2026-08-17; V2-110)
- **- **Grafo multi-hop (PPR) + bi-temporal explícito — dos piezas de V2-111 §9, construidas por delante de las** (2026-08-17; V2-095, V2-102, V2-111)
- **- **An escalated flow closed itself seconds after opening — a structural race, not an occasional one (V2-113,** (2026-08-17; V2-113)
- **- **Lead-in filler leaked into the chat wall AFTER the real reply — now its own module, and structurally unabl** (2026-08-18; V2-096, V2-101, V2-102, V2-122)
- **- **Showing data is the generic sheet's job, not a reason to write a component — and a created widget was neve** (2026-08-18; V2-098, V2-115)
- **- **One sentence must be ONE flow — and flow continuity can no longer hang on getting completeness right; plus** (2026-08-18; V2-090, V2-095, V2-096, V2-097, V2-102, V2-116)
- **- **A worker started with the engine's own developer manual inside it, and its raw provider error was delivere** (2026-08-18; V2-105, V2-117)
- **- **The flow-merge TRIGGER, built at last — and neither of the two resolvers we already had could do it (V2-12** (2026-08-18; V2-029, V2-075, V2-090, V2-105, V2-113, V2-117, V2-123)
- **- **A SECOND SHELL over one engine — the mobile PWA, and the two contracts that made it cheap (V2-124, 2026-08** (2026-08-18; V2-088, V2-092, V2-124)
- **La memoria estaba sana; la deuda era ESTRUCTURAL — y tres imports inversos se BENDICEN, no se arreglan** (2026-08-23; V2-114, V2-117, V2-273)
- **Un recall que NO llega se veía igual que una memoria vacía** (2026-08-25; V2-031, V2-273, V2-311)
- **Un encargo viejo viajaba en CADA prompt como un hecho permanente de la persona** (2026-08-26; V2-254, V2-337)
- **La SONDA de backend esperaba como una llamada real: 20,3 s en el PRIMER acceso a memoria** (2026-08-26; V2-103, V2-311, V2-349)
- **El widget de YouTube tiene LISTA, y `add` NUNCA arranca la reproducción (V2-366, 2026-08-27)** (2026-08-27; V2-092, V2-366)
- **Buscar vídeos va al REPRODUCTOR, no a la hoja de resultados (V2-402, 2026-08-27)** (2026-08-27; V2-366, V2-380, V2-402)
- **- **El Brain Worker corre con lo que la NUBE puede contratar, y un escalón que no ve se declara ciego** (2026-08-27; V2-403)
- **El deck móvil se NAVEGA, y su restore alcanzó la paridad V2-351 (V2-474, 2026-08-29)** (2026-08-29; V2-351, V2-465, V2-474)
- **- **El arranque en frío enseñaba claves i18n crudas — y la leyenda buena llegaba sin que la viera nadie** (2026-08-29; V2-124, V2-481)
- **Cinco filas eran pocas, y decirle que hay más no es enseñárselas (V2-479, 2026-08-29)** (2026-08-29; V2-374, V2-479)
- **A terminal field cannot tell a process, and a zero must say why it is zero (V2-512, 2026-08-30)** (2026-08-30; V2-506, V2-512)
- **The instrument must not turn a coincidence into a cause (V2-506, 2026-08-30)** (2026-08-30; V2-506)
- **A retired provider may not be named by ANY ladder (V2-504, 2026-08-30)** (2026-08-30; V2-500, V2-504)
- **A lab measures the PRODUCT, not the machine it runs on (V2-502, 2026-08-30)** (2026-08-30; V2-500, V2-502)
- **- **The memory's semantic space comes from a CLOUD provider, and a paid call is metered (V2-501,** (2026-08-30; V2-103, V2-501)
- **El reparto de modelos vive en UNA tabla pública, y un solo failover por servicio (V2-500, 2026-08-30)** (2026-08-30; V2-500)
- **Z.AI es del BRAIN WORKER y de nadie más (V2-496, 2026-08-30 — deroga V2-462)** (2026-09-01; V2-462, V2-496)
- **- **El compositor del brief pedía «no razones» a un modelo que NO PUEDE dejar de hacerlo, y toda búsqueda** (2026-08-29; V2-225, V2-488)
- **- **La red MeshKore estaba construida, verificada en vivo y NUNCA se consultaba — dos causas apiladas y** (2026-08-29; V2-118, V2-167, V2-211, V2-486, V2-487)
- **Una frase deja DOS píldoras críticas, y el corte expulsaba un hecho de SEGURIDAD (V2-491, 2026-08-29)** (2026-08-29; V2-123, V2-490, V2-491)
- **- **DOS puertas por las que entra un vector de otro espacio, y ninguna fallaba con ruido (V2-484 y V2-485,** (2026-08-29; V2-482, V2-484, V2-485)
- **La voz de V2-497 estaba colgada DESPUÉS de la puerta que más se cierra (V2-503, 2026-08-30)** (2026-08-30; V2-311, V2-482, V2-484, V2-497, V2-503)
- **Un reparador INERTE parecía un reparador SIN TRABAJO (V2-497, 2026-08-29)** (2026-08-29; V2-311, V2-482, V2-485, V2-497)
- **Los GUSTOS son estado ACTIVO, y el slot obvio está medido como MUERTO (V2-498, 2026-08-29)** (2026-08-29; V2-337, V2-491, V2-497, V2-498)
- **- **Una limitación de INGESTIÓN dicha sin palabra de categoría también es crítica (V2-499, 2026-08-29,** (2026-08-29; V2-490, V2-491, V2-499)
- **Un vector de espacio AJENO no lo repara nadie, nunca (V2-482, 2026-08-29)** (2026-08-29; INI-026, V2-482)
- **La TERCERA puerta al scheduler no normalizaba (V2-480, 2026-08-29)** (2026-08-29; V2-151, V2-249, V2-480)
- **La puerta del backstop de entrega tampoco era la LONGITUD (V2-478, 2026-08-29)** (2026-08-29; V2-364, V2-371, V2-478)
- **Una garantía escrita en un solo idioma es un defecto para todos los demás (V2-475, 2026-08-29)** (2026-08-29; V2-475)
- **La entrega se NOMBRA y lo no verificable no se da por cumplido (V2-469, 2026-08-29)** (2026-08-29; V2-341, V2-469)
- **Un caso BLOQUEADO no es una avería, ni un turno que gastar cada vuelta (V2-448, 2026-08-28)** (2026-08-28; V2-260, V2-448)
- **Un solo formateador de fila (V2-455, 2026-08-28)** (2026-08-28; V2-240, V2-451, V2-455)
- **La sesión NUNCA pide la cámara — mic-only (V2-456, 2026-08-28)** (2026-08-28; V2-088, V2-456)
- **Cadena de buscadores de imágenes (V2-466, 2026-08-28)** (2026-08-28; V2-466)
- **El reproductor publica su lista y el visor tiene teclado (V2-465, 2026-08-28)** (2026-08-28; V2-026, V2-380, V2-465)
- **La ronda deja un VÍDEO — modo escaparate + grabador (V2-464, 2026-08-28)** (2026-08-28; V2-464)
- **La tarjeta se abre donde aterrizan los datos (V2-463, 2026-08-28)** (2026-08-28; V2-346, V2-463)
- **Z.AI: el plan primero, los créditos después (V2-462, 2026-08-28)** (2026-08-28; V2-458, V2-462)
- **Un MATIZ sobre una foto no es un encargo · y la conversación por API se VE (V2-461, 2026-08-28)** (2026-08-28; V2-032, V2-461)
- **Un agente del plató arranca con la sesión EN BLANCO (V2-460, 2026-08-28)** (2026-08-28; V2-460)
- **Tres agentes en esta máquina, tres puertos, y ninguno se mueve (V2-459, 2026-08-28)** (2026-08-28; V2-459)
- **Enseñar una foto es un turno de 3 s, no un encargo de 355 (V2-457, 2026-08-28)** (2026-08-28; V2-402, V2-457)
- **Un saldo agotado apaga a los escalones de su MISMA cuenta (V2-458, 2026-08-28)** (2026-08-28; V2-243, V2-252, V2-458)
- **La oferta de PARAR se hace una vez — el hecho se queda (V2-454, 2026-08-28)** (2026-08-28; V2-131, V2-224, V2-454)
- **El recall que NO llegó se cuenta — «preguntó lo que ya sabía» tiene DOS causas (V2-453, 2026-08-28)** (2026-08-28; V2-311, V2-432, V2-453)
- **- **El prompt está en castellano y el operador habla inglés: el modelo copiaba su idioma (V2-452,** (2026-08-28; V2-221, V2-452)
- **Las filas de la hoja viajan aunque NO haya navegador (V2-451, 2026-08-28)** (2026-08-28; V2-259, V2-432, V2-438, V2-441, V2-444, V2-451)
- **Un precio de mercado ANTES de entregar nada — y los TRES caminos de entrega (V2-450, 2026-08-28)** (2026-08-28; V2-223, V2-450)
- **La entrega multimedia no está en la hoja (V2-445, 2026-08-28)** (2026-08-28; V2-366, V2-402, V2-445)
- **El mismo defecto en el SEGUNDO bloque, y era el que disparaba (V2-444, 2026-08-28)** (2026-08-28; V2-222, V2-443, V2-444)
- **Sin filas, lo único que hay es la PALABRA del worker (V2-443, 2026-08-28)** (2026-08-28; V2-152, V2-238, V2-249, V2-330, V2-358, V2-440, V2-443)
- **Pedirlo dos veces no es hacerlo dos veces (V2-442, 2026-08-28)** (2026-08-28; V2-123, V2-442)
- **«Le pedimos lo imposible»: avisado de que había algo y servido con CERO filas (V2-441, 2026-08-28)** (2026-08-28; V2-330, V2-441)
- **El censo del INSTANTE separa dos causas que se veían idénticas (V2-440, 2026-08-28)** (2026-08-28; V2-330, V2-439, V2-440)
- **`results::X` y `X` son la MISMA hoja, y una volvía VACÍA (V2-439, 2026-08-28)** (2026-08-28; V2-242, V2-259, V2-439)
- **La cara dice que hay filas y la hoja no las da (V2-438, 2026-08-28)** (2026-08-28; V2-438)
- **Un elemento muerto dice qué hacer (V2-437, 2026-08-28)** (2026-08-28; V2-437)
- **Una memoria rechazada dice POR QUÉ (V2-436, 2026-08-28)** (2026-08-28; V2-344, V2-436)
- **El worker PUEDE escribir lo que le decimos que escriba (V2-435, 2026-08-28)** (2026-08-28; V2-435)
- **Un RELEVO no es un encargo nuevo, tampoco para quien LEE la hoja (V2-434, 2026-08-28)** (2026-08-28; V2-432, V2-434)
- **El puente del worker habla el vocabulario de widgets (V2-433, 2026-08-28)** (2026-08-28; V2-429, V2-433)
- **La hoja llena y el prompt diciendo que no (V2-432, 2026-08-28)** (2026-08-28; V2-352, V2-432)
- **Un «no» bien fundado es una ENTREGA (V2-431, 2026-08-28)** (2026-08-28; V2-431)
- **El precio que DICE es el que TIENE (V2-430, 2026-08-28)** (2026-08-28; V2-430)
- **Un comando rechazado dice qué se intentó (V2-429, 2026-08-28)** (2026-08-28; V2-424, V2-426, V2-429)
- **Un traceback se recorta por la COLA (V2-428, 2026-08-28)** (2026-08-28; V2-421, V2-425, V2-428)
- **La apertura del tester no puede recitar nuestra hoja (V2-427, 2026-08-28)** (2026-08-28; V2-427)
- **El `cd` bloqueado, y la premisa falsa que lo provoca (V2-426, 2026-08-28)** (2026-08-28; V2-426)
- **El error de payload dice QUÉ falló (V2-425, 2026-08-28)** (2026-08-28; V2-425)
- **El `&` solo también lo bloquea nuestro guarda, y no estaba en la regla (V2-424, 2026-08-28)** (2026-08-28; V2-412, V2-424)
- **Una fila INFRA dice CUÁL (V2-423, 2026-08-28)** (2026-08-28; V2-423)
- **La misma búsqueda dos veces no son dos búsquedas (V2-422, 2026-08-28)** (2026-08-28; V2-422)
- **Un payload que falta dice lo que SÍ hay (V2-421, 2026-08-28)** (2026-08-28; V2-421)
- **El denominador es lo que se le MOSTRÓ, no lo que hay en la hoja (V2-420, 2026-08-28)** (2026-08-28; V2-420)
- **Un worker MIRANDO EL MENÚ no es un worker estrellado (V2-418, 2026-08-28)** (2026-08-28; V2-418)
- **Una función que decide fechas leía DOS relojes (V2-419, 2026-08-28)** (2026-08-28; V2-419)
- **El plató no para: 24/7 con guardián (V2-417, 2026-08-28)** (2026-08-28; V2-417)
- **El marcador dice con qué CEREBRO se midió cada fila (V2-415, 2026-08-27)** (2026-08-27; V2-415)
- **Que nos BLOQUEEN no es que el mundo esté vacío (V2-414, 2026-08-27)** (2026-08-27; V2-414)
- **Una recarga es INVISIBLE desde el motor, así que se vuelve a probar (V2-413, 2026-08-27)** (2026-08-27; V2-243, V2-413)
- **La búsqueda mira desde donde vive la persona (V2-411, 2026-08-27)** (2026-08-27; V2-411)
- **El prompt del worker no enseña lo que nuestro guarda bloquea (V2-412, 2026-08-27)** (2026-08-27; V2-412)
- **El dedup decía que NO y no decía POR QUÉ (V2-507, 2026-08-30)** (2026-08-30; V2-507)
- **Un encargo CONFIRMADO conserva su hoja (V2-508, 2026-08-30)** (2026-08-30; V2-117, V2-128, V2-227, V2-238, V2-259, V2-507, V2-508, V2-509)
- **Lo que vuelve de una búsqueda es una PISTA, y la NOTA seguía ordenando entregarla (V2-510, 2026-08-30)** (2026-08-30; V2-222, V2-226, V2-234, V2-236, V2-479, V2-508, V2-510)
- **Lo que CUENTA lo que pasó no es lo que TRAE algo (V2-511, 2026-08-30)** (2026-08-30; V2-236, V2-240, V2-321, V2-364, V2-511)
- **The gate reads the ORDER, not the words (V2-509, 2026-08-30)** (2026-08-30; V2-128, V2-507, V2-508, V2-509)
- **A SHIPPED widget is forked, never edited in place — and never deleted from disk (V2-515, 2026-08-31)** (2026-08-31; V2-515, V2-518)
- **A catalog costs nothing until it is CONNECTED (V2-526, 2026-08-31 — DESIGN, no code yet)** (2026-08-31; V2-078, V2-083, V2-169, V2-520, V2-526)
- **- **Stopping is DISCARDING — abandon_work (V2-528, 2026-08-31; supersedes the 2026-07-10 freeze-to-resume** (2026-08-31; V2-214, V2-528)
- **- **A `[SISTEMA]` note is never the errand: the SECOND door, and a question is not a promise (V2-534,** (2026-09-01; V2-049, V2-095, V2-530, V2-534)
- **A NEGATED clause is not a promise (V2-534 follow-up, 2026-09-01)** (2026-09-01; V2-049, V2-095, V2-252, V2-534)
- **STABLE PREFIX FIRST — the prompt's block order is what the provider's cache can see (V2-536, 2026-09-01)** (2026-09-01; V2-097, V2-255, V2-533, V2-536)
- **The MURAL — placement that dodges the chat, the widget RAIL, and auto-arrange (V2-537, 2026-09-01)** (2026-09-01; V2-087, V2-464, V2-474, V2-537)
- **The rail is DOCKED, and a card gets the size its manifest declares (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **A sheet is for RESULTS, and an ITEM is a real candidate (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **Figures are made SPEAKABLE at the TTS node, and only there (V2-538, 2026-09-01)** (2026-09-01; V2-538)
- **An undeclared capability is one the model NARRATES — the agenda's view is an action (V2-540, 2026-09-01)** (2026-09-01; INI-027, V2-521, V2-540)
- **A canvas click has to land on the sheet the operator is LOOKING AT (V2-540, 2026-09-01)** (2026-09-01; V2-259, V2-540)
- **Who may interrupt is CONFIGURATION — per-connector notification policy (V2-532, 2026-09-01)** (2026-09-01; V2-520, V2-522, V2-527, V2-532)
- **- **The turn clock tells OUR share — pre-turn attribution + prefix-cache visibility + pooled judges (V2-533,** (2026-09-01; V2-533, V2-536)
- **- **Inside an active conversation, NOBODY judges — the attention gate went deaf mid-dialogue (V2-531,** (2026-09-01; V2-531)
- **An errand has a NAME, and it is not a slice of the conversation (V2-530, 2026-08-31)** (2026-08-31; V2-151, V2-199, V2-530)
- **The lead-in filler sounds BEFORE the reply — it IS the reply's first segment (V2-529, 2026-08-31)** (2026-08-31; V2-122, V2-529)
- **The proactive delivery QUEUE — one message at a time (V2-527, 2026-08-31)** (2026-08-31; INI-008, V2-047, V2-525, V2-527)
- **⏻ ON has to START it — the reload was the tell (V2-525, 2026-08-31)** (2026-08-31; V2-092, V2-525)
- **The BOUNDARIES of a work session (V2-524, 2026-08-31)** (2026-08-31; V2-524)
- **Messaging is a MAIN widget now — the operator's spec (V2-521/522/523, 2026-08-31)** (2026-08-31; V2-051, V2-520, V2-521, V2-522, V2-523)
- **Connecting a channel can be ASKED FOR (V2-520, 2026-08-31)** (2026-08-31; V2-051, V2-520)
- **The attachment can never swallow the message (V2-519, 2026-08-31)** (2026-08-31; V2-519)
- **The widget's CONFIG corner + confirmations live in the CHAT (V2-518, 2026-08-31)** (2026-08-31; V2-518)
- **CONTACTOS: un directorio para TODAS las identidades — y su vista contesta (V2-541, 2026-09-01)** (2026-09-01; V2-124, V2-208, V2-473, V2-523, V2-540, V2-541)
- **Borrar una superficie es MUDAR lo que llevaba, o es perderlo (V2-542, 2026-09-01)** (2026-09-01; V2-538, V2-542)
- **- **MENSAJERÍA: la vista es una acción que contesta, los medios se VEN, y las órdenes llegan a las apps** (2026-09-01; V2-520, V2-531, V2-541, V2-543)
- **- **The INSIDE of a widget belongs to widget_data — the prompt no longer contradicts the catalog (V2-544,** (2026-09-01; V2-222, V2-467, V2-539, V2-544)
- **- **What a pure show may RUN is decided by the ACTION, not by the words — and the lens phrases resolve before** (2026-09-01; V2-544, V2-545)
- **The messaging widget FOLLOWS the real apps instead of drifting from them (V2-546, 2026-09-01)** (2026-09-01; V2-546)
- **A KNOWN phrase skips the model — the ACTION MAP (V2-539, 2026-09-01)** (2026-09-01; V2-095, V2-539, V2-545)

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

## Frontera PÚBLICO/PRIVADO — este repo es público (fair-code) y se lee desde fuera

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
- **Con sesiones concurrentes, la protección NO está en cómo AÑADES sino en qué COMMITEAS: `git commit -- <rutas>`**
  (2026-08-20, aprendido rompiendo el escritorio). La norma anterior —«stage fichero a fichero»— se siguió al pie de
  la letra y no bastó: **`git commit` a secas commitea el ÍNDICE ENTERO, y el índice es COMPARTIDO** entre las
  sesiones que trabajan en el mismo árbol. Ese día un commit del arnés se llevó dentro el borrado de un componente
  que otra sesión tenía en el índice por un `git rm`, y HEAD quedó con un `import` apuntando a un fichero que ya no
  existía: **el escritorio entero sin cargar**, y sin que fallara nada en el commit. Con pathspec se commitean solo
  esas rutas desde el working tree y el resto del índice se ignora. La comprobación barata que lo acompaña:
  **`git diff --cached --name-only` tiene que estar VACÍO antes de empezar** — si trae ficheros ajenos, alguien
  llenó el índice y estás a un `git commit` de llevártelos. Y el detalle que se escapa siempre: en
  `git status --short`, staged es `M ` (marca en la PRIMERA columna) y solo-modificado es ` M`; un espacio de
  diferencia. **Si ya está pusheado, NO se reescribe `main` por una atribución**: el código no se pierde (un commit
  no toca el working tree de nadie), solo queda mal atribuido, y reescribir historia compartida cuesta más de lo
  que arregla.
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
