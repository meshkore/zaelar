---
epic: v2-colmena
title: zaelar v2 «Colmena» — entierro de Hermes + cerebro propio (FlashBrain + SlowBrain) + memoria central
status: in-progress
owner: ricart
branch: feat/v2-colmena
target_version: 1.0.0
created: 2026-07-09
updated: 2026-07-09
---

# EPIC v2 «Colmena» — plan maestro de migración

> **Fuente de verdad del DISEÑO**: los diagramas vivos en `/architecture` (pestañas Arquitectura ·
> FlashBrain · SlowBrain · Memoria · Widgets) + `.meshkore/docs/architecture/zaelar-memory.md`.
> **Fuente de verdad del CÓMO SE CONSTRUYE (orden + tareas)**: este EPIC y sus iniciativas V2-001→V2-010.
> Este documento NO duplica el detalle de diseño; enlaza a él.

## 1. Objetivo

Sustituir el cerebro **Hermes** (agente ACP externo, upstream vivo, `runtime.locked_ask`) por un **cerebro
propio de dos velocidades** que controlamos de punta a punta, con una **memoria central local** que también
es nuestra, y un **sistema nervioso de eventos** in-process. zaelar deja de depender de un binario externo
que hace `git pull` sobre sí mismo; pasa a ser un sistema que entendemos y podemos escalar.

Piezas del cerebro (ya diseñadas en los diagramas v2):

- **FlashBrain** (`nucleo/flash/`) — CÓDIGO PROPIO reflejo, sub-segundo. Router de input + cliente de modelo
  rápido (Ollama local / Grok AIMLAPI, **modelo por invocación**) + gestor de frontend/widgets + lanzador de
  procesos + escalado. Enchufado al motor de voz como provider `livekit.agents.llm.LLM`.
- **SlowBrain** (`nucleo/dispatch.py` + `nucleo/memory_agent.py` + `nucleo/agentes/`) — deliberación async =
  constelación de agentes **Claude Code** (sustituible por Codex tras la interfaz `CodeAgent`, **modelo por
  invocación**). Dispatcher + agente de MEMORIA ★ + agentes de trabajo (web/código/otros).
- **Loop orquestador** (`nucleo/loop.py`, ~1 Hz) — hilo del tiempo: tareas programadas, 🔥 chispas
  (pensamiento espontáneo), dispara el consolidador ("sueño"), reporta por voz+UI.
- **Memoria central** (`memory/`, top-level) — SQLite `zaelar.db` (WAL) + sqlite-vec + FTS5 + RRF + grafo +
  olvido-por-peso + refuerzo + consolidador. La escriben FlashBrain, el agente de memoria y los widgets;
  la lee el retriever (ruta caliente, ms). **Absorbe `files/`** (capa episódica).
- **Sistema Nervioso** (`bus/`, top-level) — pub/sub in-process (generalización de `voice/observer.py`) +
  log durable en SQLite + puente SSE al frontend. Transporte **HÍBRIDO**: llamadas directas en la ruta
  caliente (voz), eventos para lo async/fan-out. **NADA de Kafka/broker.**

## 2. Estrategia: strangler-fig (construir en blanco → integrar → retirar)

1. **Construir en blanco** las piezas nuevas (bus, memoria, nucleo) SIN cablearlas al camino de voz.
   El sistema sigue arrancando con `BRAIN=duo`/`hermes` como hoy — cero regresión.
2. **Integrar** cada pieza detrás de un flag (`BRAIN=nucleo`), en paralelo a lo viejo. Se verifica en vivo
   antes de tocar el default.
3. **Retirar** Hermes/duo al FINAL (V2-009), solo cuando el cerebro nuevo está verificado. El entierro es la
   última fase, no la primera.

**Invariantes de la migración:**
- Lo viejo sigue funcionando hasta que lo nuevo esté verificado (tests + arranque limpio en `BRAIN=nucleo`).
- El contrato agnóstico del motor de voz se conserva: `tag_protocol`, `speech`, `proactive`, `brain_notes`,
  `prompt`, `health_state`. El cerebro nuevo entra por la MISMA costura (provider LLM) por la que entra `duo`.
