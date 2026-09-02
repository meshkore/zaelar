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

- **El worker escribe lo natural y el CLI le cobraba el turno — tres formas más (V2-341, 2026-08-26)**:
  barridos TODOS los logs de sesión del plató salen **41 errores de contrato con `nav_cli`**. Quitando los 18
  `open` que V2-306 ya cerró, quedan tres vivas: **una URL suelta sin verbo (5)**, **`type_at <ref> "texto"`
  con la aridad de `type` (5)** y **un `ref` con los corchetes que NOSOTROS imprimimos (1)**. La tercera es la
  más nuestra: `dom.py` pinta `[2] button "Buscar"` y el encabezado de `_print_state` dice «usa el número
  **[ref]** con click/type» — copiar literalmente lo que le enseñamos devolvía `invalid int value: '[2]'`. En
  la ronda 3 de `search-buy-used-car` cinco errores encadenados dejaron la hoja a CERO mientras el turno
  contaba que seguía navegando. **Ninguna adivina la intención**: `http(s)://` no es ningún otro verbo del
  catálogo, y un segundo argumento no numérico en `type_at` solo puede ser texto.
  - **Lo que NO se acepta, y es la mitad que sostiene la regla**: `submit`/`back`/`state` inventados (no son
    la aridad equivocada de un comando que existe, son comandos que no existen), `type_at 410 260` a medias
    (son coordenadas legítimas incompletas; convertirlo escribiría «260» en el elemento 410 — actuar con un
    argumento inventado, lo que cerró V2-253) y un `ref` no numérico (haría clic en el elemento equivocado,
    V2-248). Los tres con test.
  - ⚠️ **La trampa, y salía VERDE**: la primera versión leía `argv[1]`, pero `main(argv=None)` deja que
    argparse lea `sys.argv[1:]`, así que **el verbo está en la posición 0**. Todos los tests pasan una LISTA,
    donde `argv[1]` es el primer argumento — así que el fallo pasaba la suite entera y habría reventado con
    `TypeError` en **cada invocación real del worker**, o sea el puente del navegador muerto para todos. Hay
    un caso que fija `sys.argv` y llama a `main()` sin argumentos exactamente para eso.
  - **Quita UNA de las tres causas de esa ronda, no la ronda.** El backstop midió **8 silencios, todos con
    `rows=0`**: silencio correcto, la hoja nunca se llenó. Y siguen abiertos, medidos en la ronda 4: **tres
    workers con el mismo objetivo** (similitud 0,5–0,615 contra el umbral 0,60 — la paráfrasis que V2-123 dejó
    declarada, ahora con coste), y **el worker avanzó al paso 1/6 y el turno no lo dijo**. Nodo 2.5, desarme
    en las tres mitades. Sin verificar en vivo.

- **Las dos puertas del motor le decían cosas opuestas al mismo worker (V2-350, 2026-08-26)**: y en el peor
  orden — un worker **relevado** (registro nuevo con su mismo `task_id`, token nuevo) **no podía ENTREGAR y sí
  podía CONTAMINAR**. `/api/worker/act` le devolvía 403 y `/api/agent/report` no miraba el token, así que sus
  siete coches con año y kilómetros verificados nunca llegaron a pantalla mientras sus notas se escribían en el
  registro del worker que acababa de nacer. De ahí la línea imposible de la traza: «arrancando — lleva 18 s» a
  los 36,8 s y «selección final lista» a los 51,5 s — no es un worker rápido, son dos escribiendo encima. **Y
  contamina la MEDICIÓN**: el juez leyó «el motor devuelve 403 al widget» como un hecho de la ronda y lo puso de
  bloqueador nº1; un instrumento que se cree las notas de un fantasma no mide. El corte es **una sola
  comprobación de identidad en las dos puertas**, con la fontanería que ya existía (`ZAELAR_TASK_TOKEN` viajaba
  en el entorno desde `mem_cli`). **Un token ausente no es un token equivocado**: sin token se sigue como
  siempre —un worker viejo no puede quedarse mudo por una cabecera que nadie le enseñó a mandar— y se corta solo
  el que NO CASA. Y se le **dice**, con qué hacer: el 403 mudo le costó 45 s de reintentos creyendo que el motor
  fallaba. Nodo 2.33. **Sin decidir**: si a un relevado hay que matarlo o dejarle entregar por voz — es del
  operador.

- **Un contratiempo también se cuenta: solo las buenas noticias llevaban un «cuéntalo» (V2-348, 2026-08-26)**:
  cuarta cara de V2-222 y la simétrica de la segunda. Medido en `search-buy-used-car` ronda 8: el paso decía
  «coches.net caído tras portada (página de error)» y el turno contestó «está entrando en el marketplace y ya va
  dando pasos». **No era desobediencia**: el bloque de TAREAS DE FONDO tenía rama para SIN paso reportado
  (V2-133), para ENCALLADA (V2-131) y para YA ENTREGADO / YA HA ENCONTRADO (V2-222) — y **ninguna** para un paso
  que trae una mala noticia, así que el modelo relató la mitad que el bloque nombraba. La rama va DENTRO del
  mismo imperativo que la que refleja (dos órdenes en un párrafo salen a cara o cruz) y pide **nombrar** lo que
  falló y el plan B. El trinquete cobró de paso: el bloque entero se mudó a `live_blocks.py` con el precedente
  exacto de V2-276, `_short_note` viajó con su único llamante y `prompt.py` bajó a 725. ⚠️ Al mudarlo sin
  llevarse `_short_note`, el `except Exception: pass` que lo envuelve **se tragó el NameError y el bloque salió
  VACÍO, sin un solo error**: un fail-open protege de que un fallo de datos tumbe el turno y del mismo golpe
  esconde un cableado roto. ⚠️ Y el primer desarme **no mordió** —quité solo el primer fragmento de la cadena y
  la palabra clave vivía en el siguiente—: un desarme que sale verde es una mutación mal hecha hasta que se
  demuestre lo contrario.

- **Un nombre que comparten todas las filas no nombra a ninguna (V2-346, 2026-08-26)**: la MISMA regla de
  `dom.py` —la de V2-334, aquí abajo— pero una capa más arriba, entre FILAS en vez de entre nodos. Medido en la
  sesión `faadd628` del plató ES: AutoScout24 devolvió doce filas de las que nueve llevaban por título el enlace
  «+ Vehículos del profesional (FLEXICAR SAN SEBASTIAN…)» que cada tarjeta arrastra dentro, todas sin `url`.
  `by_identity` las contó como nueve resultados con nombre —tienen letras—, entraron en la hoja, y el turno
  anunció «en OcasionPlus Arganda hay uno por 11.565 euros». El juez lo puso de **bloqueador nº1** del caso, que
  llevaba tres rondas en 0/1. La plantilla se reconoce por prefijo compartido por **al menos la mitad** de las
  nombradas (así viene: los nueve difieren solo en el paréntesis final) y exigiendo que cada fila **añada algo
  detrás** — cuatro títulos IDÉNTICOS son lo contrario, el mismo producto en cuatro tiendas de un comparador.
  No es una lista negra de textos: mañana es otra tienda y otro idioma. Nodo 4.50. **Es el CINTURÓN, no el
  arreglo**: la causa raíz es V2-347. Y de paso el trinquete de arquitectura cobró un fallo mío — V2-345 había
  engordado `session.py` a 845 líneas y yo lo di por ajeno sin comprobarlo; la emisión de la narración se
  extrajo entera a `progress.narration_out` y el fichero quedó en 820.

- **Una ruta que comparten decenas de anclas no es la ficha de nada (V2-334, 2026-08-26)**: es la regla que
  `dom.py` ya aplica al ANCESTRO —«un dato que nombra a todas no nombra a ninguna»— llevada a la URL. Medido:
  ficha real **2** anclas por ruta · `/redirigir` **26** · `/privacy-policy` **297** · enlace a la propia página
  **2083**. Ese hueco es lo que hace legítimo el corte en 8. **No es una lista de textos** —el texto del botón lo
  inventa cada sitio— sino un hecho de la página. Y tiene un efecto que no esperaba: al cortar los botones,
  `cands` queda vacío y entra el recolector sin anclas (V2-320-A), que saca los nombres reales; sin el corte, una
  página de diez ofertas colapsaba en UNA fila llamada «IR A LA OFERTA». **Invariante del desarme: un umbral
  demasiado agresivo NO se detecta mirando el título —el recolector de respaldo lo rescata— sino el ENLACE, que
  ese camino no tiene.**

- **Sin filas no se puede pedir que las cuente (V2-330, 2026-08-25)**: la cara «YA HA ENCONTRADO algo» ordenaba
  «CUÉNTALE lo que encaje, con nombre y precio» — y las filas solo viajan cuando la hoja ya tiene alguna con
  nombre. Sin ellas el turno recibía un imperativo IMPOSIBLE y el modelo contestaba lo único honesto que le
  quedaba. Medido: **sin filas, 79 % de esos turnos responden con espera; con filas, 42 %**. No era
  desobediencia — era la única salida que le dejábamos, y desde fuera se leía como mentira: cinco de los diez
  casos con mecanismo ≥4 y resultado ≤3 traían ese veredicto, y el de la cámara citaba la instrucción por su
  nombre. Es la trampa que el docstring de `_sheet_top_rows` nombra desde V2-298, escrita por nosotros. **El 42 %
  restante —con filas delante y aun así esperando— es OTRO defecto y sigue abierto.**

- **El informe dice qué nombró ZAELAR él mismo (V2-329, 2026-08-25)**: decía lo que el sistema le puso delante
  (`offered` → «¿se lo inventó?») y no lo que él dijo (→ «¿lo entregó?»). Sin ese hecho, el juez confunde «sigue
  trabajando en los detalles» con «oculta lo que tiene», y lo hizo TRES veces el mismo día — la peor,
  `search-secondhand-monitor`, bajó de PASS a FAIL con «decide no mostrarlos para mantener una ficción de
  búsqueda activa» tras haber entregado cinco candidatos con nombre y precio en cuatro turnos. **No se reutilizó
  `recites_our_candidates` a propósito: misma pregunta, asimetría de coste OPUESTA** — allí un falso positivo
  tira una ronda buena (por eso es estricto y cazaba 1 de 3 aquí), y aquí quien habla tiene la lista delante, así
  que no hay que protegerse de «no podía saberlo». **Invariante: un hecho sin instrucción no cambia nada — el
  transcript ya estaba delante del juez las tres veces.**

- **Un SUPERÍNDICE no es parte del número (V2-326, 2026-08-25)**: las fichas cuelgan del precio una llamada a
  nota al pie en `<sup>`, y `textContent` la pega — medido en autoscout24: `<span>€ 399</span>` + `<sup>1</sup>`
  salía como **`€ 3991`**, un error de MAGNITUD (×10) justo en el dato sobre el que se compara. **No se arregla
  saltando los nodos con hijos**, que es lo primero que parece: la lectura por ancestros existe a propósito
  porque hay precios que solo viven en el padre (`<div>€ <span>399</span></div>`). Lo que sobra es el
  superíndice, así que se quita el superíndice. Coste asumido y escrito en su test: un sitio que ponga los
  céntimos en `<sup>` los pierde — redondeo (0,25 %) frente a magnitud (×10), y en la dirección que este fichero
  ya eligió («no se reconstruye el separador decimal… adivinar mal ahí cambia un precio por cien»).

- **Pedir ayuda no es equivocarse (V2-325, 2026-08-25)**: `widget_cli --help` contestaba «comando desconocido»
  con **exit 2**. Medido en los logs de sesión del plató: de 332 sesiones de worker, 81 usan `nav_cli` y solo 5
  llegan a `widget_cli` — y **tres de esas cinco mueren en el primer gesto**, pidiendo ayuda. Importa más de lo
  que parece porque ese puente es la ÚNICA forma que tiene un worker de poner en la hoja lo que aprende ABRIENDO
  fichas: sin él, la hoja solo se llena con lo que el extractor automático saca de un listado, y todo lo que se
  investiga página a página muere en el contexto del worker (ronda del seguro: 8 opciones reunidas, 2 en la
  hoja, y el prompt repitió esas dos nueve turnos). **Invariante: la puerta de entrada de un puente del worker
  se mide en sus LOGS DE SESIÓN, no en la observabilidad — ésta solo capta una fracción de los comandos (control
  medido: `nav_cli` 9 apariciones para decenas de invocaciones reales).**

- **Cuando dos anclas apuntan al mismo anuncio, gana la que lo NOMBRA (V2-324, 2026-08-25)**: los 19 coches de
  un listado salían sin nombre **sin que nada estuviera roto**. El dedup se quedaba con la primera del DOM —la
  de accesibilidad, «Abrir detalles del anuncio»— y tiraba la que decía «Skoda Octavia 2.0TDI»; después, el
  borrado de genéricos de V2-234 erasaba las 19 repetidas, **con razón**. El borrado era correcto y llegaba
  TARDE. Por eso el arreglo NO es una regla nueva sobre qué textos parecen nombres —esa es la cinta de correr,
  y era el camino que se iba a tomar—: es **dejar de descartar el dato que ya teníamos**. Las alternativas se
  guardan y elige el bloque que ya sabe cuál es genérica, porque eso solo se puede saber al final, cuando se ha
  contado qué texto se repite entre fichas. **Invariante: antes de añadir una heurística que reconozca lo malo,
  comprobar si lo bueno ya estaba y lo estamos tirando.**

- **«Cero filas» no es «sin resultados» (V2-323, 2026-08-25)**: un listado VIRTUALIZADO no crea sus fichas hasta
  que te acercas. Medido en `autoscout24.es`: 0 anclas de anuncio sin desplazarse, **40** tras hacerlo — 1 fila
  contra 19, con la página declarando «16.752 coches». V2-294 había decidido a propósito no reintentar con cero
  filas por coste, y el argumento era bueno; lo que faltaba era el discriminador que lo respeta en vez de
  pisarlo: **el ALTO de la página** (11,5× la pantalla aquí, 0,2× en una búsqueda vacía de verdad), porque una
  página de resultados sin nada no llega ni a una pantalla. El mecanismo vive en `widgets/navegador/lazy.py` —
  módulo propio porque el trinquete de arquitectura rechazó engordar `owner.py`, y tenía razón por debajo del
  recuento: es mecánica de página, no estado de la pestaña. **La vista VUELVE a su sitio, y no por limpieza: el
  `click_at` siguiente del worker lleva coordenadas de una foto tomada antes.**

- **Verificar el ARREGLO no es verificar el CASO (V2-322, 2026-08-25)**: V2-321 cerró «una fecha no es un
  teléfono», con 11/11 renderizando, desarme en dos direcciones, 816 verdes y comprobación en vivo. Todo cierto,
  y el caso que lo destapó **volvió a fallar**: «la hoja se llenó con elementos de interfaz de autoscout24».
  Había una SEGUNDA forma del mismo defecto que ninguna regla de forma podía cazar — `2020\n360.000`, el año de
  un anuncio y su kilometraje, dos nodos distintos que `innerText` pega en la frontera de bloque. Tomada como una
  cadena no se parece a nada sospechoso: diez dígitos, separadores válidos. Solo es absurda cuando se sabe que son
  DOS datos, y lo único que lo dice es el salto de línea (`\s` incluía `\n`). **Invariante: un arreglo no está
  cerrado cuando pasa su test, sino cuando el caso que lo destapó cambia de cara. El test unitario mide lo que ya
  entendiste; volver a medir el caso es lo único que encuentra lo que no.**

- **Una FECHA no es un teléfono, y la diferencia costaba la hoja entera (V2-321, 2026-08-25)**: `dom.telText`
  aceptaba `2026-08-25 12` como número al que llamar — diez dígitos con guiones y espacio, los tres separadores
  que admite. Su comentario decía descartar fechas «porque la barra no es separador aquí», lo cual cubre
  `25/08/2026` y no el formato ISO, que es el que las páginas escriben. **El daño no era la fila de más**:
  `by_amount` reparte la hoja por lo accionable —importe **o teléfono**— así que un teléfono falso ascendía el
  mobiliario del pie («Inicio», FAQ, «Envíanos un comentario») a la cabecera, el top-5 que ve el cerebro pasaba a
  ser eso, el cerebro se negaba a ofrecerlo con razón, y el juez lo puntuaba como ocultar resultados. Seis saltos
  desde una línea, y en el sexto la culpa parecía del modelo. El corte es de **forma** (como «un cero no es un
  precio»), sin lista negra de textos; el mobiliario desaparece solo porque `if(!price && !tel) continue` ya
  existía. **Invariante: un criterio estructural nuevo en este extractor se prueba RENDERIZANDO un DOM, y se
  desarma en las dos direcciones — que deje pasar lo que debe cazar, y que mate lo que debe respetar.**

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
  `nucleo/agentes/otros.py`, `nucleo/agentes/web.py`, y el bucle barato de `widgets/navegador/agent.py`. El loop
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
- **UN BRAIN WORKER HACE CASI DE TODO — la seguridad es un FILTRO, no una lista corta de permisos** (norma del
  operador, 2026-08-21). Conviene tenerlo escrito porque la lectura contraria —«un worker apenas puede hacer
  nada, así que ampliarle la superficie es peligroso»— lleva a diagnosticar mal: ante una capacidad que falta, la
  pregunta correcta es **cuál es su filtro**, no si debería tenerla. Lo que un worker puede hacer HOY, comprobado
  en el código y no de memoria:
  - **WIDGETS**: leer uno (`read_widget`), **operar sus datos** (`widget_data` con cualquier acción DECLARADA en
    su manifest), abrirlo y cerrarlo — por `nucleo/widget_cli.py` y por el plano `act`. Y **crear o modificar el
    CÓDIGO** de un widget escalando (`spawn`, ALLOW) a una sesión `kind="code"`, que pasa por el gate de
    validación del generador.
  - **NAVEGADOR**: conducir un Chromium real (`nucleo/nav_cli.py`), con el confirm-gate de `nucleo/danger.py`
    delante de lo irreversible.
  - **RED MeshKore**: preguntar al oráculo y encargar a agentes vivos (`nucleo/mesh_cli.py`), solo gratis y
    aplicado en código.
  - **MEMORIA**: leer y escribir (`nucleo/mem_cli.py`) por `remember_external`, con sus gates de precisión.
  - **CONECTORES y MENSAJERÍA**: `push_channel` (CONFIRM) y las tools prestadas del FlashBrain.
  - **MCP**: sus tools se reconocen en el stream (`mcp__*`) y cuentan como pasos normales.
  - **EL FILTRO, que es lo que hace que esto sea seguro y no temerario**: solo acciones DECLARADAS (un widget
    expone su vocabulario, no su interior) · **CONFIRM** delante de lo irreversible · **DENY** para lo que es
    operator-only por semántica (`_DENY_TOOLS`) · Bash acotado a los puentes, nunca pelado (el invariante del
    escritor único de la memoria) · cwd confinado (V2-117) · y el catálogo de tools prestadas crece **con marca
    explícita, nunca por accidente**.
  - **Lo que falta hoy y es un hueco, no una decisión**: no hay forma de **programar un cron/recordatorio** — ni
    puente, ni acción en `_KNOWN_ACTS`, ni tool prestable. Un worker al que se le encarga «recuérdaselo el
    miércoles» no puede, **y lo que hizo fue decir que lo había hecho y escribirlo durable en memoria** (medido
    2026-08-21: `sys_kv` sin ninguna entrada de scheduler y una píldora diciendo «Recordatorio PROGRAMADO … a las
    09:00»). Se cierra como todo lo demás: dándole la capacidad **con su filtro**, no dejándosela fuera. Ver
    `V2-236`.
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
  DeepSeek directo; `susurro` (`openai/gpt-4.1-mini`) y el bucle del
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
  justifica donde una MEDICIÓN lo respalde y esté escrita — y **hoy no hay ninguno**: el 2026-08-19 el operador
  retiró el último (la tarea `i18n` de `memllm`) y fijó que **DeepSeek V4 Pro es el único titular**, en el motor
  y en las pruebas. La medición §12.5 que sostenía esa excepción era sobre v4-FLASH por el BROKER, que es donde
  `thinking:disabled` se acepta y se ignora; por el endpoint nativo se obedece, así que el motivo del descarte
  desaparecía con el cambio de endpoint. Nunca como defecto cómodo, y ya nunca por reputación del proveedor.
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
    otro modelo por el mismo broker (V2-034, A/B de 2026-07-12). Desde el 2026-08-19 el titular es DeepSeek V4
    Pro DIRECTO y **no hay alternativa de otro proveedor ofrecida en la UI** (norma del operador). ⚠️ Esta línea
    llevaba desde el 2026-08-02 nombrando un titular que el propio documento contradecía más abajo: si tocas
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
  del lote (§12.5) eligió entonces un modelo de Anthropic — 100% de cobertura y placeholders intactos en japonés Y
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
- **La autodetección de idioma colgaba SOLO de la voz — un canal de texto se quedaba en inglés para siempre**
  (`i18n/init/detect.py::ensure_for_text` + `nucleo/flash/probe.py`, V2-170, 2026-08-20). El pipeline de LiveKit
  ABRE una instalación nueva preguntando «¿en qué idioma te hablo?» detrás de un modal bloqueante (V2-101); un
  canal de TEXTO no tiene ese turno, así que se quedaba en el defecto de producto (inglés) mientras viviera.
  **Medido en un sandbox limpio —el mismo que corre cada caso de uso—: `{"active": "en", "chosen": false}`, o sea
  que TODA la mitad `__es` del catálogo se ha estado midiendo contra un motor en inglés.** Y el daño no es cómo
  se lee la respuesta: del mismo código de idioma resuelve su locale `nucleo/flash/site_catalog.py`, así que el
  catálogo genético manda un encargo español a `www.opentable.com`, `www.ticketmaster.com` y `www.amazon.com`
  donde `es` daría `www.thefork.es`, `www.entradas.com` y `www.amazon.es`. Hay prueba directa: en la corrida real
  de teatro del 2026-08-19 el worker fue a Ticketmaster y reportó «apenas lista teatro español — solo 2 eventos
  en toda España». Es verdad, y es lo que se ve desde dentro cuando te mandan al país equivocado.
  - **Síncrono, no en segundo plano**: en segundo plano arreglas el turno 2, pero el encargo del turno 1 ya
    salió apuntado al país equivocado. Medido: 5,4 s el turno entero, clasificación incluida.
  - **NO se replica en el provider de voz, y es una GUARDA DE REGRESIÓN**: un lock silencioso ahí competiría con
    la pregunta del modal y podría fijar el idioma antes de que el operador conteste. Hay un test que lo exige.
  - Jamás pisa una elección deliberada (`should_detect()`: con `stt_language` persistido, no vuelve a mirar).
  - Verificado en vivo en sandbox: español → `es` y respuesta en español; inglés → `es` NO, se queda en `en`
    (la mitad que si no pasa por accidente). Tests: `tests/agent_headless/unit/test_first_run_language.py`
    (nodo 2.15). **Sigue abierto**: `resolve_locale` tiene UN solo eje idioma→país, así que un hispanohablante
    en EE.UU. recibe el país equivocado igual; hace falta una señal de PAÍS separada.
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
  `deepseek-v4-pro` DIRECTO; `NAVEGADOR_AGENT_MODEL_STRONG` al atascarse; humano Bézier+jitter; anti-atasco). 
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
  - **Se pregunta EN EL IDIOMA DEL OPERADOR — y el campo es `prompt`, que es lo que enciende el analizador.**
    Corregido el 2026-08-19 el mismo día: el oráculo tiene DOS modos y elige por campo. Con `query` hace
    coincidencia léxica BM25 contra un catálogo en inglés; con `prompt` pasa el texto por su propio análisis.
    `find()` mandaba solo `query`, así que «vuelo de Madrid a Roma» volvía `general` con **0 agentes** —
    y volvía **200**, que se lee igual que «la red no tiene a nadie». Con `prompt`, la MISMA frase en español
    da `bookings.flights` → `aerocast`. No era un problema de idioma: un dominio entero de la red estuvo
    invisible por un campo, y de ahí salió la conclusión falsa (que llegó a estar escrita en tres ficheros) de
    que había que traducir al inglés. Se mandan los dos campos y el encargo va en las palabras del operador,
    que es lo que la doc del plugin decía desde el principio.
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
    fail-open: red caída, sin agente o agente que no contesta degradan al navegador de siempre — hoy hay tres
    agentes vivos y gratis (`roomrover` hoteles, `aerocast` vuelos, `ticketlumen` eventos) y para el resto el
    navegador sigue siendo el camino.
  - **`general` NO es clave de ruta.** Es el cubo del oráculo para «no sé clasificarlo», y es una respuesta
    NORMAL de una consulta que sí sirve: «entradas de teatro en Madrid» → intent `general` → `ticketlumen`.
    Cachear bajo esa clave mandaría el siguiente encargo de fontanero al agente de teatro.
  - **VERIFICADO EN VIVO con un Brain Worker de verdad** (2026-08-19): encargo en español por el dispatcher
    real → el worker leyó el PASO 0, preguntó en español, llamó a `roomrover` con fechas absolutas y entregó
    tres hoteles con precio y enlace en **141 s sin abrir el navegador**. Es el caso
    `book-hotel-night-known__es`, el que se pasó una corrida entera contra el `chal_t=` de Booking.
  - **Dónde está todo lo demás**: el contexto estable (las DOS superficies de la red —agentes vivos y
    clusters—, qué está construido y qué no) en
    **`.meshkore/docs/architecture/zaelar-meshkore-network.md`**, y lo que se va midiendo o queda abierto en
    **`V2-169`**, que es una iniciativa PERMANENTE y no un ticket que se cierra.

- **Un código de idioma inventado no falla: es un idioma** (`i18n/init/detect.py`, V2-251, 2026-08-21). El
  arnés soltó de pasada `i18n.detect: ... locked operator language -> 'it'` — italiano, caso en español. No era
  el clasificador: `_by_llm` leía su respuesta con `re.search(r"[a-z]{2}", …)`, o sea **las dos primeras
  minúsculas de cualquier sitio**. Medido: `It is Spanish (es)` → `it`, `The language is es.` → `th` (tailandés),
  `Language: es` → `la`, `Sure, es` → `su`. **Lo que lo hacía invisible es que todos son códigos ISO válidos**:
  no parece roto, parece otro idioma — y se persiste como elección deliberada, así que `should_detect()` pasa a
  False y no se reintenta jamás. Con `max_tokens=4` el preámbulo se trunca justo en `It is`, así que la forma que
  más falla es la más probable (familia de V2-171). Duele porque el mismo código resuelve el locale de
  `site_catalog`: el encargo sale al país equivocado en el turno 1, que es lo que este módulo bloquea el turno
  para evitar. Regla nueva, **«inequívoco o nada»**: la respuesta limpia ES un código, o hay EXACTAMENTE un token
  de dos letras como palabra entera, o `None`. **Rechazar es el lado seguro y no es callejón sin salida** — no
  persiste nada, `should_detect()` sigue True, el turno siguiente reintenta; un bloqueo erróneo es mudo y
  permanente, uno rechazado cuesta un reintento (mismo criterio que V2-248 con el `ref` y V2-249 con las fechas
  ambiguas).
  - **Descartada la vía obvia**: validar contra una lista NO habría cazado nada — `it`/`th`/`la`/`su` son códigos
    reales, y `langs.supported()` da solo `en`/`es` mientras el sistema genera bundles bajo demanda, así que la
    validación habría roto el multi-idioma legítimo. Hay un test que guarda ese razonamiento para que nadie lo
    «mejore» metiendo un whitelist.
  - **Alcance acotado por el arnés ANTES del arreglo**: 65 de 66 rondas guardadas bloquearon `es` bien; la única
    `it` fue la que corrió con los proveedores caídos. El clasificador solo contesta con una FRASE cuando el
    modelo está degradado o relevando → **ninguna medida del tablero quedó contaminada**.
  - Nodo 2.15, 9 casos rojos con el parseo viejo. **Sin verificar en vivo.** Lo cogió memoria-dev fuera de su
    territorio por decisión del orquestador: **el dueño de un arreglo es quien tiene la evidencia**.

- **Un informe de lo que ya pasó no es una orden** (`frontend/app/services/sse.js`, V2-261, 2026-08-21). El
  operador vio en pantalla una tarjeta de navegador BASE y vacía apareciendo ENCIMA de la real, dos segundos
  después. No la abría nadie: era un **eco del propio canvas**. `desktop._persist()` informa del conjunto
  abierto, `voice_api.canvas_state` NORMALIZA `navegador::t2` a `navegador`, el diff dice «se ha abierto
  navegador» y emite `widget/show src=user` — la auditoría de V2-039 — **por el mismo canal que las órdenes**.
  Evidencia: `['navegador::t1'] → ['navegador::t1','navegador']`, siempre 2 s después.
  - **Estaba VISTO y solo instrumentado**: el comentario de `voice_api.py` cita «V2-047 F9 (two browsers, one
    blank)». Se añadió el evento para poder mirarlo y nunca se cerró.
  - La regla: **el canvas nunca obedece su propio informe**; `src:"user"` marca lo que NACE del canvas, y quien
    lo mandó es quien no tiene nada que hacer con ello. Se corta en `sse.js` —único punto por el que pasan
    escritorio y móvil (contrato del nodo 4.18)— y NO en la ruta: la auditoría tiene que seguir emitiendo con su
    etiqueta o se mueve la taxonomía de familias con la que se está midiendo.
  - **Filtra `show` y `close`, no `data`**: `data` es un aviso de repintado, y filtrarlo dejaría una hoja
    abierta sin refrescarse — un fallo mudo. Hay un desarme que separa filtrar de menos de filtrar de más.
  - Era mío además de del navegador: V2-259 acababa de instanciar la hoja, así que sin esto habría heredado el
    mismo fantasma. Nodo **4.37**, que MONTA el manejador en vez de leer la fuente.

- **Dos búsquedas son dos hojas, y estrenar deja de significar borrar** (`widgets/results/data.sheet_key`,
  V2-259, 2026-08-21). Petición del operador: *«si tenemos un widget de results abierto, búsqueda terminada, y
  lanzamos otra, se abre un widget nuevo. Con esta regla no cometeremos errores de borrar búsquedas.»* Y **el
  borrado que temía estaba en el código, con su comentario**: la hoja era UNA clave (`store.load(WIDGET_ID)`) y
  `_sheet_open` llamaba a `begin_task(fresh=True)`, que la estrenaba —sin resultados ni historial— en cuanto
  llegaba el encargo siguiente. La alternativa, reutilizarla, enseñaba los resultados de la búsqueda anterior
  bajo el título de ésta. Ninguna de las dos era buena, y las dos estaban medidas.
  - **La clave es el ENCARGO, no el navegador**: continuación exacta de V2-257 (la tarjeta MUESTRA, N; la hoja
    GUARDA, una). Dos navegadores de la misma búsqueda siguen cayendo en la misma hoja.
  - `sheet_key("")` sigue siendo `results` **byte por byte**, así que no hay migración ni queda un linaje
    huérfano compitiendo (la trampa de V2-242). El disco usa `--` porque `store._safe_id` no admite `::`; el
    canvas sigue usando `::`, que es lo que `desktop.js` sabe partir. Y `view_data(q)` no cambió de firma: **ya
    recibía el sufijo y lo ignoraba**.
  - **`fresh` dejó de ser una decisión difícil**, y el relato pasa a ser de cada uno
    (`dispatch.sheet_progress(task_id)`); la hoja SIN encargo detrás conserva el entrelazado, que para ella
    sigue siendo la respuesta honesta. **El puente resuelve la instancia, no el worker**: el prompt le dice
    «entrega en `results`» y `worker_api` le pone el `sheet` de su encargo — pedirle el id sería una forma nueva
    de equivocarse.
  - **El cerebro ve TODAS las hojas** y cada bloque dice de cuál es: «la número dos» con dos búsquedas en
    pantalla son dos cosas distintas, y leer una sola habría hecho contestar con seguridad sobre la que no era.
  - ⚠️ **Y un defecto que ESTE cambio sí introdujo, cazado en la primera medida en vivo**: la clave de la hoja
    era el `task_id`, y `escalate._seq` **arranca en 0 en cada proceso**. Tras un reinicio, el primer encargo caía
    en `results--1` —la hoja de la sesión anterior— y `begin_task(fresh=True)` la estrena, o sea **la borra**: el
    «error de borrar búsquedas» reintroducido por la puerta de atrás. El id lleva ya un sello de PROCESO
    (`dispatch.sheet_id_for`) y se guarda UNA vez en el record, como la superficie. `sheet_of()` NO lo reconstruye
    desde el `task_id`: un encargo cuya hoja nunca se abrió no tiene hoja.
  - ⚠️ **Un bug que este cambio iba a introducir**: `desktop.js::close` cancelaba la tarea de CUALQUIER tarjeta
    con `::`, con `w.base||"navegador"` de reserva — daba por hecho que la única pieza instanciada era el
    navegador. **Cerrar una vista no cancela un encargo.** Nodo **4.36**, 15 casos, sensibilidad en siete
    direcciones. **F3 construida aparte** (`widgets/instances.py`, nodo **4.38**): «cierra los
    resultados» con dos abiertas PREGUNTA cuál, **nombrando los encargos y no los ids** — y la pregunta tiene que
    poder contestarse, así que dos hojas que se titulan igual se desambiguan en vez de repetirse. Es una
    ambigüedad de OTRO EJE que la de `runtime.identify()`: aquella decide qué PIEZA, ésta cuál de sus TARJETAS.
    La regla vive UNA vez aunque `nucleo.py` cierre desde TRES puntos, y **preguntar cuenta como actuar**: si el
    fallback devolviera False, el login-fallback se llevaría el turno como si nadie hubiera hecho nada. La fontanería que faltaba:
    `open_widgets` guarda las BASES —correcto, el estado del cerebro habla de piezas— así que hizo falta
    `voice_api.open_instances()`; vacío significa «no lo sé» y se cae al comportamiento de siempre.

- **El navegador MUESTRA y la hoja GUARDA** (`widgets/results/intake.py`, V2-257, 2026-08-21). Petición del
  operador con su captura delante: la tarjeta del navegador pintaba cinco «resultados» que eran los botones del
  pack local de Google («Sitio web», «Cómo llegar») y un log de dieciséis eventos, bajo una cabecera que decía
  «Navegador» y no identificaba nada. Al mirarlo salió el fallo estructural que hay debajo: un encargo
  `kind:"web"` resuelve `surface = LIST`, así que `dispatch._sheet_open()` **le abre la hoja de resultados
  delante en cuanto encarga** — y nadie escribía en ella. Los TRES caminos por los que el navegador encuentra
  algo (`act_api._hand_over`, `owner._automate`, `dispatch._finalize_web`) terminaban en `tasks.set_results()`,
  que escribe la TARJETA.
  - **La asimetría que lo explica**: `_METHOD_BLOCK` enseña la hoja —con su contrato y sus dos pasos— al worker
    GENÉRICO desde siempre; el prompt del worker WEB no la nombraba **ni una vez** (contado sobre el texto
    renderizado: `widget_cli` 0, `results` 0). La misma petición llenaba la hoja o no según a qué worker se
    enrutara, y las que abren un navegador caen justo en el que no lo sabía.
  - Así que el `missing_signals: ['widget']` de V2-223 **nunca fue un fallo de extracción: no había puerta**. Y
    el test de entonces se llamaba `..._lands_in_the_results_sheet` mientras assertaba `tasks.get()["results"]`
    — el nombre decía la intención y el código medía otra cosa. Renombrado.
  - **La frontera**: `navegador` = MONITOR de UN navegador (título de la TAREA en la cabecera vía `live_title`,
    la captura, y el estado en 3 líneas deduplicadas), **N tarjetas**; `results` = los hallazgos de todos,
    **UNA hoja**. Es la única que escala: por tarjeta, dos navegadores parten los resultados en dos cajas que no
    se pueden comparar; todo junto acaba en un widget único e imposible.
  - **Una puerta, tres caminos** (`widgets/results/intake.push`), y `append` nunca `present` —el segundo
    navegador borraría al primero—, con la FUENTE viajando con la fila y el `tel` a `facts` (V2-240: en un
    encargo de servicio es el dato que resuelve). El HECHO se queda en la tarea: `has_results` es lo que el
    prompt lee (V2-192/V2-200) y quitarlo habría sido la regresión.
  - **El test rojo mejoró el arreglo**: el invariante de V2-192 («un `set_results` tiene su final a menos de 700
    caracteres») se puso rojo al meter la entrega EN MEDIO. En vez de ensanchar la ventana, la entrega pasó
    DESPUÉS del cierre — y de paso quedó fuera el caso `cancelled`: si el operador dijo que parásemos, no le
    llenamos la hoja. Nodo **4.35**, 16 casos, sensibilidad en ocho direcciones. **Sin verificar en vivo.**

- **Un formulario que calla no se distingue de uno que funciona** (`frontend/app/services/feedback-state.js`,
  V2-256, 2026-08-21). El operador mandó una sugerencia y la pantalla no dijo NADA. La respuesta existía y era
  precisa —`{"ok":false,"error":"send_failed","status":401}`, reproducido en su motor vivo— y `send()` la tiraba:
  era `if (res && res.ok) { … }` sin `else`. La clave `feedback.sendError` YA estaba traducida a los dos idiomas
  **y no la usaba nadie**.
  - **El gracias tampoco se veía nunca, por DOS causas independientes** (desarmadas por separado; cada una pone
    rojo un check distinto). Una: `justSent() ? h(…) : null` como HIJO — en este hyperscript un hijo reactivo
    tiene que ser una FUNCIÓN, así que el ternario se evaluó UNA vez al construir el árbol, leyó `false` y no
    añadió nada; ningún `setJustSent(true)` posterior podía poner un nodo ahí, sin error en ninguna parte (el
    canvas desconectado de V2-124, otra vez). Dos: **el gracias vivía en la pestaña de la que te sacan** — un
    envío correcto salta a «Enviadas», que pone `display:none` sobre `.fw-new`. Arreglar solo una de las dos
    seguía enviando un formulario que no confirma nada.
  - **Una lista inalcanzable no es una lista vacía.** `listFeedback()` degrada a `{ok:false, items:[]}` y la
    pestaña pintaba «todavía no has enviado nada»: no es una verdad más pequeña, es otra y falsa.
  - **Cuarta regla duplicada de la semana**, y esta vez la copia buena era la del MÓVIL: `MenuSheet.js` sí tenía
    la rama de fallo. Ahora las dos superficies leen la respuesta por el mismo módulo y hay un test que falla si
    alguna vuelve a mirar `.ok` por su cuenta. Ojo con la recaída: la primera versión de este parche volvía a
    derivar la clave del estado vacío dentro del widget, y salió VERDE hasta el desarme D — **reintroducir la
    duplicación dentro del arreglo que la elimina es fácil**.
  - **La línea visible nombra el hecho**: la frase traducida más «(401)». Un paréntesis, nunca una traza; el
    `send_failed` genérico no se muestra y un `status:"received"` de un cuerpo de ÉXITO no es un código HTTP.
  - Nodos **4.33** (decisión + cableado) y **4.34** (RENDERIZADO en Chromium: conectado, con caja, no
    transparente, y texto traducido — `t()` devolviendo la clave es truthy y pasa cualquier test de fuente).
    Sensibilidad en ocho direcciones. **Esto NO hace que el envío LLEGUE**: cierra la ceguera del motor, no el 401 que devolvió el extremo
    de ingesta. Por qué lo devolvió no es asunto de este repo.

- **Para vigilar el ARTEFACTO, el artefacto tiene que contener lo que se comprueba** (`voice/observer.py` +
  `widgets/navegador/agent.py`, V2-255, 2026-08-21). V2-254 dejó abierto que nada impide una CUARTA copia de la
  regla de las píldoras, y el arnés propuso la señal buena: **no vigiles a los ESCRITORES, vigila el ARTEFACTO**
  — todas las superficies terminan en un prompt que sale hacia un modelo, y eso ya se graba (`turn_detail`, el
  único punto que cierran los DOS canales). Faltaba una cosa: **el artefacto no contenía la parte que se
  comprueba.** Medido: el bloque de recall cae en el carácter **2.896** de un prompt de 16.585, a 104 de la
  cabeza de 3.000 — y en un turno real van delante el estado cacheado y la conversación reciente, así que se cae
  siempre. Un verificador diría «limpio» sobre un prompt sucio: **un techo solo es peligroso si el lector acepta
  prefijos**, aplicado al registro. Cabeza a 6.000, sin tocar la cola (el estado vivo, V2-195), y **el hueco se
  sigue nombrando** — eso permite decir «no puedo certificar» en vez de «limpio».
  - Y el suceso de V2-253 sale ya por **`tool_dropped`**, el canal que nació en V2-171 para exactamente eso en el
    FlashBrain. El navegador tenía el mismo suceso y lo contaba solo en sus pasos: **para un instrumento de
    fuera, no ocurría**. Misma forma de evento a propósito — quien ya lo consume no cambia nada. Nodos 2.4 y 4.2,
    sensibilidad en tres direcciones.

- **La regla estaba escrita en TRES sitios y aplicada en UNO** (`nucleo/flash/prompt.py`, V2-254, 2026-08-21).
  El arnés mandó un dato suelto —el agente buscó «fontanero **Soria**» con `operator.location` = «Vive en el
  centro de Madrid»— y de ahí salieron tres arreglos en cadena: V2-242 cerró la ESCRITURA, memoria-dev cerró el
  DOSIER… y seguía saliendo, porque faltaba la tercera superficie: **el recall activo, el que corre CADA TURNO**.
  Medido con los dos anteriores dentro: «Weather in Soria now: 14.5C» **por encima** de «Vive en el centro de
  Madrid», bajo «puede que venga a cuento (de tu memoria)».
  - **La lección no es el arreglo**: es la misma forma que V2-252 y V2-253 — **el fallo no fue la regla, fue
    tenerla repetida**. Aquí se APLICA la que ya existe (`memory.api.background_slot_off_topic`, con UNA casa
    desde `a2b791c`) en vez de escribir una cuarta copia.
  - **Condicional, no censura**: si el operador nombra el tema, la píldora entra (promesa de la auditoría de
    2026-07-14), y hay un caso que se pone rojo si alguien lo convierte en un filtro ciego. Y **fail-soft con
    dirección**: si la regla no se pudiera importar se enseña de MÁS, nunca de menos — quedarse sin recall es
    peor que enseñar de sobra. Nodo 2.4, 10 casos, sensibilidad en dos direcciones.
  - **Abierto**: nada impide una CUARTA copia. Un trinquete tendría que saber qué superficies renderizan
    píldoras a un modelo, y esa lista es justo la que se demostró incompleta tres veces.

- **Unos argumentos ILEGIBLES no son una acción sin argumentos** (`widgets/navegador/agent.py`, V2-253,
  2026-08-21). Sale de la regla que el cluster adoptó ese día (propuesta de memoria-dev): **un techo solo es
  peligroso si el lector acepta PREFIJOS**. Barridos los del motor con ese criterio, los lectores son seguros
  —`attention._parse_directed` y `segmenter._parse_judge` exigen el objeto entero y caen a un default— **menos el
  que conduce el navegador**: `_next_action` devolvía el NOMBRE de la acción con `{}` cuando su JSON no parseaba,
  y el bucle ejecutaba `click` sin ref, `type` sin texto o `navigate` sin url. Es la familia de V2-171 y **peor,
  porque no se descarta: se ACTÚA**, sobre una página real y con el argumento inventado por omisión.
  - Ahora no se ejecuta, y **se distingue quién lo rompió**: el TOPE es nuestro (se sube) y unos argumentos
    inválidos son del modelo (se reintenta) — «no emitió acción» tapaba las dos y mandaba a mirar al modelo
    cuando el culpable era nuestro. Un `{}` legítimo (`snapshot`, `back`) sigue valiendo.
  - Nodo 4.2, 9 casos, **con el barrido clavado**: dos comprueban que los otros lectores siguen exigiendo el
    objeto entero — si alguno se relaja, su techo se vuelve peligroso sin que nada falle.

- **El canal de TEXTO no relevaba — y era la TERCERA vez que `probe.py` se separaba del provider de voz**
  (`nucleo/flash/provider_failure.py` NUEVO, V2-252, 2026-08-21). Tuvo al arnés **ocho horas sin poder medir**:
  con la cadena real sembrada, un turno devolvía `402 Insufficient Balance` **en el mismo segundo** en que el log
  decía «`deepseek-directo` SIN SALDO → relevo a `aimlapi-failover`». La voz relevaba, i18n relevaba, el texto
  no. No faltaba la política: faltaba aplicarla.
  - **Lo estructural lo trajo memoria-dev**: `probe.py` es la implementación PARALELA del provider de voz y el
    arnés corre por ese canal. Ya mordió el 2026-08-18 (`22f3674`: las tags `[[cron.create]]` se capturaban y no
    se ejecutaban → mecanismo INALCANZABLE para lo que se midiera) y el 2026-08-15 (el relevo por fallo duro se
    añadió a la voz y no aquí). **Dos copias de una decisión se separan sin avisar, y el aviso llega cuando
    alguien mide algo que sale mal por un motivo que no es el que mide.** Así que la decisión —atasco vs fallo
    duro, a qué escalón, si queda alguno— vive en UN sitio y la leen los dos; lo que NO se comparte es qué dice
    cada canal.
  - **El reintento con sus dos frenos**: un intento, un relevo, un reintento (como el canal de cluster desde
    2026-08-03), y **solo si el turno no había dicho nada** — repetirlo tras haber hablado lo diría dos veces.
  - **Segunda trampa, del arnés**: hay DOS fuentes de «quién es el titular» — el turno usa `spec_from_config()`
    (`fast.model`/`fast.base_url`) y la cadena se ordena por `fast.providers`; reordenó la escalera y no cambió
    nada. Como `note_failure` sin `tier` pregunta a `pick()`, **el cooldown podía caer sobre un proveedor SANO
    dejando elegido al roto**. Ahora se pasa el `spec` y el culpable se resuelve por su `base_url`; si el
    endpoint no está en la cadena **no se inventa un culpable**.
  - **VERIFICADO EN VIVO** por el arnés (desbloqueado, midiendo). Nodo 2.4, 16 casos, sensibilidad en cinco
    direcciones. Las guardas de cableado son el corazón: un test sobre el predicado habría pasado en verde las
    tres veces.
  - **Abierto**: `fast.model` y `fast.providers[0]` pueden discrepar y nadie avisa — unificarlas toca la config
    del operador.

- **Un solo reloj para el «hoy» que se le DICE al worker** (`nucleo/dispatch_prompts.py`, V2-250, 2026-08-21).
  Salió de un aviso de método a memoria-dev: él auditó su lado y encontró que la agenda del dosier filtraba con
  `date.today()` (`75f2a34` — replay a 2026-03-10, cita a 6 días por delante, **agenda VACÍA** porque
  `date.today()` decía 2026-08-21 y toda fecha futura se leía como pasada). La misma forma estaba aquí, y en el
  peor sitio: **`_today_block()` es el bloque que le dice al worker qué día es**, y leía el reloj de PARED
  mientras todo lo que resuelve un momento en este motor pasa por `scheduler.time.time()` (`parse_when`,
  `next_cron`, y por eso `router_guards` lo lee explícitamente: «ONE clock»).
  - Con los dos relojes de acuerdo —producción— no se nota. Al medir sí, y aquí es **peor que en el dosier**: no
    filtra datos, **le dice al modelo la fecha equivocada**, y todo lo que razone con «hoy» sale mal sin que nada
    falle. Nodo 2.5, 5 casos con las DOS direcciones (sin reloj fijado tiene que ser el de pared — si no,
    «seguir al reloj del motor» se satisface con cualquier fecha fija) + guarda de fuente contra el `strftime()`
    sin argumento.
  - ⚠️ **Impacto real, acotado por el arnés y corrigiendo lo que escribí**: dije que sus medidas sobre «el
    último / de hoy» estaban tomadas contra una fecha equivocada, y **no le afecta** — su arnés NO usa replay ni
    congela el reloj, así que sus rondas corren en tiempo real, que es justo el caso en que los dos coinciden.
    Hoy esto **no arregla ningún fallo en producción ni ninguna medida ya tomada**: cierra una divergencia de
    relojes que paga quien FIJE el reloj (los tests de memoria) y pagaría entero un replay el día que exista.
  - **Queda por mirar** `widgets/agenda/planner.py` (`datetime.now()` para el día de la semana): en producción
    acierta y al medir no, pero es del widget y quiere su propia medida.

- **La píldora que se auto-avala: un aviso PROGRAMADO existe de verdad, o no se dice** (`worker_policy.py` +
  `worker_api.py` + `dispatch_prompts.py`, V2-249, 2026-08-21). El hallazgo más viejo de los que seguían
  abiertos: el worker escribía en memoria, de forma durable, «Recordatorio PROGRAMADO … a las 09:00» **sin
  ninguna entrada de scheduler**. No era desobediencia — probado en el CÓDIGO: `_KNOWN_ACTS` no tenía ninguna
  acción de agenda, así que le era IMPOSIBLE. El camino del FlashBrain sí funcionaba; el agujero se abría solo al
  ESCALAR a un worker.
  - **El encuadre es del operador y corrige el que puse yo**: escribí que era una decisión de seguridad
    pendiente, y no: **un Brain Worker ya hace casi de todo** y la seguridad aquí **es un FILTRO**, no una lista
    corta de permisos. La pregunta no era «¿debería poder?» sino **«¿cuál es su filtro?»**.
  - El filtro: **ALLOW** (a diferencia de `push_channel`, que sale HACIA FUERA y no se deshace; un aviso es
    interno, visible y cancelable) · **tope de 3 POR TAREA**, contado por atribución sobre las tareas vivas ·
    **atribuido** (`[worker:<task_id>]` en el nombre) · y **lo ambiguo NO se adivina**: `parse_when` devuelve ""
    adrede ante «esta tarde», y *un aviso sobre una fecha inventada es peor que ninguno*.
  - **Dos parsers y en ese orden**: `parse_schedule` para las formas de máquina y `parse_when` para las habladas
    — el worker escribe como habla.
  - ⚠️ **La primera versión enseñaba «in 2 hours» en el prompt y NO parsea**; lo cazó el test al escribirlo. Es
    V2-219 otra vez, así que ahora un caso comprueba **cada ejemplo que se enseña contra el parser** y otro exige
    que la lista del prompt y la del error sean la MISMA. Nodo 2.5, 17 casos, sensibilidad en cuatro direcciones
    —una de ellas: **una capacidad que el modelo no sabe que tiene no existe**.
  - **Cierra UNA instancia, no la CLASE** (lo señaló memoria-dev): la memoria guarda como hecho durable una
    afirmación del SISTEMA sobre sus propios efectos, y mañana el recall la confirma. `remember_external` veta lo
    que dice un TERCERO y el gate de REM contrasta un insight con sus píldoras; **nada contrasta una píldora con
    el mundo**. La mitad que pone quien EJECUTA es dejar la PRUEBA: la respuesta trae `ref: "cron:<id>"` y se
    emite una fila `⏰ aviso programado` con el id real — y un aviso que NO se pudo poner **no deja fila**, porque
    esa línea sobre algo que no ocurrió es la misma mentira con más autoridad.
  - **Abierto**: no hay `cancel` — un worker pone un aviso y no lo quita.

- **Un `ref` caducado decía QUÉ pasaba y no CÓMO salir** (`widgets/navegador/owner.py`, V2-248, 2026-08-21).
  **Tercera y última** causa de muerte por cuenta propia de las que dejó abiertas V2-236 (las otras: V2-241 y
  V2-247). Medido: `ref 26 no existe`, la forma de V2-212. El mensaje era `ref 26 no existe en el snapshot
  actual` — **verdad y no sirve**: no dice cuántos refs hay, ni que la página haya cambiado, ni que la salida
  está a un comando (`look`). Mismo contrato del nodo 4.20 y de V2-203.
  - Tres mensajes según lo que pasó: **no has mirado nunca** · **la página CAMBIÓ** (se guarda la URL de la
    mirada; ahí el motivo no es que el número esté mal escrito) · **ref fuera de rango** (con el rango real). Y
    en los tres, la prohibición explícita de repetir: la reacción natural del modelo ante un fallo es repetir, y
    aquí repetir no puede funcionar nunca.
  - ⚠️ **NO se reintenta solo con la mirada nueva.** Parece la mejora obvia y es un fallo de SEGURIDAD: los
    números se REPARTEN al mirar, así que el mismo número es otro elemento — en una página con botón de pagar,
    clicar otra cosa. Clavado por una guarda de fuente porque es la clase de «optimización» que alguien añade de
    buena fe. Nodo 4.2, 9 casos, sensibilidad en dos direcciones.

- **Traer el elemento a la vista es una CORTESÍA, no el clic** (`widgets/navegador/dom.py`, V2-247, 2026-08-21).
  De las causas de muerte que V2-236 dejó abiertas: **tres `scroll_into_view_if_needed` con Exit code 1 en un
  mismo worker**, y ese worker muerto. La llamada iba **sin proteger** al principio de `_human_click_handle`, así
  que un elemento tapado, dentro de un acordeón cerrado, sin layout o despegado a mitad se llevaba por delante la
  acción ENTERA — aunque el clic siguiera siendo posible, porque `h.click()` de Playwright hace su propio scroll
  y su propia espera.
  - **Por qué existe la cortesía** (y por qué no se borra): el clic humano se da en COORDENADAS —curva de Bézier
    con jitter—, así que el elemento tiene que estar en pantalla para que el ratón caiga donde el usuario lo
    vería. Cuando no se puede, se clica por la vía normal: **se pierde el disfraz, no la tarea.**
  - `bounding_box()` igual (sobre un handle despegado revienta), y `_human_type_handle` hereda la protección: no
    poder traer a la vista dejaba sin escribir un campo que se podía rellenar. Nodo 4.2, 6 casos, sensibilidad en
    dos direcciones —una de ellas comprueba que el camino bueno SIGUE siendo humano.

- **Un escalón que se atasca SIEMPRE no se penalizaba nunca** (`nucleo/flash/provider_chain.py`, V2-246,
  2026-08-21). El arnés sembró la cadena real en su sandbox (cerrando V2-244) y el relevo **entró**: «SIN SALDO →
  relevo a aimlapi-failover». Y el turno seguía mudo. Probado contra AIMLAPI con la clave del operador:
  `deepseek/deepseek-v4-flash` **TIMEOUT a los 75 s** —el modelo del escalón de failover— y
  `deepseek/deepseek-v4-pro` en 18,3 s. El escalón de socorro apuntaba al modelo que el broker no servía.
  - **El agujero es nuestro y lo dejan dos mecanismos entre medias**: `note_slow` vive en el camino de la
    RESPUESTA (solo ve turnos que acabaron) y `note_failure` **se salta a propósito** cuando el turno se atascó
    (un atasco suele ser pasajero). Entre las dos, el turno se corta, se dice «se atascó y lo corté», y el
    siguiente vuelve al MISMO escalón. Para siempre.
  - `note_stall()` con la MISMA política que los lentos: dos atascos SEGUIDOS, racha compartida con `note_slow`
    (un turno bueno la rompe), mismo cooldown corto y mismo techo de turnos. Si el atascado es el último escalón
    no se castiga — quedarnos sin proveedor es peor. Nodo 2.4, sensibilidad en tres direcciones.
  - **No arregla la config del operador**: su failover sigue apuntando a `-flash`. Esto hace que se releve en vez
    de quedarse mudo.

- **Callar un escalón es legítimo; callar QUE LO CALLAS, no** (`nucleo/flash/provider_chain.py`, V2-244,
  2026-08-21). El arnés midió dos líneas seguidas —`memllm[i18n]` relevando a AIMLAPI y el cerebro de voz
  diciendo «SIN RELEVO disponible» en el mismo segundo— y concluyó que el cerebro es el único componente sin
  relevo. **Es falso en la máquina del operador**: su `fast.providers` tiene DOS escalones (`deepseek-directo` +
  `aimlapi-failover`). La pista estaba en su propia línea: el escalón que falló se llama **«titular»**, y ese
  nombre solo lo genera `_voice_chain()` **cuando no hay lista explícita** — el sandbox pone `ZAELAR_WORKSPACE`
  nuevo, así que `config/v2` va vacía. **Forma inversa a la de `meteo-soria`**: aquello parecía sandbox y era
  producto; esto parecía producto y era sandbox.
  - **Lo real**: un self-host recién clonado tiene la cadena de voz = solo el titular, así que un titular muerto
    deja el producto mudo con «SIN RELEVO disponible» a secas. **La regla no se toca** (es del operador y su razón
    está escrita); lo que se añade es NOMBRAR lo callado, con la frase que lo activa (`fast.providers`). Dos
    frenos: un escalón **sin credencial** no está callado, no existe; y uno **ya en cooldown** no es una salida —
    `deepseek-directo` usa la MISMA cuenta que se quedó seca.
  - ⚠️ Un test de esto falló al escribirlo **por leer la config REAL de la máquina** y habría quedado verde por el
    motivo equivocado: de ahí `_sin_lista_explicita()`. La misma trampa, dos veces en una hora.
  - **Decisión del OPERADOR**: si AIMLAPI entra en la cadena de voz POR DEFECTO. Los relevos de fábrica se
    eligieron por LATENCIA y **ninguno sirve para SOBREVIVIR a un titular muerto**.

- **246 tests verdes que ninguna suite ejecutaba, y TRES formas de desaparecer** (`tests/run_testmap.py` +
  nodo 7.17, V2-245, 2026-08-21). Mencioné de
  pasada que `test_brain_relay.py` estaba fuera del mapa; memoria-dev auditó la suya (37 sin mapear), los cerró y
  **me devolvió la trampa**: colgar un fichero de un nodo `live` lo SACA de CI (`deterministic_paths()` los
  salta), así que mapear al nodo equivocado se parece mucho a no mapear. En mi área: **14 ficheros, 183 tests**,
  todos verdes e invisibles — **incluidos los que acababa de escribir para V2-243**, o sea que no estaban
  cubiertos por el «suite verde» que reporté. Y uno llevaba **ROTO desde V2-098** (`pc._cooldown` dejó de existir
  al pasar a `CooldownStore`): sus tres casos reventaban en el `setup` sin que nadie lo viera. La suite pasa de
  **3.284 a 3.467**.
  - **La TERCERA forma, y es del arnés**: `deterministic_paths()` filtra por la unión de los `domain_ids` de las
    suites, así que un capítulo que ninguna reclame se cae entero. `tests/use_cases/suite.json` lleva
    `"domain_ids": []` → **sus 36 tests no los corre nadie**, justo los que garantizan que sus MEDIDAS son de
    fiar. Entregado medido y **sin tocar**: es su frontera.
  - **El trinquete existe** (nodo 7.17) y comprueba las TRES: declarado · nodo no-`live` · capítulo reclamado por
    alguna suite. Uno que solo mirara PRESENCIA certificaría el fallo que existe para evitar. `tests/use_cases/`
    queda fuera con su motivo escrito hasta que su dueño dé el OK — un guarda que otro no espera es un guarda que
    se salta a la primera— y la lista de exclusiones existe para ADELGAZAR.

- **Un SALDO agotado no es una cuota, y quedarse sin proveedor no es un tropiezo** (`nucleo/workers/providers.py`
  + `flash/provider_chain.py` + `voice/engine/llm/providers/nucleo.py`, V2-243, 2026-08-21). Medido en
  PRODUCCIÓN, no en un banco: el arnés paró de medir a las 02:28 con `Insufficient Balance` (DeepSeek, HTTP 402)
  ×2, anunciado como **«sin cuota hasta el 21 Aug 03:02 · SIN RELEVO disponible»**, y su canario —que había
  pasado dos veces una hora antes— **mudo en todos los turnos**. Dos defectos de redacción, los dos caros porque
  cambian lo que el operador HACE:
  - **«Sin cuota hasta las 03:02» es falso.** Una cuota anuncia cuándo vuelve y vuelve sola; un saldo no vuelve
    hasta que alguien recargue. Y heredaba el suelo de 30 min, así que cada media hora se gasta un turno (o un
    worker) redescubriendo que la cuenta está vacía. Ahora: predicado `is_depleted` **aparte** de
    `classify_failure` (que comparten las dos cadenas y devolvería `None` ante un valor nuevo — misma razón que
    `is_context_overflow`), cooldown de 6 h, y el aviso dice **«SIN SALDO — no vuelve solo, hay que recargar»**.
    **La ausencia de fecha es parte del predicado**: un forfait que dice «insufficient credit … reset at …»
    vuelve solo, y apagarlo de más es perder el escalón preferido.
  - **«¿Me lo repites?» es una mentira cuando no queda ningún proveedor.** Es la frase correcta ante un tropiezo;
    con la cadena seca el operador se queda repitiéndose a una máquina que no puede contestarle, sin enterarse de
    lo único que lo arregla. El turno pregunta `pick(ROLE_VOICE) is None` y lo dice.
  - ⚠️ Un test existente usaba «insufficient credit» como ejemplo de «cuota sin fecha» y este cambio lo convierte
    en el OTRO caso: se le cambió el ejemplo, no la intención. Nodos 2.4/2.5, sensibilidad en tres direcciones.
  - **Ojo**: 3 tests de `tests/cluster/unit/test_brain_relay.py` están ROTOS y **no están en el testmap** desde el
    refactor de V2-098 (`pc._cooldown` ya no existe). Fallan igual sin este cambio. Es V2-158 otra vez.

- **Una píldora de fondo no es un hecho sobre la persona** (`widgets/background.py`, V2-242, 2026-08-21). El
  arnés midió en `best-plumber-same-day` que `weather:soria` (`mid/note`, importancia 0,3) le ganaba a
  `operator.location` (`long/profile`, «Vive en el centro de Madrid») y el worker buscó **«fontanero Soria»** tres
  veces seguidas. La píldora la escribe cada hora `widgets/meteo-soria`, que **viaja TRACKED en el repo público**:
  no es memoria sucia de un test, es la que tiene cualquiera que clone.
  - **La LECTURA la cerró memoria-dev** (`memory_agent.compose_context`, `39e68a7`): un slot con namespace no
    entra en el dosier del worker salvo que la tarea lo nombre.
  - **Esto cierra la ESCRITURA.** Los lectores separan «hechos del operador» de «píldoras de fondo» **por la
    FORMA DE LA CLAVE** —puntos para la persona, namespace para el fondo— y nada impedía que un tick escribiera
    `operator.location`, ni que una nota **SIN slot** cayera bajo «LO QUE SABES DEL OPERADOR» (sin `:` no la
    filtra nadie) acumulándose además sin sustituir. **Una convención sin candado es una promesa**, y el sitio
    donde ponerlo es el único que SABE que el autor es un trabajo de fondo.
  - **En la CLAVE y no en `meta['widget']`**, por medida de memoria-dev: el retriever **no devuelve meta**. Probó
    la forma exacta — `meteo-soria:weather:soria` fuera de «busca un fontanero», DENTRO de «el tiempo en Soria».
  - **Las píldoras ya escritas** las migró memoria-dev (`6945496`, v5→v6). Su trampa era más concreta que la
    sospecha: cambiar la clave sin migrar deja **DOS linajes VIVOS** (`weather:soria` 14,5 °C y
    `meteo-soria:weather:soria` 21,0 °C, las dos `valid=1`) y la vieja sigue compitiendo en recall. Y el espejo de
    `_own_slot` en la migración **no es deriva**: una migración congela la regla de SU versión.
  - **Sigue pendiente de decisión del OPERADOR** si esos widgets personales —dos de ellos dicen dónde vive—
    deben viajar en un repo público. Nodo 4.1, 9 casos, sensibilidad en dos direcciones.

- **La puerta avisaba UNA vez y el worker chocó TRES** (`nucleo/workers/session.py`, V2-241, 2026-08-21). De la
  evidencia abierta de V2-236: uno de los workers muertos chocó **tres veces** con nuestra propia puerta de
  permiso. V2-211 puso la red —si choca, se le explica cómo reescribirlo— pero se disparaba **una vez por
  sesión**: del segundo choque en adelante nadie le decía nada y murió en silencio, justo lo que la red existía
  para evitar. Y la corrección **no nombraba el comando**, solo repetía las reglas del cajón — una regla general
  no le dice CUÁL de sus comandos sobra.
  - Ahora se corrige **cada** choque hasta un tope de 3 (los medidos), la corrección **nombra el trozo que la
    puerta paró** (`denied_fragment`, las tres formas del CLI) y **no se inventa ninguno** si el texto no lo dice.
  - **El tercer aviso cambia de mensaje**: deja de corregir y pide ENTREGAR lo que tenga — la diferencia entre
    una tarea incompleta y una tarea muda. Y luego se calla: un bucle de avisos se come el contexto que le queda.
  - **Un final sin entrega tras chocar lo DICE**, nombrando el comando: no es un fallo de la tarea, es que la vía
    está cerrada aquí, y eso el operador sí puede resolverlo. Sin pisar una entrega real ni disfrazar un relevo.
  - ⚠️ **Cambia el contrato de V2-211** a propósito (de «una corrección por sesión» a «cada choque, con tope»), y
    el test que lo fijaba se reescribió explicando por qué. Nodo 2.5, sensibilidad en cuatro direcciones.
  - **Sigue siendo prompt, no mecanismo**: mejora la información y el final, no impide el choque. El mecanismo
    sería reescribir el comando (quitar el `cd <ruta> &&` y ejecutar el resto **si ya está en nuestro allowlist**,
    o sea sin ampliar un permiso), y hoy no se puede porque el evento `step` solo conserva `{where, action,
    target}` resumido y el comando crudo no llega. Eso quiere su propia decisión.

- **El extractor exigía PRECIO, así que un fontanero devolvía CERO filas** (`widgets/navegador/dom.py` +
  `act_api.py`, V2-240, 2026-08-21). Con las muertes de worker ya cerradas, el arnés dejó
  `best-plumber-same-day` en 1/5 con un diagnóstico honesto —*«pide un fontanero CONCRETO y le dan un directorio;
  eso es criterio, no fontanería»*— y **no era criterio**: la prueba estaba en su propia medida de la ronda
  anterior, **«0 filas extraídas»**, la misma cifra en `weekend-barber`. `_JS_EXTRACT` llevaba
  `if(!pm) continue; // Without a price, it is not a listing`, y «un anuncio tiene precio» es verdad de UNA clase
  de encargo —la compra— y de ninguna otra. Un fontanero, un barbero o un cerrajero no publican precio, así que
  la página devolvía cero filas y al turno solo le llegaba el enlace del directorio. **Cuarta vez en la misma
  tanda que el turno describe con fidelidad lo poco que le llega y el diagnóstico apunta a su conducta.**
  - Es justo lo que prohíbe la norma del operador: **los recursos se clavan, no se adaptan al caso de uso**. Este
    filtro estaba adaptado al caso de uso de la compra.
  - Ahora una ficha es **un NOMBRE más un dato accionable**: *o un importe que pagar, o un número al que llamar*.
    Sin nombrar sector ni sitio. El teléfono se lee de la TARJETA con la MISMA definición de tarjeta que el
    nombre —sale a `cardWalk()` para que exista una sola vez—, un `tel:` es inequívoco y en texto se exigen 9-14
    dígitos CON separadores (lo que descarta un precio, un EAN y una fecha).
  - **Un `tel:`/`mailto:` no es una ficha**, es la forma de contactar con ella: sin excluirlos como candidatos un
    directorio devolvía cada negocio dos veces.
  - **El número viaja hasta la conversación.** Extraerlo y dejarlo caer sería V2-236 otra vez; en un encargo de
    servicio es el dato que RESUELVE. Nodos 4.32 (renderiza) y 4.31, sensibilidad en cuatro direcciones.
  - **Solo cubre el teléfono**: dirección u horario todavía no cuentan. Cada señal nueva es una puerta más por la
    que puede entrar el menú de navegación, así que la siguiente quiere su propia medida.

- **Un RELEVO no es una muerte** (`nucleo/workers/session.py` + `nucleo/dispatch.py`, V2-238, 2026-08-21). Cuando
  el proveedor se queda sin cuota, `_finish` hace lo correcto: relanza el encargo con el siguiente escalón y vacía
  la entrega a propósito para que el operador no vea dos. Lo que hacía después es dejar `ok=False` y
  `status="error"`, y con eso **la sesión relevada quedaba indistinguible de un worker muerto**. De ahí salían
  tres cosas, y la primera es la cara:
  - **Un aviso FALSO al operador**: `_remember_ended` leía ese `ok=False` y empujaba la nota de V2-222 —*«la
    tarea de fondo ha MUERTO sin resultado y no se va a reintentar sola»*— **mientras el relevo trabajaba**.
  - **DOS escaladas para una muerte**: `_resumable` lee el mismo `ok=False`, así que en una gestión web disparaba
    ADEMÁS el auto-resume de la continuidad web. Dos workers sobre un encargo — y hasta V2-237/V2-239, los dos reanudando la
    MISMA sesión del CLI. **Este defecto ALIMENTABA aquél**: no solo se repartía mal el testigo, se pedía dos veces.
  - **Una muerte contada de más** en la observabilidad, que es de donde salen las medidas del arnés.
  - El arreglo es un HECHO, no una heurística: **`SessionRecord.handoff`** dice a dónde pasó el testigo, y con él
    la sesión tiene su propio final —**`relevada`**, dentro de la enumeración de V2-198— en vez de disfrazarse del
    de al lado. Se marca DESPUÉS de que el relanzamiento salga bien: fingir el testigo antes de saber que alguien
    lo cogió convertiría una muerte silenciosa en una muerte silenciosa Y sin aviso. La hoja NO se cierra al
    relevar (es del ENCARGO, no de la sesión).
  - **Hallazgo colateral, salido del LOG y no del razonamiento**: las tres ramas de `_finish` que no son un relevo
    escriben un `result_summary` que ANUNCIA un fallo y **ninguna tocaba `ok`**, que nace en `True`. En la primera
    pasada de sus tests se lee, literal, `Tarea completada: Me he quedado sin cuota en el proveedor…`. Las tres
    cierran `ok` ahora.
  - ⚠️ **Y una trampa de método que casi cuela cinco desarmes**: en zsh un parámetro sin comillas NO se parte en
    palabras, así que `pytest $T` con dos rutas dentro corrió *«no tests ran»* cinco veces seguidas — cinco
    comprobaciones de sensibilidad «en verde» que se habrían leído como cobertura. **Un desarme tiene que enseñar
    cuántos tests corrieron.** Nodo 2.5, 14 casos, sensibilidad en cinco direcciones.

- **Un `native_sid` que MATÓ a un worker no se vuelve a armar** (`nucleo/dispatch.py`, V2-239, 2026-08-21).
  V2-237 hizo que la entrada de reanudación se CONSUMA, y está bien; el arnés lo midió sobre `05dd79f` con el
  worktree fijado y su veredicto fue **«NO cierra»**: sesión `0364d544-505` → workers 3 y 4, muertos 2/2 a los
  380 y 420 ms. El otro extremo del ciclo reciclaba el id: al cerrar una gestión incompleta la entrada se
  reescribía con `rec.native_sid or (resume or {}).get("native_sid")`, y **no tener el suyo significa exactamente
  que el CLI nunca anunció su sesión** —`rec.native_sid` lo pone el `spawned`, que nace del `system/init`— o sea
  que la reanudación NO prendió. El id volvía a la entrada, el siguiente se lo llevaba, y volvía a morir en el
  arranque. **Consumir la entrada no basta si el camino de la muerte la vuelve a armar con el mismo id.**
  - `nav_task` **sí** conserva su respaldo: la pestaña del navegador es otro recurso, sobrevive al worker y no
    estaba matando a nadie.
  - La dirección contraria está clavada por un test porque el atajo es tentador: **borrar el id siempre** satisface
    el caso y **mata la continuidad web en silencio** (un `--resume` que prende sí deja su `native_sid`).
  - La construcción de la entrada sale a **`_resume_entry()`** para poder probarla de verdad: dentro de
    `_run_session` hacían falta un pool, un backend y un navegador, así que solo se podía comprobar la fuente — y
    una guarda de fuente no caza esto, que es un `or` con la semántica equivocada.

- **La búsqueda dio la respuesta perfecta y MURIÓ dentro del worker** (`nucleo/workers/findings.py` NUEVO,
  V2-236, 2026-08-21). El arnés leyó la observabilidad entera (antes veía el 38 % de 1291 eventos): los eventos
  `kind='search'` traían «Philips 27E1N1800A/00 — 27" UHD 4K — 159,00 €» y «Alurin CoreVision 27" — 149,99 €»,
  justo lo que el operador pidió. **Búsquedas 7 · respuestas 5 · notas al cerebro desde ese canal 0.** El porqué:
  el worker se cae antes de entregar y el texto bueno se va con él — **8 workers lanzados · 3 ok · 3 con ERROR · 2 cancelados** por el propio arnés al cerrar su sandbox con el worker todavía trabajando. (La primera cifra que
  circuló, «5 de 8 muertos», la corrigió el propio arnés: contaba como muertes sus dos cancelaciones de test.)
  **Zaelar dijo «la búsqueda se ha caído sin terminar»: decía LA VERDAD**, y se le puntuó como vaguedad. Tercera
  vez en la misma tanda que el turno describe con fidelidad lo poco que le llega y el diagnóstico apunta primero
  a su conducta.
  - Mismo remedio que V2-223 por la otra puerta: **el hallazgo se empuja cuando existe**, no cuando el worker
    entregue. En `WorkerSession._on_event` (rama `step_result`), que es donde `where` ya viene normalizado — un
    solo sitio cubre Claude Code, Codex y Grok **y las tools NATIVAS de cada CLI**, que es donde se medía la
    pérdida — y en `worker_api._exec_allow`, que es NUESTRA búsqueda prestada al worker.
  - **El JUICIO se queda en el cerebro**, **UNA sola instrucción** (V2-226), **un `is_error` no es un hallazgo**,
    se **recorta diciendo cuánto falta**, y el dedup es por CONTENIDO (la misma respuesta no es nueva; otra
    distinta sí) y se olvida con la sesión.
  - ⚠️ **El primer intento de sus tests no probaba nada de lo que decía**: llamaban al predicado a mano, así que
    con el enganche BORRADO de `_on_event` pasaban los dieciséis. Lo cazó la comprobación de sensibilidad, no la
    lectura. Es V2-199 otra vez — **un test que no recorre el camino real prueba que el código compila**— y esta
    vez lo detectó el método en lugar de una ronda. Nodo 2.5, 17 casos, sensibilidad en seis direcciones.
  - **Lo que NO arregla**: por qué 5 de 8 workers mueren. Quita el daño, no la causa.

- **El extractor PARTÍA el precio y no cogía el nombre** (`widgets/navegador/dom.py`, V2-235, 2026-08-21).
  Medido por el arnés con V2-234 ya dentro: las notas crudas decían «169 — 00 € — …/LG-27US500-W-…/dp/…» y
  «284 — 87 € — …/Dell-…», o sea **un monitor de 169 € anunciado como de 0 €**. Zaelar volvió a salir limpio —
  dijo «LG 27US500-W 4K por 169 €» sacando el modelo DE LA URL, que es lo correcto con lo poco que le dimos.
  - **La COMA faltaba de la clase de caracteres** (`\d[\d.]{0,9}\s*€`: punto de millares sí, coma decimal no),
    así que sobre «169,00 €» el patrón empezaba a casar en «00». Es la misma avería que producía los «00 €» que
    ya se habían visto y se habían apuntado como rareza de los anuncios.
  - **El NOMBRE no está en el enlace del precio**: en una rejilla el importe vive en su propio `<a>` y el nombre
    en el encabezado de la tarjeta. Se coge de ahí — estructural y sin nombrar ningún sitio: *un listado es una
    rejilla de tarjetas y el nombre de cada cosa es el encabezado de la suya*. Con **dos frenos probados**: como
    mucho cinco niveles, y **parar en cuanto el ancestro deja de ser una tarjeta** — si no, el «Resultados» de la
    sección nombraría a todas las filas, y un nombre que vale para todo no nombra nada. Sin nombre se queda SIN
    nombre; no se inventa.
  - **NO se reconstruye el separador decimal** cuando entero y céntimos vienen en nodos distintos: se entrega
    «169 00 €» tal cual. Meter una coma sería adivinar —hay sitios que separan los MILES con espacio— y adivinar
    mal ahí cambia un precio por cien.
  - Nodo 4.32, **renderizando**: el fallo solo existe cuando el navegador compone `innerText`, que no es el HTML.
    Cinco formas de listado y sensibilidad en cinco direcciones, con el script de mutación **asertando que la
    mutación casa** — la lección de V2-234, donde un desarme que no llegó a aplicarse salió verde.

- **La nota llevaba delante el CROMO DE NAVEGACIÓN, y el turno describió eso** (`widgets/navegador/act_api.py`,
  V2-234, 2026-08-20). Medido por el arnés en `cheapest-monitor` con la extracción cruda delante: el navegador
  sacó seis filas — las tres primeras SIN TÍTULO (enlaces de categoría: «portátiles hasta 799 €», «móviles menos
  de 200 €», «tablets hasta 200 €») y las tres siguientes tres monitores REALES a 99 € con enlace de producto y
  foto. Zaelar contestó: *«lo que ha sacado la página son categorías genéricas de PORTÁTILES, MÓVILES Y TABLETS,
  no monitores»*. Son las filas 1, 2 y 3, en su orden.
  - **La causa es `items[:3]`, en orden de DOM.** El turno no se saltó la cuarta fila: **la cuarta no estaba en la
    nota**. Describió fielmente lo único que le dimos. Y el mismo corte ciego dos líneas antes
    (`set_results(items[:5])`) le servía las categorías a la hoja. **No es mala suerte de esa tienda**: los
    enlaces de categoría y de filtro salen ANTES que las fichas de producto en el DOM de cualquier listado, así
    que un corte por posición se come el resultado **por construcción** — la misma forma que el corte de
    evidencia, que siempre se come el final porque los anuncios van arriba.
  - **Corrige el diagnóstico que se estaba manejando**, mío y del arnés: NO era «la decisión de anunciar vive en
    el prompt» ni hacía falta un mecanismo de anuncio nuevo. V2-223 ya había arreglado la fontanería.
  - **PARTIR, no ordenar** (`by_identity`): una fila sin título no tiene identidad de cosa, así que no ocupa la
    cabecera; el orden relativo se conserva dentro de cada mitad. No se juzga cuál es mejor —eso es del cerebro, y
    `observability/evidence.py` prohíbe interpretar— se separa por un hecho estructural. **No es una lista negra**
    (mañana es otra tienda): «tiene nombre» vale para un hotel, un coche, un piso en Los Ángeles o una entrada de
    teatro, y para el listado que nadie ha escrito todavía.
  - **La MISMA url no son tres hallazgos**: la segunda nota de esa ronda llevaba tres filas y las tres eran la
    misma url de anuncio. Repetir no solo ensucia, **ocupa el cupo** — dos de los tres huecos se gastaban en decir
    lo mismo. Se conserva la primera aparición; una fila SIN url no se deduplica contra nada (la ausencia de
    dirección no es una identidad compartida).
  - **No se tira nada**: lo que queda fuera se CUENTA («y 1 fila más y 2 repetidas de la misma página»). Y **sin una sola fila
    con nombre la nota lo DICE y da salida**, en vez de servir enlaces como hallazgos — callarse dejaría al turno
    sin poder decir «esta página no está dando lo que pediste, cambio de sitio», que es cierto y útil.
  - **La fase cuenta RESULTADOS, no filas**: «12 resultados» con nueve enlaces de categoría dentro es una cifra
    que el operador lee y se cree, y `found(0)` no calla —dice «sin resultados en esta página»—, que es lo que
    hace falta para cambiar de sitio en vez de insistir.
  - Nodo 4.31, 11 casos, con la extracción cruda reproducida entera. **Trampa de medición que trae el arnés**: su
    `verify.py` filtra `if it.get("title")` antes de contar, así que su columna venía limpia mientras al cerebro
    se le servía la sucia — este arreglo se mide contra el evento CRUDO, nunca contra esa columna.

- **UN ENCARGO, UNA SUPERFICIE: el panal de hexágonos se RETIRA** (`frontend/app/components/ActivityStrip.js`
  BORRADO, V2-233 ámbito D, 2026-08-20). El encargo era agrandarlos y hacerlos legibles. Construyéndolo salió que
  el mismo hecho se contaba en **tres** sitios —el panal, la pestaña «Proceso» de la hoja y la pestaña «Procesos»
  del chat— porque los hexágonos pintaban TODA tarea viva **sin mirar la superficie que el ámbito A ya había
  decidido**. Puesto delante del operador, no arbitró entre las tres: quitó una. *«Retiramos los hexágonos… solo
  en el widget del chat/procesos, y en el widget de visualización la primera tab es la de proceso… Simplifiquemos,
  borra lo innecesario.»*
  - **La regla que deja**: la superficie se decide al ENCARGAR y ahí, y solo ahí, se cuenta lo que pasa. Lo que no
    tenga superficie propia se cuenta en «Procesos» del chat, que es una **LISTA** (qué corre, qué acabó) y no un
    segundo relato. Tres superficies contando el mismo hecho no es redundancia inofensiva: obliga a mantener tres
    y a mirar tres, y las tres se desincronizan.
  - **El loader pasa al BOTÓN de la pestaña** mientras la tarea vive: al primer resultado la hoja salta sola a la
    lista, y desde ahí lo único que puede decir «sigo trabajando» es ese botón. El contador de fases vuelve al
    acabar, que es cuando ese número informa (cuántos pasos costó) en vez de confundir «va por doce» con «se quedó
    en doce». Medido: 14 px, animando de verdad por CSS.
  - **Lo que se tiró, dicho entero**: los hexágonos al doble con su contraste medido, el hover y su nodo. Un
    hallazgo de esa tanda conviene no volver a pagarlo — la capa era `pointer-events:none`, así que **cualquier
    `:hover` de CSS allí habría estado muerto sin fallar**, y un test que comprobara que la regla existe habría
    pasado igual. Por eso el hover se resolvía por geometría y se medía renderizando.

- **El contrato de pantalla estaba en verde y el operador seguía sin ver nada** (`nucleo/dispatch.py` +
  `widgets/results/data.py`, V2-233 ámbito C, 2026-08-20). La hoja de resultados es la superficie del progreso en
  vivo, y su contrato ejecutable daba 6 de 6 renderizando — porque monta `widget.js` en una página en blanco y le
  pasa a mano tres cargas útiles: prueba que la hoja **se comporta** cuando le llegan los datos, no que alguien los
  produzca. Y no los producía nadie. `widget.js` lee `data.progress` y su propio comentario dice «llega derivado en
  cada `view_data`»; **`view_data()` no devolvía esa clave en absoluto**, y nadie emitía `widget/show` para
  `results` al encargar. Un contrato cumplido en un test y ausente en el producto.
  - **`dispatch.sheet_progress()` → `{alive, phases}`, DERIVADO en cada lectura y nunca guardado**, igual que
    `counts`: el dueño de «qué está pasando» es el registro vivo, y tener el mismo estado en dos sitios deja en
    pantalla el rancio. **`alive` es «hay un encargo en marcha», no «ha dicho algo»** — la hoja se abre viva con
    `phases: []`, y ese hueco de segundos ES la pantalla en blanco que el operador pidió quitar.
  - **Se abre al ENCARGAR**, en `run_listener` justo tras `surfaces.set_once` (el único punto por el que pasan
    todas las puertas del dispatcher), y **se cierra DESPUÉS del `pop`** del registro — al revés, `sheet_progress()`
    seguiría viendo la sesión y la hoja se guardaría diciendo que trabaja. Al reanudar no se cierra: el encargo
    continúa.
  - **Tres cosas que no estaban en el encargo y sin las cuales no se sostiene.** (1) `process` **faltaba de
    `_TABS`**: el clic del operador en «Proceso» volvía `ok:false` y no se persistía — la pestaña se pintaba igual
    y al siguiente refresco de datos, que durante un encargo vivo llega con CADA fase, el derivado se lo llevaba de
    vuelta a Resultados. (2) Sin **estrenar** la hoja al encargar, el segundo encargo de la sesión abre sobre los
    resultados del primero y con su título: la función solo se sostenía en el primer encargo. (3) **Escribir al
    terminar** es lo que APAGA el loader (el emisor de fases solo dispara al CAMBIAR una fase) y lo que deja la
    historia **persistida** con el informe: la hoja sobrevive a un reinicio, y un informe cuya explicación de cómo
    se llegó a él ha desaparecido cuenta la mitad.
  - **Asumido y dicho**: con DOS encargos vivos las fases se MEZCLAN en orden de tiempo mientras la hoja sea única
    (C4) —quedarse con uno escondería que hay otro trabajando—, y un encargo nuevo con otro AÚN VIVO no la vacía.
  - Nodos 4.28 (16 casos) y 2.5 (dos por el camino REAL, `run_listener` contra el bus: llamar `_sheet_open` a mano
    habría pasado igual con la línea borrada, la lección de V2-199). El contrato de pantalla del arnés se
    **registró** en el testmap como 4.29 — no lo estaba, o sea que no corría en `tests run all`.
  - ⚠️ **El número**: los ámbitos A/B/C se commitearon como `[V2-227]`, que ya estaba cogido por un caso de uso del
    arnés. El trabajo vive en **V2-233**; los commits `e8b5c4c`/`b211331`/`58a2339` citan el número equivocado.

- **La nota del hallazgo llevaba TRES órdenes, y el turno obedeció la del medio** (`widgets/navegador/act_api.py`,
  V2-226, 2026-08-20). La nota de V2-223 decía «si responde a lo que pidió, dáselo; si no, no lo ofrezcas como
  resultado; **pero entonces tampoco digas que sigues buscando sin más**». Medido en la primera ronda limpia
  (sha `0b89510`): el navegador había extraído el anuncio de flamenco de 25 € y el turno contestó «se ha quedado
  a medias y **no ha llegado a darme resultados**». Obedeció la cláusula del medio —no ofrecerlo como hotel, que
  es lo que la nota existe para evitar— y se comió la última: con un resultado delante, informó de ninguno.
  - Es **la misma forma que V2-224 acababa de medir** en el otro bloque: dos órdenes en una frase se resuelven a
    cara o cruz. La bifurcación pasa a ser un matiz DENTRO de un solo imperativo («nómbralo en este turno y, en
    la misma frase, di si sirve») y la frase que nunca puede ser cierta —«no hay resultados»— se prohíbe
    explícitamente en vez de dejarla como consecuencia que el modelo tiene que deducir.
  - Regla que sale de las dos: **una instrucción por nota y por bloque.** Si hace falta una bifurcación, va
    dentro de la orden, nunca como segunda orden. Nodo 4.25.

- **Decirlo una vez no es olvidarlo** (`nucleo/dispatch.py` + `nucleo/flash/prompt.py`, V2-224, 2026-08-20). La
  instrucción incondicional de V2-221 funcionó —el arnés midió **2 de 2** turnos diciéndolo, en el turno 2, sin
  que nadie preguntara— pero llevaba la anti-repetición DENTRO de la misma frase, y eso se midió en **dos rondas
  del MISMO commit con fallos OPUESTOS**: en una lo dijo en el turno 2 y lo repitió en el 5, 6, 7, 8 y 9 (el
  disco rayado de V2-189); en la otra lo dijo en el turno 2 y luego lo NEGÓ siete turnos («Sigo con ello», «Dame
  un momento»).
  - **No es un umbral mal puesto**: «¿ya se lo dije?» era una deducción del modelo sobre la ventana, y era un
    HECHO que nosotros teníamos y no le dábamos. Ahora se cuenta (`dispatch.mark_death_reported`, que mueve el
    turno que lo LLEVÓ delante, no el que murió: entre la muerte y el prompt siguiente puede no haber ninguno).
  - **La redacción sigue la frase con la que el arnés lo diagnosticó: callar la repetición NO es callar el
    estado.** La cara posterior deja de dar la noticia y mantiene la prohibición — «no se lo vuelvas a anunciar,
    pero SIGUE MUERTA: si pregunta cómo va o dice que espera tranquilo, no digas «sigo con ello» ni «dame un
    momento»». Sin esa mitad, arreglar el disco rayado reabre el silencio, que es justo lo que pasó en la ronda 6.
  - **Una instrucción por turno**, y hay un test que lo fija: dos órdenes en la misma frase se resolvían a cara o
    cruz según la ronda. Nodo 4.26, 9 tests.

- **El compositor de investigación LEÍA la cadena de proveedores y nunca la ESCRIBÍA** (`nucleo/research.py`,
  V2-225, 2026-08-20). `_spec()` va por `provider_chain.pick()` y su docstring promete que «si el proveedor
  principal está sin cuota, releva en vez de morir». No se cumplía, y **no porque faltara el relevo**:
  `note_failure()` tenía UN solo llamador de producción en todo el árbol (`connectors/meshkore/brain.py`), así
  que el cooldown que dispara el relevo solo existía si el cerebro de CLUSTER había fallado antes por el mismo
  sitio. El compositor vivía de esa casualidad.
  - **Evidencia** (arnés, dos rondas de `hotel-under-15-days`, 2026-08-20): a las 20:01, 20:07 y 20:10 se eligió
    el MISMO proveedor agotado las tres veces, con dos reintentos cada una, y el worker salió a ciegas después de
    cada una — «429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-08-25 01:39:02]». Ese
    texto es exactamente la forma que `classify_failure` lee como `exhausted` CON fecha de reset, que es el caso
    que pone cooldown y devuelve relevo. **No faltaba mecanismo: faltaba la llamada.**
  - **Impacto, y es el techo de varios casos**: hasta el 2026-08-25 TODA escalada de investigación salía sin
    dirigir. Por eso el mejor «resultado» de una ronda fue un espectáculo de flamenco de 25 €. Un caso que
    dependa de research no podía puntuar en resultado, y no por el producto.
  - Se reintenta con el relevo EN LA MISMA llamada: marcar el escalón arregla la tarea siguiente, reintentar
    arregla también la que está en curso — y la evidencia son tres tareas seguidas a ciegas.
  - **El fail-open no se toca** (sin relevo, el worker sale sin brief, como siempre) y **un modelo fijado por el
    operador nunca se reporta**: poner en cooldown un escalón que el compositor no usó relevaría al cerebro de
    cluster por culpa ajena. Nodo 4.27, 7 tests.

- **El prompt se contradecía a sí mismo, y el turno elegía la mitad cierta** (`nucleo/dispatch.py`, V2-222,
  2026-08-20). El arnés midió con un contador de las dos vías sobre `hotel-under-15-days`: lo que se EMPUJA como
  nota de sistema se dice en el turno siguiente **3 de 3** (3 s la pregunta del worker, 7 s el muro), lo que solo
  se RENDERIZA como línea de estado del prompt, **0 de 13** — con el imperativo de V2-221 delante las trece
  veces. Su conclusión fue «el turno obedece lo empujado e ignora lo renderizado». El recuento es correcto; la
  lectura no era completa. Leyendo el system prompt ENTERO de los ocho turnos de `20260820-194231`, **siete
  llevaban el mismo encargo dos veces**, carácter por carácter: «TAREAS DE FONDO EN CURSO (… NO reinicies ni
  digas que ya está): «Busca hoteles de 4 estrellas…» — abriendo una página… [paso 2/5, 40%]» y «TAREAS DE FONDO
  — YA ACABADAS: «Busca hoteles de 4 estrellas…» FALLÓ … DÍSELO EN ESTE TURNO».
  - **Causa**: el primer intento falló, `_remember_ended` lo archivó, y la reanudación automática de una gestión web
    incompleta (`dispatch._schedule_auto_resume`) relanzó el MISMO encargo con otro id. Los dos bloques decían la verdad sobre sesiones distintas mientras el operador tenía UN
    encargo. **«Sigo esperando resultados» era la mitad CIERTA**: el turno no desobedecía, resolvía una
    contradicción — y por eso V2-221 midió 0/7 en la ronda que lo llevaba, y habría medido 0/7 escrito de
    cualquier otra forma.
  - **La lección de método, que vale más que el arreglo**: un prompt que se discute a sí mismo es invisible si se
    lee la línea que uno fue a buscar. Solo aparece leyéndolo entero. Y el precio de no verlo es acusar al
    modelo de desobedecer cuando está haciendo lo correcto — la misma trampa que
    [[feedback_leer_el_prompt_antes_de_acusar]].
  - **Tres piezas**: la sesión que va a reanudarse sola no se anota como terminada (el origen, con el MISMO
    predicado que decide la reanudación — dos copias derivarían y la deriva es invisible: una archiva una muerte
    mientras la otra reintenta en silencio); una sesión cuyo objetivo esté CORRIENDO ahora nunca se reporta como
    terminada (el cinturón — una escalada repetida también duplica un objetivo); y la que sí murió se **empuja**
    por `brain_notes`. La línea de estado se QUEDA: es el contexto de los cinco minutos siguientes y ahora es
    cierta.
  - Nodo 4.24, 11 tests. Un assert de V2-199 casaba `_remember_ended(rec)` al carácter y falló por una firma
    nueva sin que la conducta cambiara; ahora casa por la llamada.

- **Lo que el navegador ENCUENTRA no llegaba a nadie** (`widgets/navegador/act_api.py`, V2-223, 2026-08-20). En
  `hotel-under-15-days` el worker hizo su trabajo y bien: `navigate` a Booking con los parámetros PERFECTOS
  (Sevilla, 4 noches, 2 personas, dentro de 15 días), extrajo un anuncio de flamenco de 25 €, **pivotó solo** a
  Google Hoteles y a las 19:45:29 extrajo **«Exe Sevilla Macarena», «65 €», con URL**. Dieciséis segundos
  después el turno 7 dijo «Sigo pendiente y te digo en cuanto tenga algo». Su prompt no contiene «Exe Sevilla»
  ni «Macarena» ni «65 €», y la ronda reportó `missing_signals: ['widget']`: tampoco estaba en la hoja.
  - **Causa**: `set_results` lo llamaba ÚNICAMENTE `dispatch._finalize_web`, al FINAL de la sesión, raspando de
    nuevo la página que hubiera en pantalla para entonces. La ronda se quedó sin turnos antes de llegar ahí, así
    que el resultado vivió y murió en el stdout del worker.
  - Ahora **cada extracción no vacía va a la hoja y sale como nota empujada**, deduplicada por CONTENIDO y no por
    tarea: la primera extracción fue el anuncio y el hotel bueno llegó después — deduplicar por tarea se habría
    comido el único resultado bueno de la ronda.
  - **El JUICIO se queda en el cerebro, y es una decisión**: la nota entrega los hechos y nombra la prueba («si
    responde a lo que pidió, dáselo con nombre, precio y enlace; si no es lo que pedía, no lo ofrezcas como
    resultado — pero entonces tampoco digas que sigues buscando sin más»). Una orden de «anuncia esto» habría
    ofrecido el espectáculo de flamenco de 25 € como el hotel de cuatro estrellas.
  - Nodo 4.25, 9 tests. Con V2-215 y V2-220 cierra la frase que ordena el día entero: **los muros, las
    preguntas, los fallos y los RESULTADOS solo llegan al operador si pasan por la nota empujada.**

- **Una tarea de fondo MUERTA no es una pregunta pendiente** (`nucleo/flash/prompt.py`, V2-221, 2026-08-20). El
  arnés leyó el system prompt de CADA turno de `hotel-under-15-days` (19:12): turnos 2 al 8, **ocho seguidos**,
  con «TAREAS DE FONDO — YA ACABADAS: «Reservar una noche…» **FALLÓ**» delante, contestando «sigo con ello, te
  aviso». Sin muro y sin pregunta de por medio. Eso **parte el problema en dos mitades que se venían
  confundiendo**: la ENTREGA ya estaba (V2-198 pone el hecho en el prompt, V2-220 hace que un aviso proactivo
  llegue por el canal de texto — el teatro lo demuestra cronometrado, 7 s del muro a la boca) y lo que queda es
  la **OBEDIENCIA**.
  - **Causa**: la instrucción de V2-198 era CONDICIONAL —«si el operador pregunta por ello»— y una tarea muerta
    no es una pregunta pendiente, es una persona esperando algo que ya no va a llegar. Mismo corte que V2-185
    con el muro y por lo mismo: **mientras la mitad tranquilizadora sea la que dice qué HACER, el modelo cree a
    esa**. No es pereza del modelo: se le daba una instrucción que no aplicaba y ninguna que sí.
  - La cara nueva trae las cuatro cosas que las anteriores ya enseñaron que hacen falta: **nombra la tarea**
    (V2-193), se dice en ESE turno aunque no pregunte, **nombra la frase que sustituye** (sin la frase dentro, el
    modelo no tiene con qué contrastarse) y ofrece salida.
  - Y una cláusula que no es adorno: el registro tiene TTL de 5 min, así que la línea viaja en varios turnos —
    sin **«si ya se lo dijiste, no lo repitas»** el arreglo del silencio se convierte en el disco rayado que
    V2-189 midió.
  - **Es un PARTIR, no un reescribir**: una tarea que acabó BIEN conserva la redacción condicional (ahí «si
    pregunta» es verdad, y gritarlo empujaría a relatar contabilidad que nadie pidió) y una CANCELADA no cuenta
    como fallo (V2-196: pararse no es fallar).
  - Nodo 4.23, 9 tests. **Lo que NO arregla**: que el prompt lo diga mejor no garantiza que el turno lo diga —
    misma frontera que dejé escrita en V2-213. Si la próxima ronda enseña esta cara y el turno calla igual, lo
    que falta ya no es información ni redacción: es que la decisión salga del prompt y pase a mecanismo.

- **El aviso proactivo existía y no tenía dónde llegar** (`voice/proactive.py`, V2-220, 2026-08-20). El arnés
  pidió «si el muro merece un system note, un worker que muere en sus argumentos también». El mecanismo YA
  existía —el bucle avisa del atasco desde V2-073, por `proactive.notify()`— y lo roto era esa función:
  `brain_notes.push` vivía DENTRO del `if speak and _speaker is not None`, así que **sin sesión de voz viva
  `notify()` hacía exactamente una cosa: emitir a observabilidad**. En el canal de TEXTO (el que conduce el
  arnés, y el que usa cualquiera en chat) eso es TODA entrega proactiva que existe: el aviso de atasco, el final
  de un worker, mensajería y Architect. Por eso el arnés medía `stuck/nudge` disparando mientras el turno decía
  «sigo con ello» y lo reportó como dos problemas: era uno.
  - Misma forma que V2-215 una capa más arriba, y el mismo remedio, porque `brain_notes` es la única costura que
    funciona en los DOS canales. La nota es una **INSTRUCCIÓN**, nunca la frase pelada (V2-214): su lector es el
    agente en otro momento.
  - **Sensibilidad por los dos lados, que es lo que lo separa de una entrega doble**: con la voz VIVA no se
    apunta nada (decirlo y apuntarlo es que el operador lo oiga dos veces), y el fallback viejo —voz viva sin
    hueco de silencio— sigue disparando, verificado, para que esto no sustituya una vía por otra en silencio.
    `speak=False` sí apunta: un llamante que no quiere VOZ no ha dicho que no quiera que el operador se entere.
  - Nodo 3.11, 7 tests.

- **El worker dejaba de trabajar en la aridad de NUESTRO propio CLI** (`nucleo/nav_cli.py` +
  `nucleo/worker_bridge.py` + `nucleo/bridge_usage.py`, V2-219, 2026-08-20). Medido en `hotel-under-15-days`,
  con la consecuencia contada: **`n_search_events: 0`** — ni una búsqueda en toda la ronda, porque murió en sus
  argumentos antes de llegar a la web mientras el turno decía que trabajaba.
  - **`scroll down` es el CLI el que está equivocado, no el worker**: cualquier otra herramienta que haya
    conducido lleva una dirección ahí, su propio manual dice `scroll 800` —o sea que CONOCE la sintaxis y no la
    usa— y escribió lo natural **cuatro veces en dos casos sin relación**. Eso deja de ser anécdota. Acepta la
    dirección; un número sigue significando ese número exacto y un valor ilegible sigue fallando, solo que el
    error dice las dos formas. **No es una tabla de verbos hardcodeada**: aquí nadie CLASIFICA una intención —
    la dirección ya era el argumento.
  - **`worker_bridge act` sin payload sí es el worker**, y ahí lo que falta no es aceptarlo sino DECIR cómo se
    escribe (nodo 4.20). En este puente duele más que en ninguno: es la vía por la que PIDE una búsqueda, así
    que morir en sus argumentos lo deja ciego el resto de la tarea. La pista trae la línea del `use_tool` para
    copiar y va **ENTRE** la queja y el `usage`, porque un worker lee de arriba abajo.
  - El **mecanismo** del parser guiado se comparte (V2-153); el **conocimiento** no: cada puente pone su
    `_hint_for`.
  - **La puerta de permiso NO era el `cd`** (corrección del arnés, ronda 18:28: `cd in '<engine>' was blocked`
    **y** `ls in '<engine>/t…' was blocked`). Escribí la regla alrededor de un VERBO, y una regla así deja fuera
    el siguiente comando — siempre hay un siguiente comando. Ahora dice «no salgas de tu directorio» y nombra
    cd/ls/find/cat. **Con contrapeso, porque sin él rompía el camino de visión**: SÍ puede abrir con Read un
    fichero cuya ruta absoluta le demos nosotros (la captura), que V2-117 verificó en vivo. Su test asertaba el
    literal viejo; reescrito contra la regla medida.
  - Nodo 2.5, 14 tests.

- **Un hecho recogido en TODAS partes y dicho en NINGUNA** (`widgets/navegador/tasks.py`, V2-215, 2026-08-20).
  El arnés leyó el registro de la tarea en dos rondas: `cancel-subscription` (16:34) con `status=working`,
  `wall="la página pidió resolver un captcha"`, `phase_active=false`, `walls_hit=1`; `find-theatre` (16:26) con
  `question="Voy a pulsar «COMPRAR ENTRADAS». ¿Lo confirmo?"` y `walls_hit=2`; **brain-notes en las dos: 0**. Su
  lectura es la buena: **zaelar no inventa — lee un campo y lo cuenta fielmente**; lo que no existía era el
  camino de vuelta. `_announce_wall` deja un hito, apaga el spinner y abre la tarjeta — las tres son superficies
  que hay que estar MIRANDO; `ask()` hacía menos, solo el feed. `active_progress()` sí lleva las dos cosas al
  prompt (V2-202/V2-207) pero **esa vía solo se recorre cuando el operador PREGUNTA cómo va**.
  - **Tiene que ser `brain_notes` y no `proactive.notify`**: el fallback a nota de esa función vive DENTRO de
    `if speak and _speaker is not None`, así que sin sesión de voz viva una entrega proactiva llega al panel de
    observabilidad y la conversación no se entera por ningún camino. Las notas las drenan los dos canales.
  - La nota trae el **MOTIVO** y una **salida**, y **no promete que la tarea acabe sola** — eso es V2-185, falso
    delante de un muro. La pregunta viaja **VERBATIM**, **nombra su tarea** (V2-193) y dice que el sí o el no ES
    la respuesta, sin lo cual `answer_from_turn` no llega a usarse.
  - **Una vez por muro distinto** (`_announce_wall` solo dispara al CAMBIAR): una tarea parada en un captcha
    recaptura cada pocos segundos, y una nota por captura entierra la conversación en texto de sistema.
  - **Lo que NO se hizo y por qué**: el arnés pidió además que `status` no siga en `working` con un muro puesto.
    **El `status` que él audita no lo lee el turno** — el prompt se compone de `active_summaries()` +
    `active_progress()`, y `_task_view` no entra por ningún sitio. Y sería un arreglo de CINCO puntos, no de
    uno: `LIVE_STATES` está repetida a mano en `tasks.py` 352/381/450 y `owner.py` 1127, así que un estado nuevo
    se quedaría fuera de esos cuatro **en silencio** — la forma exacta que V2-197 ya pagó en este módulo.
  - **Corrección propia**: dije que a `active_progress()` le faltaba `wall`. Era falso — lo lleva desde V2-207.
    El dato llegaba al prompt; faltaba el camino cuando nadie pregunta.
  - Nodo 4.22, 9 tests, sensibilidad en las dos direcciones. Y en el **nodo 2.5**, la mitad del cableado que sus
    tests no veían: todos llamaban a `_maybe_unstick_permission` directamente, así que habrían pasado igual con
    la llamada de `session.py:176` BORRADA; ahora un `step_result` recorre `_on_event`.
  - **Abierto**: la puerta de permiso de V2-211 no funcionó y falta saber si el código llegó a correr (el chip
    `comando no permitido` lo distingue); el snapshot rancio (`ref N no existe`) es la forma de V2-212 otra vez;
    y **pedir lo que ya tienes delante** — medido por el agente de memoria sobre el prompt REAL: «Madrid» estaba
    en el turno por dos vías (la frase anterior del usuario literal en la ventana y la línea `PROCESOS DE FONDO`
    del propio system prompt) y aun así volvió a preguntar e insistió tras ser corregido. No es recuperación ni
    prompt: es conducta.

- **El aviso existía y su CONTENIDO estaba roto** (`nucleo/flash/router_guards.py`, V2-214, 2026-08-20). Medido
  en `remember-and-remind-deadline` (15:49): *«el `prompt` del cron lleva la frase cruda del usuario, así que el
  recordatorio hará que el agente vuelva a programar en vez de avisar»*. `_reminder_prompt` compone la forma
  segura («AVISA al operador, es el recordatorio que te pidió: …») y su propio docstring explica por qué —el
  lector del cron es el AGENTE en otro momento, así que dejarle las palabras del operador le pide APUNTAR, que es
  el bucle que toda esta zona existe para cerrar—, **y solo el BACKSTOP pasaba por ahí**. Cuando la tag
  `cron.create` la emite el modelo, su `prompt` es lo que él escribiera: «el jueves tengo que renovar el seguro
  del coche».
  - Así que la respuesta a «¿regresión o nunca cubrió esta vía?» es **nunca la cubrió**: mismo defecto, la otra
    puerta. Ahora la normalización vive junto a `_reminder_prompt` y la llaman los dos canales.
  - **Estrecho a propósito**: solo se reescribe una obligación en PRIMERA PERSONA. Un cron que el operador montó
    a mano («cada lunes dame el resumen») ya es una orden dirigida al agente, y envolverlo sería romper una
    función para arreglar un defecto. Con test de sensibilidad por los dos lados.

- **DOS REGRESIONES MÍAS, medidas el mismo día y en el único caso 5/5 del tablero** (V2-202/V2-209 addenda,
  2026-08-20). `cancel-subscription-before-charge__es` pasó de **5/5 a 2/5** con el veredicto «narró que seguía
  cancelando en la cuenta del usuario sin que el mecanismo lo respaldara». Ese caso vivía justo de NO afirmar
  nada, así que es el detector más sensible que hay para esta clase de daño — y encontró las dos:
  - **`needs_input` NO significa «hay una pregunta».** El traspaso de LOGIN lo pone (`owner._authenticate`) y las
    tareas que ese traspaso PAUSA también, las dos **sin pregunta**. Mi `answer_from_turn` (V2-202) se apoyaba en
    `waiting_id()` a secas, así que un turno que llevara un «vale» —«**Vale**, abre la web de Netflix y me dices
    cuando esté en el login»— se leía como la respuesta a un confirm-gate que nadie había abierto **y se comía la
    acción real de ese turno**. La pregunta es lo único que distingue «te estoy esperando a TI» de «espero a que
    tú hagas algo en otra ventana».
  - **El ack vacío AFIRMABA trabajo en curso.** Escribí «Te lo abro, pero de momento no hay nada dentro: **sigo
    con ello**» — cambiar una afirmación falsa («aquí lo tienes») por otra más pequeña no es arreglarla, es
    hacerla más fácil de colar. Ahora dice solo lo que PASÓ: se abrió, y está vacío. Lo que esté o no en marcha
    lo dicen el estado y la línea de espera, que sí lo saben.
  - **El tercer sospechoso quedó exonerado MIDIENDO, no argumentando**: el disparo de búsqueda de V2-210 no puede
    dispararse ahí (`mi suscripción` cae en el filtro de «lo suyo» y no hay señal de dato externo), comprobado
    caso por caso antes de tocar nada.
  - La lección que deja, y es de método: **una frase de relleno nuestra es el sitio donde una afirmación falsa se
    cuela sin que nadie la escriba**. Es la tercera vez hoy (V2-176 «Hecho.», V2-209 «Aquí lo tienes», y ahora mi
    propia sustituta). Cada ack nuevo necesita el test de «¿esto AFIRMA algo que no sabemos?».

- **«Prueba otro sitio» sin decir CUÁL es un deseo, no una instrucción** (`nucleo/flash/site_catalog.py` +
  `widgets/navegador/act_api.py` + `nav_cli.py`, V2-213, 2026-08-20). El muro llega YA a todas partes: la tarea lo
  anota (V2-176), el CLI del worker lo imprime (V2-186) y el turno lo dice en voz alta (V2-185 — el transcript de
  `book-hotel` lo prueba: «la han bloqueado un par de veces… ¿sigo o paramos?»). Y las corridas seguían moliendo
  el mismo host: trece minutos en `nh-hotels.com`, y `restaurant-tonight-madrid` acabando en una página de
  resultados de DuckDuckGo. **Lo que faltaba nunca fue la información: era la ALTERNATIVA.** El catálogo tenía
  exactamente UN sitio por categoría, así que ante un muro no había, literalmente, ningún sitio escrito al que ir
  y se le pedía al worker que se lo inventara a mitad de tarea.
  - El host que acaba de bloquear se **EXCLUYE**: ofrecerle el sitio donde está atascado se lee como «insiste».
  - **La lista vacía es una respuesta legítima**: no toda categoría tiene alternativa escrita, e inventarla sería
    justo el adivinar que esto evita — el mensaje queda como antes, ni peor ni mentiroso.
  - **Límite CONOCIDO y afirmado en un test**: un encargo de COMPRAR no recibe alternativas porque
    `generic_marketplace` está deliberadamente sin detectar en `category_of` («el verbo pelado *compra* barrería
    charla normal»). Está escrito ahí para que quien enseñe al catálogo a reconocer la compra —su propio frente,
    con su propia medición— se entere aquí y no en una corrida.

- **Un `usage` dice la FORMA, no el ERROR** (`nucleo/nav_cli.py`, V2-212, 2026-08-20). Medido en
  `book-hotel-night-known__es` (15:29): `nav_cli type_at: error: argument y: invalid int value: 'Hotel Palacio
  de la Merced Burgos reservas 3'`. **`type` toma un [ref] del snapshot y `type_at` toma COORDENADAS de la
  captura**: el worker usó la aridad de uno con el nombre del otro, que es el fallo natural entre dos comandos
  hermanos. El mensaje de argparse dice qué falló y nada de qué hacer — la misma clase de fallo mudo que el
  `informe.json` de V2-203, y el mismo contrato del nodo 4.20: lo que el puente sabe, lo DICE, y un fallo dice
  además cómo se sale de él. Ahora el error nombra la confusión y el comando que SÍ era, sin perder el `usage`.
  Con test de sensibilidad: la pista sale en SU error, no en todos — una pista permanente es ruido que el worker
  aprende a ignorar.

- **La puerta es NUESTRA: el worker se muere en ella y en silencio** (`nucleo/dispatch_prompts.py` +
  `nucleo/workers/session.py`, V2-211, 2026-08-20). Tres casos medidos el mismo día, tres comandos distintos, la
  misma forma: `cd in '…/zaelar/engine' was blocked` (find-theatre 15:24), `requires approval: curl -s "…"`
  (cheapest-monitor 15:35) y `requires approval: cd /Users/…` (remember-and-remind 15:38). **En headless nadie
  aprueba**, así que una petición de aprobación es un callejón sin salida: el worker la lee como un no, para, y
  el turno sigue contando que avanza. Es el confirm-gate de V2-202 una capa más abajo.
  - **Se ataca por delante**, que es lo que ya funcionó con el intérprete el 2026-08-02 (el worker quemaba
    minutos probando `python`/`python3`/`.venv/bin/python` porque nada le decía cuál estaba permitido). Las
    reglas del cajón donde corre **no las puede deducir**: o se las damos, o las descubre chocando, y chocar aquí
    cuesta la tarea. Nunca `cd` (ya está en su directorio y `PYTHONPATH` viaja en el entorno desde V2-117), UN
    comando por llamada (nada de `&&`, `;`, `|`, `$(…)`: se lee como varias operaciones y para en la primera no
    permitida), y solo los puentes — con la ALTERNATIVA nombrada, porque «no uses curl» a secas es como un worker
    empieza a escribirse su propio script.
  - **Y una red por detrás**: si aun así choca, se le dice EN EL MOMENTO que no le ha rechazado ninguna persona y
    cómo se reescribe — un turno inyectado, UNA vez, la misma forma que la entrega anticipada de V2-117. Con test
    de sensibilidad: ese hook lee TODOS los `step_result`, así que una coincidencia ancha metería avisos de
    sistema en corridas sanas.
  - **Lo que el arnés no descarta y queda escrito**: su sandbox puede amplificarlo (el motor corre desde el repo,
    así que el worker alcanza rutas del repo más a menudo). El modo de fallo —morir callado en nuestra propia
    puerta— no depende de eso.

- **Un dato del mundo, dicho con una cifra y sin consultar nada** (`nucleo/flash/router_guards.py` +
  `probe.py`, V2-210, 2026-08-20). Medido en `quick-fact-opening-hours`: «¿A qué hora abre mañana el Museo del
  Prado y cuánto cuesta la entrada general?» → «Mañana abre a las 10:00 y la entrada general cuesta 15 €», con
  **cero herramientas** (familias: flash, memory, system; ningún `search`) y la auditoría sin una sola anomalía.
  **Y las cifras son aproximadamente correctas, que es justo lo que lo hace peligroso**: el modelo va seguro, no
  pide la tool, y un precio equivocado dicho con seguridad se lee igual que uno correcto. V2-022 fijó que esta
  clase se contesta en el turno desde una fuente y V2-135 arregló la mitad de composición de este mismo caso; lo
  que faltaba era el disparo para el turno en que el modelo no pide nada.
  - **Las dos mitades son obligatorias**: la PREGUNTA de horario/precio/dirección/teléfono de algo de ahí fuera
    (y no de lo suyo — «¿a qué hora es MI cita?» es la agenda), y la RESPUESTA afirmando una CIFRA comprobable
    («suele abrir por la mañana» no afirma nada que comprobar). Un «ve a buscar» de más lo pagan turnos que
    estaban bien; uno de menos cuesta un dato inventado.
  - **Con la fuente inalcanzable la respuesta original NO se conserva**: quedarnos con ella es quedarnos con el
    dato improvisado. Se sustituye por «no he podido comprobarlo» — peor respuesta y mejor información.
  - **La VOZ se queda fuera, y es una decisión argumentada, no un descuido**: ese canal EMITE los deltas del
    modelo según llegan, así que cuando el turno podría comprobar **la frase inventada ya se ha dicho**;
    añadir detrás la versión con fuente es hablar dos veces en toda pregunta de precios. El arreglo bueno allí
    es el mismo disparo **antes** de generar, que toca el camino caliente y quiere su medición de latencia. Hay
    un test que exige que la exclusión siga siendo explícita en el código.

- **Desde fuera del proceso, «el muro no se anotó» y «se anotó y el turno lo ignoró» se veían IDÉNTICOS**
  (`widgets/navegador/data.py`, V2-207, 2026-08-20). `active_progress()` construye `walls_hit`/`last_wall` desde
  V2-176 y son lo que llega al prompt, pero `_task_view()` —la única vista legible desde fuera,
  `GET /widgets/navegador/data?q=<task>`— no los exponía. Así que con «Access Denied» en el stream y la tarjeta
  sin rastro de muro, **los dos diagnósticos opuestos daban la misma lectura**: `walls_hit == 0` es un fallo de la
  ANOTACIÓN y `walls_hit > 0` con el turno diciendo «sigo con ello» es un fallo del TURNO. Elegir mal cuesta una
  ronda entera de medición, que es lo que pasó en `find-theatre-tickets__es`. Dos líneas, pedidas por el arnés
  con el caso delante. `wall` (la página de AHORA, se recalcula en cada captura) y `walls`/`last_wall` (la
  historia, que sobrevive al re-enrutado) siguen separados a propósito: mantenerlos distintos ES V2-176.

- **La MISMA cita dos veces, ahora por la data-op del modelo** (`widgets/agenda/data.py`, V2-208, 2026-08-20).
  Medido en `remember-and-remind-deadline` (14:39), leído del `state.json` del sandbox: `[«renovar el seguro del
  coche» 2026-08-27, «Renovar el seguro del coche» 2026-08-27]` — un artículo y una mayúscula de diferencia.
  V2-194 cerró esta forma para el BACKSTOP (`already_in_agenda`, que comprueba antes de despachar) y la data-op
  del PROPIO modelo no tenía guarda: dos turnos, dos `add_meeting`, nadie comparando.
  - **La guarda vive junto a la ESCRITURA**, no en el llamante, así que la heredan todos los que escriben —
    modelo, backstop, puente del worker, el botón de la tarjeta. Es el mismo razonamiento que puso
    `already_in_agenda` al lado de su escritura y no dentro de la decisión pura.
  - **La HORA forma parte de la clave, y no solo el día**: dos visitas al mismo piso a las 10:00 y a las 17:00
    son dos citas. La regla es estrecha a propósito —mismo día, misma hora, mismo título sin artículos ni
    mayúsculas ni puntuación— porque un duplicado que se traga en silencio es peor que uno que se ve. Y un título
    que se queda VACÍO al normalizar («el», «la») no casa con nada: colapsar la basura la escondería.

- **«Aquí lo tienes» sobre una tarjeta vacía — y la frase es NUESTRA** (`nucleo/flash/router_guards.py` +
  `voice/engine/core/langs.py`, V2-209, 2026-08-20). Medido en `book-hotel-night-known__es` (13:49): «Resérvame
  una noche…» → «Voy a mirarlo en su web» → **«Aquí lo tienes.»** con la tarea en `working`, sin habitación ni
  precio. El juez: «alucinación de éxito». El modelo no escribió esa frase: la escribió `show_ack`, el ack
  canónico de un turno cuyo único acto fue abrir una superficie. **Segunda vez que una frase enlatada nuestra es
  la que miente** — V2-176 frente 1 fue «Hecho.» sobre una tarea que acababa de EMPEZAR.
  - `_surface_is_empty` contesta esa pregunta desde el 2026-08-17 y solo la ESTAMPABA en la fila de
    observabilidad; el ack seguía afirmando la entrega. Ese era el alcance de entonces («convierte ese acuse
    falso en un dato consultable»); lo nuevo es tener el coste medido.
  - **El caso del navegador es el que el chequeo genérico no puede contestar**: el estado guardado de esa
    tarjeta NO está vacío (lleva la tarea), así que «¿está vacío el estado?» responde «hay algo que enseñar»
    sobre trabajo en curso. Con una tarea VIVA, una tarjeta es una ventana a algo sin acabar, nunca una entrega.
  - **No es «no lo digas nunca»**: abrir la agenda CON citas dentro sí es una entrega, y prometer de menos sobre
    un resultado real es otra forma de estar mal. Con test de sensibilidad por los dos lados y fail-open (nunca
    afirmar que algo está vacío si no se puede saber).
  - La decisión vive en `router_guards` y la llaman los dos canales: esta clase de fallo sobrevive precisamente
    divergiendo entre ellos. Y un detalle que costaría un falso positivo: `action.split(":")[-1]` NO sirve para
    sacar el id, porque una tarjeta de instancia lleva dos puntos dentro (`canvas:show:navegador::t1` → «t1»).
  - Nodo 2.x, 7 tests. **Y un test mío que no probaba nada**: usaba `langs.get`, que no existe, dentro de un
    `if … else None: continue` — o sea que el bucle no miraba ni un idioma y pasaba igual.

- **Le decíamos al worker que mirara una captura que no estaba en disco** (`widgets/navegador/act_api.py` +
  `nucleo/nav_cli.py`, V2-205, 2026-08-20). `_shot_path()` devolvía la ruta del PNG **estuviera o no el fichero**,
  y `nav_cli` convierte cualquier valor no vacío en una ORDEN: «MÍRALA con Read "<ruta>"». Así que toda acción
  anterior a la primera captura buena —o posterior a una que falló— mandaba al worker a leer nada. Medido en
  `find-theatre-tickets__es` (15:06): `worker/task «📄 archivo ⚠️ error»: File does not exist. Note: your current
  working directory is /private/var/…/T/zaelar-workers/2`.
  - **La nota del cwd es lo que lo hacía parecer un problema de ruta, y no lo es**: la ruta es ABSOLUTA y V2-117
    ya verificó que el CLI permite leer fuera del directorio de trabajo. El fallo era ANUNCIARLA sin comprobar.
    El snapshot de texto es el fallback que el propio docstring de `_shot_path` documentaba desde siempre.
  - **Un `look` sin captura SÍ lo dice.** Ese comando existe para producir una, así que volver sin ella no es
    «nada que contar»: es el fallo de justo lo que se pidió. Con `ok` y silencio el worker lee éxito y pierde el
    camino de visión sin enterarse. La marca de que la respuesta viene de `look` es `viewport`, así que un
    `snapshot` normal no dice nada — con test de sensibilidad por los dos lados.
  - **NO es el mismo defecto que el `informe.json` de V2-203**, aunque los dos se lean como «el worker no
    encuentra un fichero»: allí no ocurrió la escritura del PROPIO worker, aquí le apuntamos a la nuestra. Mismo
    síntoma, dos raíces — y las dos aparecieron en corridas independientes el mismo día.

- **El puente del payload contestaba con el OSError pelado, y el worker lo leía como un callejón sin salida**
  (`nucleo/widget_cli.py`, V2-203, 2026-08-20). Medido en `cheapest-monitor` (ronda 21):
  `Exit code 2 no puedo leer el payload de informe.json: [Errno 2] No such file or directory` — nada entregado
  en diez turnos, y el turno diciendo que la tarea seguía en marcha. El mensaje dice QUÉ falló y nada de qué
  hacer, que es el fallo que `nav_cli` ya pagó en V2-186: **el puente es la ÚNICA vista que el worker tiene de
  este lado**, así que un callejón sin salida aquí lo es para la tarea entera.
  - Dos hechos lo convierten en salida, y los dos son gratis: **DÓNDE está mirando** (la ruta es relativa, y un
    worker que escribió en otro directorio no puede deducirlo de un `[Errno 2]`) y **QUÉ hay ahí de verdad** —
    escribir `resultados.json` y presentar `informe.json` es invisible de otra forma. Más el recordatorio de que
    son DOS pasos y éste es el segundo.
  - **No arregla por qué faltaba el fichero** (un paso de investigación caído, un Write que no ocurrió). Arregla
    que el fallo fuera mudo sobre su propio remedio. Una ruta ABSOLUTA no recibe el consejo del cwd: la receta
    las prohíbe y hablarle del directorio de trabajo sería ruido.
  - Nodo 2.5, 6 tests. **Y dos errores míos en ellos**, los dos por no ejecutar antes de afirmar: un caso pasaba
    la ruta sin la `@` (así que probaba el parser de JSON inline, no el del fichero) y otro pretendía simular un
    directorio ilegible borrándolo sin entrar en él — leyó el `informe.json` REAL que hay suelto en la raíz del
    repo (8,9 KB, del 2026-08-17, resto de un worker de antes del cwd confinado de V2-117: la colisión que ese
    arreglo eliminó, con su prueba en el disco).

- **El confirm-gate paró un clic irreversible y no preguntó a NADIE** (`widgets/navegador/tasks.py` +
  `nucleo/flash/prompt.py`, V2-202, 2026-08-20). Medido en `find-theatre-tickets__es`: el worker murió con
  `acción «Comprar entradas» NO confirmada por el operador` mientras el juez, sin ver ese texto, describía
  «esperando una confirmación que nunca se pidió al usuario». El gate hizo todo lo que su módulo le pedía
  —escribió la pregunta, puso la tarea en `needs_input`, disparó el aviso proactivo— y **no tenía salida del
  módulo del navegador ni vuelta a la conversación**: `active_progress()` (la ÚNICA ruta de una tarea viva
  hacia el prompt) se dejaba `question` fuera, y `waiting_id()` —construida exactamente para esto— **no tenía
  ni un llamador en producción**. La única puerta para contestar era el botón de la tarjeta, y delante de
  alguien que está HABLANDO no hay tarjeta.
  - **No hizo falta reproducirlo en vivo**: un campo que no se copia y una función sin llamadores se
    demuestran en el código. Lo que sí camina el camino real son los tests, por las dos mitades.
  - **El plazo era el de otro canal**: 60 s es lo que tarda el botón que está AL LADO de la pregunta. Por la
    conversación el cerebro se entera al componer su turno siguiente, pregunta ahí, y el operador contesta en
    el de después — expiraba a mitad del viaje. 300 s, el TTL del gate hermano (`dispatch._CONFIRM_TTL`),
    elegido en su día por la misma razón.
  - **La decisión vive con el estado que resuelve** (`answer_from_turn`), no copiada en cada canal: es la
    TERCERA puerta con la misma llave (V2-126 re-lanza una tarea, `widgets/confirm.py` opera un widget, ésta
    desbloquea un clic que espera AHORA dentro del navegador), y V2-153 ya pagó lo que cuestan dos copias de
    una decisión. Con guarda: un solo «sí» contesta a UNA pregunta, no a las dos que hubiera abiertas.
  - **Visto y NO tocado**: `voice/proactive.py::notify` se salta la nota al cerebro cuando no hay sesión de voz
    (`brain_notes.push` vive dentro del `if speak and _speaker is not None`), así que en el canal de texto una
    entrega proactiva no llega a la conversación por ningún camino. Aquí lo cubre la cara nueva del estado;
    como clase afecta a toda entrega proactiva y pide su propia medición.

- **Una tarea de verificación se cuelga del CASO, no del arreglo** (`tests/infrastructure/unit/test_roadmap_closure.py`,
  V2-201, 2026-08-20). El arnés recoge la mitad de vuelta del contrato casando `T<n>-uc-<slug>-verify.md`
  contra ids de **ESCENARIO**. Una tarea nombrada por el DEFECTO no resuelve y **anuncia trabajo que nadie va a
  coger**: el tablero dice que hay verificación pendiente y no la hay. Cometido CUATRO veces la misma noche
  (T428, T429, T435, T437). El arnés ya avisa, pero solo al correr `--verify`; el guarda lo caza al CERRAR, que
  es cuando se comete — y al estrenarlo encontró una quinta ajena, `T326`, dos días en `next`.
  - **Salida explícita**: hay defectos transversales cuyo re-test legítimo es la tanda entera y no un caso
    (V2-133, visto en 8 de 12). Forzarles un id falso sería peor, así que basta con escribir «NO la recoge
    `--verify`» y decir cómo se re-prueba. La salida es legítima; lo que faltaba era declararla.
  - **Contar no es verificar**: llevaba tres rondas informando de «once tareas esperando» y eran **6**, con 2
    huérfanas — una cuenta a ojo de ficheros en `next`, mezclando tareas de arreglo con las de verificación.
    Misma lección que V2-199/V2-200, aplicada a mis propios informes.

- **Cada cara del bloque del navegador tiene que poder DISPARARSE** (`tests/browser/unit/navegador/test_every_face_is_reachable.py`,
  V2-201, 2026-08-20). Dos arreglos seguidos pasaron sus tests sin hacer nada en producción (V2-199, V2-200) y
  los dos se encontraron con la misma pregunta: **¿el estado del que depende llega a existir?** Convertida en
  test: por cada condición sobre la que el bloque se ramifica, tiene que existir código de PRODUCCIÓN que la
  escriba. No prueba que la cara sea correcta —para eso están los tests de al lado— sino que **no es código
  muerto**, que es la diferencia entre «este arreglo está mal» y «este arreglo no existe».
  - **Verificado que se pone ROJO** (se rompió a propósito el patrón del login), y con un segundo test que
    exige que los nombres de las caras sigan apareciendo en `prompt.py` — si no, renombrar una dejaría el
    guarda mirando al vacío sin fallar.
  - **El repaso de la tanda entera sale limpio**: el único muerto era el ya arreglado. El sospechoso de la
    ronda, el frente 3 de V2-176, resultó alcanzable — `owner._authenticate` escribe `awaiting_login` al abrir
    la ventana y deja la tarea en `needs_input`, que es un estado VIVO, así que la cara se renderiza sobre una
    tarea activa. Un repaso que no encuentra nada es un resultado, siempre que quede la evidencia.

- **El arreglo anterior no estaba roto: estaba MUERTO** (`nucleo/flash/prompt.py`, V2-200, 2026-08-20).
  Aplicando la lección de V2-199 al resto de la tanda, el siguiente sospechoso era V2-192 — y lo era: los
  **tres** sitios que escriben resultados en una tarea de navegador (`owner.py`, `_finalize_web`, `web_cc`)
  llaman a `finish()` acto seguido, así que **una tarea ACTIVA con resultados no existe en producción** y la
  cara «YA TIENE RESULTADOS» no podía dispararse nunca. Sus cuatro tests pasaban porque creaban ese estado a
  mano.
  - **Y eso deja al descubierto la causa real** del veredicto que lo originó («ocultó que había encontrado
    datos reales y afirmó que la tarea estaba paralizada»): **el worker tiene los datos antes que el
    registro**. Encuentra los candidatos, sigue componiendo, `results` no se escribe hasta el final, y mientras
    tanto la tarea cruza los 120 s sin cambiar de URL y sale como BLOQUEADA.
  - La cara se ata ahora a la señal que SÍ existe viva —la amplitud que el propio worker reporta,
    `hbnote considered --kept N`— leída por el seam que ya enlazaba los dos registros (`record_by_nav_task`),
    no por uno nuevo. `kept == 0` o no poder leerlo significa **no**, nunca «sí»: eso mantiene V2-185 intacto.
  - El test que habría evitado esto recorre el código y exige que **cada `set_results()` vaya seguido de un
    final**. Si deja de ser cierto, que volver al campo sea una decisión y no una suposición.
  - **Regla, corrigiendo la de V2-199**: no basta con que el test cree el dato como lo crea producción — hay
    que comprobar que **producción llega a crear ese dato**. Dos arreglos seguidos pasaban sus tests sin hacer
    nada, y los dos se encontraron preguntándole al código, no a un veredicto.

- **Un test que no recorre el camino real prueba que el código compila, no que funciona** (`nucleo/dispatch.py`,
  V2-199, 2026-08-20). **V2-198 no funcionaba en producción y sus 9 tests pasaban.** `recently_ended_sessions()`
  leía `_SESSIONS` buscando las acabadas, y `_run_session` **saca el registro en su `finally`**: en un dispatch
  real no quedaba nada que leer. Los tests metían el registro a mano y no lo sacaban nunca — probaban una
  situación que en producción no existe ni un instante. Lo cazó **una escalada REAL**, corrida a propósito en
  vez de añadir un arreglo más sin medir: worker terminado, brain-note enviada, `recently_ended_sessions() → 0`.
  - `_ENDED_SESSIONS` + `_remember_ended(rec)` **antes** de tirar el registro, en los dos sitios donde una
    sesión muere de verdad. El confirm-gate NO: tiene su propia línea (V2-126/V2-190) y anunciarlo además como
    «TERMINÓ» sería contarlo dos veces y mal. Un dict LIGERO, no el `SessionRecord` — ese objeto lleva los
    handles del worker.
  - Y el guarda que habría bastado: recorre el fuente de `_run_session` y exige que el ÚLTIMO `pop` vaya
    precedido de `_remember_ended`, con la excepción del confirm-gate escrita en el propio test.
  - **Regla práctica**: cuando un arreglo dependa de DÓNDE VIVE un dato, el test tiene que crear ese dato como
    lo crea producción — no colocarlo. Un test escrito por la misma cabeza que escribió el código hereda sus
    suposiciones, y aquí la peligrosa era «el registro sigue ahí cuando la tarea acaba».

- **Una sesión de WORKER que acaba desaparecía del estado** (`nucleo/dispatch.py` + `prompt.py`, V2-198,
  2026-08-20). Medido: con `status=running` el estado dice «TAREAS DE FONDO EN CURSO»; con `status=done`
  **no dice NADA** — ni que acabó, ni cómo, ni con qué. Es literalmente lo que V2-150 cerró para las tareas de
  navegador («se le había quitado de delante lo único que podía contradecirle») **un nivel por encima, y
  peor**: una tarea de navegador solo existe con `kind=web`, mientras que **toda** escalada abre una sesión de
  worker — así que los casos que se resuelven por BÚSQUEDA (`cheapest-monitor`) o por MEMORIA
  (`remember-and-remind-deadline`) no tienen tarea de navegador y para ellos V2-150 nunca se aplicó. Son justo
  los que el arnés mide con «el usuario esperando sin feedback» y «espera infinita».
  - Misma forma que V2-197: **cuatro filtros** escribiendo `("queued","running")` a mano y ninguno para el otro
    lado. Unificados en `LIVE_SESSION_STATES`/`ENDED_SESSION_STATES`, con un test que falla si aparece un
    estado sin clasificar y otro que prohíbe volver a enumerarlos a mano.
  - `recently_ended_sessions()` (TTL 5 min) y **cada final sonando a lo que fue** — TERMINÓ / se PARÓ / FALLÓ:
    «terminó» invita a pedir el resultado, «se paró» a preguntar si se retoma, «falló» a intentar otra cosa. Si
    trajo algo, la línea manda DÁRSELO.
  - **Sexto de la serie de «hechos que desaparecen» y el primero encontrado por ANALOGÍA, no por veredicto**:
    no había corrida que lo señalara — había un patrón con cinco instancias y un registro hermano sin revisar.

- **Dos listas de estados que había que mantener sincronizadas — y `open` llevaba en el hueco desde siempre**
  (`widgets/navegador/tasks.py`, V2-197, 2026-08-20). Había **tres** copias a mano de subconjuntos del mismo
  conjunto cerrado: `active_summaries()`, `recently_finished()` y el sello de `set_status()`. Un estado que no
  esté en ninguna de las dos primeras es una tarea que el estado vivo **no menciona en absoluto**, y el modelo
  sigue con lo último que sabía — eso costó `cancelled` (V2-196). Al unificarlas apareció que **`open` llevaba
  en el mismo hueco desde siempre**: lo pone `owner.py` cada vez que se abre una página PARA el operador
  («ábreme Booking»), y esa pestaña era invisible para el turno. **No lo encontró una corrida: lo encontró
  preguntarle al código qué estados escribe.**
  - `LIVE_STATES` / `ENDED_STATES` en un solo sitio, y **el sello de «cuándo terminó» lo pone ENTRAR en un
    final** — era la tercera copia, y por ella `open` entraba en los finales y la ventana de tiempo lo
    descartaba igual. Un estado terminal que no sella su hora es un final que nadie puede fechar.
  - `open` se dice como lo que es: «está ABIERTA en pantalla (se la abriste; ahí sigue)». Decir «terminó sin
    traer nada» de algo que el operador tiene delante es negarle lo que tiene.
  - **El guarda mira el CÓDIGO, no las listas**: recorre el árbol buscando `set_status(..., "X")` y falla si
    aparece un estado sin clasificar — mismo patrón que el inventario de familias del visor, y por la misma
    razón. Quinto de la serie de «hechos que desaparecen» y el primero que no arregla una instancia sino **la
    forma de tenerlas**.

- **Una tarea CANCELADA no estaba ni viva ni terminada** (`widgets/navegador/tasks.py` + `prompt.py`, V2-196,
  2026-08-20). `active_summaries()` filtra por queued/working/needs_input y `recently_finished()` filtraba por
  done/failed: **`cancelled` era el único final que no estaba en ningún sitio**, así que el estado no la
  mencionaba EN ABSOLUTO y el modelo seguía con lo único que le quedaba —su memoria de haberla arrancado—.
  Medido en `find-theatre-tickets__es`: «desconecta por completo de la realidad del sistema (status cancelled),
  manteniendo al usuario en un bucle de espera infinito sobre una tarea que ya falló».
  - Se dice **distinto**: «se PARÓ (cancelada) sin llegar a terminar». Pararse no es acabar — «terminó sin
    traer nada» invita a esperar un resultado que nadie va a producir; decir que se paró invita a preguntar si
    se retoma. Con sensibilidad en las dos direcciones.
  - **CUARTA vez en 24 h del mismo patrón**: V2-150 (una tarea que TERMINA), V2-190 (una confirmación que
    CADUCA), V2-176 f2 (una acción DESCARTADA) y ésta. **Un hecho que no está en ningún sitio es un hecho que
    la conversación sustituye por su propia memoria** — y el modelo no inventa: usa lo último que sabía, que es
    lo correcto cuando nadie le dice otra cosa. Los estados terminales son un conjunto CERRADO y pequeño, y hay
    **dos filtros que enumeran subconjuntos suyos a mano**: un quinto estado volvería a caer en el hueco. Vale
    más una función «esta tarea ya no está viva» que dos listas que haya que acordarse de actualizar a la vez.
  - Y de paso queda **descartada con evidencia** la duda de V2-195: corriendo un encargo web real y muestreando
    el estado cada segundo, **117 de 117** muestras con tarea activa tenían el bloque `NAVEGADOR` en el prompt.
    Los arreglos SÍ llegan al modelo; el «0 veces» era el artefacto truncado.

- **La captura forense de un turno guardaba la persona y tiraba el ESTADO** (`voice/observer.py`, V2-195,
  2026-08-20). `turn_detail` existe para responder «¿qué vio el modelo?» —su propio docstring lo dice— y
  guardaba `system[:8000]` de un prompt de **19.292** caracteres. La persona estática va al PRINCIPIO y
  `prompt.live_state()` se compone al **FINAL**, así que lo truncado era exactamente la mitad que cambia cada
  turno: la hora, las tareas de fondo, el bloque del navegador, un muro, una confirmación pendiente. Guardaba
  lo idéntico en los ocho turnos y tiraba lo único que difería.
  - **Casi cuesta un diagnóstico falso**: contando sobre los timelines salía «corrida con 74 eventos de
    navegador → el bloque NAVEGADOR aparece 0 veces en el prompt», y de ahí a concluir que una noche entera de
    arreglos era invisible hay un paso. Lo que faltaba era el artefacto. **Un diagnóstico que trunca la
    evidencia que le piden es peor que no tenerlo: parece una respuesta.**
  - `_prompt_excerpt()` guarda cabeza (3.000) + cola (7.000) con el hueco **NOMBRADO** —«… [N caracteres
    OMITIDOS…; el estado vivo va al final y sí está abajo] …»— porque la lección entera es que un hueco sin
    nombre se lee como una ausencia. Verificado con un prompt REAL: un turno con `chrome-error://` conserva
    `NAVEGADOR` y `· MURO:`.

- **La suite escribía en la agenda REAL del operador: 328 citas de prueba** (`conftest.py`, V2-194,
  2026-08-20). `conftest.py` ya apuntaba `settings.SETTINGS_FILE` a un temporal por el invariante «un test
  nunca lee ni escribe el estado real del operador», y **su propio comentario citaba `store.DATA_DIR` como la
  misma lección** — pero solo aplicada dentro de los tests de widgets, no a nivel de SESIÓN. Así que cualquier
  test que despachara una data-op escribía en los datos reales: **328 citas acumuladas y 2 más por corrida**.
  Nada fallaba nunca; la basura se queda ahí y solo se nota cuando alguien mira su agenda — **o cuando un
  arreglo nuevo empieza a LEERLA**, que es exactamente cómo apareció (nueve tests se pusieron rojos por orden
  de ejecución). Aislado para toda la sesión, verificado en las dos direcciones (limpiado a 0 → suite → 0), con
  guarda en `test_suite_isolation.py` y las 328 borradas.
- **La cita se apuntaba DOS veces** (`nucleo/flash/probe.py` + `router_guards.already_in_agenda`, V2-194). El
  mismo compromiso el mismo día: una es la data-op del modelo y la otra el backstop, disparado en un turno
  posterior — su puerta («solo si ESTE turno no hizo ya la data-op») **no puede ver una data-op de un turno
  ANTERIOR**. El hermano tiene esa protección desde V2-153; aquí es peor sin ella, porque un aviso duplicado se
  oye y **una cita duplicada se VE, y se queda**. Compara por DÍA + palabras del título, no por cadena exacta
  (las dos entradas medidas se diferenciaban en un «el»), y **vive junto a la ESCRITURA**: metido dentro de
  `dated_note_backstop` puso rojos nueve de sus propios tests, porque esa función es una decisión PURA sobre
  dos cadenas y un reloj y una lectura de estado global la hace depender del orden.
  - **Y el veredicto que lo destapó era FALSO**: decía «la agenda está vacía» y el workspace de ese mismo
    sandbox tenía las dos citas, en la fecha correcta. **Tercera vez** que un juicio deduce una ausencia de una
    señal que no puede ver (`results: null` en V2-186, «no respaldado por navegación» en V2-189). Es del arnés
    y no se parchea desde el motor, pero tres veces ya no es casualidad.

- **Con varias tareas vivas, el estado MANDABA entregar una y no decía cuál** (`nucleo/flash/prompt.py`,
  V2-193, 2026-08-20). Medido en `renew-gym-membership__es`: «desviaciones de atención severas (distracción con
  tareas de navegador no solicitadas), mezclando dominios (Netflix/Teatro) al preguntar por el gimnasio». Con
  tres tareas vivas el bloque las listaba bien y luego soltaba **UN imperativo que empezaba por «ESA TAREA»**,
  sin decir cuál — o sea que el operador preguntaba por su gimnasio y el estado mandaba **entregar el teatro**.
  Con UNA tarea la ambigüedad no existe, que es por lo que las cuatro caras se escribieron sin verla: todas se
  midieron con una sola viva.
  - Cada imperativo **nombra a su tarea** («`«Entradas El Rey León» YA TRAJO ALGO`»): una orden ambigua pasa a
    ser un hecho atribuido, y el modelo puede juzgar si viene a cuento. Y se emite **UNA sola** — los hechos de
    las demás siguen listados, pero un turno con cuatro imperativos es un volcado de estado, no una respuesta.
  - **Confirma el aviso de V2-192**: no faltaba una quinta cara, faltaba que la elegida dijera A QUIÉN se
    refiere.
  - Que Netflix y Teatro estén vivos en el caso del gimnasio es **del ARNÉS** —un solo sandbox por locale para
    toda la tanda (`run.py::_sandbox_batch`)— y no se parchea: en producción esas serían de verdad las tareas
    del operador. **La eficiencia subió de 1 a 4 en esa misma corrida**, que es V2-189 medido.

- **REGRESIÓN PROPIA: pasé de demasiado optimista a demasiado pesimista** (`nucleo/flash/prompt.py` +
  `widgets/navegador/tasks.py`, V2-192, 2026-08-20). La primera corrida con los arreglos de la noche dentro dio
  la vuelta al veredicto de `find-theatre-tickets__es`: «**ocultó al usuario que había encontrado datos reales
  y afirmó falsamente que la tarea estaba paralizada**». Todas las anteriores decían lo contrario — que zaelar
  afirmaba que la tarea seguía viva cuando estaba muerta. **Ese giro es la firma de un arreglo pasado de
  frenada**, y lo era: V2-185. Un worker que encuentra los datos y hace una pausa (extrayendo, componiendo)
  cruza los 120 s sin cambiar de URL, y `active_progress()` no exponía `has_results`, así que el turno solo
  podía elegir entre «sigue viva y te dará el resultado sola» y «está bloqueada»: con datos en la hoja las dos
  son falsas, **y la segunda es peor** — la primera hace esperar, ésta tira a la basura un resultado ya hecho.
  - **Tener resultados gana al atasco y también al muro**: un muro con los datos en la mano no es un muro, es
    una entrega pendiente. Cuarta cara del bloque: «DÁSELOS en este turno».
  - Con test de sensibilidad — **sin** resultados, un atasco medido sigue siendo un atasco. Es lo que impide
    que este arreglo deshaga V2-185, que se hizo por una razón igual de real.
  - Y una señal de método: el bloque del navegador ya tiene **cuatro caras** (con resultados · esperando al
    operador · bloqueada · sana), cada una nacida de una corrida distinta. Quien quiera añadir una quinta
    debería preguntarse antes si lo que falta es otra cara o una forma distinta de decidir cuál toca.

- **«Sí, adelante» → «Hecho.» → «¿Ya está cancelada del todo?»** (`nucleo/flash/probe.py`, V2-176 frente 1,
  2026-08-20). El frente suponía que la frontera estaba en el PROMPT (narrar en futuro-presente). **Se midió
  antes de tocarlo y la hipótesis era falsa**: sobre las 78 respuestas archivadas del arnés, solo **10 afirman
  un hecho** frente a **41 que expresan intención** —el modelo casi siempre acierta— y las **tres**
  afirmaciones en corridas donde el mecanismo no registró NADA son todas la misma palabra, «Hecho.», una de
  ellas en un caso que sacó **5/5**. Una frase que aparece igual en un caso que pasa y en dos que fallan no la
  dice el modelo: es nuestra. `probe.py` mapeaba `confirm_task` a la misma rama que `widget_data`, o sea el ack
  de **TERMINADO** sobre una tarea que acababa de **ARRANCAR** — con el daño en las palabras del operador dos
  líneas después.
  - Un **sí** usa ahora la línea de espera (V2-189), que es lo que de verdad pasa; un **no** conserva «Hecho.»
    porque un «no, déjalo» SÍ resuelve algo, y sin esa mitad el arreglo sería «no digas nunca hecho», que es
    otra mentira. El corte se hace donde se CLASIFICA la respuesta.
  - Comprobado antes de tocar que **el provider de voz NO tenía el fallo** (su ack se gatea con `data_done`,
    que solo lo pone una data-op real), para no «arreglar» un canal sano — con test que lo fija.
  - **Los cuatro frentes de V2-176 quedan cerrados y la iniciativa NO**: es el paraguas de un defecto que
    pertenece a varios casos, y lo que decide si está resuelto son las corridas, no que se hayan agotado los
    frentes que se le ocurrieron a quien la abrió.

- **Una tarea parada esperando a que el operador ENTRE decía «te dará el resultado sola»** (`nucleo/flash/prompt.py`,
  V2-176 frente 3, 2026-08-20). Lo que faltaba NO era detectarlo: `awaiting_login` existe desde INI-016, lo
  escribe el flujo de login real y `active_progress()` lo expone desde V2-167 — **`prompt.py` no lo leía
  nunca**. Así que una tarea parada en el login convivía con la promesa de que terminaría sola: el operador
  esperando a la tarea, y la tarea esperándole a él. Había una línea («HAY UN INICIO DE SESIÓN PENDIENTE… si
  el operador dice que ya entró, llama a `login_done`») que solo dice qué hacer **si él lo menciona primero**;
  nadie iba a avisarle.
  - Bloquea la promesa como un muro (V2-185) pero con **su propia salida**, porque la del muro sería el consejo
    equivocado: «otro sitio, que entre él, o dejarlo» → aquí falta UNA cosa, y rendirse sobre algo que solo
    falta que él teclee es rendirse mal. Y **NO es un fracaso**: pararse en su login es la conducta correcta.
  - Se dice **aunque el operador acabe de decir que espera** — «vale, espero» → «sigo con ello» es el patrón
    medido en los dos casos, y esta espera no se resuelve sola NUNCA.
  - El login **gana a un muro** en la misma tarea: dos salidas distintas para la misma pantalla es lo que hace
    que no tome ninguna.
  - **V2-176 sigue abierta con SOLO el frente 1**, que es el difícil y no es un dato que falte: distinguir
    «estoy accediendo a tu cuenta» (hecho comprobable) de «voy a intentar acceder» (intención). Es una frontera
    de lenguaje y quiere su propia medición, no otra frase en el bloque.

- **Un hecho que solo vive un turno es un hecho que la conversación pierde** (`nucleo/flash/fast_client.py` +
  `prompt.py`, V2-176 frente 2, 2026-08-20). Tercera vez en dos días, así que ya es patrón de diseño
  y no anécdota: **V2-150** (una tarea que TERMINA desaparecía del estado), **V2-190** (una confirmación que
  CADUCA borraba el hecho de que existió) y ahora la ACCIÓN que el sistema descartó. V2-171 la dejaba en las
  métricas del turno y en observabilidad —donde el operador la ve DESPUÉS— pero el turno SIGUIENTE no veía
  nada, y el orden importa: la frase («te pongo con ello») se dice *mientras* la tool call se acumula, así que
  cuando se sabe que se descartó la promesa ya está fuera. **Lo único que todavía se puede arreglar es el turno
  de después**, y ése no tenía el hecho — así que la conversación seguía como si la orden hubiera salido, que
  es el corazón de V2-176.
  - `_RECENT_DROPS` la guarda 3 minutos (la conversación inmediata, no más) y el estado lo dice con una salida:
    «NO ha pasado y no va a pasar solo… vuelve a intentarlo». Se dice **UNA vez y se limpia** — un hecho
    repetido en cada estado deja de ser un hecho y pasa a ser ruido. Con su test, y con el de sensibilidad (un
    turno sin descartes no dice nada).
  - **V2-176 sigue ABIERTA**: es el paraguas del defecto y solo se ha cerrado uno de sus cuatro frentes. El
    más prometedor sigue sin tocar — «esto necesita tu cuenta, no puedo seguir» como respuesta EXCELENTE,
    que es `wall_reason` un nivel por encima del navegador.

- **Una confirmación que CADUCA borraba el hecho de que existió** (`nucleo/dispatch.py`, V2-190, 2026-08-20).
  Medido en `renew-gym-membership__es`, y es la evidencia más limpia de la tanda: la tarea acabó
  `status=done url='' shot_rev=0` con `n_search_events=0` —**no abrió una sola página ni hizo una búsqueda**—
  mientras zaelar decía cuatro veces «sigo sin novedades **de la web de Basic-Fit**». La causa es el
  confirm-gate haciendo lo correcto (renovar una cuota mueve dinero → tarea aparcada, V2-138) y el registro
  perdiéndolo: `_CONFIRM_TTL` son 5 minutos, y al caducar `confirm_line()` devolvía `""`, así que **desde ese
  turno el estado no decía NADA**. El modelo volvió a lo único que le quedaba, su propio «empiezo ya con la
  renovación». Mismo patrón que V2-150 un piso más abajo: allí desaparecía la TAREA, aquí la PREGUNTA.
  - **El TTL NO se toca, y esa es la decisión**: un «¿de verdad lo pago?» contestado que sí cuarenta minutos
    después es justo lo que protege. Lo que se separa es el GATE (caduca) de la MEMORIA de que hubo uno
    (`_EXPIRED_CONFIRM`, 15 min — lo bastante para sobrevivir a la conversación que lo preguntó).
  - **La seguridad queda intacta y con test propio**: `resolve_confirm` sigue leyendo `_PENDING_CONFIRM`, así
    que un «sí» tardío devuelve `None`. Sin ese test, «recuerda el caducado» y «no caduca nunca» pasarían igual.
  - Un test PREEXISTENTE exigía `confirm_line() == ""` al caducar — o sea, exigía el daño. Reescrito
    conservando lo que protegía y con la corrida que lo desmintió, no volteado en silencio.

- **El relleno de espera decía CUATRO veces la misma frase, y no lo decía el modelo** (`nucleo/flash/router_guards.py`
  + `voice/engine/core/langs.py`, V2-189, 2026-08-20). «Vale, dame un momento que lo miro.» es `filler_holding`
  LITERAL: lo emite el backstop de nunca-mudo cuando el turno vuelve sin contenido propio tras una acción que
  SÍ disparó. Medido en `cheapest-monitor` (cuatro veces palabra por palabra, con el operador contestando
  «vale, quedo atento» cada vez; eficiencia 1/5) y en `restaurant-tonight-madrid` (cinco turnos), marcado GRAVE
  en ambos. La casa ya tenía la solución sin aplicar: **`data_acks` es una tupla de variantes desde V2-038**,
  porque dos «Hecho.» seguidos disparaban el detector de bucles; al relleno de espera, que se dice mucho más,
  nunca se le puso.
  - `holding_line()` agota las variantes antes de reutilizar ninguna y nunca repite la de justo antes.
  - **Pasada la segunda espera**: el único hecho honesto que hay —cuánto lleva— con una salida («¿La dejo
    seguir o la paro y probamos de otra forma?»), que es lo que el operador puede hacer con ese dato.
  - **Jamás un PASO** — la línea de V2-133, con un test que prohíbe «login», «formulario», «fase»… en
    cualquiera de las líneas. Los minutos transcurridos no son un paso.
  - Si el hecho no se puede leer, degrada la ESCALADA y **no** la no-repetición.
  - **La otra mitad del veredicto de esa ronda no se sostiene**: dice que el producto y el precio eran falsos
    «no respaldados por navegación», y el mecanismo de la misma corrida trae `navegador_task: None` con
    `search_health: {n_search_events: 12, degraded: False}` — el caso se resolvió por BÚSQUEDA, que es
    legítimo (`quick-fact-opening-hours` sacó 5/5 así). Misma clase de inferencia que la de `results: null`:
    leer una ausencia de señal como prueba de un hecho. Es del arnés y no se parchea desde el motor.

- **El muro más silencioso: la página de error del PROPIO sitio** (`widgets/navegador/tasks.py`, V2-188,
  2026-08-20). `wall_reason()` reconocía muros de TERCEROS interponiéndose (`chrome-error://`, `/sorry/index`,
  `/recaptcha/`, `chal_t=`, `__cf_chl`) y no el 404 del sitio, que es el que más se parece a un éxito: el
  navegador lo reporta como una navegación **perfecta** —status 200, host real, la página renderiza— solo que
  no es la página. Medido en `cancel-subscription-before-charge__es`: la tarea acabó en
  `netflix.com/NotFound?prev=…` y zaelar dijo dos veces «la página sigue sin abrirse del todo» y luego que el
  login estaba listo para que el operador metiera sus credenciales. **El juez lo llamó gaslighting y no lo
  era**: nada en el estado decía que aquello fuera un error, así que «aún cargando» era lo más razonable que le
  quedaba. Agravante: V2-187 hace que el estado nombre el HOST y no la URL, lo que borra el `/NotFound` — sin
  esto habría dicho `en netflix.com` y nada más, aún más limpio y aún más falso.
  - Se compara **segmento COMPLETO de la ruta**, nunca subcadena: `/404` es un error y
    `/articles/404-ways-to-cook-eggs` no. Y la **query se excluye a propósito** — la URL medida arrastraba
    `?prev=https://www.netflix.com/es-es/ContactUs`, así que buscar en la URL entera dispararía sobre la página
    BUENA de la que venía.
  - **Sigue sin detectarse** el muro servido en el CUERPO del HTML (el «Access Denied» de `entradas.com`, visto
    en vivo): un 404 se ve en la URL; un bloqueo anti-bot con URL y status normales, no. Pide mirar el texto
    del snapshot, más frágil y con su propia medición.

- **Un hecho que no se puede decir en voz alta es un hecho que no llega** (`nucleo/flash/prompt.py`, V2-187,
  2026-08-20). En `restaurant-tonight-madrid` el juez marcó como GRAVE cinco turnos seguidos de «Sigo en ello»
  sin información intermedia — mientras la tarea recorría `thefork.es`, su lista de Madrid, un dominio APARCADO
  (`casalucio.com`) y por fin la web oficial `casalucio.es`. Sí había qué contar. Lo que el estado le ponía
  delante era `en https://www.thefork.es/restaurantes/madrid · último: 🌐 abrió https://…` — **dos URLs crudas,
  y el turno se lee en voz alta** — con la prohibición de V2-145 («no describas lo que estaría haciendo») a dos
  frases. Entre un hecho impronunciable y una prohibición, el modelo eligió callar. Es el mismo error que
  V2-185 por el otro extremo: allí sobraba una afirmación falsa, aquí **faltaba un hecho utilizable y el
  permiso de decirlo**.
  - `_site_of()` → `en thefork.es`. Un host se dice; una URL no.
  - Permiso EXPLÍCITO: «si arriba pone dónde está o cuál fue su último paso, eso es un HECHO y se DICE en vez
    de "sigo en ello"». La prohibición de V2-145 queda intacta: no inventar QUÉ hace allí.
  - Fuera el hito redundante «🌐 abrió <mismo host>»; un salto a OTRO sitio sigue contando, y cualquier hito de
    verdad se mantiene — que es la razón de existir de V2-150, con su test de sensibilidad.
  - **Sigue abierto**: zaelar atribuyó el fallo de carga al sitio equivocado (dijo la web oficial; falló
    TheFork). Al final el estado solo lleva la URL ACTUAL, así que un fallo anterior se atribuye a donde acabó
    la tarea. Pide que un fallo deje su propio rastro con el sitio dentro — cómo se REGISTRA, no cómo se
    renderiza — y su propia medición.

- **El operador pidió el aviso en SUBJUNTIVO y el backstop no lo reconoció** (`nucleo/flash/router_guards.py`,
  V2-167 ronda 12, 2026-08-20). `_REMIND_ASK_RE` solo conocía el indicativo (`me avisas`); la corrida dijo «Que
  me **avises** el miércoles 26 por la mañana». Sin reconocer la petición, el día del aviso no se podía leer por
  posición, la frase entera iba a `parse_when` —que ve «jueves 27» y «miércoles 26» y se niega, con razón— y
  `scheduled_jobs.created` salió vacío mientras zaelar decía «lo dejo apuntado y programo el aviso» y remataba
  con «Ya lo tienes todo listo».
  - **Pedir algo tras «que» pide subjuntivo en español**: no es una variante rara, es la forma natural. Por eso
    el ensanche es MORFOLÓGICO (raíz + terminación) y no una frase más en una lista — es literalmente el fallo
    que V2-151 ya pagó en este mismo módulo («medido sobre siete formas naturales, cinco se escapaban»).
  - La auditoría del stream salió **limpia** (cero `is_error`), y eso ahorró la búsqueda en falso: sin excepción
    de por medio, el fallo estaba en la lógica. Un dato en negativo también es un dato.

- **Una respuesta que aún PREGUNTA archivaba una cita hecha con su propia pregunta** (`nucleo/flash/router_guards.py`,
  V2-167, 2026-08-20). «Perfecto, lo anoto. ¿A qué hora del jueves te viene bien la renovación?» metía en la
  agenda una cita titulada **«¿a que hora del»**. La regla que lo impide ya existía en el módulo —«a question
  mark means it is still asking, and nothing gets filed on a date it has not settled»— pero solo en la rama que
  lee la obligación de la ventana; a la rama de la PROMESA nunca se le aplicó.
  - **Esperar cuesta un turno y nada más**: el backstop se reevalúa en cada turno y la cita entra en cuanto la
    respuesta deja de preguntar (medido en la reproducción: entra en el turno donde la fecha queda cerrada, con
    el título correcto). Archivar antes de tiempo cuesta una entrada equivocada que nadie va a ir a borrar.

- **El muro del cuerpo DISPARÓ, y el hecho se borró al re-enrutarse** (`widgets/navegador/tasks.py` +
  `nucleo/flash/prompt.py`, V2-176, 2026-08-20). Primera medición del detector de V2-167 en
  `find-theatre-tickets__es`: **funcionó** —el juez nos devuelve nuestra propia cadena, «cuando `phase` indique
  *el sitio bloqueó el acceso*»— y `mecanismo` subió a 3. Y el caso siguió fallando por lo mismo: diez turnos de
  «sigo sin novedades… todavía no ha reportado dónde está» hasta que el operador se rindió.
  - **La causa estaba en el propio arreglo**: `wall` se recalcula en CADA `update_view`, así que describe la
    página donde está la pestaña AHORA. El worker se comió el bloqueo, se re-enrutó —lo correcto— y con la
    siguiente captura el hecho desapareció.
  - **La vuelta de tuerca que conviene no olvidar: el hecho se borró porque el sistema se recuperó BIEN.** Cuanto
    mejor se adapta el worker, más invisible se vuelve el obstáculo, y el que espera es el único que no se entera.
  - Ahora un muro golpeado se anota en la tarea con su **SITIO** y sobrevive al re-enrutado («me bloquearon» es un
    hecho; «me bloqueó entradas.com» es uno con el que el operador puede hacer algo). Acotado a 6: un bucle no
    puede hacer crecer la tarea.
  - **La historia va FUERA del `elif` de las caras** —no es una cara alternativa, es historia y compone con
    cualquiera— y si la tarea sigue ENCIMA del muro manda la cara `MURO` con su salida, porque la historia diría
    lo mismo más flojo y dos veces. Y la instrucción **nombra la frase que sustituye**: el daño no fue no saberlo,
    fue que el operador oyó diez turnos algo cierto que no le servía.
  - Octava vez del mismo patrón en esta tanda (un hecho que solo vive un turno se pierde) y la primera sobre un
    arreglo propio.

- **«¿Hay algo corriendo?» era la pregunta equivocada** (`nucleo/flash/router_guards.py` + `probe.py` + el
  provider de voz, V2-176, 2026-08-20). El backstop de promesa-sin-acción (V2-132) se gateaba por `_hw`
  —«¿hay algo vivo?»— y lo que decide es **«¿hay algo vivo PARA ESTO?»**. Medido en
  `book-hotel-night-known__es`, con la prueba en una línea del mecanismo (`status=cancelled
  url=ticketmaster.es`): el encargo del hotel no escaló porque seguía vivo un worker del encargo ANTERIOR, y
  luego cuatro turnos de «la reserva sigue en marcha» sobre una tarea de otro caso ya cancelada. Misma forma
  medida el 2026-08-19 desde el otro lado (se preguntó por Casa Lucio, se contestó sobre El Rey León).
  - Descartado antes de tocar nada: **no** es que el sello de `cancelled` no llegue. `reset_all()` cancela vía
    `set_status`, que sella la hora, así que `recently_finished()` sí lo publica — V2-196 sigue funcionando.
  - El razonamiento de la puerta está escrito en el código y era correcto e INCOMPLETO: con una tarea viva
    «sigo con ello» ES honesto y re-escalar SÍ duplicaría el trabajo — **solo si la tarea viva es de lo que se
    ha pedido**.
  - **La asimetría de coste fija el diseño**: correr un encargo dos veces es un defecto que el operador PAGA y
    VE; que le digan «sigo con ello» sobre el encargo de otro es uno que no puede ni ver. Así que el predicado
    contesta «nada corriendo para esto» solo cuando puede saberlo, y «no puedo saberlo» = como antes (objetivo
    demasiado fino, objetivo vivo ilegible, o cualquier solape real).
  - **El detalle que costó**: comparar con `_content_words` hacía que «Hotel Palacio… PARA el 30 de agosto.» y
    «entradas PARA El Rey León» solaparan en «para» — una preposición bastaba para que dos encargos sin nada que
    ver parecieran el mismo. Se arregló en un `_topic_words` propio y NO en `_content_words`: `already_in_agenda`
    compara con él, y quitarle palabras le hace casar MENOS, lo que duplica citas de agenda.

- **Una búsqueda vacía y una búsqueda IMPOSIBLE eran el mismo dato** (`nucleo/websearch.py` +
  `nucleo/flash/prompt.py`, V2-176, 2026-08-20). `search()` recorre los backends y, cuando TODOS fallan, devuelve
  `results: []` con `source: "none"` — indistinguible de «busqué bien y no hay nada». El único rastro del
  derrumbe era un `logger.warning`, así que el turno siguiente decía lo único que tenía: «sigo con ello». Medido
  en `cheapest-monitor` (tier 2, sin credenciales de por medio): veinte búsquedas, cero candidatos, diez turnos,
  `stuck/nudge` del watchdog mientras ocurría, y el remate «Hecho, te aviso al momento». La cadena estaba abajo
  (cuota + CAPTCHA): el RESULTADO no era alcanzable y **lo único que sí lo era, decirlo, tampoco**.
  - Mismo remedio que el lado del LLM, que ya lo tenía resuelto (`provider_chain.note_failure` +
    `health_state.record`): la capa registra su salud y el turno la lee. Con el MOTIVO, no genérico —
    «se me ha agotado la cuota» y «me piden un captcha» llevan a decisiones distintas del operador, y ninguna es
    esperar.
  - **El hecho CADUCA** (10 min) además de limpiarse al primer backend que responda: la cuota se renueva y el
    CAPTCHA se va, y nadie llama a `note_success` si nadie vuelve a buscar. Sin caducidad, un fallo aislado deja
    al agente diciendo «no puedo buscar» el resto de la sesión.
  - **La instrucción ataca la FRASE, no solo informa**: el daño no fue callar el hecho, fue prometer «te aviso en
    cuanto lo tenga» sobre algo que no iba a llegar. La línea nombra esa promesa y ofrece lo que sí se puede.
  - **La clasificación NO importa la tabla del arnés** (`verify.search_health`): las dos leen la misma realidad
    por extremos opuestos, y compartir la tabla las convertiría en una sola medición.
  - Fuera de alcance y escrito: la búsqueda del WORKER es otro camino (su `WebSearch` es de Claude Code, no
    nuestra cadena), y la búsqueda seguirá caída hasta ~2026-08-30 por aprovisionamiento, lo que contamina los
    43 casos de tier 2 y no lo arregla ningún commit.

- **El traspaso de inicio de sesión no estaba cableado en el canal de TEXTO** (`nucleo/flash/web_auth.py` NUEVO
  + `probe.py` + el provider de voz, V2-176, 2026-08-20). `authenticate_web` y `login_done` se resolvían en
  `probe.py` a una ETIQUETA y nada más —ni con `execute=True`: dentro de ese bloque no había una sola mención a
  auth o login— mientras la voz llamaba a sus dos closures. Medido en `cancel-subscription-before-charge__es`
  con el mejor diálogo de la tanda (`naturalidad 5`, `adaptacion 5`: se negó a fingir que tenía la cuenta y
  ofreció el traspaso) y `navegador_task` VACÍO: «Aquí lo tienes» sin abrir nada, así que «ya he entrado» no
  tenía tarea que reanudar y «dame un momento que lo miro» no tenía nada que mirar. El juez lo llamó «una
  fachada vacía» — **las palabras eran ciertas y lo que faltaba era el cableado.**
  - Es el MISMO agujero que el bloque de cron de ese fichero ya tenía escrito («el canal `probe` es el que usan
    los casos de uso, así que el aviso NO PODÍA existir en una corrida»). Y aquí el alcance es mayor: **los 54
    escenarios del segmento `credentials` pasan por este traspaso**, así que su mitad más importante era
    inmedible.
  - **Una decisión, dos canales — no dos copias.** Duplicar las closures era la vía rápida y es la que este repo
    ya pagó (V2-153). `web_auth.py` es el único cuerpo de `start`/`finish` y la voz delega.
  - Hacía falta más que mover código: `authenticate_web` cubre CUATRO caminos y solo uno abre navegador (música
    → tarjeta de `musica`, mensajería → QR en `mensajeria`, login+tarea → escalada). Esa cadena vivía solo en la
    voz, así que cablear el texto sin ella habría roto dos invariantes en su primer turno. `web_auth.decide()`
    la comparte.
  - **Detalle que costó encontrar**: las ramas tienen que ir DENTRO de la cadena de despacho de `if execute:`,
    porque su `else` reinicia `return_extra_exec`. Puestas antes, la ejecución ocurría y la corrida no lo
    reportaba — el peor sitio donde dejar un arreglo.

- **El día del aviso podía estar SOLO en la frase del operador** (`nucleo/flash/router_guards.py`, V2-167,
  2026-08-20). El desempate por POSICIÓN («lo que viene después de *te avisaré* es cuándo va el aviso») se
  aplicaba solo a la RESPUESTA. Medido en `remember-and-remind-deadline`, tres turnos: «Apúntame que el jueves
  tengo que renovar el seguro del coche, y recuérdamelo el miércoles» → «Voy a apuntarlo y programarte el
  aviso», y `scheduled_jobs.created` VACÍO. La respuesta promete sin nombrar día, así que no había nada que
  desempatar ahí, y la frase del operador se entregaba ENTERA a `parse_when`, que ve dos días y se niega. Se
  niega con razón como parser general — pero **esa frase no es ambigua para nadie**: el día pertenece al verbo
  al que sigue. La regla ya estaba escrita en un comentario del módulo y se aplicaba a una sola de las dos voces.
  - `_asked_reminder_moment()` se consulta **entre** el desempate de la respuesta y la lectura de la frase
    entera, así que todo lo que ya resolvía sigue igual. Es la pieza COMPARTIDA por los dos canales, así que un
    arreglo cubre voz y texto.
  - **Límite a propósito**: una fecha ANTES del verbo de la petición no la ve este camino y cae al de siempre.
    Adivinar el orden de las palabras es como un backstop empieza a programar cosas que nadie pidió, y un aviso
    mal fechado no se nota hasta el día que no suena (V2-121).

- **Una fecha sola no es un compromiso** (`nucleo/flash/router_guards.py`, V2-167, 2026-08-20). Encontrado a UNA
  LÍNEA del arreglo anterior, probando que no rompía nada: «El martes recuérdame lo del seguro» programaba el
  aviso **para ese instante**. `commitment_clause` corta en el verbo de la petición y la fecha va antes, así que
  la cláusula quedaba en «El martes»; `reminder_before` la leía como el día del EVENTO, veía que el aviso no era
  anterior, retrocedía una semana, caía en el pasado y disparaba «pronto». La regla de `reminder_before` es
  correcta — lo que estaba mal era **darle una fecha y llamarla compromiso**. `clause_is_only_a_date()` responde
  a la única pregunta que hacía falta: ¿dice algo aparte de CUÁNDO?

- **El muro y el atasco NUNCA llegaron al worker** (`nucleo/nav_cli.py`, V2-167 + V2-186, 2026-08-20). Los dos
  arreglos anotaban su campo en la respuesta de `/api/navegador/act` **para que el worker actuara**, y
  `nav_cli._print_state` —que es la ÚNICA vista que el worker tiene de la página, porque el prompt del worker
  web solo le da los subcomandos de `nucleo.nav_cli`— imprimía `msg`, URL, TÍTULO, VISTA y ELEMENTOS. Ni `wall`,
  ni `hint`, ni `stalled_s`. **Lo que ese printer no imprime no existe para el worker.**
  - Comprobado EJECUTÁNDOLO, no leyéndolo: una respuesta con muro y aviso salía por pantalla sin rastro de
    ninguno de los dos.
  - **Es la explicación de por qué el muro «no cambiaba nada» ronda tras ronda**: catorce capturas de la misma
    página en veinte minutos, una corrida entera contra el `chal_t=` de Booking, otra por el `/sorry/index` de
    Google. El worker no ignoraba el aviso — nunca lo recibió. Dos arreglos que viajaban por HTTP y morían a UNA
    LÍNEA de su lector.
  - El muro se imprime **antes** de la URL y de los elementos (el worker lee de arriba abajo; un muro anunciado
    después de los botones invita a seguir clicando) y **con su salida**, no solo con su nombre: un muro sin
    alternativa es un diagnóstico, y el worker ya está en un bucle.
  - **El invariante que queda** (nodo 4.20): lo que el puente ANOTA para el worker, el CLI lo DICE — impreso, o
    renderizado por otro campo que sí se imprime (`stalled_s` → `hint`). Anotar y no imprimir no falla con
    ruido: falla en silencio.
  - Visto y NO tocado: `navegador_act` crea un `TaskBrowser` nuevo sin comprobar que la tarea siga viva, así que
    un worker que insista sobre una tarea cerrada recibe `about:blank` — generador de bucles. El código lo
    permite; que haya pasado no está medido. Detalle y el borde del arreglo, en V2-167.

- **«No me habías pedido eso» era VERDAD** (`nucleo/flash/probe.py`, V2-176, 2026-08-20). La ventana
  conversacional del canal de TEXTO se escribía **solo al final** de `run_turn` (paso (f)), así que la salida
  temprana del proveedor caído —`ok: False`, sin una palabra— se llevaba por delante la frase que el operador
  acababa de decir. Medido en `restaurant-tonight-madrid`: «Resérvame mesa en Casa Lucio» → **(sin respuesta)**;
  cinco turnos después zaelar habla del encargo del caso ANTERIOR (lo único que la memoria le dejaba) y remata
  con «no tengo constancia de ese encargo **en mi estado**». El juez lo puntuó como alucinación y *gaslighting*.
  No era ninguna de las dos: era cierto, y la causa era nuestra. Otra vez el 2026-08-20 en
  `book-hotel-night-known__es` («ignoró la petición real para ejecutar una tarea residual de memoria»).
  - **El principio ya estaba escrito y la función era la correcta.** `dialog.push_user` dice desde el
    2026-08-02: «lo que el operador dijo OCURRIÓ; cancelar la RESPUESTA no borra la FRASE». La VOZ lo honra en
    todas sus fases; el texto llamaba a esa MISMA función en el único punto donde no podía servir de nada.
  - Ahora se registra **en cuanto el prompt del turno está armado** — punto elegido, no casual: el prompt se
    compone de la ventana anterior, así que ahí no duplica la frase, y **todo lo que puede fallar queda por
    debajo**, incluidas las salidas tempranas que alguien añada mañana (así nació este defecto). La única
    salida que queda por encima es la de la bóveda, y ahí la frase entra **REDACTADA**.
  - La forma que deja atrás es la correcta: una línea de usuario **sin respuesta detrás**, que se lee como «a
    esa no contesté». Un marcador inventado diría menos y podría mentir.
  - **Séptima vez en esta tanda del mismo patrón** (un hecho que solo vive un turno es un hecho que la
    conversación pierde) y la más grave: el hecho perdido era la petición del operador.

- **Un proveedor roto no se le decía a NADIE en el canal de texto** (`nucleo/flash/probe.py`, V2-176,
  2026-08-20). La voz clasifica el error, marca el cooldown, registra la salud y degrada con una frase honesta.
  El texto no hacía ninguna de las cuatro: `return ok: False` y a otra cosa. Eso explica los **tres silencios
  seguidos** del transcript de arriba — un titular sin saldo seguía siendo el titular turno tras turno, con el
  semáforo en verde. Cerrado el REPORTE (`note_failure` + `health_state`, contrato intacto); el cooldown es
  compartido a propósito, así que reportar desde aquí es lo que permite al otro canal relevarse.
  - **ABIERTO y no tocado hoy: el canal de texto no tiene relevo.** `probe.py` resuelve con
    `spec_from_config()` directo y nunca consulta `provider_chain.pick()`. Con el titular muerto, todos los
    turnos de texto salen mudos hasta que alguien cambie la config a mano. Toca coste, identidad de modelo y la
    trampa de que *el nombre del modelo viaja con su endpoint* — cambio propio, medición propia. Y su segunda
    mitad es una decisión: igualar a la voz sería responder algo honesto en vez de `ok: False`, y eso cambia un
    contrato que leen el arnés y el frontend.

- **Un muro puede estar en el CUERPO de la página, con URL normal y status 200** (`widgets/navegador/tasks.py`
  + `owner.py`, V2-167 segunda mitad, 2026-08-20). `wall_reason()` reconoce el muro por la URL y estaba bien
  así; lo que faltaba era el caso medido en una corrida real del teatro: `entradas.com` contestó la página del
  evento con un «Access Denied» de Akamai. El worker lo leyó del snapshot y se re-enrutó solo —así que la tarea
  NO se atascó— y por eso el agujero llevaba invisible: **la única prueba de que existía era que el operador no
  vio nada.** Ni `wall`, ni tarjeta abierta, ni una palabra.
  - **NO se ensanchó `wall_reason()`.** El módulo tenía escrito por qué era URL-only —«un predicado que leyera
    dos entradas distintas mentiría a la mitad de sus llamantes»— y sigue valiendo. Hay un predicado HERMANO,
    `body_wall_reason(text)`, y quien decide cuál aplicar es el que tiene los datos: **solo la pestaña de la
    tarea tiene la URL y el texto a la vez**, así que `TaskBrowser._capture()` es el único llamante que pasa
    `page_text`. Quien no lo tiene lo omite y conserva el comportamiento de antes, fijado por un test — «arreglar
    el muro del cuerpo» y «romper el muro de la URL» caben en el mismo commit.
  - **La defensa contra el falso positivo es la LONGITUD, no una lista de agujas mejor.** Un muro de bots es una
    página casi vacía (la de Akamai medida: **214 caracteres**); un artículo que habla de bloqueos tiene miles.
    La aguja solo cuenta dentro de una página demasiado corta para ser contenido.
  - **La trampa que INVIERTE esa defensa**, y no falla con ruido: si quien lee el cuerpo corta justo en el
    límite del gate, un artículo de 50k llega «corto» y la puerta pasa TODAS las páginas — el detector se vuelve
    un declarador de muros, en silencio. Por eso el tamaño de lectura (`WALL_BODY_PEEK_CHARS`) es público, vive
    en el módulo del predicado y no en el llamante, y tiene test propio.
  - **V2-167 sigue abierta** por su frente (e), la admisión que pierde peticiones (`three-tasks-at-once`).
    Verificación en vivo pendiente: **T441**.

- **El atasco llegaba al TURNO y no al WORKER** (`widgets/navegador/act_api.py`, V2-186, 2026-08-20). V2-167
  hizo viajar el MURO hasta el worker y dejó el ATASCO solo en el prompt del FlashBrain, así que las dos
  mitades del mismo hecho acabaron en sitios distintos: **el turno se enteraba de que la tarea había dejado de
  moverse, y la única parte que podía hacer algo no.** Medido en `find-theatre-tickets__es`: el worker navegó
  siete veces, llegó a la página correcta del evento, y luego hizo **catorce revisiones de captura de esa misma
  página sin una sola navegación más** durante ~20 minutos. No estaba bloqueado ni parado — desde dentro de su
  bucle, cada `look` era tan bueno como el primero. Ahora la respuesta de cada acción del puente lleva
  `stalled_s` y una salida concreta («o extraes ya lo que tienes delante, o pruebas otro sitio»). Un MURO gana
  al atasco (más específico, ya trae su salida), nada por debajo del umbral, y **UN solo umbral** leído de la
  misma env var por los dos lados — dos copias del mismo número que derivan es un fallo ya cometido aquí.
  - **`results: null` NO prueba que no hubiera extracción**, y esa inferencia aparece en varias rondas del
    arnés: ese campo lo escribe `dispatch._finalize_web()` al CERRAR la sesión, así que con `status: working`
    no puede estar poblado. Significa «la sesión no había terminado cuando se tomó la foto». Es un fallo de
    lectura del informe, del lado del arnés, y no se parchea desde el motor.

- **Una salvedad no compite con una promesa: el estado PROMETÍA que la tarea iba a terminar sola, también
  delante de un muro** (`nucleo/flash/prompt.py`, V2-185, 2026-08-20). En `book-hotel-night-known__es` el muro
  SÍ llegó al turno —zaelar dijo «Booking me ha puesto una verificación anti-robot», que es V2-167
  funcionando— y acto seguido volvió a «sigo con ello» **cuatro turnos más** con la tarea en
  `chrome-error://chromewebdata/`. Verificado midiendo el prompt: el hecho seguía llegando todos esos turnos.
  Lo que llegaba ADEMÁS, antes y cuatro veces más largo, era «**esa tarea sigue viva y te dará el resultado
  sola**» y «**no le empujes a pararla**» — las dos FALSAS delante de un muro. El modelo creyó a la mitad
  larga, que es lo que haría cualquiera. **El error de V2-167 no fue callar el hecho, fue añadirle un pero a
  una afirmación falsa en vez de quitarla.**
  - El bloque se parte según lo que sea VERDAD de la tarea. **Sana**: entero, incluida la regla de V2-152 («la
    falta de parte no significa que esté parada»), que existe por un daño real —empujar a parar una tarea que
    va bien— y no se toca; solo deja de aplicarse donde es mentira. **Bloqueada**: sin promesa, y dice que la
    tarea NO va a terminar sola, que se diga en ESE turno «aunque el operador acabe de decir que espera
    tranquilo —esperar es justo lo que hará si te callas»— y con una salida concreta.
  - Lo cierto en los dos casos sigue en los dos (un solo navegador; nunca describir lo que «estaría haciendo»),
    con un test que lo exige: partir un bloque en dos es justo como se pierde una regla por el camino.
  - **NO mata la tarea**, aunque el juez lo proponía: la tarea de navegador y el Brain Worker son piezas
    distintas y matar una sin la otra cambia una mentira por la contraria («ha fallado» mientras el worker
    sigue). Lo que cambia es que el turno deja de prometer.

- **El turno que fija la FECHA no es el que dice el QUÉ** (`nucleo/flash/router_guards.py`, V2-176,
  2026-08-20). Medido en `remember-and-remind-deadline`: el operador dijo la obligación en el turno 1 y la
  repitió en el 3, y en el 4 solo corrigió el día. Los dos backstops leían ÚNICAMENTE el turno 4, así que
  `commitment_clause` devolvía «Sí, perdona, me he liado con las fechas. Me refiero al jueves que viene, 27»
  — y eso entró como **texto del recordatorio**: el miércoles el trabajo le habría leído al operador su propia
  disculpa. Y el apunte en la agenda no se hizo (`n_after: 1`) porque el «Apúntalo» iba en el turno 3. Los dos
  fallos, el mismo. Es **la misma forma que V2-132 ya arregló para la escalada** (`escalate_goal_from_window`):
  el turno que completa una petición no es el que la describe.
  - `commitment_from_window()` — el SUJETO sale de lo que pidió la primera vez, la FECHA de lo que fije este
    turno. Solo mira atrás si un turno ANTERIOR también pidió aviso o apunte: eso es lo que hace de este turno
    una CONTINUACIÓN y no una petición nueva, y es la guarda que impide que todo herede de todo.
  - `note_asked_in_window()` — una petición de apuntar no CADUCA porque el operador necesite otro turno para
    acertar la fecha.
  - `window=` es OPCIONAL y **los dos canales lo pasan** (`probe.py` y el provider de voz), con un test que lo
    exige: sin ventana la conducta es exactamente la de antes, así que un canal sin cablear no cambia por
    sorpresa. Verificado sobre el transcript LITERAL de la corrida.
  - **Borde conocido**: un SEGUNDO recordatorio sobre otra cosa en la misma conversación heredará el sujeto del
    primero si este turno no nombra nada. Distinguirlos pide entender el turno y no emparejarlo — terreno de
    V2-075, con su propia medición. Una lista de frases de disculpa es la cinta de correr que V2-151 ya pagó.

- **El turno corría con un tope que NO cabía la tool más importante del sistema** (`nucleo/flash/fast_client.py`,
  V2-171, 2026-08-20). `_DEFAULT_MAX_TOKENS` era **200**. Un `escalate_to_slowbrain` bien escrito ocupa
  **972-1408 caracteres de JSON él solo** —medido contra `deepseek-v4-pro`, y en esa corrida se truncó también a
  400—, y ese mismo presupuesto tenía que dar además para la frase que zaelar dice en voz alta. El proveedor
  cortaba con `finish_reason="length"`, los argumentos llegaban a medias, `json.loads` reventaba y el `except`
  hacía **`continue`**: la acción desaparecía. **67 veces en 27 corridas medidas, 48 de ellas escaladas** que
  por tanto nunca llegaron a un Brain Worker. Desde fuera se lee como que zaelar prometió y no hizo; desde un
  log de conversación, como que mintió. No mintió — le tiraron la acción.
  - **Subir el tope no cuesta latencia, y se midió ANTES de tocarlo** (que era lo que protegía el 200): un tope
    es un TECHO, no un objetivo, así que el modelo para igual cuando termina. Tres corridas por brazo sobre el
    mismo turno corto: `TTFT 0,99s / total 1,45s` a 200 contra `0,91s / 1,28s` a 1200, con la MISMA respuesta de
    ~50 caracteres. Ahora 1200, ajustable por `FAST_MAX_TOKENS`.
  - **`finish_reason` no se leía en NINGÚN sitio**, y es lo que hacía esto un misterio: desde dentro del bucle,
    un corte por tope y un final limpio eran idénticos. Ahora va en las métricas de cada turno.
  - **Un `continue` no es manejo de error.** Una acción descartada se registra en `dropped_tool_calls` con su
    razón y emite evento de observabilidad — se ve en el timeline y en el Master. Subir el tope quita la CAUSA
    medida, no la CLASE (cualquier modelo puede emitir JSON malo), y la diferencia entre un fallo y un misterio
    es que se sepa.
  - Verificado en vivo en un sandbox aislado con el encargo real del caso `cheapest-monitor`:
    `action: escalate`, `request` de 330 caracteres, la tool dispara. Tests: 5 nuevos en
    `tests/agent_headless/unit/flash/test_fast_client.py` (nodo 2.4).

- **Una ruta de FastAPI no sabe qué función viene detrás del decorador** (`widgets/navegador/act_api.py`,
  V2-169, 2026-08-19). Un ayudante nuevo (`_with_wall`) quedó insertado ENTRE `@router.post("/api/navegador/act")`
  y `navegador_act`, así que se registró como endpoint el anotador: recibe un dict y lo devuelve igual, o sea
  que la ruta contestaba **200 con el eco de la petición**, sin `ok` y sin `error`, y `nav_cli` lo traducía a
  `ERROR: desconocido` para CADA acción de CADA Brain Worker. El puente del navegador estuvo así casi un día
  con la suite entera en verde: nada afirmaba nunca QUÉ función resuelve esa ruta. Lo caza
  `test_the_bridge_route_still_points_at_the_bridge`, y la regla general es que **una ruta se verifica por su
  endpoint, no por que el módulo importe**. Lo encontró una prueba REAL en cinco minutos; 2664 tests verdes no
  podían verlo.

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
  GLM-5.2 $1.40/$4.40, Kimi K2.6 $0.95/$4.00. **Gap cerrado el
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
    repo es público): viven en `../.meshkore/docs/ops/zaelar-energy-accounting.md` (el `.meshkore/` de la RAÍZ del workspace, repo
    PRIVADO — quien clone ESTE repo no lo tiene, y es deliberado), junto a
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
    coincidían en 114 de 1.070 eventos. Nodo 2.24, con las dos ramas (cancelado→estimado, completo→verdad del
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
    | AIMLAPI (titular anterior) | 31/42 | 0 | 1.297 ms |

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
    modelo** (medido: flash ×1,30, grok-4-fast ×1,05, gemini-2.5-flash **×1,00** — un ×1,3 plano
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
  `.meshkore/roadmap/initiatives/archive/V2-100-feedback-widget.md`, local; the cloud/business side is
  INI-023 in the workspace root's private repo). ⚠️ **Read V2-256 before trusting this section**: the
  engine had no failure branch at all, so a refused submission was invisible on both surfaces.
  One native surface (`frontend/app/components/FeedbackWidget.js`,
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

- **La memoria estaba sana; la deuda era ESTRUCTURAL — y tres imports inversos se BENDICEN, no se arreglan**
  (V2-273, 2026-08-23, auditoría pedida por el operador: *«código elegante, muy modular, escalable, n
  componentes»*). Medido antes de tocar nada: found@10 **94,7 %** (objetivo ≥92 cumplido), gate de fidelidad de
  REM, corpus longitudinal de 270 días y frontera con trinquete — nada funcional que arreglar. Lo que sí:
  `nucleo/memory_agent.py` eran **1.486 líneas con seis responsabilidades**, y lo estructural no es el tamaño
  sino que era **la política de escritura de la memoria viviendo FUERA de `memory/`**, o sea fuera del contrato
  que V2-114 promete reimplementable. Pasa a paquete (`lang_marks · gates · classify · dossier · external ·
  ingest`, ninguno >450 líneas) con `__init__` re-exportando la superficie completa: cero cambios en llamadores
  y en tests. La fachada adelgaza igual (1.075 → 758, con `memory/_prompt.py` llevándose lo que PINTA).
  - **Trinquetes ANTES de mover**, que es lo que hizo el resto seguro: inventario CERRADO de imports inversos
    (solo puede bajar) + la superficie de la fachada CONGELADA. Un nombre perdido en la mudanza rompe ahí y no
    en un llamador tres semanas después.
  - **6 → 3 imports inversos**, y los tres que quedan son la RESPUESTA, no trabajo a medias: `db → workspace`
    es una ruta de fichero, y los dos de `rerank.py` compran una **garantía de facturación** — su comentario
    dice que se metra estando DORMIDO para que encender el reranker remoto no salga gratis por descuido, y un
    callback registrado reabre ese agujero para cualquier proceso que olvide registrarse. **Pureza que cuesta
    dinero sin facturar es mal negocio.** El router HTTP sí sale (`server/memory_routes.py`): era transporte.
  - **`workers_pruned` pasa a None y no 0** al inyectar la limpieza del ledger: `0` es «miré y no había nada»,
    `None` es «nadie me dio con qué mirar». Confundirlos es cómo una función se pierde en silencio.
  - **La suite decía «sin red» sin serlo**: `config/v2.json` (GITIGNOREADO, de cada máquina) pisa al entorno,
    así que `MEMORY_RERANK=off` no apagaba nada y el reranker local se ponía a DESCARGAR — de 34 s a colgada
    sin tocar un test. Ahora la suite declara su entorno y ese gana DENTRO de la suite; la precedencia de
    producción intacta. Y un embedding degradado que nadie pidió pone la salud en **ámbar**, gemelo del canal
    de paráfrasis mudo: este módulo escribe con `logging` de la stdlib, así que su aviso salía sin marca de
    tiempo en medio del ruido del arranque.
  - **Tres cosas las cazó el método, no la lectura**: un fixture del conftest RAÍZ pidiendo `monkeypatch`
    reordena el teardown de TODA la suite (puso en ERROR un test que nadie tocó); un verde que no probaba nada
    porque la config había cambiado entre la medida y el arreglo; y un `except Exception` convirtiendo un
    TypeError en warning, o sea la consolidación entera dejando de correr en silencio.
  - **Abierto**: recall@1 a 7,7 pp del objetivo —T3 cerró NEGATIVA, no hay reranker mejor en nuestro runtime, y
    el candidato es el `concept_discount` aparcado con su A/B— y **el p50 real de `query()` en el turno vivo
    sigue SIN MEDIR** (el 589 ms que circula es del harness frío). Nada del retriever debería tocarse sin ese
    número. Sin verificar en vivo.
  - ⚠️ **Y un dato de contexto**: este `CLAUDE.md` ha pasado de 304 KB (V2-117, 2026-08-18) a **508 KB**. V2-117
    quitó el daño confinando el cwd del worker, pero el fichero sigue creciendo ~40 KB/día y es el contexto que
    lee cualquier agente que trabaje aquí.

- **Un recall que NO llega se veía igual que una memoria vacía** (V2-311, 2026-08-25). Buscando el p50 real de
  `query()` en el turno vivo —el número que V2-273 dejó pendiente y que gateaba tocar el retriever— salió otra
  cosa. Sobre **223 líneas de tiempo de sesiones vivas**: de 27 turnos que PIDIERON memoria durable, **21 (77 %)
  volvieron con `mem_ms: null` y «→ 0 tarjetas del largo plazo»**, y los 6 que cerraron midieron **p50 689 ms ·
  p90 797 ms** contra un presupuesto de **800 ms**. La separación es perfecta (`mem_ms: null` ⟺ cero tarjetas) y
  la distribución no cae holgada bajo el corte: **está pegada al corte**.
  - **El aviso existía y no tenía lector.** `recall_budget.compose()` pone `timings["recall_timeout"]` al agotar
    el presupuesto —y el nodo 2.28 lo afirmaba desde F1, con el comentario «y encima no dejó rastro»— pero
    `grep` daba **un escritor y cero lectores**: el `timings` se lo queda el turno y se tira, y el único otro
    testigo era un `logging.info` sin marca de tiempo en medio del ruido del arranque. Un turno que responde sin
    su memoria durable se leía, en TODAS las superficies, como un turno que no tenía nada que recordar.
    **La respuesta equivocada era la tranquilizadora** — gemelo exacto del `embed_pending=1` de dos días antes.
  - **Se publica por los DOS canales que ya usa `memory/`**: fila en la línea de tiempo (motivo + presupuesto +
    pregunta recortada, lo que se lee DESPUÉS) y ámbar de estado (lo único que se ve MIENTRAS). Y **no se
    `clear()` al salir bien**: la clave `memory` la comparten el descuadre de espacio vectorial y los embeddings
    degradados, así que limpiarla aquí borraría un aviso ajeno; envejece con su TTL. Un recall que sí llega no
    dice nada — un aviso que sale siempre no es un aviso.
  - **El presupuesto NO se toca**: subirlo es un canje latencia↔memoria del operador, y con n=6 no hay base. Lo
    que este cambio deja es la instrumentación para decidirlo con una cuenta real en unos días.
  - **Y reordena lo aparcado**: el `concept_discount` de V2-031 puede esperar, porque **afinar el ORDEN de un
    recall que el 77 % de las veces no llega no mueve nada de lo que el operador percibe.** Primero que llegue.
  Sensibilidad: desarmado el publicador, 2 de 10 casos en rojo. Sin verificar en vivo.
  - **Addenda, mismo día — la métrica FANTASMA.** Lo señaló `motor-dev-2`: `wait_for` cancela la ESPERA, no el
    HILO. `to_thread(compose_recall)` sigue hasta el final y escribe su `mem_query_ms` **en el `timings` del
    turno que ya lo abandonó**. Contra producción: los eventos de respuesta llevan **2,1 s · 3,5 s · 21 s** con
    presupuesto de 800 ms (9 de 20 por encima del corte). El coste de un recall que nadie usó, publicado como la
    latencia de memoria de ese turno — y es justo el campo que se consulta para responder la pregunta que abrió
    la iniciativa. Arreglo: el hilo recibe **dict propio** y se fusiona solo si llegó a tiempo. Y **corrige una
    cifra mía**: los «556-797 ms» eran solo los seis que cerraron DENTRO del presupuesto, **no contenían la
    cola** — que llega a 21 s. Importa porque quien razone sobre mi número para entregar el recall tarde como
    nota al turno siguiente necesita saber que puede llegar cinco turnos tarde.
  - **Paso 3 — el refuerzo sigue a la ENTREGA, no al cálculo.** El tercer defecto de la misma raíz, y el que
    tocaba memoria: `compose_recall` pedía `reinforce_used=True`, y `reinforce()` es escritura durable
    (`access_count++`, `last_access=now`, `weight+step`). Como el hilo abandonado termina igual, **los 21
    recalls que nadie vio ya venían subiendo el peso y rejuveneciendo píldoras por preguntas que jamás se
    contestaron con ellas**. Ahora refuerza quien ENTREGA: dentro de presupuesto (al turno) y en el rescate
    tardío FRESCO (al turno siguiente, matiz de `motor-dev-2` y es correcto — sin él, «no reforzar lo no
    entregado» se satisface no reforzando nunca); un bloque descartado por rancio no refuerza. **Lo que se
    mueve es el MOMENTO, no la política**: `query()` no reforzaba los `ids` del paquete sino UNA píldora de
    contenido, y llevarse la selección con el disparador habría reforzado 40 en vez de 1 **sin que fallara
    nada** — por eso `reinforce_ids_for` se queda dentro de `memory/`. Trinquetes: guarda por AST sobre el
    literal + el reporte en la fachada (1 y 2 en rojo). Y mordió el de frontera de V2-273: la superficie de
    `memory.api` está congelada y un nombre nuevo no entra sin declararse en `__all__` y en el inventario.


- **Un encargo viejo viajaba en CADA prompt como un hecho permanente de la persona** (V2-337, 2026-08-26,
  encargo del arnés). Midieron que zaelar arrancó hablando de COCHES al pedirle un monitor, arrastrando el caso
  anterior del lote. No era recall por similitud ni la ventana: era el **bloque de ESTADO**, que va siempre y no
  depende de la pregunta. `salient_long` ordena por importancia·peso, y ahí entraba «Tarea pendiente para el
  asistente: buscarle un coche de segunda mano» **junto a «Vive en Madrid» y bajo la misma orden**: «dalo por
  sabido sin buscar».
  - **No es cosa del plató**: en la memoria VIVA del operador, **3 de las 5 plazas eran encargos** (un vuelo a
    Londres, un fontanero sin cuota, una prueba de worker), desplazando a la persona. Plató ES 2/5, US 0/3.
  - **Ninguna regla lo tapaba**: `background_slot_off_topic` (V2-254) es de RECUPERACIÓN y esta superficie no
    pasa por `query()` — la **cuarta** superficie fuera de la regla, tras las tres de su docstring. Y va por
    SLOT: las píldoras de encargo tienen **`slot` NULL**, así que nada puede superseder-las.
  - **La clase ya estaba en el dato y se tiraba.** `mem_processor` manda una tarea delegada a `kind="result"`
    («jamás a goal.current») y `salient_long` DEVUELVE `kind`; `compose_state` no lo miraba. Sin lista de
    palabras y sin campo nuevo: se renderiza la distinción que ya existe. Sección propia que dice lo que SON y
    nada sobre qué hacer — **no se suprimen** (sería el fallo contrario, un agente que olvida lo que le
    pidieron) y **no se ordena** en ninguna dirección, que es doctrina de `workers/findings.py`.
  - **Sensibilidad en las DOS direcciones**: mezclarlo todo otra vez → 3 rojos; mandarlo TODO a encargos → 2.
    La segunda importa igual: si no, la regla se cumple dejando al agente sin saber dónde vive su operador.
  - **Abierto**: los encargos siguen COMPARTIENDO el top-5 con la persona (2 plazas reales de 5 en la memoria
    del operador), un nodo-concepto también ocupa plaza, y las píldoras de encargo siguen sin slot y sin nadie
    que las cierre — esto reduce el daño, no cierra el encargo. Sin verificar en vivo.

- **La SONDA de backend esperaba como una llamada real: 20,3 s en el PRIMER acceso a memoria** (V2-349,
  2026-08-26, encargo de medición). Se reportó como «la memoria tarda ~10 s en no encontrar nada». **La consulta
  tarda 25 ms.** Lo que tardaba era el primer acceso de un proceso fresco: crear la tabla vectorial necesita
  `dim()` (`memory/db.py:112-114`), eso resuelve el backend, y la sonda usaba `ZAELAR_EMBED_TIMEOUT` (20 s)
  contra un Ollama VIVO pero con la GPU ocupada por el CORAZÓN. Con el backend forzado, ese mismo `get_db()`
  baja a 104 ms: el esquema es inocente.
  - **Dos presupuestos, no uno más pequeño.** `ZAELAR_EMBED_PROBE_TIMEOUT` (1,5 s) para la sonda; los 20 s
    intactos para las llamadas REALES, donde esperar es mejor que degradar el espacio. Son dos preguntas
    distintas y bajar el global habría sido más fácil y habría sido otro fallo.
  - **UN TIMEOUT NO ES UNA AUSENCIA, y es lo que hace SEGURO acortar la sonda.** Con 20 s una petición encolada
    podía llegar; con 1,5 s no, y el camino anterior lo habría leído como «Ollama no está» → fastembed → 384
    rellenados a 768 contra un índice sellado embeddinggemma. Abaratar la sonda **a secas** compraba 19 s a
    cambio de **cambiar el espacio vectorial más a menudo**: el fallo que a V2-103 le costó una auditoría. Ahora
    un reloj agotado se comporta como la saturación (conserva el espacio, difiere el vector, re-sondea en la
    llamada siguiente); lo que degrada sigue siendo un fallo definitivo y RÁPIDO, que llega en milisegundos.
  - **Y su reverso**: conservar el espacio hacía que cada embed real esperase 20 s — la latencia de V2-311 por
    otra puerta. Mientras Ollama esté mudo, las llamadas reales usan también el reloj corto; la primera
    respuesta buena restaura el presupuesto entero.
  - **A/B** (mismo código, mismo Ollama, solo la variable): primer acceso **20.251 → 1.673 ms**, primera query
    **20.161 → 1.553 ms**, y el espacio **intacto en los dos** (ollama, 768). Desarme: sonda de vuelta a 20 s →
    1 rojo; timeout que vuelve a degradar → 1 rojo.
  - **Dos cosas las cazó el método, no la lectura**: un `UnboundLocalError` MÍO que el `except Exception` de
    `_ollama_embed` reportó como «Ollama ausente» —la respuesta tranquilizadora otra vez, y sigue ABIERTO: en
    producción un bug nuestro degradaría el espacio vectorial— y una fuga de bandera que cazó la suite existente
    (`reset()` no limpiaba `_ollama_timeout`, y una heredada dejaría las llamadas reales con el reloj corto para
    siempre). Cuatro dobles de test rompieron por FIRMA: se actualiza la firma, nunca lo que afirman.
  - ⚠️ **Y una corrección mía en el sitio donde la dije**: afirmé al cluster que se sondeaba DOS veces y que el
    2× lo confirmaba. Instrumentado, la sonda es **una**; el 2× salió de comparar dos medidas y **asumir
    linealidad**. Lo medido estaba bien, lo deducido alrededor lo escribí igual de seguro y sin prueba — y una
    de las tres partes del plan ya autorizado sobraba. Sin verificar en vivo.

- **El widget de YouTube tiene LISTA, y `add` NUNCA arranca la reproducción (V2-366, 2026-08-27)**: encargo
  del operador — subir `youtube` al nivel de `musica`. `data.py` gana `list`/`pos` + data-ops
  `add`/`play_item`/`next`/`previous`/`ended`/`remove`/`move`/`sort_list`/`filter_list`/`clear_list`; el widget
  dispara `ended` (handshake `listening` del IFrame API) y el servidor encadena — uno detrás de otro solos. Las
  decisiones que sostienen el diseño: **`add` no autoreproduce** (como el «Añadir a la cola» de YouTube) y por
  eso queda FUERA de `runtime.produce` — la lista se puede llenar con el agente parado (V2-092) sin abrir un
  agujero en el gate; `pos` significa «último reproducido», que es lo que hace que quitar el que suena conserve
  el hilo (`ended` sigue con el que le seguía); `close` cierra el VÍDEO y la lista sobrevive; `filter_list` es
  SOLO vista. UI = lista LINEAL de texto sin miniaturas (diseño explícito del operador). ⚠️ Dos trampas pagadas:
  los handlers de `message` de youtube y musica escuchan el MISMO window — **sin filtrar por el id del handshake,
  el final del player de uno avanza la cola del OTRO** (el de musica era latente hasta que youtube empezó a
  emitir; arreglados los dos); y `dict(_SEED)` con una lista dentro es copia SUPERFICIAL — un `append` sobre una
  db «fresca» mutaba el seed del módulo. Nodos 4.52/4.53 (el 4.53 RENDERIZA, con desarme verificado) y 4.3.

- **Buscar vídeos va al REPRODUCTOR, no a la hoja de resultados (V2-402, 2026-08-27)**: visto en vivo por el
  operador — «buscando vídeos estás utilizando el widget de resultados». La causa era arquitectónica: una
  búsqueda de contenido multimedia NO TENÍA DUEÑO — `play_video` cargaba UNO («pon el tráiler de…»),
  `play_music` reproducía, y el plural («búscame vídeos de…») caía a `escalate_to_slowbrain`, cuya superficie
  `lista` ES la hoja (`nucleo/surfaces.py`: vocabulario cerrado, sin destino multimedia). Regla del operador,
  ahora escrita en el catálogo: **contenido que se VE u OYE (vídeo, música, podcast) se canaliza por su widget
  dedicado — buscarlo incluido; la hoja es para INFORMACIÓN**, aunque un resultado informativo (un hotel)
  contenga vídeos. Piezas: data-op `search` del widget `youtube` (varios candidatos a la LISTA, filas de `add`,
  **sin tocar el player** — la ley de V2-366 vale para buscar); `play_video` gana `action: play|list` y su
  descripción reclama la búsqueda; el NO-list de escalate la devuelve; `play_music` nombra PODCAST. La
  normalización play/list vive **UNA vez** (`video_turn.normalize_action`) y la consumen voz y probe — la
  lección V2-380/383. Nodo 4.58, desarmes en las cinco direcciones. **Sin verificar en vivo.** Abierto: el
  audio-browse puro no tiene superficie en `musica`, y un worker legítimo (curar una playlist) sigue entregando
  a la hoja — `surfaces` no conoce un destino «widget multimedia».

- **El Brain Worker corre con lo que la NUBE puede contratar, y un escalón que no ve se declara ciego
  (V2-403, 2026-08-27)**: decisión del operador — Z.AI pasa a titular del worker (`config/v2.json §code_agent`, orden
  del operador que `providers.pick()` respeta). Antes el local caía a la **licencia local de Claude Code** y
  medíamos un worker que la nube no puede ejecutar jamás: dentro de un contenedor no hay login de navegador
  (`cloud/provisioner` ya lleva `CODE_AGENT_BASE_URL=api.z.ai/api/anthropic` desde 2026-08-14). La licencia
  queda de salvavidas SOLO local. Dos fallos MUDOS salieron al hacerlo, los dos del mismo tronco —un modelo
  que RAZONA:
  · **`vision: False` para z.ai** (`nucleo/workers/providers.py::KNOWN`, que declara CAPACIDAD, nunca
    preferencia — el modelo lo elige el operador en su config). Ese gateway no le pasa la imagen al modelo: la
    sube y le da una URL que no alcanza. `glm-5.3` lo DICE; `glm-4.6`, `glm-4.5v` y `glm-4.6v` no — contestan
    con seguridad sobre una imagen que no vieron (rojo→«Orange», azul→«Teal», un PNG con texto descrito como un
    CAPTCHA de pasos de cebra). Un dato inventado con FORMA de observación es peor que un hueco, y el camino de
    visión del navegador manda una captura en CADA acción: la bandera es lo que hace llegar `ZAELAR_NAV_VISION=0`.
  · **El compositor del brief pide la RESPUESTA, no la deliberación** (`FastClient.complete(no_thinking=…)`,
    nuevo y apagado por defecto — cero regresión para el resto). El bloque de razonamiento se cobra contra
    `max_tokens`, así que el brief volvía truncado con un **200 y sin error**, y el log decía «respuesta
    ilegible» — que se lee como modelo roto y era un presupuesto que nunca cupo. Medido: ON = 67,7 s y 2.517
    tokens (con techo de 8.000); OFF = 22,3 s y 681, el mismo brief. El worker no arranca hasta que esto
    contesta, así que esos segundos son del cliente. Verificado en vivo: brief en ~13 s donde antes no había
    ninguno. Nodo 4.59, cuatro desarmes. El reparto completo y qué se puede cambiar vive en el WORKSPACE
    (`docs/ops/zaelar-model-allocation.md` de su `.meshkore`), no aquí: es producto + nube.

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

- **El deck móvil se NAVEGA, y su restore alcanzó la paridad V2-351 (V2-474, 2026-08-29)**: auditoría del shell
  móvil contra la semana de cambios de widgets + iteración de UX pedida por el operador. Lo medido primero: los
  PIPS —la única señal siempre visible de «hay más tarjetas»— estaban a `bottom:6px` DENTRO del stage, o sea
  **100 % debajo del dock fixed** (z-60, 84px+safe): no existían en pantalla, con todos los tests de fuente en
  verde. Ahora viven encima del dock y cada pip es un BOTÓN que salta a su tarjeta. Tres afordancias más, todas
  chrome del host (la regla «un dedo es del widget» no se toca): el contador `k/n` de la cabecera es un botón
  que abre el **conmutador de tarjetas** (fila por tarjeta con su título VIVO, la actual marcada, × de 44px,
  «cerrar todo»; para ENCIMA del dock y se repinta/cierra siguiendo al deck), **swipe de UN dedo sobre la
  CABECERA** para paginar, y el **badge de «reproduciendo»** en pip y conmutador — leído del
  `runtime.active_when` del manifest con la MISMA semántica que `widgets/producers.py::is_producing`
  (true/false por veracidad, resto por texto, `error` nunca produce), jamás una lista de nombres de widgets,
  que es el `if` por-widget que ese contrato existe para matar. Y `restore()` gana las cuatro piezas que el
  escritorio cogió en V2-351 y este host no — cada una muerde MÁS en un móvil: fallback de `/api/canvas/layout`
  (el localStorage es per-navegador y un teléfono ES un navegador nuevo: una PWA recién instalada abría con el
  deck vacío con encargos vivos en la cuenta), barrido de fósiles (la tarjeta BASE junto a su instancia
  resucitaba una hoja vacía encima de la llena), encargos vivos del servidor aunque este dispositivo no los
  guardara, y `navegador::tN` sin tarea viva fuera. Trinquetes: el 4.18 aprende `tr(` (las claves i18n de
  Deck.js escapaban al ratchet — tres claves faltantes con el escaneo en verde) + checks derivados de pips/
  restore/badge; nodo NUEVO **4.87** renderiza el deck con tres widgets falsos por route-interception y lo mide
  todo (23 checks, 4 desarmes verificados, y el de «instalación nueva» necesita contexto de navegador PROPIO o
  el localStorage de la página anterior lo falsea). La auditoría de widgets en vertical salió limpia:
  `imagenes` tiene flechas y miniaturas táctiles (el teclado de V2-465 es extra), las acciones de mensajería
  van a opacity .3 (atenuadas, no invisibles), y `arrange()` del deck ya era el no-op correcto. **Sin verificar
  en vivo con el motor del operador** (abrir /m headless competiría por el candado de voz); la nube no lo tiene
  hasta la próxima release.

- **El arranque en frío enseñaba claves i18n crudas — y la leyenda buena llegaba sin que la viera nadie
  (V2-481, 2026-08-29)**: pendiente conocido desde que se desplegó el móvil. Son **DOS** defectos y arreglar uno
  solo no arregla nada. (1) `t()` cae al bundle inglés y si tampoco está muestra la CLAVE —correcto en una
  pantalla cargada— y en el arranque en frío `/api/i18n/bundle` no contesta todavía, así que el **primer
  pantallazo de quien acaba de instalar la PWA** era `boot.encendiendo`. (2) `LABELS` del `BootOverlay` era un
  literal de módulo, así que `t()` corría UNA vez **al importar el fichero**: cuando el motor por fin
  contestaba, la cadena buena llegaba y no la veía nadie — el mismo patrón que V2-124 midió en el móvil. El
  suelo (`BOOT_FLOOR`) es **estrecho a propósito** (solo lo que se pinta antes de que el motor conteste) y
  **byte-idéntico al bundle base**, con guarda: si dijera algo distinto la leyenda cambiaría de frase a mitad
  del arranque. ⚠️ La primera versión del guarda solo leía la constante y **pasaba con el suelo desarmado** —
  un guarda que comprueba que el código EXISTE no comprueba que se USE; el bueno enchufa el módulo real sin
  ningún bundle. Nodo 4.1.

- **Cinco filas eran pocas, y decirle que hay más no es enseñárselas (V2-479, 2026-08-29)**: `_sheet_top_rows`
  empujaba al prompt como mucho **5** filas de la hoja. Medido dos veces: `search-buy-camera__es` tenía CATORCE
  candidatos y cuatro de las cinco mostradas eran accesorios (V2-374); `find-best-hotel-city__us` ronda 6 tenía
  **DOCE hoteles con dos por debajo del tope del operador** (€46 y €58) y las cinco mostradas eran las caras —
  el turno concluyó «all well above your $150» sobre un conjunto que no había visto entero. La segunda es la
  que decide, porque **V2-374 ya añadía el aviso «y N más no listadas» y concluyó igual**. Tope suave 5 → 12
  con un **techo DURO de TAMAÑO** (`_SHEET_ROWS_BUDGET`, 1200 caracteres): `fila()` trunca a 70+20, así que una
  fila cabe en ~100 y doce son ~1.200 caracteres en un prompt de ~10.000 tokens. El techo es de tamaño y no de
  conteo a propósito — una hoja de títulos larguísimos con un cap por unidades mete lo que le dé la gana. **No
  se reordena** por relevancia al criterio: el orden es el del DOM y reordenar por «lo que encaja» sería
  adaptarse al caso de uso. Abierto: concluir sobre lo no visto sigue sin estar garantizado por código.

- **A terminal field cannot tell a process, and a zero must say why it is zero (V2-512, 2026-08-30)**: two
  mistakes hours apart, same shape, both already on their way to another agent when they were caught.
  - The report published `navegador_task.url` — the LAST url — and from it I wrote that the agent «parked on
    Amazon's home page without searching». It had passed through `amazon.com/s?k=27+inch+4k+monitor`, the
    correct results page, two steps earlier, and Best Buy after that: **19 pages**. A terminal field invites
    exactly that reading.
  - `search_health` reported `degraded: false` while `bhphotovideo.com/c/search` answered **403 with an
    anti-robot page** (verified with `curl`). So «found nothing» and «was not let in» reached the judge as the
    same fact — and a product defect gets invented out of a retailer's mood.
  - Fixed with `page_journey`: the browser's route travels WHOLE (title + url, in order) and the pages that
    were WALLS are named. The judge is told the limit in the line it reads: *this is not the product, do not
    score it as searching badly — what IS the product is what it did when it hit the wall.*
  - Same rule as V2-506 one level up: **a number, a url or a silence only counts if it says what it is of.**

- **The instrument must not turn a coincidence into a cause (V2-506, 2026-08-30)**: two false `[alta]`
  findings in the first three rounds of the 24h iteration, both the same shape — a field meaning
  *co-occurrence* rendered as *attribution*, which the judge then signed as a product defect.
  - **Escalations counted as workers.** `duplicate_errands.groups[].n` counts escalation REQUESTS with the
    same text (`text_source: escalate.requested`). The report printed «2 workers para UN encargo … se paga
    entero cada vez» with `worker_health.spawned: 1` in the same block. One worker ran; nothing was paid
    twice. `dev-main` disproved it by reconstructing the window from the lab's `sandbox.db` — **the
    instrument spent another agent's time.** The real finding was underneath: escalation 1 opened its
    results sheet on screen and its worker never started.
  - **One broken session counted as three broken bridges.** `worker_bridges.errors` increments once per
    bridge NAMED in a session containing `Exit code 2` — its own docstring says «una coincidencia en la
    sesión, no una atribución». The judge received it as an error list and filed `[alta]` naming
    «argumentos faltantes, errores de archivo», **detail it invented**: it had received three counters.
  - ⚠️ **The judge treats the mechanism report as ground truth BY DESIGN** — that is what makes a use-case
    verdict worth more than reading a transcript. The price is that every unqualified number becomes a fact
    it reasons from and fills in. So: **a number that reaches the judge must carry what it is a number OF —
    in the line the judge reads**, not in the detector's docstring. Both detectors documented their limit;
    neither published it.
  - A wrong product defect is not a smaller version of a right one: it sends a developer to the wrong file,
    and it makes the next true finding cheaper to dismiss.

- **A retired provider may not be named by ANY ladder (V2-504, 2026-08-30)**: V2-500 retired xAI and Groq
  by measurement (`403 used all available credits`, `404 model_not_found` — `llama-3.3-70b-versatile` no
  longer exists) and removed them from ONE ladder. There are TWO. The voice LATENCY-RELAY ladder
  (`provider_chain._VOICE_RELAYS`) went on naming both for eleven days.
  - **It broke nothing, and that is the point.** In self-host that ladder resolves EMPTY (titular only), and
    measured on all three engines it was empty. No llama ever ran. What it did instead was slower and worse:
    it was the place where the allocation still said something else, so a settled decision got re-opened
    every time somebody read it — the operator has had to repeat «the memory runs on DeepSeek direct» more
    times than any measurement should need.
  - So the rule is not "the catalogue is right", it is: **a provider in the table's `retired` section may
    not appear in any ladder the engine builds.** Guarded by asking the builders as FUNCTIONS
    (`_VOICE_RELAYS`, `_known_chain`, `workers.providers.KNOWN`), never by grepping source — a text guard
    goes green on a rename and red on a behaviour-preserving refactor.
  - The latency relay now has ONE rung, and it is the same brain over another endpoint: relaying no longer
    changes the model under measurement, which was the other reason a long ladder was in the way.

- **A lab measures the PRODUCT, not the machine it runs on (V2-502, 2026-08-30)**: both labs booted from
  the same commit and the ES one answered `deepseek-v4-flash` through a THREE-rung chain while the US one
  answered `deepseek-v4-pro`, the table's titular. Two silos, two products — and every ES↔US comparison
  across that gap attributes to Spanish what belongs to the model.
  - **Cause: a decision that was right and expired.** `seed_provider_chain()` copied `fast.providers` from
    the operator's live `config/v2.json`, which in 2026-08 was the faithful thing (a sandbox with an empty
    config reported «SIN RELEVO disponible» as an engine defect and had measured its own emptiness). Since
    V2-500 the shipped ladder is the TABLE, so reading his machine became the contaminating option.
  - ⚠️ **It failed silently.** With the operator's `fast` block removed so the table would govern, the copy
    found nothing, returned `""` and left **whatever file was already on disk** in charge — a file from the
    night before. An early `return ""` was the whole symptom.
  - Fixed by seeding from the table (fast AND worker), writing `config/v2.json` **whole** so a stale block
    cannot outlive a boot, and pinning `FAST_*`/`CODE_AGENT_*` in the lab env from the same table.
  - **Two of its guards had been passing for the wrong reason**: they handed the seeder a fake operator
    engine and asserted the worker travelled — but the table names the same brain, so they would have gone
    green whatever the fake said. The missing half is now there: *a config naming a different brain must
    change nothing.*

- **The memory's semantic space comes from a CLOUD provider, and a paid call is metered (V2-501,
  2026-08-30)**: operator's rule — *«in the cloud we are going to use commercial models… and in local use one
  of those right now»*. The embeddings titular was **Ollama**, a LOCAL server: inside a container it does not
  exist, so every cloud Machine fell through to `fastembed`, whose default model is **English only**, in a
  product used in Spanish. That does not raise — it answers differently, so local and cloud had been searching
  in DIFFERENT SPACES for months behind one `logger.warning`.
  - **Chosen by measurement** (12 facts ES+EN, 12 queries sharing no words with their fact, recall@1):
    `text-embedding-3-small` **12/12** (+0.204) · `mistral-embed` 10/12 (+0.050) · `fastembed` bge-small
    **7/12** (+0.021). DeepSeek has **no** embeddings endpoint (404) and AIMLAPI's returns 403, so the
    "DeepSeek direct is titular" rule does not apply here: the service does not exist.
  - **768 dims are REQUESTED** (`dimensions`, matryoshka) — it measures the same as 1536 and fits the
    `EMBED_DIM` every database already has, so adopting the provider forces a schema migration on nobody.
  - **An outage never changes the space.** The provider returns `None` → `last_degraded` → the writer defers
    the vector and REM repairs it, exactly as for a saturated Ollama (V2-103). And `reembed()` now **stops
    without stamping** if the backend is degraded: before, it finished "fine" and sealed the cloud signature
    over a half-hashed index — the database lying about its own space, which is what the seal exists to prevent.
  - **A new paid provider needs a rate row and a meter.** The coverage gate caught it the same hour: without a
    row it billed at the punitive catch-all, ~100x the real price for the cheapest model on the list. The call
    goes through `meter_openai_response` (deferred import, same written-down trade as `memory/rerank.py`).
  - ⚠️ **A value in the environment beats a default**, so the table alone was not enough. Found underneath it:
    `MEM_PROCESSOR_MODEL=qwen2.5:3b` in the credential store — the **HEART was running an Ollama model** while
    three documents said DeepSeek — plus `GLM_MODEL`, `LLM_MODEL`, `EVAL_MODEL` and `TTS_PROVIDER=deepgram`
    (that is the STT) in `.env`. A model name in an env file is not configuration, it is a second table.
  - **The suite must never buy embeddings.** Three autodetection tests started measuring the network of
    whoever ran them (green with a key on the laptop, red in CI). The root `conftest.py` makes the cloud
    backend behave as unavailable unless a test opts in.

- **El reparto de modelos vive en UNA tabla pública, y un solo failover por servicio (V2-500, 2026-08-30)**:
  norma del operador — *«la configuración debe estar en un archivo por defecto, público y en el repositorio…
  quiero que ese archivo sea único y no quiero que estos datos estén en mil sitios a la vez»* y *«solo quiero
  un failover por servicio, no complicaciones de tres failovers en línea»*. La tabla es
  **`config/models.default.json`**; `config/models.py` la lee; los cuatro consumidores de Python leen de ahí.
  - **Estaba en SEIS sitios** y nada los comparaba, así que la norma acababa solo en el `config/v2.json` del
    operador —gitignorado, no viaja— y cada instalación nueva y cada máquina de nube arrancaban con otro
    reparto. Medido: la nube tenía **AIMLAPI de titular de voz**, la memoria iba por el broker en los dos
    lados, la cadena por defecto tenía **cinco escalones encabezados por Z.AI**, el triaje apuntaba a xAI
    **sin créditos** y los embeddings a **Ollama**, que en un contenedor no existe.
  - **Un solo failover** tiene dos motivos: una cadena de cinco no se puede razonar ni depurar, y **nunca
    llega a estar seca**, así que el turno no podía decir «no queda nadie, esto se arregla recargando».
  - **Fuera xAI y Groq**, medido el mismo día: `403 used all available credits` y `404 model_not_found`
    (`llama-3.3-70b-versatile` está retirado). Los dos últimos escalones por defecto llevaban muertos sin que
    nadie lo supiera. Su motivo queda escrito en la sección `retired` de la tabla, que es lo que impide que
    el siguiente los añada creyendo que faltan.
  - **Embeddings a `fastembed`** (en proceso, sin servidor): todo lo de la tabla tiene que poder correr en la
    nube. ⚠️ cambiar ese valor cambia el ESPACIO vectorial; una instalación existente conserva el suyo.
  - Las dos superficies de nube (`fly.accounts.toml` y `cloud/provisioner/.../machineConfig.js`) no son
    Python, así que son COPIAS y las vigila el nodo 7.26. **Abierto**: `DEEPSEEK_API_KEY` no existía en
    `cloud/` — hay que crear el secreto de Fly antes del próximo despliegue.

- **Z.AI es del BRAIN WORKER y de nadie más (V2-496, 2026-08-30 — deroga V2-462)**: norma del operador,
  literal — *«el proveedor de Z.AI solo sirve para el Brain Worker, para utilizarse dentro de Claude Code; no
  sirve como failover de nada más y no se debe utilizar en ningún otro apartado del agente»*. V2-462 había
  puesto sus DOS carteras en la cadena de VOZ (plan por `api/anthropic`, créditos por `paas/v4`) y funcionaba
  demasiado bien: la voz relevaba sola a los créditos, y así bajó el saldo de una cartera no autorizada para
  eso. **El operador lo vio en el panel de Z.AI antes que nosotros en el código.**
  - Fuera de `provider_chain._known_chain()` (que sirve a la voz, al compositor del brief y al cerebro de
    cluster), fuera el proveedor `glm` del motor de voz —que además era un RAZONADOR ofrecido como cerebro de
    voz, violando ya la regla dura— y fuera sus tres ajustes de `voice/engine/core/config.py`: un ajuste sin
    proveedor que lo lea es una invitación a volver a enchufarlo.
  - **El único sitio donde vive es `nucleo/workers/providers.py::KNOWN`**, con su endpoint Anthropic y su
    `vision: False` medido.
  - Medido en vivo: el plan agotado da `1310 … reset 2026-09-01` y **NO cae a créditos solo**; los créditos
    contestan 200 por `paas/v4`, que es **OpenAI-compatible**. Y el worker lo conduce el CLI de Claude Code,
    que habla **Anthropic** — por eso el escalón de créditos del worker queda **declarado y sin construir**:
    mudarlo de un renglón daría un 404 con pinta de caída justo en el escalón de socorro.
  - Guardas de propiedad NEGATIVA (nodo 2.6), que es la que se rompe sola: no está en la cadena, ni en los
    relevos de latencia, ni como proveedor de voz, ni como ajuste — y el worker SÍ lo conserva. Desarme
    verificado.

- **El compositor del brief pedía «no razones» a un modelo que NO PUEDE dejar de hacerlo, y toda búsqueda
  dirigida degradaba a búsqueda ciega en silencio (V2-488, 2026-08-29)**: medido en el plató US, idéntico en
  las dos rondas del hotel — `400 {'code': '1210', 'message': 'This model always engages in thinking and
  cannot be disabled; please use low, high, or max'}` → «el worker sale SIN brief (búsqueda sin dirigir)». **Y
  no relevaba**: un 400 de parámetro no es una caída de proveedor, así que `classify_failure` no da tier de
  relevo y la excepción llega al fail-open — ninguna de las dos redes que el módulo ya tenía lo tapaba. La
  culpa era NUESTRA: el proveedor sirve, y hasta decía qué valores admite.
  - `no_thinking` **no se quita**: está medido (2026-08-27) que con razonamiento el bloque se carga contra
    `max_tokens` y 1.600 vuelve truncado e ilegible; apagarlo da el mismo brief en 22,3 s y 681 tokens. Lo que
    faltaba era el otro caso. Sobre ese rechazo concreto se reintenta **con** razonamiento y **3.200** de
    presupuesto — el número sale de la medición (2.517 tokens de salida con thinking), no de una estimación.
  - **Una sola puerta** (`_pedir`) para la llamada normal y la del relevo: la corrección valía para las dos, y
    una regla escrita dos veces es como la segunda copia se queda atrás sin que nada falle.
  - El predicado exige la **conjunción** (hablar de razonamiento Y de que no se puede desactivar; el código
    `1210` vale solo) para no tragarse un 429 de cuota agotada — si lo hiciera, el relevo de V2-225 dejaría de
    dispararse. Y **el tier no se pone en cuarentena**: apartar a un proveedor que sirve, por un parámetro
    nuestro, deja además sin él al cerebro de cluster.
  - Tercera cara de **la capacidad se MIDE, no se lee** (razonador que se come `max_tokens`; «lee imágenes»
    que no lee; y ahora «se le puede apagar el razonamiento» a quien no). Nodo 2.6, desarme verificado.

- **La red MeshKore estaba construida, verificada en vivo y NUNCA se consultaba — dos causas apiladas y
  ninguna en la red (V2-486 y V2-487, 2026-08-29)**: el operador la pidió explícitamente para las búsquedas de
  servicios (hoteles, vuelos), y el censo decía **0 consultas en 399 informes de worker**.
  - **(1) El PASO 0 solo viajaba en el prompt del NAVEGADOR** (`dispatch_prompts._web_prompt`), y el encargo
    con el que se pide no llega ahí. Medido en el enrutador, no en la red: `classify_kind` promociona a
    `kind="web"` lo que `site_catalog.category_of` reconoce, y ese detector exige un verbo de RESERVA —
    «resérvame hotel en Nueva York» → `hotel_booking`, pero **«búscame el mejor hotel de Nueva York» → `None`**,
    o sea `generic`. Y el prompt genérico **no nombraba `mesh_cli` en ninguna línea**: el worker no descartaba
    la red, no sabía que existe. Se arregla por el PROMPT y no por el enrutador a propósito: ensanchar
    `category_of` movería a `web` encargos que hoy atiende un genérico, y el propio `errand_kind` documenta por
    qué eso es peligroso (el fraseo de una búsqueda es el de una investigación). Dar el PASO 0 al genérico no
    cambia QUIÉN atiende, solo le dice que pregunte antes de buscar. Es la MISMA asimetría de V2-118 (catálogo
    de sitios) y V2-211 (reglas del cajón), y por eso el bloque queda en **una sola función**
    (`_mesh_first_block`) con dos encabezados: tenerlo escrito dos veces es como la segunda copia se queda
    atrás sin que nada falle.
  - **(2) Un 400 que dice QUÉ campo falta SÍ es una respuesta.** `ask` lo aplastaba a «respondió 400» y `serve`
    lo volvía a aplastar a **«los agentes de la red no contestaron»** — una diagnosis falsa y cara: manda a
    abrir un Chromium contra Booking teniendo la respuesta a un campo de distancia. Medido en vivo contra
    `roomrover`: texto libre → `400 parse_failed` con el detalle «pass structured fields»; con `city/checkin/
    checkout/adults` → `400 missing_fields need:[country_code]`; con él → **200 con diez hoteles reales de
    Nueva York, precio, nota y enlace de reserva, en 0,4 s y sin navegador**. La forma la avisaba el propio
    docstring del módulo desde el primer día; estaba sabida y se tiraba igual.
  - **O texto libre O campos, nunca los dos** — y esto NO es deducible: con `prompt` dentro, el agente toma su
    camino de lenguaje natural y **descarta los campos**; el mismo cuerpo que devuelve diez hoteles sin él
    devuelve `parse_failed` con él. Escribí «lo explícito gana al texto libre» como suposición sobre el
    precedence del agente y la medición la tumbó.
  - **Sigue sin haber esquema de nada de nuestro lado**: el agente declara lo que necesita (`agent_asks`), el
    worker —que tiene el encargo y el razonamiento— compone los campos, y viajan tal cual por `--field
    clave=valor`. Ni una tabla de hoteles ni de vuelos, que es el invariante del módulo desde V2-167.
  - Nodo 2.6, desarme verificado en los dos arreglos. **La red respondiendo está verificada en vivo por
    nuestro propio puente**; que un worker lo haga solo, no — eso lo mide el plató.

- **Una frase deja DOS píldoras críticas, y el corte expulsaba un hecho de SEGURIDAD (V2-491, 2026-08-29)**:
  `critical_facts` corta a 6 por importancia·peso y deduplicaba por cadena EXACTA. Una sola frase del operador
  deja dos píldoras críticas —la destilada por el CORAZÓN (`path='llm'`) y la literal que guarda la red de
  salud (`path='health-net'`, `ingest.py`)— y al ser textos distintos no colapsaban: **cada hecho ocupaba dos
  de las seis plazas**. Medido sembrando cuatro hechos críticos distintos por su camino real (celiaquía,
  frutos secos, diabetes, marcapasos): **el marcapasos DESAPARECE** de la línea más prominente del prompt,
  expulsado por las copias de los otros tres. Es el fallo que esa línea existe para evitar —«olvidar una
  alergia bajo densidad es un fallo de seguridad», dice su propio comentario— cometido por su propio cap. Y
  con V2-490 repitiendo la línea al final, el mismo hecho llegaba a salir **cuatro veces** en 718 caracteres.
  - **El enlace es EXACTO, no un parecido, y eso es lo único que lo hace seguro**: la píldora destilada guarda
    en `meta.raw` la frase del operador y el texto de la de la red ES esa frase. Se retira la copia cuando otra
    píldora crítica **declara haber nacido de ella**. Por prefijo, porque `raw` viaja recortado a 120.
  - ⚠️ **Deduplicar por PARECIDO se probó y se descartó CON NÚMEROS**, porque aquí un falso positivo BORRA una
    restricción médica: el par que SÍ debe fundirse (destilada vs literal de la celiaquía) puntúa jaccard
    **0,30** / cobertura 0,50, y los que JAMÁS deben fundirse —«frutos secos» vs «marisco», penicilina vs
    ibuprofeno— puntúan **0,25-0,33** / 0,50. **Ningún umbral los separa**, así que no hay umbral bueno: solo
    la procedencia. Es la lección de V2-123 (el dedup engañado por la puntuación) en un sitio donde el falso
    positivo no cuesta trabajo repetido sino una alergia perdida.
  - ⚠️ **Y un margen que me inventé**: subí el fetch del SQL de `*2` a `*3` «para que quepan las copias», y el
    desarme enseñó que **ningún caso lo exige** — las destiladas pesan 0,95 y las copias 0,7, así que las que
    sobreviven al ranking son justo las que se conservan. Revertido: una constante que nadie puede volver a
    justificar es deuda, no margen. **Un desarme que no muerde también acusa al arreglo, no solo al test.**
  - Nodo 1.6, desarme en los dos sentidos (3 rojos sin el dedup, 1 sin la guarda que protege a la píldora que
    declara su origen) y la dirección contraria con caso propio: tres alergias distintas siguen conviviendo.
    **Sin verificar en vivo.**

- **DOS puertas por las que entra un vector de otro espacio, y ninguna fallaba con ruido (V2-484 y V2-485,
  2026-08-29)**: V2-482 quitó el daño permanente y dejó escrito que la puerta no estaba medida. Lo está, y
  **son dos, con causas distintas**. Las dos se reprodujeron de punta a punta antes de tocar nada.
  - **(1) El permiso caducaba con el RELOJ, no con el BACKEND** (`memory/reembed.py::space_ok`). El veredicto
    se cachea 60 s porque lo consultan cada insert y cada recall, y se cacheaba **solo por tiempo** — pero es
    un veredicto sobre el espacio ACTIVO, así que durante hasta 60 s tras un cambio de backend devolvía la
    respuesta de la pregunta anterior. Un backend que cae a `hash` dentro de esa ventana escribe con el
    permiso de cuando Ollama estaba vivo, y **`last_degraded` es False A PROPÓSITO para un hash configurado**
    («es su propio espacio consistente — lo gobierna la firma embedsig»): los dos guardas se remiten el uno al
    otro y no queda ninguno. La fila sale con vector, sin marcador y sin error. **El backend pasa a ser parte
    de la clave**, leído CRUDO del módulo y no por `active_backend()` — ese accessor resuelve, y resolver
    puede sondear: un guarda que corre en cada insert y cada recall no puede meterles una llamada de red por
    delante.
  - **Y la comprobación que DECIDE se hace DESPUÉS de tener el vector**: la primera se hace sin saber en qué
    espacio va a salir, y la resolución del backend ocurre DENTRO de `_emb.embed()`. La primera se queda —
    evita pagar un embedding que se va a tirar—, pero la que manda es la segunda. ⚠️ **Reproducirlo exige
    insertar CON SLOT**: sin slot, `insert_memory` consulta antes `_semantic_dedup_on()`, que resuelve el
    backend por su cuenta, así que el vuelco ocurre ANTES del primer guarda y ése ya lo caza. Un caso sin slot
    salía **verde con el arreglo desarmado**.
  - **(2) El nodo-concepto escribía su vector SIN NINGÚN guarda** (`writer._get_or_create_concept`). Aquí no
    hay carrera ni permiso rancio: nunca hubo comprobación, ni de firma ni de degradación, y encima dentro de
    un `except Exception` que devuelve None. **Medido por la FORMA de cada vector no denso del índice del
    operador: 9 filas con exactamente 384 no-ceros y 384 ceros al final** — fastembed rellenado a 768 dentro
    de un índice sellado `ollama:embeddinggemma:768`, y **todas** nodos-concepto («familia», «guitar»,
    «trabajo», «preferencias»…). Con esas 9 el daño sube de 15 filas a **~25**. El nodo se sigue creando
    siempre (es un hub del grafo; sin él `_link_concepts` no cose nada): lo que se difiere es su vector.
  - **El reparador alcanza ya las dos clases.** La huella de hash solo vale para hash; un vector de otro
    modelo REAL no se reproduce desde su texto, pero **su forma lo dice**: `_fit_dim` rellena con ceros, así
    que una cola de ceros de media longitud significa que quien lo produjo tenía como mucho la mitad de esas
    dimensiones. Acotado por la otra punta y es lo que impide que el arreglo se coma una base sana: **en un
    índice sellado con fastembed, un vector rellenado ES el nativo**. La frontera es gruesa a propósito
    (`dim // 2`): un modelo de 512 rellenado a 768 deja 256 ceros y NO se caza — ensancharla empezaría a
    adivinar sobre vectores meramente dispersos, y un falso positivo aquí tira un vector bueno.
  - ⚠️ **Y un verde prestado de los míos, en el sitio de siempre**: los casos usaban `monkeypatch.undo()` para
    enfriar el caché, y ese deshace TODO lo que la función lleva puesto — incluido el `ZAELAR_DB` del fixture.
    Con él revertido, el guarda pasaba a leer el `.embedsig` de la memoria **REAL del operador**, así que
    pasaban en solitario por una firma ajena y fallaban en la suite entera. La regla ya escrita
    (`ZAELAR_HOME` no basta, hay que apuntar la BD del plató) tiene una forma más: **una utilidad de test que
    deshaga parches indiscriminadamente devuelve al proceso a la base real**.
  - Nodos 1.2 y 1.5, desarme en los dos sentidos en cada mitad. **Sin verificar en vivo**, y no puede estarlo
    todavía: el reparador corre dentro del proceso, en la pasada del sueño, así que la base del operador no
    cambia hasta que reinicie sobre HEAD.

- **La voz de V2-497 estaba colgada DESPUÉS de la puerta que más se cierra (V2-503, 2026-08-30)**: al medirlo
  a la mañana siguiente, con la GPU libre y Ollama contestando normal, `repair_embeddings` seguía devolviendo
  **0 con 45 filas esperando — y en 0,0 s**, que es el delator: la pasada no llegó a mirar ni una fila.
  `repair_embeddings` tiene **DOS salidas** y V2-497 solo le dio voz a una. El guarda de entrada
  (`vec_available` / `_embed_sig_ok`) devuelve antes de leer nada, así que `_report_repair_backlog` —colgado
  tras el bucle— es **inalcanzable justo en el fallo más probable**: un backend que se va no degrada fila a
  fila, deja de resolver, la firma deja de casar y la pasada se rechaza en la puerta en todos los sueños
  siguientes. El guarda es CORRECTO y se queda (reparar con otro espacio activo mete vectores ajenos, que es
  lo que V2-482/V2-484 existen para impedir): lo que estaba mal es que **negarse fuera indistinguible de no
  tener trabajo**. Ahora cada puerta dice CUÁL fue, porque piden acciones distintas —firma descuadrada se
  arregla apuntando al proveedor que selló el índice; sqlite-vec ausente es un problema de instalación— y el
  aviso va también a `health_state`, que aflora solo. **Callado si no espera nada** (instalación nueva con
  firma que nunca casó no tiene atraso ni problema) y **nunca LIMPIA** la clave `memory`, compartida (V2-311).
  Rectifica de paso una afirmación mía del día anterior: dije que el túnel de Ollama saturado era LA causa de
  que los ~25 vectores dañados no sanaran, y con la GPU libre seguían sin sanar — era UNA causa. Desarme: al
  restaurar el `return 0` mudo, **3 rojos**; los otros 10 del fichero siguen verdes porque cubren el camino
  del bucle, y dos de los nuevos afirman SILENCIO (guardas contra avisar de más, no prueban el defecto).
  Nodo 1.5. **Sin verificar en vivo**: que el re-embebido CURE de verdad sigue sin probarse de punta a punta.
- **Un reparador INERTE parecía un reparador SIN TRABAJO (V2-497, 2026-08-29)**: encargo del operador —
  disparar REM a mano y probar que la teoría de V2-482 se sostiene. Sobre una COPIA de su base el purgado
  **disparó y funcionó** (25 vectores ajenos retirados, 16 hash + 9 rellenado, y los 9 rellenados TODOS
  nodos-concepto, justo lo que V2-485 predijo) y acto seguido **`repair_embeddings` devolvió 0** con 45 filas
  esperando. Instrumentado: `embed()` devolvía 768 dims con `last_degraded=True` — o sea el hash de emergencia,
  porque `/api/embed` contestaba `server busy, maximum pending requests exceeded`. Es la condición
  `_ollama_busy` que el módulo ya documenta y resuelve BIEN (difiere el vector en vez de degradar el espacio);
  lo que no estaba resuelto es que difiere **en silencio, una vez al día**.
  - **El defecto es un confundido, no el backend**: `0` significaba a la vez «no había nada que reparar» (sano)
    y «45 esperando y el backend rechazó todas» (roto). El salto por fila era un `continue` pelado, y
    `hygiene()` informa de `embed_pending` pero **solo su porcentaje heurístico llega a alertar**. Y el purgado,
    que sí avisa al retirar, dejaba la mitad ruidosa junto a la mitad muda: se lee como *funcionó, todo bien*.
    **La respuesta equivocada era la tranquilizadora**, otra vez (V2-311, V2-482).
  - **Descartado con NÚMEROS el arreglo tentador**: reintentar. Sondeado 40 veces en 30 s con un modelo de 40 GB
    en la GPU: **40 rechazos, 0 aciertos** — mientras un modelo grande la ocupa, la negativa es TOTAL, no
    intermitente. Así que la pasada **se rinde tras 3 caídas seguidas** (45 llamadas inútiles → 3; 4 s → 0,4 s)
    y no es 1 porque el resolutor deja a un saturado re-sondeando en la llamada siguiente: hay un caso que exige
    que un bache suelto NO cueste la pasada entera.
  - **Se retira una afirmación mía que era falsa**: el docstring del purgado prometía «la pasada que sigue lo
    re-embebe en el espacio correcto» y el aviso decía «se re-embeben en esta misma pasada». Esa mitad es
    CONDICIONAL — corregido donde lo dije. El purgado se queda incondicional (su argumento se sostiene solo),
    pero deja de prometer la otra mitad.
  - **Quién ocupaba la GPU, y el operador debería saberlo**: un consumidor REMOTO por
    `cloudflared tunnel run meshkore-ollama`. **Mientras ese túnel sirva un modelo grande, la memoria no puede
    reparar ni deduplicar nada.** Nodo 1.5, cuatro desarmes. **Esto hace VISIBLE que la reparación no corre; no
    la hace correr** — los ~25 vectores del operador sanarán en el primer sueño con la GPU libre.

- **Los GUSTOS son estado ACTIVO, y el slot obvio está medido como MUERTO (V2-498, 2026-08-29)**: norma del
  operador — *«los gustos no son datos históricos ni cosas que hayan sucedido en el pasado, sino que tienen que
  estar ahí»*. Medido antes de tocar nada: el bloque pasivo real de su memoria tenía **dos líneas** —una regla
  de trabajo y un `[RESET]` del sistema— y **ni un gusto**, con 12 píldoras `kind='pref'` guardadas (Ferrari ×7,
  guitarra ×2). No se pierden al escribirse: **pierden el RANKING** (0,3-0,494 contra un corte dominado por
  píldoras de 0,99).
  - ⚠️ **`operator.tastes` era la vía natural y no habría escrito nunca nada.** Dos hechos: el prompt del
    CORAZÓN enseña EXPLÍCITAMENTE que un gusto es ADITIVO y va con `slot=null` (un slot invalida lo anterior, y a
    alguien le pueden gustar los Ferrari Y la guitarra), y **`operator.family` lleva desde el 2026-08-17 en el
    catálogo con CERO escrituras** — de 448 durables vivas, 437 sin slot y solo `operator.name`/`operator.location`
    en uso. La regla aditiva del destilador gana a la entrada del catálogo.
  - El arreglo es la forma de `critical_facts` (V2-491): **lo que tiene que estar SIEMPRE no compite por una
    plaza**. La clase ya está en el dato (`kind='pref'`) y se tiraba — se renderiza la distinción que existe, sin
    slot, sin campo y sin lista de palabras (principio de V2-337). `pref` sale de `salient_long` para no pintarse
    dos veces. Se llama **GUSTOS Y PREFERENCIAS** porque eso es lo que la clase contiene: junto a Ferrari vive
    «prefiere que las tareas las haga un worker», y llamarlo «gustos» convertiría esa fila en una afición.
  - **Los costes, enteros**: 4 de 6 plazas son ecos del mismo gusto —fundirlos es de `semantic_dedup`, hoy
    bloqueado (V2-497), y **un dedup léxico tampoco serviría**, medido: sus siete ecos están en DOS idiomas y no
    comparten palabras de contenido—; y la guitarra (peso 0,05) no entra, **pero no por la política de
    decaimiento actual** (λ=0,001/día ⇒ vida media 693 días): son víctimas del bug de sobre-decaimiento arreglado
    el 2026-07-19, así que no se toca el decaimiento por un daño histórico ya cerrado. Nodo 1.1, cuatro desarmes.

- **Una limitación de INGESTIÓN dicha sin palabra de categoría también es crítica (V2-499, 2026-08-29,
  autorizado por el operador aceptando los falsos positivos)**: `_CRITICAL_HEALTH_RE` casa la CATEGORÍA
  («alérgico», «celíaco», «intolerante»), que es como se dice la mitad de las veces; la otra mitad dice lo que
  NO PUEDE HACER — «no puede comer gluten». Esa frase no lleva ninguna palabra del catálogo, así que no se
  marcaba `critical`, no llegaba a la línea ⚠️ CRÍTICO y competía por una plaza del ranking: **exactamente el
  fallo que V2-490 midió** con macarrones ofrecidos a un celíaco. Va en `_is_critical_health`, el guard del
  writer, único chokepoint de TODA escritura.
  - **El coste no es inocuo y por eso lleva UNA acotación**: la línea crítica tiene cap (6), así que una frase
    social colada puede EXPULSAR un marcapasos — el daño que V2-491 acababa de cerrar. Se acota por la única vía
    que no exige adivinar: **una restricción que NOMBRA UN MOMENTO habla de ese momento, no de la persona**
    («hoy no puedo comer contigo»). Lo ambiguo sin marca temporal («no puedo comer más») **NO se filtra**: ante
    la duda esta línea existe para pecar de más — un plato que no se ofrece cuesta una pregunta, una alergia
    olvidada cuesta otra cosa. Ese falso positivo queda MEDIDO y con nombre en un test, para que quien estreche
    el detector vea qué está cambiando. Nodo 1.6, tres desarmes en tres direcciones.

- **Un vector de espacio AJENO no lo repara nadie, nunca (V2-482, 2026-08-29)**: `repair_embeddings` solo
  busca filas SIN vector, que es lo que deja el guarda de firma del writer al refusar. Una fila cuyo vector
  ajeno se coló por un fail-open TIENE vector, así que la pasada de reparación **no la selecciona jamás**: las
  que el guarda cazó sanan cada noche y estas no, y son la mitad peor —ruido fundido en el RRF de cada recall
  semántico e invisible en todo recuento de `embed_pending`—. **Medido sobre la memoria VIVA del operador: 15
  filas durables con un `_hash_embed` LITERAL** (coseno 1.0000 contra recomputarlo de su propio texto) dentro de
  un índice sellado `ollama:embeddinggemma:768`, y son las píldoras de GUSTOS — las ocho de Ferrari entre ellas.
  - **La consecuencia, medida sobre esas mismas filas**: `semantic_dedup` no puede fundirlas NUNCA, porque su
    umbral está calibrado sobre embeddinggemma (0,82-0,90 entre ecos de un hecho) y las colisiones hash entre
    esas ocho frases topan en **0,788**. Ocho copias vivas de un gusto, cada una decayendo sola (las de guitarra
    a peso 0,049), ninguna con peso para llegar al bloque pasivo. **El umbral no es lo que está mal: lo están
    los vectores** — por eso no se toca.
  - **Solo el espacio HASH es detectable así, y es el punto**: hash es el destino de la degradación de
    emergencia, o sea el espacio que se filtra. Un vector de otro modelo REAL no se reproduce desde el texto, y
    mantenerlo fuera es trabajo del guarda de firma. No hace nada cuando hash ES el espacio sellado (dev, tests,
    BD nueva) ni cuando no hay firma: **sin espacio declarado no hay nada respecto a lo que ser ajeno**.
  - **Borrar el vector es TODA la reparación**: la pasada que sigue selecciona la fila justo porque ya no tiene,
    y la re-embebe en el espacio bueno. Marcarla `embed_pending` además es lo que hace CONTABLE en `hygiene()`
    un fallo al conseguirlo, en vez de silencioso.
  - ⚠️ **La fusión CONSERVA, no ACUMULA — y esto NO cierra el frente de los favoritos.** Dije al cluster que
    con los vectores sanos las ocho colapsan «en una con el peso de las ocho», y se subió a INI-026 como el
    hecho que decidía. **Es falso**: `semantic_dedup` conserva la MEJOR e invalida el resto, y llama
    `reinforce([keep], step=0.0)` — el `step=0.0` es explícito, sube `access_count` y resetea el decay, **el
    peso no lo toca**. Simulado sobre copia de la base real con la regla de desempate del propio código:
    Ferrari 8→1 sobrevive con **0,297**, guitarra 2→1 con **0,03**, corte del top-5 **0,446**, y el top-5 sale
    **byte por byte idéntico**. Así que arreglar los vectores quita el ruido del RRF y siete duplicados, y
    **no cambia quién llega al bloque pasivo**. Deduje que fundir acumula evidencia sin leer la rama de fusión,
    y lo dije con la misma seguridad que los tres hechos que sí había medido.
  - **Abierto, y es lo que de verdad falta**: el guarda de escritura EXISTE y hoy FUNCIONA —reproducido: refusa
    y marca `sig_mismatch`—, así que esos 15 entraron por un **fail-open**, no por falta de guarda. Cuál de los
    dos (`_embed_sig_ok` cuando el import revienta, o `space_ok` cuando no encuentra el `.embedsig`) **no está
    medido y no se afirma**. Esto quita el daño permanente, no la puerta por la que entró.
  - **Y contesta al encargo de FAVORITOS ESTRUCTURADOS (INI-026/B3) que lo destapó**: un slot de gustos es la
    forma equivocada, medido — un slot es SINGULAR por construcción (tres gustos con `slot=operator.tastes` →
    **1 vivo, 2 `valid=0`**) y además `semantic_dedup` solo corre sobre `slot IS NULL`, así que ponerles slot los
    saca del único fusor que tienen. La forma para esta misma clase ya la fijó el operador en `memory/slots.py:77`
    con `operator.family`: «un resumen en TEXTO que se restablece por reformulación (`garble_guard=False`), **no
    una lista estructurada nueva**». Matiz que corrige la trampa del encargo: un slot con `:` no queda fuera del
    recall sin más — `background_slot_off_topic` lo tira SALVO que el prompt nombre la palabra, o sea que solo
    recuerda su gusto si él ya lo ha dicho, que es lo contrario de lo que se quiere. Nodo 1.2, desarme en los dos
    sentidos (sin la llamada 1 rojo, sin acotar el espacio 2). **Sin verificar en vivo.**

- **La TERCERA puerta al scheduler no normalizaba (V2-480, 2026-08-29)**: `safe_reminder_prompt` dice en su
  docstring que existe «para que las DOS puertas al scheduler digan lo mismo» — y la acción `schedule` del
  worker es la TERCERA, nació después (V2-249) y nunca la llamó. Medido en la primera ronda de
  `find-a-future-release-and-remind-me`: el trabajo quedó programado con la frase CRUDA del operador dentro, así
  que el día que suene el agente le leerá sus propias palabras — y las leerá como una petición que APUNTAR, que
  es el bucle que toda esta zona existe para cerrar. **No se ensancha ninguna regex**: la forma de PETICIÓN
  («¿te enteras y me avisas?») sigue sin cubrirse, y perseguir formas es la cinta de correr de V2-151.

- **La puerta del backstop de entrega tampoco era la LONGITUD (V2-478, 2026-08-29)**: había un tope de 300
  caracteres con esta premisa escrita — «una respuesta larga ya está contando algo, y pisarla sería peor».
  Medido en `find-best-hotel-city__us` ronda 5, la premisa es falsa: el turno era largo —«I've got a partial
  shortlist up on screen, six central candidates for that weekend»— y **no nombró ni un hotel ni un precio**.
  Contaba una NARRACIÓN, no un hecho, así que el operador se quedó con menos que tras un «te aviso» y encima
  convencido de que ya tenía algo. **Tercera corrección de la misma puerta mirando la propiedad equivocada**:
  el vocabulario de espera (V2-364), la pregunta (V2-371) y ahora el tamaño. La propiedad que importa —si el
  turno NOMBRA lo que la hoja tiene— ya se calculaba fila a fila (`fresh`), así que no había que inventarla:
  bastaba con dejar de taparla. La protección real sigue en pie y ahora se COMPRUEBA en vez de suponerse: un
  turno que ya nombró sus filas produce `fresh` vacío y no recibe nada, mida lo que mida. El test que afirmaba
  la premisa vieja se reescribió en las dos direcciones. 2222 verdes.

- **Una garantía escrita en un solo idioma es un defecto para todos los demás (V2-475, 2026-08-29)**: la
  familia de garantías de entrega (`nucleo/flash/delivery.py`) —la que existe porque «cuando la conducta
  correcta es determinista la garantiza el código, no la temperatura»— estaba escrita ENTERA contra formas del
  castellano, puertas y frases. Falla en las dos direcciones a la vez y ninguna parece un fallo desde fuera:
  `stalled_task_backstop` **nunca disparaba en inglés** (su puerta `_WAITING_REPLY_RE` no tenía ni una forma
  inglesa, así que «let me nudge the search» sobre una tarea tres minutos encallada pasaba de largo), y
  `sheet_delivery_backstop` **sí disparaba, pegando un párrafo en español** a una respuesta inglesa — la
  garantía convertida en el defecto que existe para evitar. Medido en `find-best-hotel-city__us` (2026-08-28,
  2/5 con mecanismo 3: la búsqueda encontró cuatro hoteles con precio y la entrega dio dos, con dos precios
  dichos mal y el atasco narrado como normalidad). Se añaden las puertas inglesas y las dos frases en inglés,
  con `_speaks_en()` guardado y falso por defecto: esta familia no puede perder una entrega por un import. **La
  trampa que dejó al descubierto** es la que hay que recordar: los tres tests que afirmaban la forma castellana
  no declaraban idioma, lo heredaban — y el ambiente de un proceso de test limpio es **inglés**
  (`langs._default_code()`), así que afirmaban «lo que salga por defecto» y acertaban por accidente. Una frase
  que el sistema le dice al operador se prueba con el idioma DECLARADO, nunca heredado. Nodo 2.2, 980 verdes.
- **La entrega se NOMBRA y lo no verificable no se da por cumplido (V2-469, 2026-08-29)**: una noche de
  casos de catálogo (vídeos, playlist de enlaces, monitor US) con la misma raíz en cuatro caras. (1) Regla
  nueva de `nucleo/flash/prompt.py`: un criterio del operador que el modelo no puede VERIFICAR («con buenas
  reseñas», «sin IA») no se entrega nunca como cumplido — se entrega lo que hay diciendo, en la misma frase,
  con qué señales se aproximó o que no puede garantizarlo. (2) `widget_data_turn`: «Hecho.» a una PREGUNTA es
  una no-respuesta — el ack enumera lo que el widget tiene con sus pistas (`named_ack`); un fallo de op se
  dice SOBRE la respuesta hablada (`ensure_failure_named`); y los enlaces pegados viajan TODOS
  (`complete_pasted_links` — el modelo soltaba el primero). (3) `video_turn.ensure_delivery_named`: el
  resultado de una búsqueda de lista se nombra en el MISMO turno (la voz no puede hacerlo después: el
  despacho es async). (4) El mecanismo alrededor dejaba mentir a los de arriba: un anuncio de DDG no es un
  resultado (`websearch._is_ad`), el navegador de tareas habla el idioma del MOTOR
  (`navegador/owner._browser_locale` — al agente US se le servía el Amazon español y el «Select your
  Country» de Best Buy), y un payload de texto plano para `web_search` ES la query
  (`bridge_usage.bare_query_payload`, la regla de V2-341: la forma natural no cuesta el turno). En youtube:
  un hit sin título (Shorts) no es candidato, el conteo casa con los nombres que da, y la pista de «suena»
  dice la verdad (pos 0 falsy + reproductor que bloquea la inserción ofrece el enlace). Nodos 4.56, 4.58 y
  10.122-10.127; la campaña con sus mediciones vive en la iniciativa V2-469 (roadmap en disco).

- **Un caso BLOQUEADO no es una avería, ni un turno que gastar cada vuelta (V2-448, 2026-08-28)**: el runner
  se niega a conducir un escenario cuyas tareas de roadmap siguen pendientes (norma del operador del
  2026-08-21) y sale en 3 s; el supervisor lo archivaba como **INFRA**, la etiqueta de «el instrumento se
  rompió», que manda a mirar donde no hay nada roto — la misma lección que el día que una avería del ARNÉS se
  archivó como un caso que falla, un escalón más abajo. Y el defecto caro es el otro: un caso bloqueado
  **nunca llega al marcador**, así que la rama de «nunca medidos» volvía a elegirlo **en cada vuelta, para
  siempre**. Medido: `repeat-a-finished-search`, pendiente de V2-260. La
  clasificación sale a `_veredicto_de_cola` —dentro de la función que conduce la ronda haría falta un plató
  entero para probar lo que decide una cadena— con BLOQUEADO **antes** que INFRA, porque esa cola no contiene
  «PASSED» de ninguna clase y caería en el `else`. Fuera de la rotación, mismo trato que los `capped`. Nodo 10.113, tres desarmes — y **el segundo no mordía** en la primera versión: la cola que usaba caía en el
  `else`, que también es INFRA, así que pasaba con la rama borrada.

- **Un solo formateador de fila (V2-455, 2026-08-28)**: V2-451 dejó DOS —el de la pestaña y el de la hoja— y
  su propia sección «lo que no cierra» lo decía. La regla que formatean tiene **tres inquilinos y cada uno
  costó una ronda**: la AUSENCIA dicha (una fila sin importe salía como un título a secas y el modelo tenía
  que deducir del silencio que no hay precio), el TELÉFONO como dato accionable (V2-240) y la PISTA de
  búsqueda que NO es un candidato (llamarla «SIN PRECIO» la presenta como una ficha a la que le falta un dato)
  — **y la copia nueva tenía una de las tres**, o sea que la
  divergencia ya había ocurrido el mismo día. `errand_sheet.fila(item)` es ahora el único, y el desarme pone
  en rojo los DOS caminos, que es justo lo que antes no pasaba.

- **La sesión NUNCA pide la cámara — mic-only (V2-456, 2026-08-28)**: la CameraUnit está oculta desde el
  2026-08-09, pero los DOS motores de sesión conservaban el `getUserMedia({video})` best-effort del arranque
  (y otro en `toggleCam`), así que cada arranque seguía disparando el permiso de cámara del navegador — sobre
  todo en el móvil — para una preview que nadie puede ver. Orden del operador: **comentado, no borrado** (los
  cuatro bloques llevan la fecha y reactivar es descomentar). La trampa del cambio es la de siempre: la URL de
  `session.js` sirve `session-lk.js` bajo LiveKit (`server/livekit_api.py`) — arreglar solo el que probaste
  deja el vivo pidiendo permiso. Nodo 4.81 (fuente, patrón de V2-088): ningún `getUserMedia` de vídeo ACTIVO
  en `app/` ni `mobile/`, el micro sobrevive al apagado, y el barrido impide una tercera puerta con otro
  nombre; desarme verificado descomentando el bloque (2 rojos).

- **Cadena de buscadores de imágenes (V2-466, 2026-08-28)**: petición del operador tras una tarde de captchas
  de Google. **Medido antes de elegir** (misma máquina, misma consulta): google captcha · ecosia captcha
  (proxia) · ddg/brave/startpage/qwant solo pintan tras interacción · **yandex 30 tiles con el coche
  CORRECTO** · bing 52 tiles con el coche EQUIVOCADO 9 de 10. La ruta JSON de DDG (`i.js`+`vqd`) da **403**,
  descartada. Orden `("google","yandex","bing")` — **es la medición, no la reputación**, y Bing el último no
  es estética: era el primer recambio, así que cada captcha mandaba el turno al índice más flojo y el coche
  equivocado se leía como defecto del producto. `images()` prueba en cadena y el resultado dice quién
  contestó (`source`), quién falló primero (`degraded_from`), **por qué** (`blocked`=esperar ≠ `empty`=
  reformular) y a cuántos se preguntó (`tried`). Coste conocido y DICHO: los títulos de Yandex vuelven en su
  idioma (ruso) — mejor un pie ilegible sobre el coche correcto que uno limpio sobre otro coche. Añadir un
  índice = una fila más su `search_images_*`. 9 casos, parser puro sin red.

- **El reproductor publica su lista y el visor tiene teclado (V2-465, 2026-08-28)**: auditados los tres de la
  familia de medios lado a lado. `youtube` era el ÚNICO sin `ref_index()` — el cerebro no veía la lista, así
  que «pon la tercera» no tenía contra qué resolver (y nunca debe inventar un id, V2-026), y con la tarjeta
  ABIERTA Y VACÍA el brief no podía decirlo: el «doy por entregado lo que no está» de V2-380/383. Marca
  cuál suena. `imagenes` era el único sin teclado (← →, en la TARJETA y sin robárselas a quien escribe).
  **Descartado a propósito**: darle `active_when` a `imagenes` — ese contrato significa PRODUCIENDO y engancha
  el ⏻ global; una foto quieta no se suspende.

- **La ronda deja un VÍDEO — modo escaparate + grabador (V2-464, 2026-08-28)**: petición del operador —
  grabar la pantalla mientras el caso corre en background, con el chat abierto y los widgets alineados como
  el snap del sistema, y enlazar el .webm sin sonido desde el informe (material de showcase). Piezas:
  `Desktop.arrange()` (rejilla, esquiva chat acoplado y franja del orbe), `POST /api/canvas/arrange` (el snap
  por API, mismo rail SSE que show/close), modo `?showcase=1` (chat acoplado izquierda + auto-arrange con
  debounce en cada apertura — SOLO en showcase, al operador normal un auto-orden le movería lo suyo) y
  `recorder.py` + `run.py --record` (Chromium espectador 1920×1080, `record_video_dir` de Playwright). **La
  parada del espectador es por STDIN, nunca por señal**: el .webm solo se materializa al cerrar el contexto,
  y matarlo pierde el fichero de una ronda que ya se pagó. Verificado en vivo: primer .webm real de 21 MB con
  la ronda entera. Nodo 10.119.

- **La tarjeta se abre donde aterrizan los datos (V2-463, 2026-08-28)**: 12 fotos en el almacén del visor y
  el operador mirando un canvas donde la tarjeta nunca se abrió. La voz emitía el `show` al llegar la tool;
  el canal probe —el que conduce TODAS las rondas del plató— no lo emitía nadie, y **youtube y musica tenían
  el mismo agujero**. Sexta vez de la misma forma («cablear en ambos»), así que esta vez la decisión va al
  rail COMPARTIDO: `*_turn.execute` emite el show, solo si algo CARGÓ, y un `stop` de música no reabre. Dos
  piezas más: **evidencia por búsqueda** (`image_turn._evidence` — la ronda de los diccionarios fue
  indiagnosticable porque el show siguiente pisó el almacén y la query basura desapareció; ahora cada
  búsqueda emite query/fuente/nº/blocked/degraded, incluida la vacía) y el juez recibe «⚠️ ESCRITOS PERO
  NUNCA ABIERTOS» cuando un widget tiene escrituras y cero shows en la ronda (V2-346: un hecho que no se
  enuncia es invisible). 7 casos en los nodos de los tres rails; desarme verificado. **Adenda medida la misma
  tarde**: con todo eso puesto, la ronda entregó 12 fotos reales de ferrari.com en el primer turno y el juez
  la puntuó 2/5 como «alucinación visual» — el lector de evidencia solo contaba workers/navegador. Una
  búsqueda de imágenes ES el mundo exterior: `verify.image_searches` + la auditoría la acepta como evidencia
  (solo CON fotos) + el juez la recibe enunciada, también la fallida y la degradación a Bing. Nodo 10.118.

- **Z.AI: el plan primero, los créditos después (V2-462, 2026-08-28)**: el plan de código amaneció agotado
  (`1310`, reset el 1 de sept) y el juez del plató perdió una ronda (GLM 429 → DeepSeek 402 → AIMLAPI 504×2).
  El operador recargó DeepSeek, puso $20 de créditos en Z.AI y dictó la política: forfait primero, créditos
  al agotarse, **progresivo**. Lo medido que hay que saber: el endpoint del plan **NO cae a créditos solo**
  (1310 con saldo al lado); los créditos viven en **paas/v4 (OpenAI-compatible), misma key** — misma cuenta,
  dos carteras y dos protocolos en el mismo host; en paas **glm-4.6 razona por defecto** y devuelve
  `content:""` con todo en `reasoning_content` — `thinking: disabled` es parte del contrato de la pata; y los
  créditos **no sirven el endpoint Anthropic** → los workers no pueden usarlos (su cadena ya releva a
  DeepSeek-Anthropic, vivo tras la recarga). Cableado en DOS sitios: la pata `glm_credits_call` del juez
  (ENTRE plan y DeepSeek — mismo modelo, otra cartera, las notas siguen siendo comparables) y el escalón
  `z.ai-créditos` del canal MeshKore. Las dos trampas que lo habrían matado sin ruido: `_is_zai()` casaba por
  HOST (paas habría ido a `/v1/messages` → 404 con pinta de caída, justo en el escalón de socorro; ahora
  excluye `/paas/`), y el emparejamiento de V2-458 (misma cuenta) — lo salva que el 1310 **anuncia su reset**
  → cuota, no saldo → no arrastra. Nodos 2.4 y 10.25, desarmes en los dos lados; la sensibilidad protege los
  $20: con el plan vivo los créditos NO se gastan.

- **Un MATIZ sobre una foto no es un encargo · y la conversación por API se VE (V2-461, 2026-08-28)**: en la
  primera corrida del caso con el operador delante, el turno 1 puso 12 fotos en el visor (✅) y «una de esas,
  la que mejor se vea, **pero que sea el Amalfi, no otro Ferrari**» no llamó a NINGUNA tool —prometió y
  calló— y al turno siguiente escaló a un Brain Worker. **El defecto estaba escrito en la descripción de la
  propia tool, puesta ese mismo día**: «escala … o mejores si las que ya enseñaste NO LE VALEN» — y ese
  matiz ES eso, así que el modelo obedeció. Dos cosas que no hay que confundir: **la hoja genérica de
  Resultados no la eligió el worker, la abre la ESCALADA** (esa tarjeta es la ficha de la tarea), así que el
  destino de la entrega no era el problema; y el turno mudo lo causó **no tener dicho a dónde va «una de
  esas»** —el mecanismo (`widget_data` sobre las acciones del visor) ya existía—. Regla del operador: «en
  realidad sólo estamos pidiendo una imagen» → un matiz afina la `query` y se vuelve a llamar YA, «una de
  esas» es del widget, y se escala SOLO si pide sacarlas de UNA web concreta. Sin subir el techo del
  catálogo (21.191/21.200), compactando la tool tres veces. Nodo 4.84. · **Y el muro de chat**: el canal de
  texto (probe / `POST /api/flash/say`) no se veía en pantalla porque nació HEADLESS (V2-032), y eso dejó de
  ser verdad el día que el plató tuvo puerto fijo para que el operador mirara — un agente que trabaja con el
  chat en blanco es indistinguible de uno colgado. Se marca con un CAMPO (`wall`), no con el label, y **NO
  como `transcript`**: esa rama alimenta el atajo de órdenes por voz del navegador y un turno que dijera
  «cierra la agenda» se ejecutaría dos veces. Nodo 4.85, las DOS mitades (motor + navegador).

- **Un agente del plató arranca con la sesión EN BLANCO (V2-460, 2026-08-28)**: el operador abrió el 43921
  recién levantado y lo primero que vio fue la hoja de un encargo de coches de alquiler de días antes. El
  runner ya limpiaba antes de CADA caso desde el 2026-08-21 (misma queja, otro camino); faltaba el arranque a
  mano. Un agente del plató es persistente a propósito —esa es la razón del puerto fijo— y **lo que persiste
  no es el proceso sino el workspace en disco**, así que canvas, trabajo de fondo y ventana de observabilidad
  sobreviven a un reinicio, que es justo lo que hace ilegible una ronda: el ◷ no sabe separar «este test» de
  lo de antes. `up` limpia al arrancar y hay verbo `lab clean <k>` para hacerlo sin reiniciar. Es
  **`/reset/hard`, jamás `/api/reset/full` con banderas**: ese relanza el motor con un `make run` en el
  directorio REAL y `run-livekit.sh` siega todo `python -m server` por NOMBRE — se llevaría el plató y el
  motor del operador de una vez. Y se dice en los dos sentidos (`cleaned`), porque pedir la limpieza no es
  haberla conseguido. Nodo 10.117.

- **Tres agentes en esta máquina, tres puertos, y ninguno se mueve (V2-459, 2026-08-28)**: el operador volvió
  a `127.0.0.1:43921` —donde había estado mirando al agente español— y no había nada. No era un arranque
  fallido: **esa dirección solo existía para la mitad del arnés**. El laboratorio tenía 43921/43922 clavados y
  documentados como que nunca cambian, mientras la tanda desatendida arrancaba en `preferred_port(43918)`: UN
  número para los dos idiomas y, encima, deslizante a un puerto efímero si estaba ocupado. Así que «el agente
  español» tenía dos direcciones según qué comando lo hubiera levantado, y la que se deslizaba no era una
  dirección — la ronda corría donde cupiera y después nadie podía decir dónde. El deslizamiento **compraba
  menos de lo que parecía**: un motor huérfano tumbaba igual todas las tandas siguientes (medido en
  `test_run_persistence.py`), solo que callando. Ahora hay UNA tabla (`tests/platform/ports.py`: 43917
  operador · 43921 ES · 43922 US), el puerto sale del **idioma del caso** y no de quién lanzó la tanda,
  `preferred_port()` **se ha ido** (mientras exista alguien la vuelve a llamar «solo para que no falle el
  arranque»), y un puerto ocupado es un **error que dice quién lo tiene** y sale con 4 (no se puede medir), no
  con 3 (no se debe). Nodo 10.116, dos desarmes. También se comprueba que el 43917 de la tabla es el que
  `server/__main__.py` arranca solo: esa fila no la controla el arnés y una colisión ahí se paga con la
  sesión de trabajo de una persona.

- **Enseñar una foto es un turno de 3 s, no un encargo de 355 (V2-457, 2026-08-28)**: el operador pidió a mano
  «una foto real del Ferrari Amalfi» y el sistema escaló a un Brain Worker — **372 s y $1,96**, con las fotos
  volcadas en la hoja de resultados genérica y la primera visible a los 3m25s (presentó dos veces). Medida la
  misma petición por las dos rutas: worker 355 s / $1,96 / Autocar India y mad4wheels, frente a `show_images`
  **3,0 s / ~0 / cdn.ferrari.com, Wikimedia 3128×2333, netcarshow 3748×2811**. La ruta rápida no es solo más
  rápida, **trae más autoridad**: el worker nunca llegó a la galería de Ferrari porque se pinta con JS y su
  `fetch` vio una página vacía, mientras que un índice de imágenes ya la había rastreado. Así que escalar se
  queda para **CURAR**, no para encontrar. Tres piezas: el visor `widgets/imagenes/` (foto grande, tira de
  miniaturas, ‹ ›, título con la FUENTE — un previsualizador y nada más, por V2-402: lo que se VE tiene widget
  propio), la tool `show_images` hermana de `play_music`/`play_video` **cableada en los DOS canales** (voz y
  probe, el defecto que esta casa ha pagado cuatro veces), y la receta del worker, que decía con esas letras
  que «una foto» va a la hoja — o sea que la ruta rápida las enseñaba y la lenta las volvía a volcar en una
  tabla. **La frontera es qué ES la respuesta**: «enséñame fotos de X» → visor; «búscame un hotel» → la foto
  es una columna de la ficha. Bing se midió y se descartó como titular (9 de 10 eran otro coche) pero queda de
  socorro etiquetado si Google bloquea. Nodos 4.82 y 4.83. El bug que solo apareció RENDERIZANDO: el aviso de
  «esta imagen ya no carga» se llevaba por delante las flechas, justo cuando más hacen falta.

- **Un saldo agotado apaga a los escalones de su MISMA cuenta (V2-458, 2026-08-28)**: la cadena del operador es
  `deepseek-v4-flash → deepseek-v4-pro → aimlapi-failover` y los dos primeros cobran de la misma clave. Con la
  cuenta a cero, el único reintento que concede V2-252 se gastaba **en un hermano imposible** y el tercer
  escalón —el único de otra cuenta, que respondía 200— no se probaba nunca: el turno salía mudo. Un saldo es
  un hecho de la CUENTA, así que cae sobre todos los que la comparten, y hacen falta **dos** señales: **mismo
  host Y misma credencial resuelta**. La credencial sola no basta y no es hipotético — lo destapó un test que
  ya existía (siembra `Z_AI_API_KEY` y `AIMLAPI_KEY` con el mismo literal), así que una regla que solo mirara
  la clave habría apagado Z.AI al fallar AIMLAPI. Ante la duda **no se empareja**. La distinción de V2-243 no
  se toca: una CUOTA es del modelo y se repone sola.

- **La oferta de PARAR se hace una vez — el hecho se queda (V2-454, 2026-08-28)**: el bloque dice «si una tarea
  sale ENCALLADA o SIN AVANZAR, dilo con esas letras **la primera vez** y ofrece pararla», y **el modelo no
  puede saber si es la primera** — es un hecho NUESTRO, lo mismo que V2-224 aprendió con el aviso de muerte.
  Medido sobre las 334 rondas guardadas: **49 (14 %) repiten la oferta dos o más veces**, diez de ellas en las
  últimas quince de hoy. El daño no es la redundancia: **el operador YA CONTESTÓ** — en `search-buy-used-car`
  dijo «párale y prueba de nuevo, o miramos por otro sitio, tú decides» y el turno siguiente volvió a plantear
  la misma disyuntiva. Se cuenta en **`nucleo/turn_marks.py`** (módulo propio: el trinquete pidió extraer en
  vez de subir el techo de `dispatch`, y el asunto es real — *lo que un turno ya le puso delante al modelo*), y
  **el HECHO se queda**: quitar también el estado devolvería el «sigue en marcha» que V2-131 cerró. De paso,
  `live_blocks` cruzó las 900 líneas y el bloque de tareas salió a `nucleo/flash/task_block.py`, con el mismo
  precedente que `navegador_lines`. Nodo 4.80, cuatro desarmes. **No cierra** que el sistema LEA la respuesta
  del operador: se deja de preguntar por conteo, no porque se haya entendido lo que contestó.

- **El recall que NO llegó se cuenta — «preguntó lo que ya sabía» tiene DOS causas (V2-453, 2026-08-28)**: o el
  recall no llegó (el presupuesto de 800 ms vence y el turno sigue sin memoria durable — avería nuestra, y **la
  mayoritaria**: V2-311 midió 21 de 27 recalls vivos abandonados) o llegó y el modelo lo ignoró (conducta).
  Desde fuera se ven idénticas — la forma del confundido que V2-432 cerró para la hoja, en otro subsistema.
  **No faltaba la señal**: el motor la emite desde V2-311 («recall sin entregar», con motivo y consulta) y el
  informe **no la leía**, así que `weekend-motor-events__es` se archivó como fallo de ADAPTACIÓN [alta] sin
  nada que dijera si esas preferencias llegaron al prompt. Al juez se le da con la instrucción, no solo el
  hecho: **no lo puntúes como fallo de memoria ni de adaptación**. Con cero perdidos no se dice nada. Nodo
  10.115, cuatro desarmes. **No cierra** que el recall no llegue: subir el presupuesto es un canje
  latencia↔memoria que decide el operador.

- **El prompt está en castellano y el operador habla inglés: el modelo copiaba su idioma (V2-452,
  2026-08-28)**: barrido de las 40 rondas US guardadas — **8 (20 %) llevan castellano en la voz de zaelar**, y
  **tres contestan ENTERAS en castellano** a un angloparlante («Hecho, te aviso en cuanto tenga candidatos»);
  las otras cinco son una palabra suelta dentro de una frase inglesa («Bueno», «todavía»), que es la firma de
  la copia. **El idioma NO está mal fijado** (`memory_language: {"effective":"en","explicit":true}`) y el lock
  ya era duro («REGLA ABSOLUTA, POR ENCIMA DE TODO»): lo que faltaba era **decir que lo que LEE está en otra
  lengua a propósito** — todos los bloques del prompt están en castellano siempre, y el lock mandaba escribir
  en inglés sin nombrar lo que NO hay que copiar (la lección de V2-221: sin la frase dentro, el modelo no
  tiene con qué contrastarse). Se añade una cara al lock **solo cuando el operador no habla castellano**, con
  las cuatro palabras medidas nombradas y los saludos dentro de la regla —tres de los ocho casos son una
  respuesta inglesa que acaba en «Bueno…»—. **El camino castellano queda byte por byte igual**: allí el aviso
  sobraría y engordar el prompt de todos los turnos por un defecto que ahí no existe es el canje equivocado.
  Nodo 2.40, cuatro desarmes. **No cierra** que el prompt esté en castellano; esto es el cinturón.

- **Las filas de la hoja viajan aunque NO haya navegador (V2-451, 2026-08-28)**: la causa que V2-432, V2-441 y
  V2-444 fueron dejando escrita, y es estructural — **el bloque de filas colgaba de la PESTAÑA**.
  `_sheet_top_rows` resuelve la hoja DESDE la tarea de navegador y `navegador_lines()` solo compone caras si
  hay tareas, así que un encargo resuelto por BÚSQUEDA no tiene por dónde enseñar nada; y ni siquiera se emite
  el aviso de V2-438, porque vive dentro de la función que nadie llama. Medido en `cheapest-monitor__us`:
  **`navegador_task_id` VACÍO, seis monitores con nombre y precio en la hoja, `shown_to_model: false`, y todo
  el censo a cero — ni un aviso**, con el juez de bloqueador «respondió con una promesa vacía… la hoja ya
  tenía 6». **El alcance, medido y no deducido: el 58 % de las rondas de hoy (46 de 78) no abre navegador** —y lleva así desde el 26 de agosto—, así que en más de la mitad el bloque de filas no podía dispararse ni avisar de que no lo hacía. Eso explica por qué «la hoja llena y el prompt diciendo que no» ha sido el bloqueador más repetido del tablero sin que las tres iniciativas anteriores lo cerraran. Ahora el resumen del encargo lleva **su hoja** (`sheet_of(r)`, que ya estaba a mano y es de quien
  es la hoja, V2-259) y el bloque de TAREAS DE FONDO añade «— YA ENTREGADO (de su hoja): …». **Sin hoja
  sellada no se lee nada**: la caja PELADA es el cementerio de rondas anteriores —lo que cae sin encargo detrás
  y nadie vacía— y leerla enseñaría hallazgos de otro encargo como propios. Nodo 4.79, seis desarmes. ⚠️ Y **el instrumento no podía ver el arreglo**: las filas nuevas llevan otra cabecera y `_rows_in` leía solo la del navegador, sobre la línea del navegador — en las cuatro rondas siguientes `navegador_task_id` estaba VACÍO en las cuatro, así que `shown_to_model` habría salido `False` para siempre y yo habría concluido que el arreglo no funciona. Ahora lee el prompt ENTERO y conoce las dos. **VERIFICADO EN VIVO** (11:37, `best-rated-rental-car__us`, sha `572e6ed`): primera ronda **sin navegador** con todo dentro → `shown_to_model: True`, **3 de 3 entregados con nombre y precio** (Fox $63, Europcar $75, Dollar $91) y `told_but_given_no_rows: 0`, donde las diez anteriores sin navegador salían todas con 0 filas. Y los bloqueadores que quedan en esa ronda son de otra clase —no avisar de que ninguno traía valoraciones, contestar una pregunta directa con un estado genérico—: **conducta, no fontanería**, que es donde había que llegar para poder medirla. **Queda abierto** que hay dos lectores del mismo dato — el de la pestaña y éste.

- **Un precio de mercado ANTES de entregar nada — y los TRES caminos de entrega (V2-450, 2026-08-28)**: fui a
  medir la clase que domina el tablero US (dar precios sin nada detrás) y el barrido de las **329 rondas
  guardadas** deja **2 de 246 medibles**, las dos verificadas leyendo. Lo que cambia para qué sirve el
  instrumento salió por el camino: en `compare-insurance-quotes__us` el juez escribió «INVENTÓ el resultado
  final» y **la nota de la búsqueda había caído 2,6 segundos antes** del turno. Hay **TRES caminos** por los
  que un hallazgo llega al cerebro —la hoja, la extracción y la NOTA EMPUJADA (V2-223)— y el veredicto miraba
  uno; así que su valor principal no es acusar sino **impedir que se acuse**, y la línea que va al juez lleva
  esa mitad primero. **Ocho errores míos por el camino**, todos del barrido y ninguno de la lectura: mirar
  solo la primera respuesta, el separador de millares (que además saca el TOPE de la ventana), la ventana a 24
  caracteres, topes reales fuera de la lista, `sheet_named_ms=None` leído como «no se entregó nunca» con el
  turno CITANDO la hoja, un solo reloj, comparar cadenas en vez de números, y exigirle moneda al operador
  («pago unos 60 al mes»). Y una novena de método: **un script que muta en memoria y escribe al final es
  todo-o-nada**, así que un `assert` intermedio descartó en silencio un arreglo que yo daba por aplicado — lo
  encontré imprimiendo el patrón real, no leyendo mi diff. Nodo 10.114, seis desarmes; el de las unidades saca
  **3 rojos** porque mezclar segundos con milisegundos hace que todo turno parezca anterior a la entrega.

- **La entrega multimedia no está en la hoja (V2-445, 2026-08-28)**: V2-402 fijó que el contenido que se VE u
  OYE se canaliza por su widget dedicado —buscarlo incluido— y que la hoja es para INFORMACIÓN. **El arnés
  nunca se enteró**: seguía midiendo la entrega contra `results_sheet`, que para esa familia está vacía POR
  DISEÑO. Medido en `find-videos-on-a-topic-no-ai-slop`: `widget_ops` trae `youtube.search ×4` —o sea que el
  enrutado funcionó— y el informe publicó `results_sheet: 0`, con el juez concluyendo que zaelar «anunció 2
  vídeos sin respaldo en el sistema» y puntuando resultado 1. **No es una ronda, es una CLASE de escenario**
  midiéndose contra la superficie que no usa. Quinto instrumento acusando al producto la misma noche. Se lee
  la lista de los DOS reproductores (los dos la tienen desde V2-366) y se reporta APARTE de la hoja —
  mezclarlas borraría la frontera que hay que poder comprobar—, y al juez se le dan **las dos mitades**: con
  elementos, la hoja vacía es lo esperado; **vacía, eso sí es no haber entregado**, o el arreglo sería una
  amnistía para la familia entera. Nodo 10.112, cinco desarmes.

- **El mismo defecto en el SEGUNDO bloque, y era el que disparaba (V2-444, 2026-08-28)**: V2-443 marcó `kept`
  como afirmación del worker en la cara del NAVEGADOR, y hay otro bloque que lee el mismo campo —el resumen de
  **TAREAS DE FONDO**— que lo escribía igual de firme y encima ordenaba tratarlo como entrega («entonces la
  tarea SÍ ha traído eso — cuéntalo en este turno»). Medido en `best-pediatric-dentists__us` con
  `told_but_given_no_rows` estrenándose: **7 turnos avisados con cero filas**, veinte dentistas con nombre y
  ★rating en la hoja, ninguna fila en ningún prompt — **y la cara del navegador no se encendió ni una vez**,
  así que arreglar solo V2-443 dejaba vivo justo el camino que se estaba midiendo. Cuarta vez que esta casa
  paga lo mismo: **el fallo no fue la regla, fue tenerla repetida.** El contador tuvo que aceptar las DOS
  frases por la misma razón: miraba solo la del navegador y habría dado cero donde había siete. Lo ENTREGADO
  se sigue ordenando contar, con test (V2-222 intacto: negar una entrega que el operador tiene delante es peor
  que no haberla hecho). Nodo 4.78, tres desarmes. **Sigue abierto** por qué esas 20 filas no viajaron a
  ningún prompt: el censo dice que la caja era la correcta y había una sola hoja en toda la ronda.

- **Sin filas, lo único que hay es la PALABRA del worker (V2-443, 2026-08-28)**: la cara de «ya ha encontrado»
  tiene dos fuentes — con filas, la hoja la respalda y es un HECHO; **sin filas solo queda `kept`**, la cuenta
  que el propio worker escribe con `hbnote considered --kept N`. El bloque la renderizaba en firme y, encima,
  le prohibía al turno la frase contraria («NO digas que sigue sin resultados… eso es falso»). Medido en
  `find-theatre-tickets__us` con el censo de V2-440 dentro: **la cara disparó once veces con
  `worker_outcome.found: []`, cero filas en ninguna hoja y la hoja del encargo diciendo «sin resultados
  todavía»**. Le poníamos delante una afirmación falsa y le prohibíamos la verdadera, así que la única salida
  era decirle al operador que ya estaba sacando cosas — y eso se puntúa como prometer lo que no se tiene.
  Misma familia que V2-358 y V2-249: **no se tira, se MARCA**. Y **la prohibición se parte en dos**, que es lo
  que de verdad cambia el turno: «TODAVÍA NO HA LLEGADO nada» habla de la ENTREGA, es cierto y se puede decir;
  «NO HA ENCONTRADO nada» habla del mundo, **no lo sabemos** y sigue prohibido — que era lo que V2-330
  protegía y sigue en pie. La tarea se sigue diciendo VIVA o «no ha llegado nada» se leería como «está parada»
  y empujaría a relanzarla (V2-152). Nodo 4.77, cuatro desarmes, y los cuatro salieron verdes en la primera
  pasada con **«no tests ran»**: en zsh un parámetro sin comillas no se parte en palabras (`${=T}`) — la
  trampa de V2-238, otra vez.

- **Pedirlo dos veces no es hacerlo dos veces (V2-442, 2026-08-28)**: al juez se le decía «el mismo encargo se
  lanzó N veces … puntúa EFICIENCIA abajo» **sin decirle cuántos workers NACIERON**, y con eso archivó
  `buy-known-product__us` como que «duplica trabajo de navegación» — con `n_spawned: 1` en el mismo informe.
  El dedup había absorbido la segunda escalada, que es su trabajo: no hubo navegación duplicada, hubo una
  escalada de más. Cuarto caso de la misma noche de un instrumento acusando al producto de algo que no hizo
  (barrido: 15 duplicados idénticos en 214 rondas, y en las cuatro últimas absorbidos). **No se absuelve en
  bloque** porque el defecto real está medido —24 y 25 de agosto, grupos de dos y tres con TRES workers
  nacidos—: lo que decide es cuántos nacieron, y ese número ya viajaba sin que nadie lo mirara. **Fail-closed**:
  sin el campo se mantiene la advertencia, porque «no lo sé» no puede absolver o el arreglo borraría hallazgos
  archivados. Nodo 10.111, tres desarmes. Sigue abierto lo caro: la PARÁFRASIS (V2-123) no la absorbe nadie.

- **«Le pedimos lo imposible»: avisado de que había algo y servido con CERO filas (V2-441, 2026-08-28)**: el
  contador de turnos CIEGOS se salta a propósito los que llevaban `says_found` —a ésos sí se les dijo—, y eso
  dejaba sin contar el caso que V2-330 nombró y no cerró: la cara ordena «CUÉNTALE lo que encaje, **con nombre
  y precio**» y el prompt no trae ni una fila. Medido en `search-buy-bicycle__es`: **10 turnos avisados con
  cero filas**, con los resultados existiendo los últimos 315 s, `sheet_hidden_from_the_prompt: n=0` (con
  razón) y el juez puntuándolo como negar la entrega — los dos hechos ciertos y ninguno contado. V2-330 ya
  tenía el efecto medido (**sin filas 79 % de esos turnos responde con espera; con filas 42 %**); faltaba el
  contador POR RONDA para saber si el arreglo llegó. **Al juez se le dice, con las dos mitades**: no bajar la
  nota por no dar nombres que no tenía, y **sí** por callar que había algo — sin esa segunda mitad el hecho se
  vuelve una amnistía y el 42 % restante deja de puntuarse. Nodo 10.109 ampliado, seis desarmes, y el sexto es
  el que faltaba en tres nodos de esta semana: **los cinco primeros pasan enteros con la línea de `run.py`
  borrada**, o sea con el campo sin calcular — un contador que nadie llama mide cero, y el cero se lee como
  «no pasó».

- **El censo del INSTANTE separa dos causas que se veían idénticas (V2-440, 2026-08-28)**: la cara dice «YA HA
  ENCONTRADO algo» y la hoja no da ni una fila, y eso tiene DOS causas con arreglos OPUESTOS — **desfase** (el
  worker aún no ha entregado: el aviso es correcto y no hay nada que tocar) y **caja equivocada** (las filas
  están en otra hoja: ahí sí hay defecto). La única forma de decidirlo era comparar contra el estado FINAL de
  la ronda, y **un estado final no puede contestar una pregunta sobre un instante**: medido en
  `search-buy-bicycle__es`, mi instrumento marcó `e84138-2` como equivocada y esa caja acabó con **35 filas**
  — era la correcta y estaba vacía cuando se miró. Ahora el motor emite, junto a las cajas que miró, **cuántas
  filas con nombre tiene cada hoja en ese instante** (recuento, nunca contenido) y el arnés deriva de ahí el
  veredicto, con dos salidas más que evitan inventar: un censo ILEGIBLE es un HUECO —jamás «desfase»— y las
  filas en la hoja DESNUDA son la **caja FANTASMA**, categoría propia. Esa tercera no es cosmética: esconderla
  bajo «desfase» es falso (en un desfase no hay nada escrito y aquí las filas existen a un palmo) y contarla
  como una hoja de encargo mandaría a arreglar la RESOLUCIÓN cuando lo roto es la ENTREGA — el motor miró
  bien. Pasa de verdad: la ronda de la bici trae `written_ids: ['results', 'results::e84138-2']`. ⚠️ Y una
  corrección DENTRO del propio arreglo: la primera versión llamaba «caja equivocada» a que otra hoja tuviera
  filas, y es falso —el censo lista TODO el almacén y **la hoja de un encargo anterior tiene filas
  legítimamente**—, así que con dos encargos una ronda sana salía marcada. Queda como `otras_con_filas`, un
  HECHO que se compara con la cadena del encargo y no un veredicto que el instrumento adivina; lo cazó un
  test que solo fallaba dentro de la suite completa. Lo que
  esa ronda SÍ deja medido y sigue abierto: **10 de 12 turnos avisados de que había algo con CERO filas**, con
  los resultados existiendo los últimos 5 minutos — la trampa de V2-330, escrita por nosotros. Descartado por
  el camino: no es `sheet_key` (V2-439) ni el lector (reproducido en aislamiento, con la caja resuelta
  devuelve las filas). **Primera medida en vivo (`find-theatre-tickets__us`): 11 avisos, los 11 DESFASE** — y el clasificador viejo los marcó los 11 como caja equivocada, así que hubo que retirarlo también del JUEZ, que seguía leyéndolo: contarle una avería inexistente once veces en una ronda le baja la nota de mecanismo por algo que no pasó. Lo que esa ronda deja como defecto real y sin ambigüedad: **la cara dice «ya ha encontrado algo» once veces con la hoja vacía en todas partes** — la señal que la enciende no está respaldada por ninguna fila. Nodo 10.110, siete desarmes — y el primero **no mordía**: los tests pasaban con el
  emisor MUDO, o sea un lector interpretando un campo que nadie escribe, que publica ceros y se leen como «no
  pasó». El censo va acotado, así que **el orden decide qué se puede diagnosticar**: primero las cajas que se
  miraron (el ancla), después las que más filas tienen.

- **`results::X` y `X` son la MISMA hoja, y una volvía VACÍA (V2-439, 2026-08-28)**: el canvas nombra una
  instancia `results::<corr>` (V2-259) y el almacén usa `results--<corr>`, porque `store._safe_id` no admite
  `::`. Cuando a `sheet_key` le llega el id del canvas ENTERO, el saneado se come los dos puntos y compone
  `results--results82d86e-2` — una clave que **no existe**, así que la hoja vuelve **vacía**, indistinguible
  de «aún no hay nada»: sin error, sin traza, sin filas. Salió tirando del hilo de por qué el bloque de filas
  no ha aparecido nunca en 45 rondas medidas, y **no cierra aquello**: lo explicaría solo si algún llamante
  pasa el id del canvas, y eso NO está medido — el arreglo es defensivo y una instancia pelada se comporta
  exactamente igual que antes. Tres cuidados: **solo el prefijo PROPIO** (tolerar cualquiera convertiría el id
  de otro widget en un alias silencioso de una hoja nuestra), `sheet_key("")` sigue siendo `results` byte por
  byte (sin migración y sin dos linajes vivos compitiendo, la trampa de V2-242), y **cero líneas netas**: el
  trinquete tiene ese fichero-dios en 1029 y mi docstring de tres líneas lo pasaba de largo — el razonamiento
  vive en la iniciativa, en el fichero basta el hecho. Nodo 4.76, tres desarmes.

- **La cara dice que hay filas y la hoja no las da (V2-438, 2026-08-28)**: el CUARTO camino, y el único que
  quedaba mudo. La cara de resultados se enciende con `_p["has_results"]` **o** con `_found_candidates`, y el
  `or` **hace cortocircuito**: si el primero es cierto, `_sheet_has_rows` ni se llama y sus tres avisos no
  existen. Entonces `_sheet_top_rows` resuelve por su cuenta, no encuentra caja con filas, y el turno sale
  diciendo «ya ha encontrado algo, pero sus nombres AÚN NO están escritos» — con los nombres escritos. Medido
  en `reorder-prescription__us`: tres turnos a **32, 72 y 111 segundos DESPUÉS** de que la hoja tuviera seis
  farmacias con nombre y dirección, avisados de que había algo y con **cero filas**; el modelo nombró cero de
  seis y el juez lo llamó «falla gravemente al no entregar esos datos». Se instrumenta el hueco (con las cajas
  que miró, para poder compararlas con dónde están las filas) y **no se arregla a ciegas**: **primera medida (08:06)**: en `renew-gym-membership__us` miró
  EXACTAMENTE la caja que acabó teniendo la fila, así que no es resolución sino **desfase** entre el instante
  en que la fila se registra (eventos) y aquel en que la hoja la entrega (`view_data`) — cuatro turnos
  después de existir. **Su impacto sigue sin probarse**: en esa ronda la entrega fue 4 nombres sobre 1
  disponible, o sea que el modelo entregó igual por las notas empujadas y el desfase no costó nada. Cuarta vez
  en la noche que una señal prometedora encoge al mirarla de cerca: se deja puesta y no se le atribuye daño
  hasta que una ronda lo demuestre. Nodo 4.70 ampliado, tres desarmes. ⚠️ Y una lección de
  lectura: **las DOS ramas del bloque contienen «YA HA ENCONTRADO»** —también la que dice que no hay nombres—,
  así que buscar esa frase NO distingue «se le dieron las filas» de «se le dijo que las habrá».

- **Un elemento muerto dice qué hacer (V2-437, 2026-08-28)**: **siete** «Element is not attached to the DOM»
  en dos rondas del plató, con el worker repitiendo `click 13` una y otra vez. El mensaje era el crudo de
  Playwright y nada más — mientras su hermano, el ref fuera de la mirada, dice desde siempre «haz `look`… no
  inventes refs ni reintentes el mismo». Son **el mismo problema** —un ref que caducó— contado de dos maneras,
  y solo una servía. Se añade la salida y se CONSERVA el mensaje crudo: es cierto y le sirve a quien depura,
  mientras que al que está trabajando le falta justo lo otro. Dos entradas más de la misma tanda: el
  `select_option` sobre un div que parece un `<select>`, y el timeout. Lo que YA dice qué hacer no se duplica
  —una línea que se repite deja de leerse— y un error desconocido NO se inventa una salida, porque sugerir un
  remedio equivocado es peor que no sugerir ninguno. Nodo 4.75, tres desarmes.

- **Una memoria rechazada dice POR QUÉ (V2-436, 2026-08-28)**: con el comando ya dentro de las anomalías,
  **cinco** intentos del worker de guardar hallazgos OPERATIVOS —«Wallapop filtro que funciona:
  …max_sale_price=8000», «Milanuncios bloqueado por anti-bot», «coches.net da error persistente», «Facebook
  Marketplace requiere login»— murieron con `HTTP Error 422: Unprocessable Entity` **y nada más**. Es
  exactamente el conocimiento que evita que el siguiente worker repita el trabajo (la razón de ser de V2-344).
  El servidor SÍ dice por qué —«descartado por el gate de precisión (<razón>)», en el CUERPO— y
  `urllib.error.HTTPError` solo trae el número: el worker reintentaba o se rendía a ciegas. Ahora se propaga,
  con dos cuidados que salieron de los desarmes: un cuerpo ILEGIBLE no puede empeorar el error (un fallo al
  explicar un fallo deja al que lee peor que si no se hubiera intentado) y el camino sano no cambia. **El gate
  NO se toca**: que rechace estos cinco puede ser correcto o demasiado estrecho, y decidirlo sin saber la
  razón sería el error que esta noche se ha pagado tres veces. La pista es que el gate pasa hallazgos con
  forma de ANUNCIO y estos cinco son operativos — el CÓMO en vez del QUÉ; si la memoria debe guardarlo es
  decisión del operador. Nodo 4.74, tres desarmes.

- **El worker PUEDE escribir lo que le decimos que escriba (V2-435, 2026-08-28)**: le pedíamos escribir un
  fichero y no le dábamos la tool. El payload de los puentes va por `@fichero` desde que la puerta de permisos
  rechazó el JSON en línea, y el prompt lo dice con todas las letras —«escríbelo con Write a un fichero de tu directorio»—, pero **`Write` no estaba en la
  allowlist** que se pasa al CLI (30 entradas, ninguna), así que pedía una aprobación que en headless nadie va
  a dar. Medido en `find-best-hotel-city__us`, con la cadena entera visible por primera vez gracias a los
  arreglos de la misma noche: «Claude requested permissions to write to …/informe.json, but you haven't
  granted it yet» y acto seguido «no puedo leer el payload de informe.json». Nueve turnos ciegos y 1/5. Una
  instrucción que el sistema hace imposible de cumplir no es una instrucción: es una trampa para el modelo Y
  para quien lea el transcript. **Solo `Write`**, ni `Edit` ni `NotebookEdit`: el worker estrena directorio de
  usar y tirar y escribir su propio JSON es la operación más pequeña que hay, mientras que modificar ficheros
  existentes es otra cosa y nadie la ha pedido. Con `deny_tools` (input no confiable) sigue sin nada. Hay un
  test que exige que el prompt y la allowlist digan lo MISMO: el defecto no era que faltara una tool, era que
  faltaba la que el prompt pide. Nodo 4.73, tres desarmes.

- **Un RELEVO no es un encargo nuevo, tampoco para quien LEE la hoja (V2-434, 2026-08-28)**: el final de
  V2-432. Un relanzamiento por falta de cuota HEREDA la hoja de su predecesor, pero el **sello de la pestaña**
  «se escribe una sola vez, en `tasks.create()`» y el relevo crea pestaña nueva — así que el sello apunta a la
  caja nueva (vacía) mientras los hallazgos siguen en la heredada. El sello no está ausente: está **RANCIO**, y
  su docstring solo contemplaba lo primero. `boxes_of_tab` da las dos, **sello primero y registro después**
  —invertirlo cambiaría de quién es la hoja, y eso sí toca a quien escribe—, y el lector se queda con la
  primera que TENGA filas. Las filas que se muestran salen de **esa misma caja**: si la señal dijera que hay
  algo y las líneas vinieran de otra, el prompt afirmaría tener resultados sin poder nombrarlos, que es peor
  que las dos cosas por separado. **Solo el LECTOR** —hay un test que lo exige recorriendo el árbol—, y ése era
  el requisito para tocarlo con el operador durmiendo: equivocarse en el enrutado de ESCRITURA manda los
  resultados a una caja que nadie mira, que es justo el defecto que se arregla. Nodo 4.72, cuatro desarmes —
  y uno de ellos enseñó que un `.pyc` rancio puede sobrevivir a la restauración y dejar el código bueno
  comportándose como el defecto. **⚠️ La CAUSA no se sostiene (06:38)**: con Z.ai recuperando cuota, la señal
  de caja vacía debía caer si venía de los relevos por saldo, y no cae — 4 de 15 rondas sin cuota frente a 2 de
  6 con ella. La señal es real y del motor; el ARREGLO es defensivo y no puede hacer daño (mira una segunda
  caja solo si la primera no tiene lo que busca, y no toca a quien escribe); la causa que escribí venía de leer
  el caso que `nucleo/sheets.py` documenta del 2026-08-23 y **no de evidencia en estas rondas**. Queda abierta.
  Segunda historia causal de la noche que tumba mi propia medición, y las dos por comprobar una consecuencia
  que la teoría obligaba a tener.

- **El puente del worker habla el vocabulario de widgets (V2-433, 2026-08-28)**: la anomalía llegó ya con el
  comando dentro (V2-429) — «ERROR: el widget «music» no existe · lo que se intentó: …»— y la carpeta se llama
  `musica`. El puente resolvía con `paths.dir_for`, que casa con el id de la CARPETA y nada más, mientras
  `widgets/registry.py` construye normalizada la identidad de los 26 (id + nombre + alias): el vocabulario
  estaba y nadie lo miraba desde ese lado. **Y no era solo cosa del inglés**: la misma búsqueda rechazaba
  `reloj`, el nombre castellano del widget cuya carpeta es `clock`. `widgets/naming.resolve` recupera de
  entrada `reloj → clock` y `playlist → musica`. Tres reglas: una **colisión es una negativa, no una apuesta**
  (elegir uno de dos widgets donde el llamante va a ESCRIBIR es peor que decir que no), el «no existe» **dice
  los que hay** (un nombre rechazado a secas deja al worker reintentando el mismo — medido esta noche en otras
  tres puertas), y **las dos puertas** (leer y operar) lo usan, con test, porque arreglar una sola dejaría al
  worker resolviendo un nombre para leer y fallando con el mismo para escribir. `music` seguía sin resolver
  porque no estaba en NINGÚN manifiesto: añadido al de `musica` y solo ahí, que es el caso medido — los
  manifiestos son el vocabulario único que lee todo el sistema, y una tabla de sinónimos en el puente habría
  creado un segundo que se separa del primero sin avisar. **Abierto y del operador**: `calendar`, `weather` y
  `browser` tampoco resuelven; inventar el vocabulario inglés de los 26 no es mecanismo, es producto. Nodo
  4.71, cuatro desarmes.

- **La hoja llena y el prompt diciendo que no (V2-432, 2026-08-28)**: «tenía resultados y contestó que no
  había novedades» es el bloqueador más repetido del tablero, y hay otra lectura que decide de quién es la
  culpa — **si en su prompt ponía que la tarea seguía atascada, contestó exactamente lo que le pusimos
  delante**. Medido en `find-direct-flight-budget__es`: `sheet_named_ms` cae entre el turno 5 y el 6, y en los
  turnos 6, 7 y 8 el bloque vivo traía la cara de «sin avanzar» y CERO filas con **cuatro vuelos con nombre**
  en la hoja; el juez le puso 2/5 por «negar lo que el sistema le mostraba», y el sistema le mostraba lo
  contrario. **⚠️ RECTIFICADO: el hallazgo era MÍO, no del producto** — con el detector arreglado, dos rondas medidas dan
  9 de cada 10 turnos AVISADOS y cero ciegos, así que el sistema sí se lo decía. Y la «verificación en vivo»
  del juez era CIRCULAR: ese hecho se lo había metido yo en `mechanism_facts`. Sobreviven `vacías: 7` (señal
  del motor), el mecanismo del sello rancio (leído del código) y lo de `Write` (error literal del CLI); se cae
  la ESCALA. **El recuento estaba MAL MEDIDO**: el detector buscaba la frase en la línea de «TAREAS
  DE FONDO» y el imperativo de resultados es OTRA línea del prompt, así que «45 de 48 rondas, 257 turnos ciegos»
  hay que volver a medirlo (corregido 05:48; los informes viejos no permiten recalcularlo). Lo que NO se cae es
  el caso que lo abrió —`find-direct-flight-budget__es`, leído a mano turno a turno— ni el mecanismo del sello
  rancio, que se confirmó con una señal del MOTOR (`vacías: 7`) y no con este detector. En su día el barrido
  dijo (de 262 en bruto, 5
  eran tarea ya terminada y se descuentan). Eso reordena la lectura de meses de tablero: buena parte de «narra
  trabajo que no ocurre» y «retiene lo que tiene» no es conducta, es que no se lo dijimos. **Dónde NO está la
  avería**: `_found_candidates` ya cae a `_sheet_has_rows` cuando el worker no reportó su cuenta, y éste lee por la
  pestaña con los dos caminos del escritor (V2-352) — la sospechosa es la resolución de la CAJA del encargo, porque la ronda tenía
  dos hojas (`results` y `results::6175ca-1`) y el bloque vivo no encontró las filas de la que las tenía. No
  se afirma: el plató se borra en cada ronda y no se puede reproducir a mano. Lo que hay es el número en cada
  informe, y **al juez se le dice que no lo puntúe como negar**. Nodo 10.109, cuatro desarmes. **Primer paso
  dado** (nodo 4.70): `_sheet_of_tab` avisa cuando ni el sello ni el registro resuelven la hoja —donde mueren
  los dos caminos—, con su mitad de sensibilidad (resolver por el segundo camino NO avisa: llamar avería a lo
  que funciona convierte el aviso en ruido, y el bloque vivo se compone en todos los turnos). Al instrumentarlo
  `live_blocks.py` cruzó el umbral de fichero-dios y el trinquete pidió trocear, con razón: resolver la caja
  del encargo es asunto propio —dos caminos, tres llamantes, y cuando falla falla MUDO— y vive ahora en
  `nucleo/flash/errand_sheet.py`, con un test que exige que las dos referencias sean el MISMO objeto porque
  dos copias dejarían el aviso en un sitio y el prompt componiéndose con el otro. **Verificado en vivo a los 30
  minutos** en `search-buy-guitar__es`: el juez escribió «el bloqueador nº1 es que EL SISTEMA no mostró a
  zaelar las filas durante 6 turnos seguidos, obligándole a repetir "sigo buscando" cuando ya había 15
  candidatos reales» —culpa atribuida a quien la tiene— y la ronda **pasó con 4**, cuando antes se habría
  archivado como «retiene lo que tiene». **Y la sospechosa quedó DESCARTADA**: `unresolved_errand_sheets: 0`,
  la caja sí se resolvía. **DIAGNÓSTICO CERRADO** en `compare-flights-madrid-lisboa` (04:43): 4 turnos ciegos, 0 sin
  resolver, **7 «resuelta pero VACÍA»** — el bloque vivo miró la caja `f1743e-2` (vacía) mientras las filas
  estaban en `f1743e-1`, con `worker:1` y `worker:2` sobre el mismo encargo. **Lee la caja de un worker y las
  filas están en la del otro**: resuelve siempre y resuelve a una caja REAL vacía, por eso durante meses se ha
  visto igual que un encargo que no encontró nada. **Y el mecanismo está NOMBRADO**, leyendo y no adivinando: `nucleo/sheets.py`
  documenta este defecto exacto —«A RELAY IS NOT A NEW ERRAND», medido en `cheapest-monitor` el 2026-08-23,
  con `-1` vacía y `-2` con los 13 hallazgos—, así que `f1743e-1` y `-2` son **dos escalones de UN encargo** y
  el relevo debe HEREDAR la hoja. Dónde se rompe: el sello de la pestaña «se escribe una sola vez, en
  `tasks.create()`», y el relevo crea pestaña nueva, así que su sello apunta a la hoja nueva mientras los
  hallazgos heredados siguen en la del predecesor. **Explica por qué esta noche pasa tanto**: con Z.ai sin
  cuota desde las 01:55, cada encargo relevea. El arreglo —que el sello del relevo apunte a la hoja
  heredada— toca el enrutado de dónde se leen y escriben los hallazgos de TODOS los encargos, y equivocarse
  ahí no da un error: manda los resultados a una caja que nadie mira, que es el defecto que se arregla. Queda
  con el sitio señalado.

- **Un «no» bien fundado es una ENTREGA (V2-431, 2026-08-28)**: en `find-concert-tickets__es` no había
  concierto de Rosalía en Madrid ese mes —respuesta completa y correcta— y el worker llenó la hoja de eventos
  que no eran, dejando a la persona **siete minutos** esperando. El método cubría «si no se puede certificar,
  dilo con honestidad» (paso 7) y faltaba **lo contrario**: sí lo certifiqué, y lo que certifiqué es que no
  existe. Sin decirlo, el único final que le queda al worker es seguir buscando — volver vacío no está en su
  repertorio, así que rellena, y rellenar es PEOR que el vacío porque el vacío se lee en dos segundos y la
  lista de cosas-que-no-son hay que descartarla una a una. Paso 8, con las dos mitades: se entrega diciendo
  dónde miraste y qué descartaste (un «no» sin eso no se distingue de no haberlo intentado), y **nunca
  rellenar** para no volver vacío. **Sin medida en vivo**: es una línea de prompt y lo medido aquí es que un
  hecho empujado llega 3/3 y el mismo en el prompt 0/13 — ésta es norma de cierre y no hecho, que es la clase
  que el worker sí sigue, pero eso es expectativa y no medición. Nodo 4.69, tres desarmes.

- **El precio que DICE es el que TIENE (V2-430, 2026-08-28)**: en `compare-broadband-plans__es` la hoja tenía
  «Digi → 23 €/mes», el agente lo dijo BIEN dos veces y a la tercera soltó «lo de Digi ronda los **4,9 euros**
  al mes» — mismo candidato, precio inventado, contradiciéndose a sí mismo, y justo en el turno en que el
  usuario pedía los datos para decidir. El juez lo cazó a ojo y lo puso de bloqueador nº1; el informe no tenía
  con qué respaldarlo NI contradecirlo. Un precio equivocado no es un matiz: quien contrata con ese dato se
  lleva veinte euros de sorpresa al mes, y el dato bueno lo tenía delante. Conservador a propósito (ventana
  corta detrás del nombre, precio en la hoja obligatorio, varios importes y uno que cuadre no marca,
  tolerancia de un céntimo) porque un falso positivo acusa al producto de mentir. Dos cosas que enseñó el
  desarme: **el ancla no puede ser `_title_head`** —exige dos palabras y con su listón `Digi · 500 Mb…` no
  tiene ancla, así que el caso medido no se habría cazado— y **los títulos con acento eran invisibles**,
  porque el ancla va sin acentos y se buscaba sobre el texto crudo: «masmovil» nunca aparece dentro de
  «MásMóvil», y DOS tests estaban pasando por eso y no por la lógica. El plegado es 1:1 para que el índice
  valga sobre el original. **El barrido por las 61 rondas guardadas fue lo que lo hizo fiable**: la primera
  versión decía «21 rondas con precio equivocado» y ese número era mentira — etiquetas de listado usadas como
  ancla («Buen precio», «Opción i/v»), un ancla que valía para DOS Passat de la misma hoja, el punto de millar
  leído como decimal («4.999» → 4,999) y el redondeo al hablar («ronda los 200» sobre 205) contados como
  mentiras. Cerradas: **4 rondas de 61 (6,5 %)**, con errores del 84 %, 38 %, 31 % y 9 %. Y una sexta en
  dirección contraria: contra el informe REAL el caso que lo motivó había dejado de cazarse, porque «Digi»
  sale DOS veces en ese turno y la primera no lleva precio — miraba solo la primera mención, y mi fixture
  sintético tenía una sola. Seis errores míos en un detector de treinta líneas, y los seis los enseñó el mismo
  gesto: pasarlo por los datos guardados en vez de por los que me había inventado. Nodo 10.108, dieciséis
  tests, diez desarmes.

- **Un comando rechazado dice qué se intentó (V2-429, 2026-08-28)**: cuatro rechazos distintos de la puerta
  de permisos en una sola noche («simple_expansion», «brace with quote», el `&`, el `cd`) y en los CUATRO el
  evento guardaba qué regla se rompió **y nada del comando**. Eso no distingue las dos causas, que piden
  acciones opuestas: el worker escribió algo raro (conducta, se mide) o **nuestro propio prompt se lo enseñó**
  (culpa nuestra, se arregla en el prompt). **Dos de las cuatro eran lo segundo** —V2-424 y V2-426— y hubo que
  reconstruirlo a mano cada vez; la cuarta se quedó sin reconstruir por falta de rastro. El sistema tenía el
  comando delante, en el `tool_use`, y lo tiraba al casar el paso con su resultado. Ahora el meta del paso lo
  guarda y `step_result` lo recupera, **solo cuando el paso falla** (el comando de un paso sano es ruido, y
  una fila que sale siempre deja de mirarse) y **sin escribir un campo vacío** cuando no lo hay (`cmd: ""` se
  lee como «se intentó nada», que no es «no lo sabemos»). Los cuatro los cacé por casualidad leyendo logs; el
  quinto se lee del informe — la diferencia entre arreglar defectos y poder arreglarlos. **Media faena
  corregida a los diez minutos**: el comando llegaba al evento crudo y la ANOMALÍA del informe —lo que se
  lee— seguía diciendo solo la regla rota; guardar el dato y no llevarlo donde se mira no arregla nada. Nodo
  4.68, siete tests, cinco desarmes.

- **Un traceback se recorta por la COLA (V2-428, 2026-08-28)**: los tres tracebacks guardados en el tablero
  como anomalías de certeza «hecho» quedaban en «Traceback … `<frozen runpy>` … `_run_module_as_main` …
  File "/Users…» — cien caracteres de andamiaje **idéntico en cualquier fallo de Python**, con la línea de la
  excepción cortada fuera. El recorte por delante es correcto para un mensaje normal y lo peor posible para un
  traceback, donde lo que sirve está al final. Tres hechos registrados y ninguno diagnosticable: el informe
  afirmaba que había un error interno del navegador y no dejaba saber cuál — la forma más cara de tener razón,
  y la misma familia que V2-421 y V2-425 (el sistema tiene la respuesta y no la imprime). `_error_gist` se
  queda la cola cuando el texto abre como un traceback y lo marca con `…` —un error que empieza a media frase
  sin avisar se lee como otro error—; el resto se recorta por delante, porque darle la vuelta a todo
  arreglaría tres anomalías y rompería las otras nueve. Nodo 10.107, tres desarmes.

- **La apertura del tester no puede recitar nuestra hoja (V2-427, 2026-08-28)**: lo encontró un TRINQUETE
  alimentado por el plató 24/7 — `test_medido_contra_TODAS_las_rondas_guardadas_no_hay_falsos_positivos` barre
  las líneas del tester de todos los informes y exige como mucho tres marcadas, «el umbral sube cuando el
  corpus crece con otro flip, nunca porque el detector se haya ensanchado». La ronda de `search-buy-camera__us`
  metió una cuarta y obligó a mirarla: era un FALSO POSITIVO, la línea de apertura del tester («Find me a used
  DSLR camera with a low shutter count for under $400»). `known_titles` es la hoja del FINAL de la ronda y el
  barrido va turno a turno, así que contra la primera línea se comparaba con títulos que aún no existían. **En
  castellano no salía**: el encargo y el anuncio se parecen mucho más cuando los dos están en el idioma del
  sitio, así que lo destapó el plató US — razón concreta para tener los dos midiendo. Mi primer arreglo puso la
  frontera en «`heard` vacío» y **el test de al lado lo tumbó**: una línea a media conversación que nombra un
  título que zaelar NUNCA dijo también llega con `heard` sin él, y ésa sí es un flip — el caso fuerte de la
  regla. Lo que hace inocente a la apertura no es el silencio, es que todavía no hay nada NUESTRO que se pueda
  haber leído: parámetro explícito `opening`. Y al desarmarlo falló la otra mitad: el test que barre los
  informes REIMPLEMENTA el bucle, así que seguía verde con `run.py` roto (25 comprobaciones sobre el defecto
  restaurado); lo cubre ahora la guarda de cableado. Tres desarmes.

- **El `cd` bloqueado, y la premisa falsa que lo provoca (V2-426, 2026-08-28)**: tercera firma más repetida
  del recuento de anomalías (9 entre `worker/task` y `memory/memory`): «cd in '…/engine' was blocked. For
  security, Claude Code may only change directories to the allowed working directories». La regla ya decía
  «no salgas de tu directorio», y faltaban tres cosas. (1) **El worker no está siendo descuidado**: `python -m
  nucleo.nav_cli` PARECE necesitar la raíz del repo para que `nucleo` sea importable, así que meterse ahí es
  una inferencia correcta a partir de lo que le enseñamos — el entorno ya lleva lo que el import necesita y
  nada se lo decía, y una regla que contradice lo que el propio comando sugiere pierde contra el comando.
  **Contestar esa premisa no puede hacerse nombrando el sitio**: escribí la frase con el nombre dentro para
  negarlo y saltó `test_y_NINGUNO_afirma_que_el_worker_corre_en_la_raiz_del_repo`, un guarda que prohíbe esa
  frase porque es exactamente la que produjo los `cd blocked` medidos en su día — un escaneo de subcadena no
  distingue afirmar de negar, y hace bien, porque el modelo tampoco a la tercera lectura. (2) El mensaje del
  rechazo no estaba en la regla, tercera vez esta noche. (3) El prompt cierra con «si un comando te pide
  aprobación, lo escribiste mal: REESCRÍBELO», y para el `cd` eso es FALSO —no es una forma mal escrita, es un
  sitio al que no se va— así que seguir ese consejo quema turnos en reescrituras imposibles: ahora se dice que
  **no hay rodeo**. NO arregla por qué la MEMORIA lanza un `cd` (5 de las 9). Nodo 4.61 ampliado, tres
  desarmes.

- **El error de payload dice QUÉ falló (V2-425, 2026-08-28)**: contando las ANOMALÍAS MEDIDAS de las 44
  filas del marcador —hechos, no prosa del juez—, `payload JSON inválido` sale **18 veces, más del doble que
  la siguiente firma**, y el mensaje era literalmente eso: ni qué tenía de inválido ni qué se leyó. Un worker
  no puede arreglar lo que no sabe que escribió mal, así que reintenta igual (tres y cuatro intentos
  idénticos seguidos en el rastro). Dos cosas: **tolerar la valla de markdown** —a un modelo al que le pides
  un JSON le sale ```json solo, y no es ambiguo: una valla tiene una sola lectura, así que rechazarla no
  protegía de nada y gastaba una vuelta— y **decir qué falló** (línea, columna, motivo del parser y los
  primeros caracteres de lo leído). Lo que NO se tolera es el «casi JSON» —comillas simples, comas de más,
  claves sin comillas—: eso SÍ es ambiguo y un parser indulgente ejecutaría una acción que el worker no dijo,
  peor que rechazarla; igual que una lista, porque `act` espera un objeto y un `{}` silencioso mandaría una
  acción vacía como si fuera buena. Cuántas de las 18 eran la valla no se sabe: el mensaje no lo guardaba, que
  era el defecto. Nodo 4.67, cuatro desarmes.

- **El `&` solo también lo bloquea nuestro guarda, y no estaba en la regla (V2-424, 2026-08-28)**: medido en
  `find-best-hotel-city__us` (plató 24/7): el worker terminó un comando con `&` y nuestra propia puerta lo
  mató — «This command uses the `&` background operator, which defers execution past approval-time safety
  checks». La ronda murió a los 4 turnos, con seis navegaciones y cero resultados. La regla listaba `&&` y
  **nunca un `&` solo**: son operadores distintos, y el rechazo que lee el worker es un TERCER mensaje,
  distinto de los dos que el prompt sí enseña — o sea que un modelo que obedeciera «nada de `&&`» al pie de la
  letra no tenía con qué atar su error a ninguna regla. Mismo defecto que V2-412, un operador más allá. Va
  aparte y con el mensaje del guarda dentro, y con la alternativa al lado (lo lento YA es asíncrono por los
  puentes: se lanza y se recoge con `wait`) — prohibir sin alternativa es como acaban callados. Nodo 4.61
  ampliado, tres desarmes.

- **Una fila INFRA dice CUÁL (V2-423, 2026-08-28)**: las cuatro puertas que llevan a INFRA piden acciones
  OPUESTAS —arnés caído (bug del instrumento), turnos vacíos (recargar un proveedor), recall degradado
  (levantar el prewarm), juez sin nota (mirar su cadena)— y desde el tablero se veían las cuatro igual.
  Medido con el 24/7 ya corriendo: dos filas pasaron de FAIL a INFRA en una hora y reconstruir cuál de las
  cuatro ramas las movió fue **imposible** (descarté embeddings, turnos vacíos y caída del arnés una a una y
  me quedé sin respuesta): el dict de la ronda ya no existe cuando alguien lee el tablero. En un bucle que
  corre ocho horas sin que nadie lo mire, ésa es la diferencia entre «está midiendo» y «lleva toda la noche
  produciendo basura», y la segunda es peor que estar parado porque parado se nota. Ahora el motivo lleva el
  dato dentro (cuántos turnos de cuántos, qué backend) y va DELANTE del veredicto en una fila INFRA: el
  veredicto habla de un producto que esa ronda no llegó a medir, y leerlo como si sí invita justo al
  diagnóstico equivocado. **Corregido una hora después y por el propio bucle**: dos filas nuevas salieron con
  «el arnés se cayó» y no había traceback ninguno — `crashed` NO significa «se cayó», es un campo con TRES
  inquilinos (conductor fuera de papel, fuente de verdad ilegible, excepción real) y **cada uno trae ya
  escrita su frase**; la de aquella ronda decía «el conductor se salió de su papel en el turno 13». Adivinar
  un motivo teniendo el bueno delante es el mismo error que este nodo arregla, un piso más arriba. Ahora se
  imprime el que viene en el campo y el veredicto-INFRA del juez tiene su propia puerta. Nodo 10.106, cinco
  desarmes.

- **La misma búsqueda dos veces no son dos búsquedas (V2-422, 2026-08-28)**: `weekend-plan-barcelona__es`
  en el plató 24/7 hizo **56 búsquedas web, 31 consultas, 0 candidatos verificados** y dejó la hoja vacía,
  repitiendo la misma consulta sin cambiar un criterio — «eso no es diligencia, es dar vueltas» (juez). No
  había ni caché ni detección de repetidos en ningún punto del camino. **No se bloquea la repetición, se
  CONTESTA y se marca**: bloquear rompería un reintento legítimo, y devolver lo ya traído al instante corta el
  bucle igual y deja el hecho escrito (`repeated`), que es lo que convierte «dio vueltas» de impresión en
  dato. El TTL de **120 s** es la decisión entera: largo para matar un bucle apretado (56 búsquedas en nueve
  minutos), corto para que un «mira otra vez» a ritmo humano traiga mundo fresco — una caché de búsqueda que
  dure más que la paciencia de una persona sirve datos rancios justo a quien pidió lo contrario. No se cobra
  dos veces (`_meter_search` factura lo que RESPONDIÓ un proveedor), normaliza espaciado y mayúsculas, y está
  acotada a 64 entradas porque vive en el proceso del motor y no es un almacén. NO arregla POR QUÉ repite: le
  quita el coste al síntoma y lo deja medido. Nodo 4.66, cinco desarmes.

- **Un payload que falta dice lo que SÍ hay (V2-421, 2026-08-28)**: «No such file or directory:
  progreso.json» es verdad y no sirve para nada — no distingue entre escribirlo en otro directorio, con otro
  nombre, o no escribirlo, que piden acciones distintas y desde ahí se ven iguales. Medido en
  `best-plumber-same-day__es` (cerebro deepseek-v4-flash+glm-5.3): el paso murió ahí y la ronda se fue en ocho
  minutos sin entregar lo que el operador pidió TRES veces. Y lo que lo hacía peor: `widget_cli` YA listaba
  los `.json` presentes en ese mismo error y `worker_bridge` no — los dos puentes contestando distinto a la
  misma pregunta, que es exactamente la divergencia que dejó a un worker ciego ocho errores seguidos cuando un
  puente aceptaba `@fichero` y el otro no. `bridge_usage.what_is_here()`, al
  lado de `read_payload` y por su mismo motivo: **el mecanismo se comparte, el mensaje lo pone cada puente**.
  Acotado (es el stderr de un puente, no un explorador) y best-effort (un directorio ilegible no puede
  convertir un error claro en una excepción). Norma de «si tienes la respuesta, imprímela»: el puente está
  PARADO ahí dentro. NO arregla por qué el fichero no estaba — convierte un callejón en un paso recuperable y
  deja el rastro. Nodo 4.65, cuatro desarmes.

- **El denominador es lo que se le MOSTRÓ, no lo que hay en la hoja (V2-420, 2026-08-28)**:
  `delivery_completeness` prometía medir «de las filas que el sistema LE PUSO DELANTE» y dividía por toda la
  hoja. Cuando se escribió, la hoja tenía cinco filas y el prompt las llevaba las cinco — las dos
  denominaciones eran la misma y no se podía notar. `_sheet_top_rows` empuja **como mucho 5** («bounded hard,
  because this lands in a prompt, not on a screen») y una hoja puede tener treinta. Medido en
  `search-buy-used-car` (cerebro glm-5.3): hoja de 28, prompt con 5, nombró 3 → el informe publicó «retención
  masiva, 11 %» con un `missed` lleno de coches que NUNCA estuvieron en ningún prompt. La obediencia perfecta
  habría dado 18 %. Tercera vez en la misma noche que el instrumento acusa al producto. Ahora los títulos se
  leen de SUS PROPIOS PROMPTS (no del límite del motor: una constante que alguien cambia y la medición vuelve
  a mentir sola), `in_sheet` se publica aparte —«cuánto de lo que tenemos no le enseñamos» es un hallazgo
  sobre nosotros— y **al juez se le dice**, que es quien pone la nota. La captura de `live_line` sube de 400 a
  1200 caracteres: las filas viajan ahí dentro y a 400 se cortaban justo donde empiezan, con lo que la lectura
  habría salido vacía SIEMPRE, que se lee como «no se le mostró nada». Deja abierta una pregunta del operador:
  con 28 en la hoja le enseñamos el 18 % — ¿cinco filas son pocas? El número lo darán las rondas del 24/7.
  **Y estuvo INERTE cuatro horas**: con el plató ya midiendo, `shown_to_model` salía `False`
  en las seis rondas, porque las filas viajaban dentro de `live_line` y la lista de TAREAS llega sola al tope
  — el bloque empieza más allá del corte, y subir el tope solo mueve el problema al siguiente prompt largo
  (todos lo son). Devolvía vacío siempre, que se lee como «no se le mostró nada»: una ausencia en el sitio
  plausible no es una ausencia. Arreglado con un CAMPO propio (`sheet_rows`) escrito desde la línea completa
  antes de recortar; un campo no se recorta por accidente. El desarme también falló a la primera —mi fixture
  dejaba la cabecera dentro de `live_line`, así que pasaba sobre el defecto restaurado—. Nodo 10.105, ocho
  desarmes. NO tapa lo del producto: en esa ronda el modelo se inventó dos coches teniendo
  cinco reales delante, y eso es conducta.

- **Un worker MIRANDO EL MENÚ no es un worker estrellado (V2-418, 2026-08-28)**: primera ronda del plató
  24/7 (`weekend-plan-barcelona__es`, cerebro glm-5.3) archivada con dos `error_interno` de certeza «hecho» y
  un juez escribiendo «el worker falló técnicamente al extraer el precio». Lo que el worker hizo fue lanzar
  `nav_cli` y `worker_bridge` SIN subcomando: argparse contesta `usage:` y sale con **2**, así que una sonda de
  descubrimiento llega vestida de caída (las dos siguientes, con `-h`, salieron con 0 y se registraron bien).
  El instrumento acusando al producto — el único error que una herramienta de medida no puede permitirse,
  porque un fallo falso manda a alguien a arreglar algo que nunca pasó. La regla es estrecha: **el argumento
  que falta es `cmd` mismo** → nadie eligió subcomando → está leyendo la carta; un argumento mal en un
  subcomando REAL (`nav_cli click` sin ref) dice lo mismo y sale con 2 y ése SÍ es una llamada rota. Y el
  puente tiene que ser nuestro. Vive en `nucleo/workers/probes.py` (módulo propio: `session.py` está a 5
  líneas de su techo) y se aplica en UN punto, `_emit_step_result`, de donde salen `is_error`, las anomalías
  del auditor, el contador del span y lo que el juez lee. NO dice que sondear sea gratis: cuatro idas y
  venidas para leer un menú que el prompt detalla entero es conducta, y la conducta se mide — pero no como una
  caída. Nodo 4.64, tres desarmes.

- **Una función que decide fechas leía DOS relojes (V2-419, 2026-08-28)**: dos tests de
  `safe_reminder_schedule` se pusieron rojos **al pasar la medianoche**, sin que nadie tocara nada. El fixture
  congelaba `time.time()` y la guarda resolvía «hoy» con `localtime()` **sin argumento**, que va al reloj del
  sistema por debajo y no pasa por ahí. En producción los dos coinciden, así que no había defecto de producto
  — había algo peor de otra manera: **esos dos tests nunca habían medido nada**, pasaban porque el día real
  coincidía con el clavado en el test, y el día que deja de coincidir parece una regresión de la guarda.
  Arreglado con `localtime(time())`, un solo reloj y por tanto medible desde un solo sitio, más un test que
  congela MUY lejos (martes 9 mar 2027) para que una lectura del reloj del sistema caiga el día que se
  escriba y no un año después. El primer instante que elegí era miércoles —el día que nombra el encargo—, así
  que la guarda no corregía y el test habría pasado sin medir nada. Nodo 2.3.

- **El plató no para: 24/7 con guardián (V2-417, 2026-08-28)**: el supervisor YA era el motor —bucle
  infinito, de uno en uno porque hay un navegador por plató, corte por silencio (180 s) y por techo (720 s),
  no muere por una ronda, se recarga solo al cambiar su código—; lo único que no sabía es **volver a
  existir**. `supervisor_24x7.sh` levanta los platós y entra al bucle con `exec` (sin `exec`, quien vigila
  vigila a un padre muerto; y un supervisor contra puertos muertos no falla, escribe una fila INFRA por
  escenario a toda velocidad, que es peor que estar parado), y `ops/keepalive.sh` lo relevanta con candado por
  PID comprobado contra el proceso —un fichero suelto lo dejaría bloqueado para siempre tras un `kill`, y dos
  guardianes son dos rondas peleándose por la misma pestaña—. **NO es launchd y que nadie lo reintente a
  ciegas**: el repo vive bajo `~/Documents` y TCC le niega la lectura a un agente de launchd sin Acceso Total
  al Disco concedido a mano (medido: `127 · can't open input file` sobre un fichero que existe y es
  ejecutable); `crontab` topa con lo mismo. El plist queda escrito y validado en `ops/` para cuando el
  operador dé el permiso: es lo único que añade sobrevivir a un REINICIO. Seis tests sobre el shell y el
  plist, cuatro desarmes — uno no mordía porque comentar la línea dejaba el texto dentro del comentario.

- **El marcador dice con qué CEREBRO se midió cada fila (V2-415, 2026-08-27)**: una nota es una nota SOBRE
  algo. La fila ya sellaba qué JUEZ la calificó (la cadena del juez cae de proveedor y sus medias difieren en
  0,44 puntos: un «bajó de 3 a 2» puede ser solo otro medidor); un piso más abajo pesa más, porque el juez es
  el instrumento y el cerebro ES el producto. Medido: la tanda US corrió con Z.ai sin cuota, así que sus Brain
  Workers los sirvió el escalón de RELEVO (`deepseek-v4-flash`) y no el titular que la nube contrata
  (`glm-5.3`) — cinco filas de 1-2 iban al tablero indistinguibles de las medidas con el titular. Se lee del
  FLUJO, no de la config, con las dos trampas que lo rompen sin ruido: `worker_start` lo reusa el arranque del
  motor de voz (sin `model`), y una fila de relevo NO tiene `kind == "perf"` porque el `extra={"kind": …}` de
  la cadena pisa el kind al guardarse — filtrar por kind da cero relevos en una ronda llena. En el tablero `?`
  (fila anterior a esto) y `—` (ningún worker, legítimo en un caso conversacional) son distintas a propósito.
  Al juez NO se le cuenta (`judge.RAW_ONLY`, con el motivo): `search_health` sí, porque con la búsqueda muerta
  «no buscó» deja de ser un defecto, pero un relevo no cambia si narrar progreso inexistente está mal — solo
  cambia sobre QUÉ producto es la nota, y contárselo ablandaría la calificación. Nodo 10.103, cinco desarmes.

- **Que nos BLOQUEEN no es que el mundo esté vacío (V2-414, 2026-08-27)**: los dos hechos llegaban idénticos
  —`results: []`— y merecen respuestas opuestas. Medido en vivo con las consultas de los propios casos US: **4
  de 6 volvieron vacías porque DuckDuckGo servía un desafío anti-bot**, y nada lo decía. Tres capas mudas a la
  vez: (1) el bloqueo llega como **HTTP 202**, un estado de ÉXITO, así que `raise_for_status()` lo deja pasar;
  (2) el clasificador buscaba las palabras que usaríamos NOSOTROS (`captcha`, `unusual traffic`) y la página
  real dice «bots use DuckDuckGo too… Select all squares containing a duck», sin la palabra «captcha» en
  ningún sitio, así que un bloqueo duro salía como `error`; (3) la fila `search` llevaba `n: 0` y la consulta y
  **ni una palabra del porqué**, así que `search_health` —que existe justo para cazar este confundido— rascaba
  una prosa inexistente y declaraba sana una capa muerta. `browser_search._looks_blocked` ya hacía esto para
  Google; el escalón de DDG, el único que hay en un self-host sin navegador, no tenía nada. Ahora el motivo
  viaja **encima del resultado** (`failure: {kind, detail}`) y el arnés lee **el campo primero**, la prosa
  después (la vía vieja se conserva: el `WebSearch` del worker sí escribe su motivo en palabras). Comprobado contra la
  evidencia antes de atribuirle nada: las rojas de la tanda US de anoche **NO** son esto — en el plató Google
  va primero y funcionó (el juez de `search-buy-used-car__us` anota «la búsqueda web, que funcionaba, 2
  consultas», con 21 candidatos en la hoja); aquel fallo era de ENTREGA. El 4-de-6 se midió en un proceso sin
  navegador, que es la forma de un self-host sin Chromium — para quien esto importa de verdad. Nodo 4.63, cinco desarmes —uno de ellos NO mordía hasta añadir dos tests de la fontanería real:
  todos los demás inyectaban el fallo por arriba y se podía borrar el reconocimiento entero con 8 verdes.
  **No arregla que nos bloqueen**: lo hace visible, no lo evita.

- **Una recarga es INVISIBLE desde el motor, así que se vuelve a probar (V2-413, 2026-08-27)**: seis horas
  mudo con un proveedor sano una fila más arriba. Medido: el `402 Insufficient Balance` de las 18:55 castigó
  los dos escalones directos **6 h**, el operador recargó a las 19:40, y el motor no tenía forma de aprender
  que había entrado dinero — siguió mandándolo todo al relevo; a las 22:07 el relevo empezó a dar timeout y el
  cerebro se quedó sin voz. `_DEPLETED_COOLDOWN_S` pasa a **20 min** en las DOS cadenas (cerebros y escalones
  del CLI, copias separadas a propósito). El techo viejo acertaba sobre el mundo —un saldo no se repone solo—
  y se equivocaba sobre nosotros: la alerta existe para que alguien recargue, así que el momento interesante
  es el de DESPUÉS. **La distinción de V2-243 no se toca**: una CUOTA dice «espera hasta X» y se le cree, un
  SALDO no tiene fecha; hay test para que acortar el segundo no acorte el primero. Nodo 4.62; dos tests de las
  6 h reescritos con su motivo. Abierto: no hay señal de «ya he recargado» (botón en el master, o apagar la
  alerta al primer éxito).
- **La búsqueda mira desde donde vive la persona (V2-411, 2026-08-27)**: doce hoteles REALES de Nueva Orleans
  entregados en EUROS a un cliente de San Francisco con presupuesto en dólares. Se lee como fallo de filtrado
  y es de GEOGRAFÍA: un sitio decide moneda y mercado por el locale del navegador y por `Accept-Language`, no
  por las palabras de la consulta, y las dos estaban clavadas a España. Lo peor era que estaba A MEDIAS — el
  catálogo de sitios ya resolvía por locale, así que mandábamos al worker a los sitios americanos correctos y
  se los preguntábamos en español. Ahora siguen al idioma del motor, **por llamada** (el operador cambia de
  idioma con el motor vivo), con las env vars como escotilla y el español como fail-open. Nodo 4.60.
- **El prompt del worker no enseña lo que nuestro guarda bloquea (V2-412, 2026-08-27)**: las cuatro rondas de
  la primera tanda en inglés traen los mismos errores internos («Contains simple_expansion», «brace with
  quote») y en una se llevaron la ronda entera — 3 navegaciones, 10 búsquedas, CERO productos. La causa era
  nuestra: `worker_bridge act` es por donde el worker PIDE una búsqueda y se le enseñaba con el JSON pegado en
  la línea, justo lo que la puerta rechaza; el rodeo por `@fichero` se había añadido ese mismo día y nadie
  tocó la frase que enseñaba lo contrario. Ahora `act` se enseña en dos pasos como la hoja, y las reglas del
  cajón nombran los dos rechazos **con las palabras del propio guarda** — una regla que no se puede conectar
  con el error recibido no se aplica. Se sigue prohibiendo la causa, no solo nombrando el síntoma. Nodo 4.61.

- **El dedup decía que NO y no decía POR QUÉ (V2-507, 2026-08-30)**: solo el ACIERTO dejaba fila
  (`task/dedup`), así que «no casó con ninguna tarea viva» y «no había ninguna tarea viva contra la que
  casar» se leían IGUAL desde fuera — y piden arreglos OPUESTOS: una vara rota, o una sesión que murió al
  nacer. Medido en `cheapest-monitor__us` (ronda 20260830-114302): dos hojas abiertas (`results::101c0f-1`
  a las 11:34:03, `-2` a las 11:34:22), **UN solo worker arrancado** (los 209 eventos `task` de la ventana
  llevan id=2; no hay un `task/start` de id=1 en ninguna parte) y **ningún `task/dedup`**. Releyendo el log
  de eventos del sandbox seguía sin poder decidirse cuál de las dos había pasado.
  - **El arnés había tapado el hueco con un número que no podía falsar nada**: contención 1,0 entre los dos
    goals que ÉL vio, que es un par DISTINTO del que compara el motor (la petición entrante contra el goal
    truncado a 200 de una sesión viva). **Una acusación que no se puede falsar es peor que el defecto que
    nombra** — en una iteración de 24 h, cada ronda podía culpar al dedup gratis.
  - `nucleo/dedup.py::scan` devuelve **veredicto + evidencia** (`live` · `best` · `against` · `bar` · `by`) y
    el caso negativo emite `task/dedup_miss`. **`live` es el campo que decide**: 0 significa que no había
    nadie contra quien casar, y de eso no se puede culpar a ninguna vara.
  - **La evidencia la produce el bucle que DECIDE, nunca se recalcula al lado** — una segunda copia deriva y
    entonces la fila reporta un número que el código no usó, que es la confusión que esto quita. Por lo mismo
    un acierto por MISMO WIDGET deja de archivarse como `by: "containment"`, una cuenta que ese camino no
    hace.
  - **Y la misma confusión una capa más adentro**: `except Exception: dup = ""` hacía que un juez que
    REVENTÓ se leyera igual que uno que contestó «son distintos». Se registra (`model: "error:<Tipo>"`); el
    fail-open **no se toca** — un juez inalcanzable no puede bloquear un encargo.
  - ⚠️ **Un defecto que el arreglo se encontró a sí mismo**: una contención de exactamente `0.0` dejaba
    `against` vacío, o sea la fila decía «no casé con nadie» sobre una sesión que acababa de comparar. **El
    cero es un resultado, no una ausencia.**
  - El trinquete de arquitectura cobró de paso (`dispatch.py` 1922 > 1865): la regla salió entera a
    `nucleo/dedup.py`, PURA sobre los encargos vivos que se le pasan — mismo precedente que `sheets.py`,
    `errand_kind.py` y `engine_url.py`. La guarda de deriva de `test_one_yardstick_of_similarity.py` se
    **repuntó a `dedup.scan`**: dejada sobre el envoltorio habría seguido pasando mientras la aritmética se
    iba a otro módulo, y **una guarda que no guarda nada se lee como cobertura**.
  - Nodo 2.5, 12 casos, desarme en cinco direcciones — y el que importa es el CONTRARIO: sin él, «emitir
    siempre» satisfaría todos los demás.
  - **Lo que NO arregla**: la escalada 1 abrió hoja en pantalla y su worker nunca arrancó — ni un evento.
    Esto es el instrumento que lo nombrará la próxima vez, no el arreglo. **Sin verificar en vivo.**

- **Un encargo CONFIRMADO conserva su hoja (V2-508, 2026-08-30)**: la fila `dedup_miss` de V2-507 zanjó en su
  primera ronda lo que eran dos hipótesis. `live: 0` en las DOS escaladas de `cheapest-monitor__us`, o sea que
  la vara nunca tuvo con qué comparar y la acusación apuntaba al fichero equivocado. Lo que pasa es una cadena:
  `run_listener` abre la hoja **al encargar** (V2-227, a propósito) y registra la sesión → `_run_session` llega
  al gate de irreversibles → `_SESSIONS.pop(key)`, **la hoja se queda en pantalla sin nadie** → el operador
  dice que sí → `resolve_confirm` relanza el MISMO texto por la puerta normal **sin hoja en su contexto**, así
  que abre una caja SEGUNDA al lado. Medido: `results::101c0f-1` abierta a las 11:34:03 y jamás escrita,
  `results::101c0f-2` 19 s después con las 200+ escrituras. **Un solo defecto explica la hoja fantasma Y el
  dedup ciego.**
  - **No hacía falta mecanismo nuevo**: `_sheet_open` YA hereda la hoja del predecesor para el relevo de
    proveedor (V2-238) y el handoff de contexto (V2-117) — «*a relay continues the errand, so it keeps writing
    where the operator is already looking*». Un confirmado es la TERCERA continuación. Solo había que hacerla
    viajar con la pregunta aparcada.
  - Un encargo **sin** hoja no lleva `""` sino nada: heredar una caja que no existe dejaría al relanzamiento
    sin abrir la suya.
  - **Y la RAÍZ está aislada y NO se toca aquí**: `danger.is_dangerous("Research … available for purchase …")`
    → **True**, por la palabra `purchase` suelta en `_DANGER_RE`. **El operador nunca la escribió** — dijo «my
    work monitor is dying and I need a new one»; la escribió NUESTRO compositor de brief, así que el motor se
    dispara su propia puerta de confirmación con un texto que acaba de redactar él. Es **V2-509** y quiere su
    medición: aquí un falso negativo cuesta dinero y un falso positivo cuesta una pregunta, así que el gate
    falla del lado seguro y no se afloja a la ligera. La forma ya tiene precedente en el mismo fichero —
    V2-128 arregló «recuérdame PAGAR la factura» preguntando cuál es la ORDEN.
  - Nodo 2.5, 7 casos, desarme en cuatro direcciones — dos de ellas en el sentido CONTRARIO (`fresh=True`
    borraría la hoja heredada; y un encargo que llega con la SUYA sellada no es una continuación, que es la
    regla de V2-259 y tenía que sobrevivir intacta).
  - **Sigue abierto**: una confirmación contestada que NO, o caducada, deja su hoja vacía en pantalla.

- **Lo que vuelve de una búsqueda es una PISTA, y la NOTA seguía ordenando entregarla (V2-510, 2026-08-30)**:
  medido en `cheapest-monitor__us` (20260830-125532, ya sin la hoja doble de V2-508 encima) — al cerebro se le
  ofrecieron titulares de comparativa («The 6 Best Budget And Cheap Monitors of 2026 - RTINGS.com»), el cuerpo
  de un **403** y su propia prosa sobre una página que solo tenía navegación, mientras los ocho monitores REALES
  (Dell S2722QC, LG 27UP850N-W…) esperaban en la hoja. Entregó un titular en el turno 4. **No desobedecía**: se
  le dio un artículo y se le ordenó entregarlo.
  - **La lección ya estaba aprendida a MEDIAS**: la fila de la HOJA marca desde el 2026-08-27 el ORIGEN de lo
    que viene de una búsqueda (`findings.hand_search_rows`, tras contar 52 «candidatos con nombre» que eran
    páginas) y la NOTA no se enteró — y la nota es el canal que mueve al cerebro (V2-222: nota empujada **3/3** contra línea
    de prompt **0/13**). O sea que el único camino que funciona era el que seguía ordenando lo contrario.
  - **Subir el corte no arregla nada** y conviene decirlo porque es el gesto obvio: son los PRIMEROS DEL DOM,
    no los relevantes (V2-234), y V2-479 ya subió el otro lector a 12.
  - La nota dice ahora QUÉ ES antes de ordenar nada: una página no es un candidato · si trae la cosa concreta
    con nombre y precio, se da como resultado · si es un artículo, un buscador o un error, se cuenta como por
    dónde se va a mirar y **NUNCA se ofrece como una opción para elegir**. Sigue siendo UNA instrucción con la
    bifurcación dentro (V2-226).
  - ⚠️ **Un desarme mío salió VERDE y lo que estaba mal era la mutación**: la frase se parte entre dos líneas
    del f-string, así que el literal no casó y no se mutó nada. Ahora cada mutación **afirma que se aplicó**
    antes de correr la suite — un desarme verde es una mutación mal hecha hasta que se demuestre lo contrario.
  - Nodo 2.5, 7 casos, desarme en cuatro direcciones — y la que decide es la CONTRARIA: prohibir entregar
    siempre se tragaría el caso para el que nació V2-236 (datos limpios muriéndose dentro de workers caídos).
  - **Sigue abierto**: el cuerpo de un error y la narración del modelo viajan igual como hallazgos
    (`session.py::_maybe_hand_web` empuja todo paso web que no sea `is_error`, y una tool que devuelve un
    rechazo con éxito no lo es). Distinguir un rechazo de un hallazgo sin acabar en una lista de frases de
    error en inglés quiere su propia medición.

- **Lo que CUENTA lo que pasó no es lo que TRAE algo (V2-511, 2026-08-30)**: `_maybe_hand_web` empujaba el
  texto CRUDO de todo paso web que no fuera `is_error` — **y una tool que devuelve un rechazo CON ÉXITO no lo
  es**. Medido en `cheapest-monitor__us` (20260830-130649) con la hoja **VACÍA** (`in_sheet: 0`,
  `shown_to_model: false`) y **17 notas** ofrecidas igual: 7 errores HTTP y negativas del propio worker, **11
  el envoltorio del buscador del CLI** («Web search results for query: … Links: [{"title":…»), **0 fichas**.
  El juez llevaba cuatro rondas archivando «presenta candidatos irrelevantes» [alta] y el agente no elegía
  mal: le dábamos eso.
  - **DOS cortes ESTRUCTURALES, no una lista de frases**: un ENVOLTORIO se delata por su forma (un array JSON
    de enlaces tras dos puntos), no por su prosa; y un hallazgo trae un DATO DURO —enlace o importe—, que es
    lo que una narración sobre la página nunca tiene. Lo pedido era «lo que empiece por *The server
    returned*», y eso es la carrera que V2-364 midió como imposible de ganar, además de dejar fuera a
    cualquier CLI que redacte su cabecera de otra forma.
  - **El ORDEN importa y tiene test**: un envoltorio está LLENO de enlaces, así que mirar primero si hay URL
    dejaría pasar los once.
  - **Coste aceptado y dicho**: un hallazgo cuyo único dato accionable sea un TELÉFONO (V2-240) no pasa por
    esta puerta. No se ensancha a propósito — «nueve a catorce dígitos» sobre prosa libre es la trampa que
    pagó V2-321, y la hoja conserva el teléfono por su camino.
  - Nodo 2.5, 16 casos, desarme en cuatro direcciones — la que decide es la CONTRARIA (exigir enlace **y**
    importe): un filtro que lo tira todo pasa todos los casos de «esto es basura» y deshace V2-236 en
    silencio.
  - ⚠️ **Segundo desarme verde en dos iniciativas, y otra vez el fallo era del TEST**: emparejaba dos cadenas
    CORTAS, cuya firma es la cadena entera, así que quemar una no podía tapar a la otra. `_HANDED` indexa por
    `body[:200]`, o sea que el peligro solo existe con textos largos que comparten prefijo — una página leída
    dos veces, estéril y luego llena. Reescrito con ese caso.
  - **No añade señal, quita ruido**: si la vuelta siguiente sale con `offered` casi a cero y la hoja SIGUE
    vacía, lo que falta está aguas arriba —el worker no extrae— y es otro fichero.

- **The gate reads the ORDER, not the words (V2-509, 2026-08-30)**: the ROOT of the V2-507/V2-508 chain. The
  confirm-gate judges the TEXT of the escalated request, **and that text is written by the BRAIN**: the operator
  said "my work monitor is dying and I need a new one" and our brief composer wrote "…available for purchase in
  San Francisco". `purchase` sits bare in `_DANGER_RE`, so **the engine fired its own confirmation gate on a
  word it had just written itself** — and with it the parked session, the dropped record, the ghost sheet, the
  blind dedup, and a question ("do I really pay for it?") over an errand that only asked to LOOK.
  - **MIRROR form of V2-128**, fixed the same way: by asking which clause is the ORDER. There "remind me to PAY
    the bill" commands REMINDING; here "research monitors FOR SALE" commands RESEARCHING. **Not one detection
    pattern was touched** — a test guards that, because deleting a word from a safety pattern is how a guardrail
    becomes a hole.
  - **The CONJUNCTION is what makes it safe** and neither half works alone, both under test: the head verb alone
    would let "find the IBAN and **PAY** the bill" through; the adjunct alone would kill "go to the store **TO
    BUY** milk". It requires a lookup head **and** purchase said only as an adjunct — a real purchase order is
    never phrased "to buy".
  - **The interrogative form had to be covered or the fix missed its own case**: the measured brief ends
    "…y dime **cuál comprar**", and the order there is *dime* (tell me).
  - **`moves_money` learned it too**: it is documented as a subset of `is_dangerous` and trims the same way, for
    the same reason — a subset that fires where its superset would not means asking a money confirmation over an
    errand the gate already let through. The invariant sat in its docstring and nothing checked it.
  - Node 2.5, 32 cases, disarm verified in four directions (4/1/1/4).
  - **Still open, and it is not code**: whether the gate should judge the OPERATOR's words or the brief the
    engine composes. This makes the brief harmless for the lookup case, which is the measured one; it does not
    answer the general question.

- **A SHIPPED widget is forked, never edited in place — and never deleted from disk (V2-515, 2026-08-31)**:
  the operator's design decision for system widgets, four phases, each with its verified disarm.
  - **The ground**: `paths.generated_root()` never collapses onto the repo again — self-host gets
    `widgets/_user/` (gitignored); a mounted workspace keeps `<workspace>/widgets`. The collapse was why a
    lab's delete could rmtree `widgets/clock` and `widgets/musica` out of the git tree (2026-08-30), and why
    a fork had nowhere to live.
  - **Imports follow the catalog**: `roots()` keeps `widgets.__path__` in step, so `import widgets.<id>.data`
    resolves through the same two roots in the same order — before, every widget outside the repo folder
    (every cloud-generated one) ran with silently dead python hooks. `paths.forget_modules(id)` evicts on
    every transition that moves which folder owns the id; `importlib.reload` does NOT re-resolve.
  - **Fork-on-modify**: a modify whose target is repo source (`paths.is_repo_source` — the FOLDER is the
    criterion, never the manifest: a harness run once relabelled 15 shipped manifests `origin:"user"`) copies
    it into the generated root and edits the COPY; the fork shadows the original everywhere while the shipped
    folder keeps receiving engine updates untouched. A failed FIRST edit discards the fork. The generator
    prompts now receive the resolved target folder — they hardcoded `widgets/<id>/`, which in the cloud
    landed every generated widget in the ephemeral checkout instead of the Volume.
  - **Delete hides**: engine source never leaves the disk. The id goes to
    `widgets/_data/_system/hidden.json` (per-tenant; filtered inside the catalog signature, so hiding
    invalidates the cache like an mtime change). Deleting a fork removes the fork's files AND hides the
    shipped counterpart — "delete" means GONE, never "back to stock".
  - **Restore** (`lifecycle.restore_widget`): rmtree the fork + unhide → always the NEWEST shipped version.
    Data survives on purpose (it lives in `widgets/_data/<id>/`, outside the code folder). Three doors:
    the `restore_widget` tool (a `restore` confirmation class — discarding the fork is destructive for the
    OPERATOR's work; resolves via `lifecycle.restorable_id`, because a hidden widget is out of the catalog
    and identify cannot see it), the card's Yes button (the confirm endpoint dispatches the new class — the
    2026-08-15 rule: a class that endpoint does not know consumes the pending and executes nothing), and
    `POST /widgets/{wid}/restore` keyed on the registry's new `forked` flag. Workers are denied the tool.
  - Node 4.1 (the three `test_a_system_widget…`/`test_a_shipped_widget…`/`test_restore…` files) + the
    rewritten contract in `test_paths_workspace.py`. Tool catalog ceiling 21200→21800 (one genuinely new
    tool, description pre-compacted).
  - **Open (operator's call, not code)**: seven personal widgets are still TRACKED in the public repo
    (`inversiones`, `meteo-soria`, `meteo-tarragona-grafico`, `futbol-champions`, `juego-serpiente-snake`,
    `personalizado-reproduzca-video`, `temporizador-pomodoro-ayudar`) — move them out under `_user/` (repo
    privacy procedure applies) or bless them in `registry._BUILTINS` as shipped examples. And the frontend
    still lacks the visual "restore" affordance the `forked` flag exists for.
  - RESOLVED 2026-08-31 (operator): the seven personal widgets were **deleted everywhere** (repo, disk,
    dead `_data`) — commit 609f689; history rewrite not requested. The restore affordance shipped as
    V2-518 (below).

- **A catalog costs nothing until it is CONNECTED (V2-526, 2026-08-31 — DESIGN, no code yet)**: before any new
  connector is written, the shelf. Measured first: the messaging `PROTOCOL` block is **1656 chars (~473 tokens)
  for THREE connectors**, re-injected every turn — thirty more written that way would put 4-5k tokens on turns
  that touch none of them. The rule, and it is a hard one: **anything merely LISTED contributes 0 prompt bytes,
  0 tool entries and 0 startup imports.** Only what is connected, or what a lookup just selected for this task,
  costs anything. Consequences worth knowing before touching it:
  - **Declaration is DATA, implementation is CODE, in separate files** (`connectors/catalog/*.json`).
    `registry.py` imports a module per family inside `descriptors()`; fine for six, a hundred imports for a
    hundred — the startup clause is the one that gets forgotten.
  - **Discovery uses NO language model.** A lexical index over the manifests' `capabilities` returns **at most
    five** candidates, ranked connected > frequent > rest, and only then does the brain choose. Choosing 1 of 5
    is a decision a model makes well; 1 of 10.000 is one it makes badly. What gets used is promoted to `state`
    as a favourite — the same *open > recent > catalog* layering as V2-078, one level out.
  - **MCP is a TRANSPORT, not a category** — it sits next to the Node bridge, in a `transport` field. What a
    thing IS depends on who starts it and how long it lasts: **interface** (the other side starts it, a session,
    identity+permissions — voice, chat, mobile shell, MeshKore cluster) · **connector** (the operator, once,
    until revoked, their credential) · **supplier** (the engine, per task, no credential — mesh agents, the
    Oracle, a public MCP server). So an MCP bound to the operator's account is a connector; a public one picked
    per task is a supplier and belongs on the shelf `nucleo/mesh_agents.py` already hires from — **one lookup
    path, not two**, or it inherits exactly the risk V2-169 exists to track.
  - **Rendering is decided and costs no new widget**: `ChatWall` gets a fifth tab (it already has four, the
    active one lives in `store.chatTab`, and the orb's ⏰ already opens it on a chosen tab) for browsing and
    requesting; `ConfigPanel`'s existing "conectores" tab (V2-083) keeps forms, QR and OAuth. That split is
    **V2-520's rule one level up — voice carries INTENT only, never a credential**, and it is already pinned by
    a test. Both surfaces read the same manifests so they cannot drift.
  - The ratchet that IS the initiative: build the prompt with the real catalog and again with N synthetic
    `planned` manifests → **byte-identical**. It must fail loudly the first time someone helpfully adds "just a
    short list of names".

- **Stopping is DISCARDING — abandon_work (V2-528, 2026-08-31; supersedes the 2026-07-10 freeze-to-resume
  sequence)**: after his reset, the fresh session's FIRST greeting said «sigo con lo del digestólogo» with zero
  workers alive. Four doors, all measured: `reset_all` froze the pending escalation into `trabajo_interrumpido`
  BY DESIGN; durable `task.*` slots survived; the [RESET] short-term card said the work «queda CONGELADO» — read
  by a model, an invitation to resume; and the window seeding (`memory.recent_window`) re-imported the wiped
  conversation verbatim. The operator's ruling: «si he hecho un puto reset es para que me lo dejes limpio … si
  en la memoria de corto plazo o en el estado estaba marcado que estábamos haciendo una tarea, eso también se
  tiene que limpiar».
  - **`reset.abandon_work(source)`** — the shared core (Reset button AND the voice order «para todo lo que
    estamos haciendo y quédate tranquilo», via `stop_worker('todo')` → `abandon_work_soon`, off the hot path):
    kills navegador/workers/escalations/queued notes, sets `trabajo_interrumpido={}` ALWAYS, wipes `task.*`
    slots (`memory.clear_slot_prefix`), and leaves an instruction-shaped record (V2-214): nothing pending, do
    not resume, do not claim to continue. WHAT was killed rides in the return → the RESET observability event
    (archived with the session) — forensics move out of the memory the next session reads.
  - **Only the reset** additionally blanks the ledger, forgets the rehydration trace, blanks widgets, and
    invalidates the CONVERSATION buffer (`memory.clear_conversation`, soft) — «el chat se borra» includes the
    SEED, or the wiped conversation walks back in through `recent_window`. The voice order keeps chat, session
    and Histórico (what it just cancelled must be visible there as `cancelled`).
  - **It discards WORK, never memory**: profile, facts, ingested messages, the agenda — untouched, held by
    tests. `clear_slot_prefix` escapes LIKE wildcards (`task.` must not match `taskX.`).

- **A `[SISTEMA]` note is never the errand: the SECOND door, and a question is not a promise (V2-534,
  2026-09-01)**: after a Reset the operator asked for catamaran prices and got two browsers — the second sheet
  titled **«Cita en Valls»**, a city name from a medical errand of weeks earlier, carried in by a late recall's
  note. Three faults lined up, each measured before touching anything: (1) V2-530's fix converted ONE backstop
  block and left the V2-049 forced escalation reading the glued turn — **and the source guard written that day
  only watched the block that had been fixed**. `looks_like_web_task(glued)` is True and
  `looks_like_web_task(operator's words)` is False, so the note IS the trigger. Same door, second handle: the
  fourth time this repo pays *el fallo no fue la regla, fue tenerla repetida*. (2) `strip_system_notes` — the
  single door every escalation passes through — skipped only the note's FIRST line, and the late-recall note
  announces itself on line one and then LISTS what it recovered, so its body survived **having lost the
  `[SISTEMA]` marker that would let anyone downstream recognise it**: worse than not stripping at all. A note is
  a BLOCK now, bounded by the blank line the gluing inserts, and `brain_notes.push` collapses blank lines inside
  a note so that boundary means one thing. (3) The reply that fired it — «¿Los precios de qué, Ricardo? … y te
  lo miro» — is the agent asking for the datum it needs, which is correct behaviour.
  - **The size of (3), measured over every firing of that gate in the operator's sessions (2026-08-17 →
    2026-09-01): ten firings — THREE clarifying questions, FOUR negations or time adverbs («ahora mismo NO
    tengo ninguna tarea corriendo»), ~three real promises. The backstop has produced exactly ONE forced
    escalation in fifteen days, and it is the ghost above.** It is not deleted: V2-049 exists for a measured
    failure (six minutes of silence after «me pongo con ello»). What was wrong is the gate.
  - **The accent is the signal, and that is why the guard is NOT in `router_guards.py`**: that module's header
    promises accent-stripped input, and stripped, «¿te aviso cuando lo tenga?» becomes a request for
    information. `nucleo/flash/clarifying.py`, re-exported so `router.asks_for_missing_detail` keeps working,
    wired into BOTH promise gates and the probe mirror.
  - **Nothing was added to any detection pattern** — V2-095 measured what hand-tuning those lists costs.
  - The ratchet asked for modules, not taller ceilings, and was right twice: `promise_backstop.py` (nucleo.py
    3524 → **3475**) and `clarifying.py` (router_guards 1396 → **1361**). The forced escalation is now DRIVEN by
    its tests instead of grepped — a source scan cannot tell a live call from a mention of itself, and V2-530's
    own disarm came back green for exactly that reason. Node 3.15, 25 cases, **seven** disarms, including the
    call site itself: a signature that stopped matching would raise at the END of every voice turn, after the
    reply streamed.
  - **Open**: nothing stops a THIRD handle — the guard lists the seams by name, so a new one inherits nothing.
    What would close it is stripping the notes before the turn text is bound, so a glued turn is not reachable
    from the backstops at all. (The four negation false positives were closed the same day, see below.)

- **A NEGATED clause is not a promise (V2-534 follow-up, 2026-09-01)**: closes that initiative's open item #1.
  Four of the promise gate's ten measured firings were «ahora mismo NO tengo ninguna tarea corriendo» and
  siblings — a status REPORT, read as a commitment because the time adverb matched and the negation next to it
  was ignored. The rule is STRUCTURAL, never a phrase list (V2-095 measured what hand-tuning those lists
  costs): a negator (`no|ni|tampoco|nunca|jamas|ningun*`) inside the SAME clause as the matched span un-promises
  it, clause-bounded in BOTH directions — «No, ahora mismo lo miro» still promises (the «no» answers the
  PREVIOUS clause) and «me pongo con ello, no te preocupes» is not un-promised by its neighbour. `nada` is
  deliberately NOT a negator: «en nada te lo miro» is a promise, and losing one is the expensive direction (six
  measured minutes of silence, V2-049). The clause arithmetic lives ONCE (`router_guards.clause_negated`/
  `unnegated_match`) and BOTH promise gates read it — `promises_action` and `promise_backstop.committed` — because
  two copies of this decision is how the last one drifted (V2-252). Tests in
  `test_promise_backstop_window.py`; disarm verified on both halves (4 red / 1 red). Spanish-only like the
  regexes it guards; an EN promise vocabulary would bring its own negators with it.

- **STABLE PREFIX FIRST — the prompt's block order is what the provider's cache can see (V2-536, 2026-09-01)**:
  `build_flash_system` used to assemble lang lock → shared STATE (which embeds the synthesized recent
  conversation, changing EVERY turn) → recall → directive → **resources (the ~73% of the system chars that does
  NOT change)** → live state. So the prefix cache broke within the first few hundred chars and re-prefilled
  ~10k tokens per turn — `prompt_cache_hit_tokens` measured at 6.1%, consecutive turns sharing only 18.9-45.8%
  of their prefix (V2-533), the same diagnosis the independent voice audit reached. Order now: lang lock +
  resources (STABLE) → state/recent/recall/directive (per-turn) → live state (LAST — the forensic capture and
  several live_blocks faces say so in writing). Measured with the REAL blocks: shared prefix between
  consecutive turns **16.8% → 97.1%**. The input side dominates this brain 14:1 and DeepSeek bills cache-hit
  input at a fraction of miss, so this is both the latency and the cost lever — sitting in a concatenation.
  - **Gated by the nodo 2.13 bench the SAME day** (V2-097 rule: routing changes do not ship if the bench
    drops), 3 rounds x 14 cases each side on the production titular (`deepseek-v4-pro` direct): BEFORE
    **38/42, 1 grave**, p50 1804 ms → AFTER **41/42, 0 graves**, p50 1883 ms. It did not drop; it improved —
    the model routes BETTER with the state and the request adjacent at the end.
  - The only cross-block reference in the prompt text («…si lo ves en tus TAREAS DE FONDO de más abajo»,
    inside the resources layer) stays true: live state still sits below resources.
  - **The forensic capture came out AHEAD**: the head 6000 now holds the stable layer and the tail 7000 covers
    the ENTIRE volatile region (state+recall+live ≈ 4.4k chars at the end) — V2-255's property (the artifact
    contains the part being checked) is now satisfied structurally. Its two geometry tests were REWRITTEN
    keeping what they protected (`test_the_artifact_shows_the_memory_it_was_given.py`): the margin ratchet now
    measures distance from the TAIL cut, and the position-risk test states where the risk lives now (a huge
    LIVE block after the recall), instead of demanding the old harm.
  - Order pinned by `test_prompt.py::test_the_stable_resources_layer_precedes_every_per_turn_block` with the
    measurement in its docstring; disarm verified (reverting the concatenation → red).
  - **Open**: the live `cache_hit_frac` series (V2-533's verdict label) is the proof; 97.1% is the ceiling,
    not the claim. `_flash_layer` still varies with open/recent widgets and the `named` selection —
    event-driven cache misses, accepted.

- **The MURAL — placement that dodges the chat, the widget RAIL, and auto-arrange (V2-537, 2026-09-01)**:
  the operator, with his screenshot in front of him: a new widget opened UNDER the floating chat and «el
  usuario no sabría que está ahí». Measured first: `Desktop._place()` already scanned for free space and
  `_bringFront()` already put a new card on top — what was broken was the OBSTACLE LIST (cards + camera +
  orb, nothing else), while the chat wall sits at z 9001, ABOVE the cards' 8000 cap by design, so the scan
  happily placed underneath it. Now `#chatwall.open`, `.cronpanel` and the rail itself are obstacles, and a
  MINIMIZED card is not (an invisible hole is not an obstacle).
  - **Minimize is a first-class state** (`.hb-minned` + `minimize/reveal/minimizeAll/revealAll`): open but
    without pixels — the card stays in `wins` and in the brain's open set ON PURPOSE (an OS-minimized window
    is still open; its data lives, `widget_data` still works), and the flag persists in the layout.
  - **The widget RAIL** (`components/WidgetRail.js`, system surface `wrail`, name:null like the top bar): a
    thin fixed bar on the left, z 9002 — above the chat, because the rule the operator set is that nothing on
    the canvas may be fully hidden without a visible trace. One chip per open card with taskbar semantics
    (minimized→reveal · buried→to front · already on top→minimize), ▦ auto-arrange (V2-464's `arrange()`,
    which now REVEALS minimized cards first and respects the rail's edge) and ⊟/⊞ minimize/show all. Only
    visible with ≥1 card; repaints on the `hb:canvas-changed` event the Desktop fires from its persistence
    chokepoints — no polling, no import cycle. Generic taskbar concept, own glyphs — no OS trade dress.
  - Import versions bumped (`desktop.js?v=4`, `system-surfaces.js?v=2`) — V2-087's lesson both ways.
  - **Node 4.92 RENDERS it** (`tests/browser/e2e/widgets/render_mural.py`, self-contained preview + fake
    widget backend by interception, 15 checks including the exact incident). Disarms verified in three
    directions — ⚠️ and two early disarms came back «green» as a DOUBLE lie: a mutation that commented half a
    line crashed `_obstacles` while a `grep -c` swallowed the traceback (a disarm's mutation is ASSERTED and
    its output read whole), and the fake card was too short to touch the chat even when placed on top of it
    (it now stands 300px tall, like the incident's).
  - **Open**: the rail is not voice-addressable in v1; the floating chat can visually overlap the rail (the
    rail wins by z); the mobile shell needs none of this (deck + pips, V2-474).

- **The rail is DOCKED, and a card gets the size its manifest declares (V2-538, 2026-09-01)**: the operator's
  next instruction on the mural — «que siempre exista por encima de todos… que se pueda comprimir a la
  izquierda y quede un borde… los iconos colocados de arriba a abajo. La barra no debe ser solapada por los
  widgets; los widgets tienen menos espacio horizontal disponible si la barra está abierta». So the rail stops
  floating: it is a full-height fixed column that OWNS the left edge (`Desktop.minX()` clamps placement, drag,
  resize, maximize and arrange; `hb:rail-resized` shoves any card out from under it when it unfolds), folds to
  a 12px clickable border, and the fold survives a reload. Chips stack top-to-bottom and scroll on their own.
  - **A rail in `_obstacles` is NOT the same as a reserved edge**, and the disarm is what proved it: with
    `minX()` neutered every placement check stayed green (the obstacle scan already dodged the bar) and the two
    that went red were MAXIMIZE and the unfold clamp. The first version of the maximize check could not
    discriminate either — a chat docked left pushes every layout past the rail on its own, so the chat has to
    be CLOSED for that measurement to mean anything.
  - **Two silent faults in the same seam, one root.** An instance id (`results::<errand>`) SKIPPED `_resolve`,
    so if the session's first card was an instance — which is the normal case mid-errand, restored on reload —
    `_meta` was never loaded and everything reading it no-opped without a word: no preferred size (the sheet
    grew line by line as the worker streamed text into it, which is what the operator saw), no live title (the
    header said «Resultados» while the sheet repeated the task below it), no transient check. And
    `_applyPreferred` was all-or-nothing, so a card restored with a saved WIDTH and an empty height — the shape
    of every card saved before sizes were persisted — kept auto height forever. The operator's own size still
    wins, now dimension by dimension.
  - Node 4.92 grew both halves and four disarms (2/2/1/2). ⚠️ Two source guards of node 4.13 broke by FORM, not
    behaviour: `_railClamp` calls `_persist()` above `_layout()`, so a guard slicing `src[index("_layout()") :
    index("_persist()")]` silently came back EMPTY and asserted over nothing. **A guard that measures a text
    range has to anchor on the range**, not on the next thing that happens to follow it.

- **A sheet is for RESULTS, and an ITEM is a real candidate (V2-538, 2026-09-01)**: the operator with the
  catamaran sheet in front of him — «hay una barra arriba con el botón de mover, luego el título sale en el
  medio, debajo sale otro título que es el real, después sale una línea que no necesito para nada donde pone el
  usuario, la sesión y copiar, y después salen los tabuladores». Four bands of chrome before a single result.
  - The identity strip is not deleted — auditing a session by handing its ids to a code agent is real work —
    it moves to the BOTTOM OF THE SUMMARY TAB, which is where auditing lives. The header is STICKY, so every
    pixel it holds is taken from results for the whole scroll.
  - **And the list itself was wrong, which is the expensive half.** That sheet's first cards were «Catamaranes
    de segunda mano | Milanuncios» with its SEO blurb, a DEALER's name where a boat should be, and a boat 4×
    over the stated budget. The worker was dumping search snippets as candidates. The rule is now stated where
    the funnel is taught (`research_prompts`, BEFORE the block that invites an early `present` — which is where
    the junk entered) and in the sheet's own `worker_guide`: an item is ONE concrete candidate with its own
    name; a portal, category or search page is a SOURCE; a candidate that breaks a hard criterion is discarded;
    and **an empty honest list beats one full of things-that-are-not**, because a page has to be discarded one
    by one and an empty sheet reads in two seconds.
  - Node **4.93 RENDERS it**, and that is the half no source check can do. ⚠️ Its first run passed «the strip
    is not in the header» **for the wrong reason**: `set_content` leaves the page on `about:blank`, the strip's
    relative fetch for its identity never resolves, and the strip REMOVES ITSELF. It is served from a real
    origin now, and the test asserts the ids are FILLED — an assertion about absence needs the thing to be
    present somewhere.

- **Figures are made SPEAKABLE at the TTS node, and only there (V2-538, 2026-09-01)**: the operator listening
  to that same search — every price came out wrong. A TTS reading «151.008 €» sees a decimal point and says
  *ciento cincuenta y uno coma cero cero ocho*; «€» is skipped or lands in writing order («dollars four
  hundred»). His framing was exact: this text «no ha pasado por el modelo de lenguaje» — it is scraped by the
  browser extractor and handed straight to the sheet and the voice, so there is nobody upstream to ask nicely,
  and a coletilla in a prompt could not cover it.
  - **`tts_node` is the one place every spoken path converges on** (generated reply, `say()`, the lead-in
    filler, a proactive notice — verified against LiveKit's own `agent_activity`, which routes both at 2701 and
    3008 through it), so a price cannot slip through by taking another road. Subtitles and the chat wall go
    through `transcription_node` and are NOT touched: on screen the operator wants to read «151.008 €».
  - **It does NOT spell numbers out in words.** A number speller is a per-language component with gender and
    agreement rules; every TTS already reads a plain integer correctly. Dropping the grouping separator is
    enough, and it is the cheap half — which is also the answer to «esto será más difícil en otros idiomas»:
    **an unknown language is returned UNTOUCHED on purpose** (in a language whose convention we do not know
    «1.500» could be fifteen hundred or one point five, and a wrong currency word is worse than a symbol the
    voice may still read acceptably). Adding a language is a row in `_LANG`, never a function.
  - **The half that makes it safe is what it refuses to touch**: `192.168.1.1` (a group followed by another
    group is an address), `2026-09-01`, `15:30`, `v3.16`. The trailing lookahead rejects another separator+digits
    while still allowing the DECIMAL part, because `$151,008.50` is the ordinary way money is written in English
    and a plain `(?![\d.,])` left its grouping comma in place.
  - **Streaming**: the node is fed CHUNKS, so «151.008 €» arrives as «151.» + «008 €» and no regex would ever
    see it whole. Only the trailing run that could still be a figure is held back — symbol included on either
    side, since cutting between «$» and «400» hands the symbol over with no number to attach to. ⚠️ A blanket
    hold also retains a SENTENCE-FINAL FULL STOP, and that period is exactly what the TTS sentence tokenizer
    needs to close a segment: holding it would delay the last sentence's audio until the stream ends.
  - ⚠️ **And the module was born DEAD, exactly like REM's synthesis**: the regexes were built with
    `str.format`, a regex is full of literal braces (`\d{1,3}`), `.format` read them as fields and raised
    KeyError — which the fail-open swallowed, leaving a function that returned every string untouched and
    looked like it worked. Caught by running it against real strings, not by reading it. Guarded by a test, the
    same way `tests/memory/unit/test_rem_prompt.py` guards its own.
  - Node **3.20**, 24 cases, four disarms (8/10/2/1 red).

- **An undeclared capability is one the model NARRATES — the agenda's view is an action (V2-540, 2026-09-01)**:
  the operator asked the agenda to show tomorrow; it answered «te abro la agenda con la vista de mañana» and
  stayed on today. His encargo was to go read the observability of that session, and it settled the question in
  three lines — events 873 / 931 / 995, 15:11: three replies promising *la vista de mañana*, and each time the
  only thing that fired was a bare `show:agenda`, which opens on TODAY. Two of the three came from safety nets
  (*show por backstop de promesa*, *show por guard determinista*), i.e. the engine noticing the promise and
  doing the closest thing it had.
  - **It was not disobedience and not a hallucinated result.** The day tabs were DOM state inside `widget.js`
    (`el._agSel`) with no name in `manifest.json`, so there was no wrong tool to choose — there was NO tool.
    `add_meeting` in that same session worked first time; the difference between the two is a manifest entry.
    A capability the vocabulary cannot express is not one the model can decline, and the honest reading is that
    it narrated the outcome because narrating was the only move available.
  - **`show_day` carries a monotonic PUSH COUNTER, and that is what makes it work twice.** The canvas re-renders
    on a store write only when the data's JSON signature CHANGES, and the widget re-applies a view only when the
    token moves — so keying on the day itself would mean *tomorrow → he clicks back to today → «mañana» again*
    writes an identical value, changes no signature and moves nothing: the same bug in another mask.
  - **Freshness is decided server-side, where the clock is.** A push kept forever means reopening the agenda
    next week lands on a «tomorrow» that is now the past. `_fresh_view` stops serving it after 10 minutes, and
    that costs an open widget nothing — `view` merely stops arriving, the token stops moving, nothing snaps
    back and the operator's own tab survives.
  - A date beyond the horizon (today..+6) has no tab, so it opens the MONTH view pointed at that month.
    Landing silently on today would be the very lie the action exists to kill.
  - **The calendar connectors now sit in the agenda's header** (his second ask, the messaging reading of
    V2-521) — and they are honest: `connectors/` holds six and not one is a calendar, so all three read *not
    built yet*, which per INI-027 is the point rather than an embarrassment. `calendars()` READS the real
    inventory instead of declaring a state, so the day one registers it lights up with nothing else to change,
    and it fails CLOSED: a registry that cannot be read is not a connected calendar. The three are Google
    Calendar, iCloud (its CALENDAR is CalDAV with an app password, unlike iCloud Drive) and a generic CalDAV
    that covers Outlook/Fastmail/Nextcloud with one connector instead of three brands.
  - Node **4.94** (renders + manifest), six disarms across this decision and the next.

- **A canvas click has to land on the sheet the operator is LOOKING AT (V2-540, 2026-09-01)**: «el botón de ver
  detalle no es clic» — and it was wired, painted and enabled. What was broken was the ADDRESS.
  `desktop.js::ctx.action` stamps the open instance into every payload under the name the canvas uses
  everywhere, `q`, while `results.apply_action` only ever looked for `sheet`, a key the canvas has never sent.
  So every click on an instantiated sheet (`results::<errand>` — what a sheet born of an errand always is) was
  answered against the DEFAULT sheet.
  - **`view_data(q)` has read the instance out of `q` since V2-259; only the writer never followed.** That
    asymmetry is why READING a sheet always worked and WRITING to it never did, and why the symptom presented
    as a dead button instead of a wrong address. The fix is the one line that resolves the sheet, not the
    button — the mismatch was shared by `detail`, `choose` and the tab switch alike.
  - **`choose` is what proves it and `detail` is not**: detail looks the item up first, so on the wrong sheet
    it fails and writes nothing, while choose writes what it is told without a lookup — it was stamping a
    stranger's pick onto the default sheet. A disarm that only exercised `detail` passed while the bug was back.
  - ⚠️ **The silence is a second defect and it is fixed too.** The click did `await ctx.action(...)` and threw
    the response away, so a real `{ok:false, error:"no encuentro ese resultado en la hoja"}` reached nobody:
    the operator clicked, nothing moved, nothing said why. A refused action now SHOWS on the button. The cause
    made it fail; the silence made it undiagnosable for as long as it lasted.
  - Node **4.95**.

- **Who may interrupt is CONFIGURATION — per-connector notification policy (V2-532, 2026-09-01)**: the
  operator's direction — the messaging connectors stay mechanical/token-free, and *whether he gets interpellated*
  must be configurable per connector. Audited first: ingest was already token-free (own 5s/5s/20s loops → bus →
  local triage), the open card already repaints by SSE, and agenda avisos + messaging notices already share ONE
  delivery rail (`voice/proactive.notify`, serialized by V2-527) — what was frozen was the POLICY:
  `notify.surface()` hardcoded its predicate and `muted_channels` was the only knob. Now
  `widgets/mensajeria/policy.py` (zero-import; it lives in the widget package because `data.py` may not import
  `connectors`, the same direction the unified store travels): per platform
  `{notify: never|direct|important|all, speak: bool}` — `important` is byte-for-byte the historical predicate
  (untouched install identical), `speak=false` silences the VOICE but keeps the `[SISTEMA]` note (a mute channel
  must not blind the brain), fail-open to DEFAULT. Voice-settable via the declared `set_notify` data-op
  (undeclared = invisible, V2-520). **An explicit reminder (agenda/cron) is NEVER governed by this policy** — an
  order is its own permission to interrupt (V2-522), guarded by a source test: nothing under `nucleo/` imports it.
  Node 4.5 (+8), disarm verified. Open: the visual selector (render-verified pass), the closed-card unread badge.

- **The turn clock tells OUR share — pre-turn attribution + prefix-cache visibility + pooled judges (V2-533,
  2026-09-01)**: the LENTO verdict's `t0` started AFTER the attention judge, the completeness judge and the
  recall wait, so a turn where WE spent 1.2 s was reported as provider TTFT. Now `pre_ms/gate_ms/acc_ms` travel
  in `_reply_extra` and the verdict names them (`· previo N ms (juez · frase · memoria)` at ≥400 ms) —
  **`total_ms`/SLOW_MS keep their meaning on purpose**: `note_slow` relays providers on them, and relaying over
  OUR preflight would punish the wrong party (test pins it). `prompt_cache_hit_tokens` (captured for billing
  since 2026-08-14, never shown to latency) now rides every verdict label (`· caché N%`): measured on session
  701fcc1b's recorded prompts, consecutive turns share only **45.8% / 18.9%** of their prefix — the provider
  re-prefills ~10k tokens per turn, and that fraction is OURS (block order puts per-turn volatile text before
  the 14-16 KB resource layer). The reorder went behind the nodo 2.13
  routing bench and SHIPPED the next day as V2-536 (below), with `cache_hit_frac` as the live before/after series. Also: `nucleo/memllm.py` gained
  a pooled keep-alive POST (both hot-path judges paid a fresh DNS+TLS per call, ~150-400 ms; verified live), and
  the TTS prewarm hook now opens Cartesia's websocket pool (the kickoff paid the handshake). ⚠️ Parts landed
  inside the concurrent i18n batch commit `a3b20a9` (files swept up uncommitted; pushed, so left as-is).

- **Inside an active conversation, NOBODY judges — the attention gate went deaf mid-dialogue (V2-531,
  2026-09-01)**: session 701fcc1b — «tengo algún mensaje» opened the widget, and then **8 of the operator's ~12
  turns were dropped as `llm_ambient`**, including «¿Me estás escuchando?» and «te he dicho que ya la has
  abierto», seconds after the agent itself had asked HIM a question; he repeated himself four times and gave up.
  Reproduced **15/15**: the DeepSeek `directed` judge answers `{"directed": false}` on those exact second-person
  phrases — cleanly, not fail-open. Third of this family (2026-08-16 created the judge, 2026-08-17 filler
  context, today). The deafness also DROVE the visible symptom: his corrections («ya la has abierto») never
  reached the model, so it kept offering to open the already-open widget against the state line.
  - **`always` mode maintained the conversation window and never consulted it** — every turn went to a binary
    coin-flip even four seconds after the agent spoke. Now the window BEATS the judge (`active_window` within
    30s of a handled turn, `evaluate_content`); the judge only decides COLD turns, the "sitting in a meeting"
    case it was built for. Stated cost: noise inside the window runs a turn — the module's own rule already
    chose that side.
  - **A real reply refreshes the window** (`send()`, per chunk, kickoff excluded): a narration longer than
    `window_s()` must not land the operator's answer on the cold judge.
  - **The cold judge gets a DIALOGUE frame**, measured: «Se estaba haciendo: …» reads a second-person sentence
    as two people in the room; «Zaelar acaba de decir: … El micrófono ha oído: …» flips the measured phrases to
    directed 3/3. Still fallible — which is why it no longer decides mid-conversation.
  - ⚠️ **A disarm on an uncommitted file is restored by RE-APPLYING the edit, never `git checkout`** — checkout
    restores HEAD, and here it wiped my edits AND two in-flight comment translations of the concurrent i18n
    pass (re-applied verbatim, attributed in the commit).
  - Nodes 3.x (`test_attention.py` +3, incl. the 8-turn replay with the judge answering what it answered live)
    + the send() source guard. **Not verified live yet**: the fix needs an engine restart and a session was open.

- **An errand has a NAME, and it is not a slice of the conversation (V2-530, 2026-08-31)**: the operator, with
  the screen in front of him — «los dos widgets de resultados tenían un título… más un comentario parte del
  diálogo». Session `7cab1afd`: his two sheets were titled «Sanidad con Sanitas en Soria» and **«Me parece bien.
  Oye, una cosita, estabas buscándome un médico. ¿Eres…»** — a slice of the conversation, cut BEFORE the errand
  is even mentioned. The same string was what the voice read out when the worker needed a datum («el proceso
  "Me parece bien. Oye, una cosita, estabas" pregunta: …»), so the defect was audible as well as visible, and it
  was one of the two options in the disambiguation question — which is why answering that question was hopeless:
  it named one errand and one pleasantry.
  - **Traced, not guessed**: the promise backstop escalated with the RAW turn as its goal
    (`router_guards`: `escalate_req["v"] = _win_goal or _op_text`), and three readers took that brief for a
    name — `sheets._sheet_open` → `begin_task(rec.goal)` → the header, `loop.py` → `goal[:40]`, and
    `instances._label`, which reads the header back.
  - **The GOAL is the operator's own words ON PURPOSE and stays that way.** Fidelity is what lets the worker do
    the right thing — he said «invéntate el apellido si te lo piden». So the brief stays a brief and the NAME
    becomes its own field (`SessionRecord.title`), beside `goal` and never instead of it: dedup compares goals
    and the master audits them.
  - **Two answers, in this order.** `errand_title.provisional()` is instant and **deliberately not clever** —
    the goal clipped on a WORD boundary, because every heuristic here GUESSES and a wrong guess renames the
    operator's errand to something he never said; the one defect it fixes alone is the mid-word cut, which is
    what made the measured title unreadable. `errand_title.compose()` is one small model call, fired
    fire-and-forget from `dispatch._name_errand`: the sheet is already on screen and the worker already
    spawning, so a slow or dead provider can only cost a box that keeps the name it had. **Naming is
    understanding** — a verb table over that exact sentence produces «Me parece».
  - `sheets.title_of()` is ONE function for the three readers, and `rename_task` is separate from `begin_task`
    **because that one ESTRENA**: reusing it would erase the results it is naming.
  - **«Cierra los dos» ANSWERS the disambiguation question.** Measured minutes earlier in the same session: he
    said it at 22:11:20 and got the question BACK; said «las dos» at 22:11:28 and got it again, this time with
    the verb changed from «cierro» to «enseño». The Susurro auditor filed it live as `[P1·routing]`. The
    question asks WHICH ONE and the answer was BOTH — an option the resolver had no way to express, so every
    rephrasing round-tripped into the same question. `instances.wants_every()` is a QUANTIFIER, not a verb
    table, and `resolve_close`/`resolve_show` now return **`ids` ALWAYS**: a caller that loops it is correct for
    one card, none, an already-disambiguated id and «both» with the same line — reading `id` is exactly what
    made two of the three closing paths miss the answer. Wired in the four call sites **plus the probe
    channel**, because this class of bug survives by diverging between voice and text. Counterweight under
    test: a plain «ciérralo» with two open still ASKS, or «answer both» would be satisfied by never asking.
  - Nodes 2.5 and 4.38, nine disarms. ⚠️ **Two came back GREEN on the first pass and both were the TEST's
    fault**, the same trap twice: reverting `_sheet_open` to the raw goal changed nothing because the file only
    checked that `title_of` EXISTS (V2-199 again — the wiring test is what makes it bite), and commenting out
    `_name_errand(rec)` left the source guard green because a substring scan cannot tell a live call from its
    own citation **and** `def _name_errand(rec)` matches the same substring.
  - **VERIFIED LIVE on the operator's engine** (`3.16+de38413`, agent stopped, no session — safe to restart):
    «Me parece bien. Oye, una cosita, estabas buscándome un médico. ¿Eres capaz de pedir cita tú solo?» →
    **«Pedir cita con el médico»** in 1.55 s; «…Búscame el traumatólogo, y creo que era en el centro PAMA» →
    **«Cita traumatólogo en centro PAMA»**; the English errand stayed in English. **Two things only the live run
    could show.** (1) **WHO names it** — the reasoning chain (the research composer's own) has one reachable rung
    on this machine and answered NOTHING in 20 s, while the voice tier composed every title in ~1.5 s; so the
    voice tier goes first, which is also the right SHAPE (naming is one line, not deliberation, so a
    non-reasoning model is what this wants) and the reasoning chain stays as the fallback. (2) asked for the `-`
    sentinel on «mmm, no sé, déjalo» the model answered **«No encargo»** — a paraphrase of the instruction that
    `clean()` would have handed over as a sheet title. The guard is STRUCTURAL, `names_the_errand()`: a name
    that shares NO content word with the brief is not naming it, whatever it says — never a list of refusal
    phrases, which is the treadmill this repo keeps paying (V2-151). Ambiguity costs only the provisional title,
    the safe direction; a language that does not separate words never overlaps and always keeps it, stated
    rather than papered over.
  - Still open: the frontend task card paints `goal`, not `title`; and the worker's own restatement of the
    errand («Recibido el nuevo encargo: cita de traumatología en el Centro Médico Pama…») is a better name than
    anything a titler composes, and nothing reads it.

- **The lead-in filler sounds BEFORE the reply — it IS the reply's first segment (V2-529, 2026-08-31)**:
  operator's report, verbatim: «la voz lo hace al revés: primero reproduce la respuesta y después el nexo …
  "Vale, empiezo con la tarea" y luego "Espera, espera"». Both defects measured. (1) The reversal was
  STRUCTURAL: the filler spoke via `session.say()`, and when it fires the reply is already the scheduler's
  CURRENT speech — LiveKit serializes on GENERATION, which for a reply includes its playout. Proof in the
  live timeline (session e081f343): the filler's synthesis fired at the exact millisecond the reply's
  playout ended. Via `say` it could NEVER sound first. (2) It fired on nearly every turn: timer at 600 ms
  vs measured TTFT of 1.9-2.8 s.
  - ⚠️ **The first attempt (pre-synthesized frames from a `tts_node` wrapper) was ALSO wrong, and only a
    LIVE turn could show it**: unit tests green, five disarms red, and **zero fillers** on a real turn with
    TTFT 2.51 s against a 1.1 s timer. This pipeline SEGMENTS the reply, so `perform_tts_inference` — hence
    `tts_node` — is only called from `_start_segment()`, which runs **when the first text chunk arrives**.
    A node that only exists once text exists can never observe that the text is LATE. Guarded
    (`test_the_wiring_uses_llm_node_and_NOT_tts_node`). The lesson, third time in this file's history for
    this one feature: **a filler's injection point is a claim about WHEN the pipeline instantiates it, and
    that claim is only testable live.**
  - **v3** (`voice/engine/speech/filler_audio.py` + `ZaelarAgent.llm_node`/`transcription_node`): the
    `llm_node` wrapper races the model's first chunk against `ZAELAR_FILLER_MS` (default **600 → 1100 ms**;
    0 stays the kill-switch — a reply within ~a second gets no filler, the operator's rule). Timer first →
    yield the filler text **plus a `FlushSentinel`**, which CLOSES the segment: the phrase is synthesized
    and played on its own while the model still thinks, with the reply as segment two, in order, in the
    same speech. v1's failure (the tokenizer retaining a short unpunctuated phrase until the reply glued to
    it) cannot return, because **v1 had no flush**. A barge-in cancels the whole speech, filler included —
    no lifecycle left to cancel.
  - **`transcription_node` strips it** from what LiveKit FORWARDS — that node's output is the subtitle
    stream AND the text written into `chat_ctx` (`forwarded_text`, not the LLM's raw `generated_text`). The
    filler is spoken and shown in the chat wall by our own marked `kind="filler"` event (V2-122 addenda),
    never inside the reply's bubble or the model's history. The strip is consumed ONCE, so a reply that
    genuinely opens with the same interjection survives.
  - **ARM/CONSUME**: only a brain turn arms one (never the kickoff); `say` speeches don't go through
    `llm_node` at all. Consumed at fire time, TTL 20 s, once. Old guards travel: never over the operator's
    voice, varied phrase, anti-echo updated (never the directed-judge's reply-context field — source guard).
  - ⚠️ **A RACE that only a SECOND live turn could show**: one turn fired the filler and the very next did
    not, with TTFT 3.26 s. The arm and the deadline race — this node is entered before `_run_inner` reaches
    `arm()` (prompt build + tool selection in between) and the gap varies: measured, one turn armed **150 ms
    before** the deadline and the next **~400 ms after** it. So the deadline is not a single sleep: past it
    we keep polling for the arm while still racing the model's first chunk. `_ARM_GRACE_S` bounds the spin
    and is **not** a behavioural bound — its disarm leaves every test green (the first-chunk future always
    resolves), and the test says that out loud instead of crediting coverage that does not exist.
  - `lead_in_filler.py` DELETED; nucleo only ARMS. Node **3.19**, 14 cases, six disarms verified red.
    **VERIFIED LIVE, both halves** — 21:57 (`zaelar-79cc37c2`): `thinking` 10.412 → filler «Veamos…» 11.512
    (the 1.1 s delay, exactly) → **`speaking` 11.789 with the filler's own 0.81 s segment** → first token
    16.456 (ttft 3.20 s) → the reply's 31 s segment, i.e. **4.7 s of real silence covered, in order**. And
    22:02 (`zaelar-c1fa7ca0`, the very turn that had failed): armed 53.452 → filler 53.456 → speaking 53.722
    → ttft 3.29 s at 55.380 → **transcript «Me llamo Zaelar.» with no filler inside it**. Pending: the
    operator's own ear on a spoken turn.

- **The proactive delivery QUEUE — one message at a time (V2-527, 2026-08-31)**: the operator's spec, dictated
  after session c480413b: «tiene que tener un buffer … cuando ya se lo ha explicado le manda otro; si dos
  tareas terminan simultáneamente, primero se informa de una y después de la segunda». What existed: nothing
  serialized concurrent notifies — each waited for quiet on its own, two workers finishing at once both saw
  silence and both called `session.say`, and order/overlap were LiveKit's internal scheduling, not ours. The
  V2-047 F7 instrumentation had already named the fix («el fix es SERIALIZAR») and stayed telemetry-only.
  - **Ticket queue in `voice/proactive.py::notify`**, strict arrival order, cross-LOOP by construction
    (threading.Condition entered via `asyncio.to_thread`) — an `asyncio.Lock` binds to one loop, and notifies
    arrive from uvicorn while the voice lives on the LiveKit job loop: the exact «attached to a different
    loop» family V2-525's sibling fix just cured. The ticket is held through the whole playout («cuando ya se
    lo ha explicado»), and the quiet re-check runs AFTER winning the turn.
  - **A message never dies in the queue**: out of budget (arrival-clocked) or turn never comes → the same
    `[SISTEMA]` note as always, and the ticket is ABANDONED so `_release` skips it — a wedged queue would mute
    every delivery forever. A crashing speaker releases via `finally`.
  - **`_BOT_GRACE_SECS` was letra muerta** — defined since INI-008, used by nobody. Wired now as the breath
    between deliveries, clocked from the last delivery's END (`_last_spoke`), not from observing busy: the next
    in line is blocked in `_wait_turn` while the previous speaks, so its quiet-poll starts after the voice
    already ended and would never see it.
  - Barge-in is unchanged: `allow_interruptions=True` and the operator-first gate stay; interrupting stops the
    current message and the queue waits for quiet before the next. Node 3.17, disarm verified (4 of 7 red).

- **⏻ ON has to START it — the reload was the tell (V2-525, 2026-08-31)**: «al darle al botón de arranque se me
  queda en amarillo parpadeando y creo que al cabo de un minuto o dos sí que arranca. Pero si hago un refresh de
  la página, automáticamente ya se pone en marcha todo.» Two faults stacked:
  - **Order.** The ⏻ ON handler called `session.start()` first and `api.runStart()` after. But `session.start()`
    opens with a gate against the server's truth (`GET /api/run`, added 2026-08-15 to kill ghost sessions), so it
    read the switch from BEFORE this very click, found `running:false`, aborted the startup and set `powerOff`
    back to true. The server is commanded first now, and the session start hangs off its reply.
  - **Nothing brought it back up.** The effect watching `powerOff` covered only the OFF direction since V2-092.
    With the flag raised from outside the tab (the SSE `run` event, another window), the voice sat waiting for
    the next `pointerdown` — the other road into `ensureVoice()`. That is the "minute or two": until he clicked
    something else. A RELOAD was instant because the boot seeding calls `ensureVoice()` itself.
  - **And the defence that already existed and was never applied here**: a `/api/run` reply is a snapshot of the
    moment it was REQUESTED. main.js's seeding has dropped stale ones against `powerCmdAt` since 2026-08-14; the
    startup gate did not. Ordering makes the race rare, the stamp makes it harmless — the command can arrive from
    another tab, which no ordering here can prevent.
  - **The tell to keep**: a state that only fixes itself by reloading the page is the state that lies. Node 4.91,
    disarm verified (4 of 5 red).

- **The BOUNDARIES of a work session (V2-524, 2026-08-31)**: the operator pressed ⏻ off, then Reset, and the
  master showed him a session **EN CURSO** on an engine whose own switch said `stopped`. The ⏻ was innocent —
  it HAD closed the session; the **Reset** opened a new one eleven minutes into the stop. Two independent
  defects, both about a boundary, plus a third found while writing the rule down:
  - **`begin_session` had no guard.** `stamp_identity` has refused to let an EVENT self-open a session while
    stopped since 2026-08-16, but `rotate_session` called `begin_session(force=True)` explicitly and walked
    past it. The new session then held nothing but the tab's own noise and stayed open forever. The guard now
    lives in `begin_session` itself — one door, not one per caller — and fails OPEN (an unreadable switch
    counts as running: losing the operator's work from the record is the worse of the two mistakes).
  - **No session ever recorded its own end.** `end_session` nulls `_session["id"]` before emitting the closing
    mark, so `stamp_identity` — correctly — would not invent a session for that `system` event: it went out
    with `sid=""` and `_session_path("")` dropped it. **0 of the last 12 session files** on his engine had
    their own `session/end`. `rotate_session`'s docstring asserted the opposite in writing; it had simply
    stopped being true. The lesson is the recurring one: **a doc that describes a seam is not evidence the
    seam still works** — the id is now stamped explicitly, from a value already in hand.
  - **The idle ceiling could only fire on the way back.** `note_real_activity` runs on activity, so a session
    nobody returns to was never closed by it. `close_if_idle()` is the same decision taken from the other
    side, offered by the pulse — it only ever CLOSES, never opens and never extends the clock, so an idle
    machine closes once. Its clock counts from `max(last_real_activity, started_ms)`: `_last_real_activity_ms`
    is global, so without the start time a session opened after a long quiet stretch is **born expired**.
  - **The rule, which is what he actually asked for**: a work session is *the stretch in which the agent could
    work*. ⏻ ON opens one, ⏻ OFF closes it, a reset in front of a stopped agent wipes the slate and opens
    NOTHING, an abandoned one closes itself. And it is an OBSERVABILITY axis, not a state boundary: memory is
    deliberately independent of it — anything that must be wiped between sessions is wiped explicitly.
  - **Master side too** (`localSessionState`): the ⏻ beats `current`, so a master polling an older engine
    still cannot print EN CURSO over a stopped switch. `runState: null` decides nothing — an agent that did
    not answer is not evidence of anything.

- **Messaging is a MAIN widget now — the operator's spec (V2-521/522/523, 2026-08-31)**: direction given in
  one long instruction; phase 1 shipped the same day, the rest is RECORDED so it cannot evaporate.
  - **Replies reach every platform**: the `msg.reply` seam existed since V2-051 and only email subscribed —
    the WhatsApp bridge had `POST /send` all along, Telethon sends in one line, and nobody drained the
    topic, so a confirmed dictated reply to WhatsApp was enqueued forever. Both connectors now drain and
    send, with email's failure policy (the operator is TOLD via brain_notes; nothing requeues — one honest
    "no pude enviarlo" beats a bad send retried forever). `reply` stays `confirm:true`: dictating is
    guided, SENDING still asks first.
  - **The visual formula**: ONE unified inbox by default (deliberately unfiltered — the operator trains
    the algorithm later), plus a per-platform LENS toggled from the header icons; email's lens is its
    natural shape (flat mails, expandable in place), WhatsApp/Telegram keep chats→thread. The header shows
    EVERY channel — dimmed = unconnected, and tapping a dimmed icon opens its connect form (same door as
    the voice, V2-520). Per-provider app-password guidance with the exact URL in the email form. Node 4.90
    RENDERS it.
  - **Memory policy (measured, and the rule to hold)**: only TRIAGED items reach central memory
    (`ingest_message`, short level) — that is "relevant + recent", not a mailbox dump, and the operator's
    rule is explicit: **never duplicate the platforms' archives — they hold the originals**. The gap is
    reach-back (IMAP search, WA/TG history on demand), not more copying.
  - **Two planned pieces, not to lose**: V2-522 write permissions per platform — with the principle that
    **an explicit order IS the permission** (naming 10 people to invite authorises every mapped channel
    for that errand; the permission system gates the UNPROMPTED, the confirm gate covers the dictated),
    and no personality impersonation for now. V2-523 the CONTACTS AGENDA as first-class memory/state (one
    person ↔ many handles incl. their cluster AGENT; merges are identity claims → operator-confirmed).

- **Connecting a channel can be ASKED FOR (V2-520, 2026-08-31)**: "conéctame el correo" opened the messaging
  card on the MESSAGE list and nothing else — no dialog, no question about which provider. Everything the
  operator asked for already existed (`connectors/email/providers.py` ships Gmail and Outlook/Hotmail with
  OAuth, and the connect form has a provider picker); it was UNREACHABLE, for two reasons that compound:
  - the channels panel is local `widget.js` state (`_connectorsOpen`) that only the header 🔌 button could
    flip, and `showChannels = _connectorsOpen || connectedCount===0` — so with WhatsApp/Telegram already
    connected, the card renders the message list forever;
  - `apply_action` had handled `connect` since V2-051 but **the manifest never declared it**, and the widget
    contract is explicit: an action `apply_action` handles and the manifest does not declare is INVISIBLE to
    the brain. A capability nobody declared is a capability nobody has.
  - Fix: a declared `open_connectors` data-op (+ a manifest `usage` telling the brain WHEN) that stores a
    timestamped `connect_focus` in the widget's own data; the widget opens the panel and expands that
    channel's form, **once per request** (`_focusDone` — otherwise the next message arriving would re-open a
    panel the operator had just closed). It carries INTENT only, never a credential: a password or an OAuth
    round-trip is not something to conduct by voice, and a test pins that.
  - Nodes 4.88 (data + wiring) and **4.89, which RENDERS** — and the render is the half that matters here:
    neutering the branch to `if(false && focus …)` left every source-level assertion green, because the
    string being grepped was still in the file. The render check looks at pixels: panel open, form with real
    height, picker offering Gmail and Outlook.
  - Also: email now wears an **envelope**, not the letter "E" the icon fallback drew next to two real brand
    logos. Deliberately not a Gmail logo — the same connector serves Outlook and any IMAP host.

- **The attachment can never swallow the message (V2-519, 2026-08-31)**: feedback with "incluir lo que ha
  pasado en esta sesión" ticked always failed with a flat `400`, and the operator's written text was lost
  with it — a report about the mail wizard, gone. TWO causes stacked, and the second is the interesting one:
  - The engine capped the evidence bundle by event COUNT (200) and **never by bytes**, while the ingestion
    endpoint refuses anything over 40 000. Measured on the operator's own session: **212 037 bytes, 5.3× the
    ceiling**. `_fit_evidence` now trims by BYTES to 30 000, keeping the **most recent** events (what is
    being reported just happened) and stamping `truncated:{kept,of}` so a reader never mistakes a trimmed
    session for a short one.
  - **A ceiling believed on both sides and measured on neither is not a contract.** The control-plane's own
    comment asserted "generous margin over the ~30KB the engine caps itself to" — that self-cap had never
    been written. Both sides now name the constant they trust (`cloud` commit `86ba233`).
  - **The message is the point; the session is an attachment.** A 400/413/422 carrying evidence is retried
    ONCE without it (`evidence_dropped:true` back to the panel). A 429 or a 5xx is NOT retried — that door
    is closed for another reason.
  - Node 4.33, 9 cases. **The first disarm came back GREEN**: the tests exercised `_fit_evidence` directly,
    so deleting its call from `_build_evidence` — the exact shipped bug — changed nothing. The added
    `test_the_builder_ACTUALLY_applies_the_trim` is what makes the node guard the WIRING and not just the
    rule. Verified against the LIVE control-plane with the operator's real session: `HTTP 200`.

- **The widget's CONFIG corner + confirmations live in the CHAT (V2-518, 2026-08-31)**: operator's design.
  The card's existing ⚙ panel (the alias editor) is the config corner: right under the title it now says
  where the piece comes from — "Tu fork del widget de sistema «id»" **with the Restaurar button** (never on
  the widget's face), "Widget de sistema · id de referencia: «id»", or "Widget tuyo". The button only OPENS
  the confirmation (`POST /widgets/{id}/restore/ask` → `confirm.request_restore`): the question lands **in
  the chat thread with Sí/No** (house norm, restated by the operator: NO popups — questions render in the
  conversation, answerable there, on the card overlay, or by voice) and resolves through the same
  `/widgets/{id}/confirm` gate as everything else. `store.widgetConfirm` mirrors the SSE
  `confirm`/`confirm-cancel` events that already paint the card overlay; a widget with `confirm_ui:false`
  stays fully voice-only (no emit → no bubble), by design. RENDER-VERIFIED live (Chromium 1280×800): fork
  panel, system-id panel, chat bubble, Sí discards the real fork from disk. The render caught what no unit
  test sees: the button clipped inside short cards (`.hb-aliases` gets max-height; the origin section sits
  at the TOP so it never scrolls out of sight). Mobile shell (`frontend/mobile/`) has no ⚙ panel — pending
  decision.

- **CONTACTOS: un directorio para TODAS las identidades — y su vista contesta (V2-541, 2026-09-01)**: orden
  directa del operador — UN widget nativo para el archivo entero de contactos (personas, sitios y empresas:
  amigos, restaurantes, fontaneros…), nunca un widget por tipo; el `restaurantes-favoritos-operador` generado
  ese mismo día se BORRÓ a petición suya para que solo exista éste, y su único dato (Elfo On, Soria) se
  re-entró aquí como sonda en vivo. **Zanja la pregunta abierta del plan V2-523**: un sitio favorito ES una
  entrada del directorio con `favorite` de marca, jamás una lista paralela. La forma del registro sigue ese
  plan (kind person/place/company, `parentId` anidado con guarda de ciclos, etiquetas libres) para que la
  integración memoria/estado futura sea una proyección y no una reescritura — **V2-523 sigue siendo la
  iniciativa real** (resolver «mándale un mensaje a Juan» por aquí); mientras tanto el archivo vive en el
  circuito de widgets con `data.durable: true`. Las lecciones pagadas van puestas DE NACIMIENTO: la vista es
  una ACCIÓN declarada con contador-testigo y caducidad en servidor (V2-540), y `show_view` DEVUELVE los que
  casan (`result.matches`) para que «¿mi restaurante favorito en Barcelona?» sea una llamada y no una promesa;
  el alta sin nombre es un error que enseña la forma del reintento (V2-473); mismo nombre+ciudad ACTUALIZA en
  vez de duplicar (familia V2-208); el match de grupos es contención sin acentos en las dos direcciones
  («fontanero» ↔ «fontaneros»), nunca una tabla de sinónimos. Nodo **4.96** (19 unit + 9 RENDERIZANDO, cuatro
  desarmes verificados) — el render cazó antes de nacer el bug de la familia V2-124: `renderDetail` repintaba
  en la COLUMNA y «Volver» habría montado el widget dentro de sí mismo sin error. Verificado en vivo
  (`3.16+4806ce1`): el catálogo lo vio sin reinicio, el dato sobrevive al restart y el ⏻ parado se respeta.

- **Borrar una superficie es MUDAR lo que llevaba, o es perderlo (V2-542, 2026-09-01)**: el operador, con el
  borde inferior del escritorio delante — «toda esta mierda que aparece abajo no tiene sentido tenerla… ya
  tenemos una barra a la izquierda y las opciones principales arriba a la derecha. Si quieres poner un icono de
  conexión, que sea el mismo que el del servidor. No quiero selectores de micrófono **aquí**». La línea
  `ConnStatus` (conexión · latencia · micro) desaparece entera: componente, superficie y CSS.
  - **El «icono de conexión igual que el del servidor» YA EXISTÍA, y eso se comprobó ANTES de borrar.** El ◉ de
    arriba pinta `overallStatus()` = peor(servidor, voz de ESTE navegador, offline), y su mitad de voz sale de
    `voiceStatus()`, que lee **el mismo `store.conn()`** que pintaba la línea. No hubo que añadir nada. Igual
    con el nivel de micro: el orbe ya lo mueve desde `store.micLevel()`, la misma señal. La barrita era un
    duplicado más pequeño del medidor que él ya mira. Solo la latencia pierde su chip, y los tiempos por turno
    están en el ◷ con mucho más detalle.
  - **«Aquí» es la palabra que aguanta la frase.** Quitar una tira de diagnóstico del escritorio es el encargo;
    quitar la capacidad de elegir micrófono no lo es, y la diferencia entre las dos es tener un sitio a donde
    llevarla: los dos selectores se van a **⚙ → Voz**, en su propia tarjeta **debajo** del botón «Guardar voz»
    — porque lo de arriba es config del servidor que ese botón escribe y estos se aplican al cambiar, y en la
    misma tarjeta el botón estaría prometiendo guardar dos controles que no guarda.
  - ⚠️ **El panel se CONSTRUYE al abrirlo y la tira existía siempre**, así que ya no basta con que `start()`
    rellene los selectores una vez: el panel tiene que poder PEDIRLO (`mountMicPickers()`), en los dos motores.
    El panel no sabe cuál le habla, así que **tira la fila de cualquier select que nadie rellenó** — así la del
    modo de captura desaparece sola en el motor legado, que no lo tiene. Y la poda espera al relleno, que es
    asíncrono: podar antes habría borrado las dos filas justo antes de que llegaran sus opciones.
  - ⚠️ **Un guarda que no sabe nombrar lo que busca afirma sobre la nada**: «no queda ningún selector suelto
    abajo» pasó en VERDE con la tira entera restaurada, porque buscaba `.desk select` y el contenedor es `#desk`
    (id, no clase) — y porque los selects estaban **ocultos**, de modo que cualquier medida por visibilidad
    también habría pasado. Se cuentan los NODOS. Mismo error de forma que ya costó dos guardas en V2-538.
  - Nodos **4.92** (tres comprobaciones nuevas, incluida la que convierte el borrado en mudanza: la salud de
    conexión sigue teniendo casa) y **4.97**. Cinco desarmes: 1/2/1/2/2 rojos.

- **MENSAJERÍA: la vista es una acción que contesta, los medios se VEN, y las órdenes llegan a las apps
  reales (V2-543, 2026-09-01)**: leído del `zaelar.db` vivo — «ve a la lista principal de los mensajes» y
  «muéstrame la lista general» solo pudieron re-mostrar el widget («Aquí lo tienes» sobre una pantalla
  quieta): la lente de plataforma era estado local de `widget.js` y «volver a la lista» no tenía acción en
  ningún sitio; el manifest declaraba 5 de las 12 acciones que `apply_action` maneja, y **el gate
  manifest↔apply_action salta los `backed` a propósito** — el unit del nodo 4.98 hace de ese gate ahora.
  `show_view` empuja la vista con contador-testigo + TTL 600 s (patrón V2-541) Y devuelve los chats que
  casan; `open` acepta el NOMBRE del chat; los clics de los iconos de cabecera pasan por la MISMA acción
  (un solo estado para UI y voz). `connect`/`disconnect` siguen sin declarar A PROPÓSITO (llevan
  credenciales — la puerta de la voz es `open_connectors`, V2-520).
  - **Los medios morían en UNA línea**: el bridge de WhatsApp descargaba cada imagen/vídeo/audio/documento
    desde el primer día (`~/.hermes/*_cache/`, `mediaUrls` en cada evento) y la whitelist de campos de
    `connectors/messaging/store.py::upsert_items` los tiraba — medido: mediaUrls/hasMedia/mediaType
    aparecían en bridge.js y en NINGÚN .py. Ahora viajan (media/mediaType/ts), las cachés del bridge
    apuntan al data_dir del widget (la ruta de assets es PLANA: solo sirve ficheros junto a state.json; lo
    de fuera se COPIA dentro), Telegram captura por MTProto lo que nunca miró (una foto sin pie llegaba
    como burbuja VACÍA) y el email guarda los adjuntos que `BODY.PEEK[]` ya traía. El widget pinta
    miniaturas y `<audio|video controls>` — **solo por gesto del usuario, jamás autoplay, y SIN bloque
    `runtime` a propósito**: un medio recibido es contenido pasivo como el QR, no producción del agente.
    El placeholder interno `[image received]` se enseña como «📷 Foto» (dato interno EN, cara ES).
  - **Propagación**: el mark-read de Telegram gana `max_id` preciso y las respuestas dejan de perder el
    hilo — `int('<chat>:<id>')` SIEMPRE lanzaba y `reply_to` caía a None en silencio; el compuesto es
    NUESTRO (`_normalize`), el parser tiene que conocer su propio formato de cable (`_tg_msg_id`).
    Email gana archivar/borrar EN EL BUZÓN REAL (RFC 6154; **Gmail anuncia `\All` y no `\Archive`: allí
    expunge desde INBOX ES archivar** — quitar la etiqueta; `UID MOVE` donde se anuncia; un buzón sin
    archivo REFUSA en vez de borrar por aproximación), cableado widget→cola→owner→bus→conector, con
    `trash` tras el confirm-gate y los fallos DICHOS por brain_notes, nunca reintentados en silencio.
  - **La ruta `backed` se tragaba la respuesta, y lo cazó la SONDA EN VIVO, no la suite**: con el owner
    corriendo, toda acción devolvía `{"queued": true}` pelado — la pantalla se movía por SSE mientras el
    turno no tenía ni la respuesta ni los errores (ausencia de error ≠ ausencia de fallo).
    `data.answer_action` es el hook de RESPUESTA/VALIDACIÓN de solo lectura de `_route_backed`: `ok:false`
    VETA el encolado, cualquier otro dict se funde en el ack; **el owner sigue siendo el único escritor**
    (guarda AST: ninguna llamada a save dentro del hook). ⚠️ Y la trampa de V2-531 pagada otra vez aquí:
    el desarme restauró `server_api.py` SIN COMMITEAR con `git checkout` y se llevó el hook entero — un
    fichero sin commitear se restaura RE-APLICANDO el edit, nunca con checkout.
  - Nodo 4.98 (15 unit + 6 render + 7 store + 9 IMAP falso), **seis desarmes verificados en rojo** con la
    mutación afirmada. **VERIFICADO EN VIVO** (motor `3.16+14fb8f9`, sin voz activa, ⏻ conservado):
    manifest con las 14 acciones, `show_view` válido → queued + respuesta fundida, `instagram` → veto con
    el error que enseña, y el OWNER aplicó el push (`view.n=1` en el store real). Pendiente de tráfico
    real: una foto de WhatsApp entrante pintándose y un archivado contra su buzón.

- **The INSIDE of a widget belongs to widget_data — the prompt no longer contradicts the catalog (V2-544,
  2026-09-01)**: four live turns, one shape — with the mensajeria card ON SCREEN, «Sí» to the model's own
  «¿Quieres que lo abra?», «Abre el mensaje.» and «Abre el mensaje de Francisco.» each produced a bare
  `show_widget` over an unmoved card plus «Aquí lo tienes». The decision records prove the model had
  everything (the brief with `[[msg.open:N]]`, «1. Francisco» in the list, `widget_data` in its tool set all
  four turns, `data_done: False` everywhere) — and on the last turn it even called `need_capability` asking
  for the `messaging` family, hunting for an open-message tool that does not exist (that family only carries
  `reply_message`). **It was OBEYING**: the canvas block commanded «"abre X" = [[show:X]], jamás widget_data»
  (written for the canvas level, it swallowed the item level), `widget_data` described itself as data-MUTATION
  only and disowned "abrir", and its parameter docs cited catalogs («Available widgets», «ACCIONES POR
  WIDGET») that the built prompt NEVER renders — while the resources block taught «abre el chat de X» →
  open{name}. A self-contradicting prompt loses to its own imperative (V2-222, 0/13).
  - Fixed in the three places that misteach it: the widget-vs-inside bifurcation lives INSIDE the [[show]]
    imperative with a concrete example (and «jamás widget_data» is gone, with a test forbidding its return);
    `widget_data` owns NAVEGAR DENTRO and disowns only the WHOLE-widget open/close; `show_widget` points
    inside-requests back («repetir show no cambia nada»); the parameter docs cite the block names the prompt
    actually renders («Widgets del canvas», «datos:»). Plus: a «sí/vale/hazlo» to the model's OWN offer
    executes the offered action — never another show (the first failure of the night).
  - Ruled OUT before touching anything: the action_map (no phrase swallows «abre el mensaje»; its seeds are
    canvas-level on purpose) and the tool-family trimming (`widgets`, with `widget_data`, was KEPT every turn).
  - Catalog ceiling 21_800 → 22_050 (compacted +434 → +140 first); an escalate NO-list clause was tried and
    REVERTED — the 2_000/tool cap caught it, and escalation was never the observed failure path.
  - `mensajeria.open`'s primary payload key is `name` now (the `widget_data` item convention lands a natural
    reference in the action's FIRST key, V2-467), and `_open_ref` coerces `n:"1"` / reroutes `n:"francisco"`.
  - Node 2.1 gained the contradiction gate (`test_the_inside_of_a_widget_is_widget_data.py`, incl. a
    cross-check that renders `widgets.brief.for_prompt` so the cited catalog names must really exist); node
    4.98 the n-as-reference case. Four disarms verified red with mutations asserted. **NOT verified live**
    (the operator's session blocked the restart); first check: «abre el mensaje de Francisco» →
    `widget_data(mensajeria, open, {name})`. Open: the «sí» resolution is still model judgement — the
    deterministic upgrade is the pending-offer carry of V2-539's family.
  - **The prompt fix alone could not reach the screen: the voice rail was UNDOING it** (same day, found by
    probing after the restart). `_handle_widget_data_tool` rewrites EVERY `is_pure_show_request` into
    `[[show:widget]]` — and «abre el mensaje de Francisco» IS one (show verb, no change verb), so a correct
    `widget_data(open, {name})` became a re-show of a card already on screen. `show_object_is_the_widget`
    tells the two apart with the MANIFEST's own vocabulary (strip the show verb and the filler; what is left
    must be names this widget answers to) — no verb table, no per-widget list — and the original incident the
    guard exists for («abre la agenda» executing an invented `add_meeting`) still lands on show. **Fails
    CLOSED**: an unreadable catalog keeps the old behavior, because a hallucinated data-op is worse than a
    show that does nothing.
  - **The probe channel had never mirrored that guard**, so it reported `widget_data open {name:'Francisco'}`
    for the very sentence the voice rail turned into a bare show: **a FALSE GREEN on the defect it was being
    used to diagnose**. Seventh instance of «cablear en AMBOS» in this file.
  - **And a third layer, in the card itself**: an open thread won over the platform lens but NOT over the
    «completo» profile, whose branch `return`s first — so with that profile selected `open` set `active_chat`
    and the card kept painting the same flat list. Everything downstream worked and the screen did not move,
    which no source-level assertion can see (node 4.98 RENDERS both profiles).
  - **VERIFIED LIVE on the restarted engine**: 5/5 phrasings («abre / ábreme / entra en / haz clic en el
    mensaje de Francisco», «abre el mensaje») produce `widget_data(mensajeria, open, {name:'Francisco'})` and
    the chat opens in the store; canvas-level shows («enséñame la mensajería», «abre la agenda») still route
    to `show_widget`. ⚠️ Measurement trap paid here: mutating the widget store from an EXTERNAL process makes
    the reads look flaky (the server holds its own cached db) — drive and read through the server, or the
    result says nothing.

- **What a pure show may RUN is decided by the ACTION, not by the words — and the lens phrases resolve before
  any model (V2-545, 2026-09-01)**: «Ábreme el Telegram» left the card unmoved, three live turns, while
  «muéstrame SOLO LOS MENSAJES de Telegram» worked — and the difference was an accident. V2-544's guard
  classified the object of a show verb by matching the text against the widget's manifest ALIASES, and
  mensajeria's aliases ARE its lens names (`whatsapp`, `telegram`, `correo`, `gmail`, `outlook`), so the terse
  form read as «show the card» and the longer one only passed because its extra words failed the match. The
  distinction is not in the phrasing; it is in the ACTION, and the widget is the one that knows.
  - **`widgets/actions.py::is_view` — a SECOND axis, orthogonal to FAST/CONFIRM/ESCALATE.** `classify` answers
    «how much friction does running this cost»; this one answers «is running it the same thing the operator
    asked for when they only asked to LOOK». Opt-in and EXPLICIT (`"view": true` per action): **nothing is
    inferred from the name**, because the same `open` is display-only in mensajeria (opens a chat) and a
    real-world side effect in navegador (loads a URL) — a name heuristic would be wrong in exactly the cases
    that matter. A widget that declares nothing keeps the old behavior. An action needing confirmation is never
    a view, whatever the manifest says.
  - **The rail does BOTH on a view action** — shows the card AND applies the view. That is what «ábreme el
    Telegram» means, and it dissolves the card-vs-inside ambiguity instead of guessing it. The discarded action
    now travels in the event: the previous version logged only the widget id, so three live turns of «Aquí lo
    tienes» over an unmoved card left no trace of WHAT had been thrown away, and the model was suspected before
    the guard was.
  - **Even with the guard fixed, the model still narrated the terse forms**: measured live, «Ábreme el Telegram»
    called NO tool and replied «Hecho, ya lo tienes filtrado a solo Telegram». So the deterministic layer takes
    them: the seed pack gains a **VERB × OBJECT grid** expanded at import into ordinary exact-match entries
    (bookkeeping, not understanding — nothing at match time gets smarter). The literal `show_widget` entries it
    now owns were REMOVED, or a fresh install and an upgraded one would disagree about what «abre el whatsapp»
    does. A view op run from the map brings the card up as well, and the loop is acquired BEFORE any emit so a
    run without one falls through WHOLE instead of half-executing.
  - **And the seed pack could not be upgraded at all**: `ensure_seeded` imported once per INSTALL («any seed row
    exists» = done), so a pack fixed later reached nobody — every engine kept the phrases of its first boot,
    including every cloud Machine. It imports once per pack VERSION now, inserting what is new and RETARGETING a
    phrase that is still an untouched shipped row; a row the operator disabled, or one the map learned, is never
    moved. Live: `433 entries · 11 retargeted`.
  - **The probe reported the mapped action and never RAN it** — right while the map only spoke canvas verbs (a
    show is meaningless headless), wrong the day it could drive a widget's DATA. With `execute` it now runs it
    and reports the hit only if it ran, the voice rail's contract. Eighth instance of «cablear en AMBOS».
  - **VERIFIED LIVE** (engine restarted): «ábreme el Telegram» · «ábreme el WhatsApp» · «muéstrame ahora el
    Telegram» · «enséñame el correo» · «muéstrame todos los mensajes» all resolve pre-LLM to
    `widget_data:mensajeria:show_view` with the lens applied in the store; «abre el mensaje de Francisco» still
    reaches `open{name}` (3/3 in isolation) and «abre la agenda» still goes to `show_widget`. ⚠️ Reading the
    store 1.2 s after a `backed` op reports the state BEFORE the owner applied it — the queue takes ~3 s, and a
    short sleep makes a working op look like a dead one.
  - **Left with the model on purpose**: a bare «vuelve a la lista principal» is genuinely ambiguous (`results`
    declares a `list` action meaning exactly that), and the pack's own doctrine keeps ambiguous whole utterances
    out. Nodes 2.1 and the actionmap node; disarms verified in both directions.

- **The messaging widget FOLLOWS the real apps instead of drifting from them (V2-546, 2026-09-01)**: reported
  live — he answered two WhatsApp messages from his own phone, came back to the widget, and they were still
  sitting there looking pending. Two structural facts behind it, both measured before touching anything.
  **(1) Every connector was wired INBOUND-ONLY.** The bridge saw his outgoing messages (Baileys delivers them
  as upserts with `fromMe:true`) and dropped them with an explicit `continue`; Telethon subscribed to
  `NewMessage(incoming=True)` only; email polled INBOX and never looked at flags. Read orders went widget → app
  and **nothing ever came back**. Every one of those signals was already on the wire; none was being read.
  **(2) There was NO conversation store** — `items` was the pending inbox and reading a message DELETED it, so
  opening a chat showed what was unread and nothing else, and the widget auto-closed the thread once everything
  was read because there was genuinely nothing left in it.
  - **`widgets/mensajeria/thread.py`** is the conversation: capped on THREE axes (per chat, per age, per number
    of chats — one JSON file rewritten on every save), ordered by TIME rather than arrival (an outbound message
    captured from the phone can reach us after a later inbound one, and a thread out of order reads as a
    different conversation), deduped by id, with a read watermark. **It lives in the widget package** because
    `data.py` may not import `connectors` while connectors already import `widgets` — the only placement where
    both sides read ONE copy of these rules.
  - **Neither `record_outbound` nor `apply_external_read` enqueues mark-read**: the app that just told us IS the
    source of truth, and echoing it back is a loop. Both are bounded by the platform's own watermark, so a chat
    cleared at 10:00 cannot hide a message from 10:05 — with a test for exactly that.
  - **Each transport is used at its real fidelity, and that is a statement about the transport, not a
    preference.** Telegram's read update is a `max_id`, resolved to that message's DATE and **DROPPED if it
    cannot be resolved** (not marking costs one stale row; marking too much hides unseen mail). WhatsApp only
    reports a per-chat COUNTER, so a read is queued only when it reaches ZERO — a partial drop cannot say WHICH
    messages were read. Email is the exact one: `\Seen` and `\Answered` answer per message, which is why the
    read signal carries `ids` as well as a watermark.
  - **The hazard that would have made this worse than the bug**: WhatsApp answers a history request with
    ORDINARY upserts, so un-tagged, "load previous" would have pushed a month of scrollback through triage and
    interrupted him about messages from weeks ago. The bridge marks the chats it just asked about and tags those
    upserts `history:true`.
  - **`open` resolves against conversations we HOLD, not only the pending list** — found by a failing test, not
    by reading: without it, answering someone from your phone made their chat **unopenable here**, because the
    inbox was the only index. The main list stays an INBOX on purpose; showing every recent chat there would
    turn a triage surface into a second messaging app.
  - Node 4.99, 23 cases, six disarms with each mutation ASSERTED before running, counterweights included (a
    message arriving after his reply is not swallowed; a chat with nothing at all still closes itself).
    ⚠️ **The RENDERING half of 4.98 caught what no source assertion could**: a backtick inside a CSS comment
    CLOSES the widget's template literal — `node --check` had passed earlier, before that comment existed.
  - Verified live on `3.16+c998220` (agent ⏻ stopped, no session): both connectors reconnected clean, the widget
    serves `thread_meta`, the manifest serves `load_more`, and the backed route returns its real veto instead of
    a bare `{"queued": true}`. **Real traffic NOT verified** — a reply from the phone, a Telegram read receipt
    and an email flag all need the operator to do it. Detail: `V2-546-the-widget-follows-the-real-app.md`.

- **A KNOWN phrase skips the model — the ACTION MAP (V2-539, 2026-09-01)**: the operator says «limpia la
  pantalla» / «abre el WhatsApp» twenty times a day, and every one of them was a full model turn. A short
  command whose meaning has already been verified does not need to be understood again. `nucleo/actionmap/`
  sits IN FRONT of the FlashBrain: one finalized utterance, normalized, looked up verbatim in a per-language
  table; a hit executes a direct action in SILENCE (the screen is the feedback) in 0.02–0.16 ms. Canonical doc:
  **`.meshkore/docs/modules/zaelar-action-map.md`**.
  - **It does not violate «no hardcoded, understand» (V2-095) because of what it may NOT do.** It matches the
    WHOLE utterance and nothing else — no keywords, no fuzzy distance, no stemming; it **never splits** a
    sentence («ponte a buscar un restaurante y abre el WhatsApp» goes to the model whole, the operator's own
    example); and **every** failure path falls through — unknown phrase, unresolvable target, undeclared
    data-op, no running loop, a broken index. `execute()` returning `False` is a routing decision, never an
    error. **When in doubt, the model.** Its certainty comes from the PROVENANCE of the row, not from string
    similarity. The unit is a phrase bounded by silence, so a chain of commands is N lookups and zero model
    calls — which is the workload that motivated it.
  - **Wired in BOTH channels through one module** (voice `nucleo.py::_run_inner`, guarded against a pending
    fragment chain, and `flash/probe.py::run_turn`), with a wiring guard in the testmap. The probe had to be
    taught to RUN the action and not merely report it: harmless while the map only spoke canvas verbs, a false
    green the day it could drive a widget's data (V2-545).
  - **The vocabulary is a CLOSED allowlist** (`executor.py`: show/close/close-all/panel/move/fullscreen +
    FAST-declared `widget_data`), executed through **the same emit funnels the model's own output uses** —
    never a parallel executor. Nothing destructive, content-carrying or credential-adjacent is representable,
    whatever a row says, and `validate()` refuses a bad seed **loudly at import** (`alert`): a module whose
    seeds silently fail to load is a module born dead. Named multi-step **workflows are deliberately not an
    action kind**.
  - **The pack upgrades; the operator's veto does not move.** `seeds/<lang>.json` ships with the repo and is
    imported once per pack VERSION (it used to be once per INSTALL, so a pack fixed later reached nobody —
    every engine, cloud Machines included, kept its first-boot phrases). New phrases are inserted and an
    UNTOUCHED shipped row is retargeted; a row the operator disabled, or one the map learned, is never
    rewritten. One install, one language: only the active language is indexed. Kill switches:
    `ZAELAR_ACTIONMAP=0` (first, off-only) + `actionmap.enabled`. DB access goes through the `memory/api.py`
    facade — the boundary guard refused the direct import, and the facade was the right answer.
  - **Which layer acted is a FIELD now, not an inference — and all three surfaces had been lying.** Ten real
    voice turns were served by the map while the viewer printed «FlashBrain» (it reads `engine`, which was not
    stamped), the Master printed «LLM», and **the Susurro said out loud «el cerebro rápido ejecutó
    correctamente cada orden»** over six turns with no model in them — an auditor reasoning about the wrong
    layer, whose repair would have gone to the model for something it never said. Now: `kind="actionmap"`
    (family `flash`), `engine`/`origin: "actionmap"` on every event (a model turn stamps `origin: "flash"`),
    `amap_ms` inside `pre_ms`, the causing PHRASE on every canvas order (close/move/panel dropped it), the
    Susurro's window naming map turns and its catalog telling it that a map fault is a `finding` with
    `area=routing`. Second surface (the Master) updated in the same pass, with a mirror guard that immediately
    caught three PRE-EXISTING drifts.
  - **`watch.py` measures what the map is MISSING** — a bus subscriber on `turn.completed` (the Susurro
    pattern) that marks a turn the model resolved with a single canvas action as a **candidate**, flagging
    whether the phrase is already in the table (an entry that exists and did not fire is a different problem).
    It observes only; nothing is promoted. ⚠️ **It was born blind to the probe channel**: `turn_detail` is one
    seam but each channel writes a different `decision` SHAPE (voice = flags, probe = a collapsed `action`), and
    a reader that knows one shape **fails by returning nothing**. Sixth instance of the parallel-implementation
    trap, and this time the docstring ASSERTED it covered both «for free». A live turn caught it; reading the
    code did not.
  - **Not built, on purpose**: `actionmap_define` + shadow-mode promotion + demotion (Phase 2), generated
    language packs (Phase 3), and workflows (out of scope). Until Phase 2 the table only grows at release time —
    so that the phase where the system teaches itself starts from measured evidence instead of intuition. Node
    2.41 (hits, misses, closed allowlist, both kill switches, both decision shapes, wiring in both channels);
    node 2.7 for the auditor knowing which layer acted. Live: 424 active `es` rows, 55 hits on the operator's
    engine.

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