- Los raíles de vuelta (`voice/proactive.notify()` + `voice/brain_notes.push()`) NO cambian.
- El core NUNCA depende de Docker. Memoria = SQLite embebido, cero infra.
- No push sin OK del operador. Un commit por tarea cerrada.

## 3. Destino de cada módulo (fate table)

| Módulo | Destino | Nota |
|---|---|---|
| `voice/engine/` | **REUSA** | STT/TTS/AgentSession/turnos/VAD/barge-in intactos. Solo cambia el provider LLM. |
| `voice/` (contrato) | **REUSA** | tag_protocol · speech · proactive · brain_notes · prompt · health_state. `observer.py` se generaliza en `bus/`. |
| `widgets/` | **REUSA + amplía** | passive + backed intactos. Ahora los widgets ESCRIBEN a `memory/` y se suscriben al `bus/`. |
| `server/` | **REUSA + reshape** | El lifespan monta bus + memoria (cola/escritor/consolidador) + loop de nucleo + supervisor. Se retiran rutas Hermes. |
| `frontend/` | **REUSA** | Se quita el banner de update de Hermes y el polling `/api/hermes/*`. |
| `tester/`, `harness/` | **REUSA + adapta** | Oleadas de INI-013 re-apuntadas al cerebro v2. |
| `connectors/` | **RESHAPE → stateless** | Solo leen + publican eventos al `bus/`. Triaje y store SALEN de aquí. |
| `config/` | **RESHAPE → v2** | Nuevo esquema; fuera settings de Hermes/duo; dentro routing de modelos (fast + code-agent) y flags de conector. |
| `brains/` | **RETIRA (último)** | hermes (ACP/cron/update) + duo + reasoner + providers hermes/duo. Sustituido por `nucleo/`. |
| `files/` | **PLIEGA en `memory/`** | La capa episódica de memoria absorbe la bandeja de bytes + el índice. |
| **`nucleo/`** | **NUEVO** | Cerebro v2: FlashBrain + SlowBrain + loop + escalado. |
| **`memory/`** | **NUEVO (top-level)** | Memoria central. Substrato compartido, NO parte del cerebro. |
| **`bus/`** | **NUEVO (top-level)** | Sistema nervioso: pub/sub in-process + log durable + SSE. |

## 4. Mapa de fases e iniciativas (orden cronológico = orden de ejecución)

| # | Iniciativa | Fase | Depende de | Qué deja funcionando |
|---|---|---|---|---|
| V2-001 | Cimientos: `bus/` + esqueleto `nucleo/` + config v2 (aditiva) | 0 · andamiaje | — | Arranca igual que hoy; bus con tests; observer sobre bus. |
| V2-002 | Memoria v2 — núcleo (`memory/`, SQLite+vec+fts+retriever+olvido) | 1 · memoria | V2-001 | `memory.query/write/state` standalone, testeado; sin cerebro aún. |
| V2-003 | Memoria — integración (`files/`→episódica, migración Hermes, widgets escriben) | 1 · memoria | V2-002 | Paste/archivo → resumen buscable; estado sembrado; widgets vuelcan. |
| V2-004 | FlashBrain — orquestación refleja + provider `nucleo` | 2 · flash | V2-002, V2-003 | `BRAIN=nucleo` responde voz sub-seg, widgets, recall — SIN Hermes. |
| V2-005 | Loop orquestador (~1 Hz) + chispas + consolidación + cron | 2 · flash | V2-004 | Proactividad y "sueño" propios; se retira el cron nativo de Hermes. |
| V2-006 | `CodeAgent` + SlowBrain dispatcher + agente de MEMORIA ★ | 3 · slow | V2-002, V2-004 | Deliberación async con Claude Code, contexto mínimo desde memoria. |
| V2-007 | SlowBrain — agentes de trabajo + escalado FlashBrain→SlowBrain | 3 · slow | V2-006 | Tareas largas (web/código) escalan, corren async, vuelven por voz+UI. |
| V2-008 | Conectores STATELESS + triaje dentro del widget mensajería | 4 · conectores | V2-003, V2-006 | WA/TG solo publican eventos; el widget tría con CodeAgent interno. |
| V2-009 | **Entierro de Hermes**: cutover `BRAIN=nucleo`, retirar `brains/`, config v2, docs/diagramas | 5 · entierro | V2-004→V2-008 | Clone limpio → `make run` → nucleo; cero Hermes; diagramas "construido". |
| V2-010 | Seguridad v2 + tester v2 + benchmarks | 6 · endurecer | V2-007, V2-009 | Deny-tools para input no confiable hacia CodeAgent; oleadas re-apuntadas. |
| V2-011 | FlashBrain: latencia sub-segundo (memoria fuera del camino caliente) | 6 · endurecer | V2-004 | Turno de charla ~1s como en v1; retriever de memoria fuera del turno. |
| V2-012 | Observabilidad: columna de agente + modelo del agente en el timeline | 7 · observabilidad | V2-006, V2-007 | El `/debug` muestra qué agente (Cloud Code) y con qué modelo (Haiku/Opus) corre cada proceso. |
| V2-013 | Memoria que APRENDE: CORAZÓN de escritura (LLM local destila píldoras dato+metadatos, decide dónde/importancia, no duplica) — LLM al escribir, queries directas al leer | 8 · memoria viva | V2-002, V2-003, V2-006 | El estado se puebla y persiste entre sesiones; adiós "lobotomía"; recuerdos como píldoras curadas, no chat crudo. |
| V2-019 | Memoria — el SUEÑO (consolidación CORTO→LARGO + olvido) + aislamiento del tester + limpieza de la BD | 8 · memoria viva | V2-013 | El CORTO se poda solo; el tester no contamina el perfil real; la BD queda limpia. |
| V2-014 | Visualizador del mapa de memoria (estado/corto/largo, grafo, tiempo real) | 8 · memoria viva | V2-013 | Icono 🧠 junto a Reset → mapa gráfico de la memoria formándose en vivo. |
| V2-015 | Gate de atención: el micro abierto no actúa sobre lo que no le hablan | 9 · atención | V2-004 | zaelar ignora la voz ambiente; solo actúa en turnos dirigidos; cierra/para siempre atendido. |
| V2-016 | Control de atención UI (icono robot) + detección inteligente de interlocutor | 9 · atención | V2-015 | Toggle 🤖 escucha-siempre↔wake-word; en 'always' distingue si le hablas a él o a otros. |
| V2-022 | Búsqueda web COMPARTIDA (`nucleo/websearch.py`) — primitivo model-agnóstico para ambos cerebros, proveedor por capas calidad-primero | 6 · endurecer | V2-004, V2-011 | El modelo decide buscar (function-calling). FlashBrain: `web_search` (dato+síntesis, en el turno, off-loop). SlowBrain: `WebSearch`/`WebFetch` nativos para informes. Proveedor por capas: respuesta-IA (Perplexity/Tavily) → Brave → DDG gratis (auto-upgrade por key). Navegar marketplace = el navegador (distinto). Arregla el "Pensando…" eterno. |
| V2-025 | Widgets: frontera DATOS vs CÓDIGO — data-op del FlashBrain vs gate de irreversibilidad (NO de escalado) (`widgets/actions.py`) | 6 · endurecer | V2-004, V2-017 | Toda acción declarada es data-op que el FlashBrain hace ÉL MISMO (arregla `add_meeting` `safe:false` que auto-escalaba a un agente de código y se colgaba >6 min); el SlowBrain queda SOLO para CREAR/MODIFICAR código. `safe` (sobrecargado) → modos FAST/CONFIRM/ESCALATE; irreversible pide OK sin escalar (`widgets/confirm.py`). Guía de uso (`usage`) obligatoria + gate que valida `actions`↔`apply_action`. |
| V2-026 | Widgets: data-ops FIABLES por function-calling (tool `widget_data`) + resolución de referencias a items en lenguaje natural (`widgets/refs.py`) | 6 · endurecer | V2-025 | El modelo rápido no emitía el tag inline `[[widget.data]]` de forma fiable ni conocía los ids (inventaba taskId). Fix: data-ops por TOOL (como web_search); el modelo pasa el item en lenguaje natural y `refs.py` lo resuelve al id REAL (fuzzy, campo del manifest, pregunta si ambiguo); brief expone `items ahora`; fechas/horas del habla normalizadas + fecha explícita en el prompt; ack hablado. Respeta la gobernanza V2-025. |
| V2-034 | Widgets: ejecución en BACKGROUND con ciclo declarado (`widgets/background.py`) | 6 · endurecer | V2-004, INI-016 | Un widget puede seguir trabajando OFF-SCREEN en su periodo (`"background":{"every":"1m"}`, mín 1s): passive → `data.py:tick(ctx)` en hilo (off hot-path), backed → `tick` al owner. Refresca + vuelca a memoria por `ctx.remember(slot=…)` (data.py sigue stdlib) → la voz responde fresco sin abrir la tarjeta (mensajería backed; meteo-soria passive). Aislado, arrancado en el lifespan; gate del generador valida `background`+`tick()`. |
| V2-027 | Prompt del FlashBrain: **ESTADO compuesto + petición, ~30 líneas** (`nucleo/flash/prompt.py` + `memory.compose_state()`) | 6 · endurecer | V2-004, V2-011, V2-026 | El system prompt se recomponía cada turno y era ENORME (~280 líneas: persona inglesa de `voice/prompt.py` + `_FAST_RULES` ~75 líneas duplicando las tools + `for_brain()` volcando TODOS los widgets/acciones/payloads/items + briefs de conector). Saturaba al modelo (olvidaba acciones, `web_search` de más). Fix: **[ESTADO compuesto] + [petición]**. El ESTADO lo compone la MEMORIA (`memory.compose_state()`, compartido por los dos cerebros): **A** misión (vive en `state.mission`, sembrada desde `langs`, no en un `.py` inglés) + **B** situacional + **C** convo reciente SINTETIZADA. Cada cerebro añade su capa TERSA de recursos; el "cuándo usar cada tool" vive en `router.TOOLS`. Items/coach/conectores solo si su widget está ABIERTO. Frontera dura CANVAS (`[[show/close]]`, tag) vs DATOS (`widget_data`, tool). Cacheado off-turno (V2-011 intacto). Verificado con input LIMPIO (probe al modelo): ~30-45 líneas, 6 rutas correctas. |

> **Nota (2026-07-09):** la antigua «regla de oro del entierro» (que exigía verificación EN VIVO con micrófono
> antes de V2-009) queda **RETIRADA por decisión explícita del operador**. La verificación por tests + arranque
> limpio en `BRAIN=nucleo` es suficiente para proceder al entierro; el operador autoriza cerrar V2-009/V2-010
> sin esperar prueba de voz humana. Todo el trabajo vive en `feat/v2-colmena` (reversible por git; sin push).

## 5. Ejecución autónoma nocturna (cómo "queda todo programado")

El estado del roadmap ES la cola: las **tareas del estándar** (`modules/<m>/tasks/T-NN-*.md`, `status: next`),
enlazadas a su iniciativa por `initiative:` y encadenadas por `depends_on` en el orden de la tabla §4. Dos vías
de ejecución, mismo orden: el **Roadmap Orchestrator** (Run All en el Architect) o el bucle `/loop`.

- El bucle se dispara con **`/loop <intervalo> <prompt>`** (skill `loop`) o con el prompt de relevo
  `.meshkore/roadmap/HANDOFF-v2-colmena.md` en una sesión limpia.
- **Cada iteración**: (1) arranca/verifica zaelar → (2) coge la **primera tarea `status: next`** cuyas
  `depends_on` estén en `done` (orden de la tabla §4) → (3) la construye en código → (4) verifica (tests +
  arranque; reinicia si tocó `.py`) → (5) pone la tarea en **`status: done`** (`completed_at`/`commit_shas`) y
  añade una línea fechada en la **Bitácora** de su iniciativa → (6) `git add -A && git commit` (co-autoría;
  **NO push**) → (7) repite.
- Una iniciativa pasa a `status: done` cuando **todas sus tareas** están en `done` y su **Aceptación** se cumple.
- Al cerrar la última (V2-010) el EPIC pasa a `done` y se bumpea `version` a `1.0.0`.
- **No adivinar decisiones del operador**: si una tarea topa con una decisión de producto abierta, se anota
  como *abierta* en la bitácora y se salta a la siguiente tarea ejecutable; no se bloquea la noche entera.

## 6. Riesgos y qué se pierde al dejar Hermes (honesto)

- **Se pierde**: memoria madura de Hermes (años de tooling), su cron nativo probado, su gestión ACP de turnos,
  y el ecosistema de skills/federación. Lo reconstruimos: memoria (V2-002/V2-003), cron (V2-005), turnos (ya los
  gobierna LiveKit desde INI-012), federación (queda el bridge vendorizado de WhatsApp, muere el "upstream vivo").
- **Nuevo riesgo de seguridad grande**: con SlowBrain, input NO confiable (peers de cluster, mensajes entrantes,
  contenido web) puede llegar a un **CodeAgent con terminal/ficheros**. Se aborda en V2-010 con deny-tools para
  turnos no confiables, allowlist, `scan_outbound` heredado y sandbox/cwd/timeout en `CodeAgent.run`.
- **Latencia**: FlashBrain debe cerrar el turno sub-segundo. El modelo por invocación permite local (Ollama) o
  Grok/AIMLAPI según hardware; se mide en V2-010 (benchmarks).

## 7. Índice de iniciativas

- [V2-001 — Cimientos v2](initiatives/V2-001-cimientos-bus-nucleo.md)
- [V2-002 — Memoria núcleo](initiatives/V2-002-memoria-nucleo.md)
- [V2-003 — Memoria integración](initiatives/V2-003-memoria-integracion.md)
- [V2-004 — FlashBrain](initiatives/V2-004-flashbrain.md)
- [V2-005 — Loop orquestador](initiatives/V2-005-loop-orquestador.md)
- [V2-006 — CodeAgent + SlowBrain dispatcher](initiatives/V2-006-slowbrain-codeagent.md)
- [V2-007 — SlowBrain agentes](initiatives/V2-007-slowbrain-agentes.md)
- [V2-008 — Conectores stateless](initiatives/V2-008-conectores-stateless.md)
- [V2-009 — Entierro de Hermes](initiatives/V2-009-entierro-hermes.md)
- [V2-010 — Seguridad + tester v2](initiatives/V2-010-seguridad-tester-v2.md)
- [V2-011 — FlashBrain latencia](initiatives/V2-011-flashbrain-latencia.md)
- [V2-012 — Observabilidad agente+modelo](initiatives/V2-012-observabilidad-agente-modelo.md)
- [V2-013 — Memoria que aprende](initiatives/V2-013-memoria-que-aprende.md)
- [V2-014 — Visualizador de memoria](initiatives/V2-014-visualizador-memoria.md)
- [V2-015 — Gate de atención](initiatives/V2-015-gate-de-atencion.md)
- [V2-016 — Control de atención UI](initiatives/V2-016-control-atencion-ui.md)
- [V2-018 — Gobierno de procesos (Reset duro)](initiatives/V2-018-gobierno-de-procesos.md)
- [V2-019 — Memoria: sueño + aislamiento del tester](initiatives/V2-019-memoria-sueno-aislamiento.md)
- [V2-031 — Memoria de fidelidad máxima (embedding SOTA local + auto-mejora continua)](initiatives/V2-031-memoria-fidelidad-maxima.md)
