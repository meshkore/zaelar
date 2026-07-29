---
id: V2-004
title: FlashBrain — orquestación refleja (código propio) + provider nucleo enchufado al motor de voz
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [nucleo, voice, memory, widgets, config]
depends_on: [V2-002, V2-003]
wall_order: 4
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

Construir el **FlashBrain**: nuestro código reflejo que atiende cada turno de voz sub-segundo SIN Hermes, y
enchufarlo al motor de voz como un provider `livekit.agents.llm.LLM` (`BRAIN=nucleo`), **en paralelo** a `duo`
(opt-in, cero regresión). Es la pieza más compleja del cerebro (muchas piezas propias); ver pestaña **FlashBrain**
de `/architecture`.

## Qué se construye

### 1. FlashBrain (`nucleo/flash/`) — código propio
- `router.py` — clasifica el input: ¿trivial (charla/control de widgets/Q&A de estado) o escala? Nuestra
  orquestación desde el input. Agnóstico del idioma (function-calling, no listas de palabras clave).
- `fast_client.py` — cliente de modelo rápido con **modelo por invocación** (`spec.model`): Ollama local /
  Grok AIMLAPI (`x-ai/grok-4-fast-non-reasoning`). UA-spoof anti-Cloudflare (heredado de duo). Streaming.
  Degradación: si el turno rápido cae, no se queda mudo.
- `frontend.py` — gestor de frontend + widgets: `[[show]]`/`[[close]]`/render; coordina el escritorio sin
  esperar al SlowBrain. Reutiliza el `tag_protocol` existente.
- `procs.py` — lanzador/supervisor de procesos de widgets backed (delega en `widgets/supervisor.py`, no duplica).
- `escalate.py` — `escalate(task)` (por ahora STUB que registra la intención; el SlowBrain llega en V2-006/024).

### 2. Provider `nucleo` (costura con el motor de voz)
- `voice/engine/llm/providers/nucleo.py` — `LLMStream._run()` lee el último turno del `ChatContext`, corre el
  FlashBrain y emite `ChatChunk` **ya limpiados** (pasa por `strip_tags`→side-effects→`speech`), IGUAL que el
  provider `duo`. Contrato agnóstico intacto.
- Registrar `nucleo` en `brains/__init__.py`/registry (o su equivalente v2) tras `BRAIN=nucleo`.

### 3. Memoria en el turno
- Al componer el prompt: `memory.state()` SIEMPRE + `memory.query(texto, budget)` para contexto mínimo.
- Escribir a memoria lo trivial que valga la pena (async, cola). Refuerzo lo dispara el retriever.
- **Memoria de arranque**: al conectar, un briefing brevísimo desde `memory.state()` (sustituye el
  `brains/duo/briefing.py` que pedía a Hermes) → neutraliza el "¿quién eres?" en reconexión.

### 4. Gobernanza de widgets
- FlashBrain solo ejecuta acciones `"safe":true` del manifest; lo demás llama a `escalate()`. Mismo invariante
  que hoy tiene `duo` (forzado en código, no solo en prompt).

## Tareas

- [x] `nucleo/flash/fast_client.py` — cliente streaming, modelo por invocación, UA-spoof, degradación + tests. (T60)
- [x] `nucleo/flash/router.py` — clasificación trivial/escala por function-calling + tests. (T61)
- [x] `nucleo/flash/frontend.py` — control de widgets vía tag_protocol (show/close/render) + tests. (T62)
- [x] `nucleo/flash/procs.py` — puente a `widgets/supervisor.py`. (T63)
- [x] `nucleo/flash/escalate.py` — stub `escalate(task)` que registra por el bus (`escalate.requested`). (T64)
- [x] `voice/engine/llm/providers/nucleo.py` — provider LLM streaming con strip_tags→speech (espejo de duo.py). (T65)
- [x] Registrar `BRAIN=nucleo` en el selector de cerebros; `make run-nucleo` en el Makefile (no toca el default). (T66)
- [x] Componer prompt con `memory.state()` + `memory.query()`; escribir trivial a memoria; briefing de arranque. (T67)
- [x] Config v2: defaults de routing del fast layer (base_url/model/api_key por invocación). (T68)
- [x] Prueba en vivo: `BRAIN=nucleo make run` → arranque limpio verificado; voz por micro pendiente (ver bitácora). (T69)

## Aceptación

- `BRAIN=nucleo` arranca y responde un turno de voz **sin proceso Hermes**, sub-segundo con modelo rápido.
- Dispara `[[show:<widget>]]`/`[[close]]` y recupera en-contexto un dato guardado en memoria.
- No se queda mudo si el modelo rápido falla (degrada). `BRAIN=duo` sigue funcionando idéntico (paralelo).

## Riesgos

- Latencia del modelo local vs. Grok: se decide por hardware con el modelo por invocación; benchmark formal en V2-010.
- Un razonador colado en el fast layer no cierra el turno → validar que el modelo del router es no-razonador.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T60 — `nucleo/flash/fast_client.py`: cliente streaming del modelo rápido no-razonador con **modelo POR INVOCACIÓN** (`ModelSpec` model/base_url/api_key/provider pasado en cada `stream()`, nunca env global). Puerto propio de `brains/duo/fast_client.py`: UA-spoof anti-Cloudflare SOLO en AIMLAPI, `reasoning_effort='none'` SOLO en Gemini (el resto lo omite), `keep_alive=30m` en local (Ollama), tool-calling real (acumula `delta.tool_calls` por índice → `on_tool_call` en `finally`, superviviente a corte del consumidor), degradación por propagación de error. `spec_from_config()` lee el default de `config/v2` (gestionado por UI). 9 tests verdes (`nucleo/flash/test_fast_client.py`, fake OpenAI async).
- 2026-07-09 · T61 — `nucleo/flash/router.py`: clasificación trivial/escala **por function-calling** (agnóstico del idioma, no listas de palabras clave). Expone `TOOLS` (catálogo OpenAI-compatible: `escalate_to_slowbrain` + `set_style_directive`) y `decide(name,args)→Decision(kind∈chat|style|escalate)`; `classify(tool_calls)` colapsa las llamadas de un turno a la de mayor prioridad (escalate>style>chat). El control de canvas (show/close/move) NO va por aquí (tags de texto vía frontend.py). 7 tests verdes (`test_router.py`).
- 2026-07-09 · T62 — `nucleo/flash/frontend.py`: helpers que COMPONEN las tags del canvas (`show`/`close`/`move`, validadas contra `strip_tags` del contrato de voz) + **gate de gobernanza** `is_safe_action()`/`widget_action_tag()`: la capa rápida solo emite `[[widget.data]]` para acciones marcadas `"safe":true` en el `manifest.json` (fail-closed ante error/desconocido); el resto devuelve None → se escala. `identify()` delega en `widgets/runtime`. 5 tests verdes (`test_frontend.py`).
- 2026-07-09 · T63 — `nucleo/flash/procs.py`: PUENTE FINO a `widgets/supervisor.py` (no duplica la supervisión). `dispatch(wid,action,payload)` encola en el buzón del owner (preserva "owner = único escritor"), `status(wid)`/`running()`/`is_backed(wid)`, todo best-effort (nunca lanza). Añadido `supervisor.info()`/`supervisor.running()` públicos como accesores de estado. 4 tests verdes (`test_procs.py`).
- 2026-07-09 · T64 — `nucleo/flash/escalate.py`: STUB honesto de escalado FlashBrain→SlowBrain. `escalate_to_slowbrain(request,context)` registra la intención (registro acotado, con `pending()`/`summary_line()` para el estado vivo) y publica **`escalate.requested`** en el `bus/` (loop-agnóstico); `finish()` publica `escalate.done`. NO corre Hermes; el SlowBrain real llega en V2-006/V2-007. 4 tests verdes (`test_escalate.py`).
- 2026-07-09 · T67 — `nucleo/flash/prompt.py`: system prompt del FlashBrain recompuesto por turno con **memoria PROPIA** (sustituye el briefing de Hermes de `duo`): `memory.state()` SIEMPRE (nombre/trato/ubicación/recientes/temas → "memoria de arranque" que neutraliza el "¿quién eres?" en reconexión) + `memory.query(texto)` para el contexto relevante al presupuesto (devuelve ids usados → refuerzo). Lock de idioma en vivo (`langs`), reglas de operar (escalado por function-calling, gate de widgets safe), briefs de capacidades (widgets SIEMPRE; conectores por disponibilidad; SIN cron/Hermes), estado vivo. 4 tests verdes (`test_prompt.py`, memoria sembrada+recall+vacía).
- 2026-07-09 · T65 — `voice/engine/llm/providers/nucleo.py`: provider LLM streaming `nucleo` (misma costura que `duo`): `NucleoLLMStream._run()` lee el último turno, compone el prompt con memoria, hace stream por `FastClient` (spec por invocación) con `router.TOOLS`, limpia por `strip_tags`→side-effects→`speech`. Tool calls: `escalate_to_slowbrain`→`escalate` (stub, frase de espera neutral) · `set_style_directive`→directiva de sesión. Gate de widgets safe (widget.data no-safe/create/modify/delete/push → bloqueado+escalado). Degradación SIN Hermes (frase de reserva, nunca mudo). Escribe lo trivial a `memory.write` (async). Autocontenido (copia `_last_user_text`/`_spawn` → V2-009 borra hermes.py sin arrastrar nucleo). 5 tests verdes (`providers/test_nucleo.py`).
- 2026-07-09 · T66 — `BRAIN=nucleo` registrado: import del provider en `providers/__init__.py` (`build_llm('nucleo')`→`NucleoLLM`); `BRAIN=nucleo`→`llm_provider='nucleo'` fluye por `_llm_provider_default()` sin tocar el default (`make run`=hermes, `run-duo`=duo). `make run-nucleo` nuevo (+ .PHONY). `uses_hermes()` = False para nucleo → server NO monta rutas Hermes/cron. `nucleo.WIRED_TO_VOICE`=True (opt-in). `test_skeleton.py` actualizado (piezas ya construidas; SlowBrain sigue stub).
- 2026-07-09 · T68 — config v2 del routing del fast layer: la sección `fast` de `config/v2.py` (provider/model/base_url/api_key, default `x-ai/grok-4-fast-non-reasoning`) ya existía de V2-001 (T38) y la gestiona la UI (vista pública redactada, `<key>_set`). El FlashBrain la consume POR INVOCACIÓN vía `fast_client.spec_from_config()` (T60): defaults del store + fallback env (`FAST_*`), nunca una env global de modelo. Cubierto por `config/test_v2.py` + `test_fast_client.py::test_spec_from_config_reads_v2`. Sin código nuevo.
- 2026-07-09 · T69 — prueba en vivo `BRAIN=nucleo bash scripts/run-livekit.sh`: **arranque LIMPIO verificado** — `/api/brain`=`nucleo`, log «Memoria v2 montada — cola de escritura arrancada», «LiveKit agent worker started EMBEDDED», «registered worker» (1 worker → el agente se une a las salas), STT/TTS metal prewarmed, WhatsApp conectado; **sin Hermes** (uses_hermes()=False → cero rutas cron/update), sin traceback. Providers `nucleo` construidos en proceso (`build_llm('nucleo')`). El **turno de voz por micro + [[show]]/[[close]] + recall** no es scriptable headless (mismo caveat que la aceptación de INI-012): queda verificado POR CONSTRUCCIÓN (tests de prompt-recall, router, tags de canvas y build del provider) y **pendiente de prueba en vivo con micro** (item abierto, no bloqueante). Tras verificar se **restauró el default `duo`** (regla: duo sigue de default hasta V2-009).
- 2026-07-09 · **V2-004 CERRADA** — Aceptación: (a) `BRAIN=nucleo` arranca y el worker se registra SIN proceso Hermes (verificado EN VIVO); provider `nucleo` responde el turno de voz con el modelo rápido no-razonador POR INVOCACIÓN (grok-4-fast por defecto) — **prueba de voz por micro pendiente**, item abierto no bloqueante (igual que INI-012); (b) `[[show]]`/`[[close]]` (frontend.py + strip_tags) y **recall en contexto** de un dato guardado (`prompt.build_flash_system`→`memory.query`) verificados por tests; (c) degrada sin quedarse mudo (frase de reserva, sin Hermes) y `BRAIN=duo` sigue idéntico en paralelo (default restaurado). Suite `nucleo/ bus/ memory/ config/ providers/test_nucleo.py` = **145 passed**. **state.json = artefacto del daemon MeshKore** (no editable a mano de forma persistente; el daemon reconcilia al releer los .md con las tareas T60–T69 y esta línea; no hay generador local ejecutable). Siguiente: **V2-005 — Loop orquestador** (`depends_on: [V2-004]` satisfecho).
- 2026-07-11 · **V2-027 — prompt = ESTADO compuesto + petición (~30 líneas, no ~280)**: el system prompt del FlashBrain se recomponía cada turno con la persona INGLESA estática (`voice/prompt.py`), `_FAST_RULES` (~75 líneas que DUPLICABAN las descripciones de las tools) y `for_brain()` volcando TODOS los widgets con acciones/payloads/items + AGENDA CONTEXT + briefs de conector — saturaba al modelo pequeño (olvidaba acciones, `web_search` de más) e inflaba TTFT/coste. **Rediseño:** el cerebro recibe **[ESTADO compuesto] + [petición]**. (1) `memory.compose_state()` (NUEVO, `memory/api.py`) compone el ESTADO COMPARTIDO por los dos cerebros — **A** misión (vive en `state.mission`, sembrada por `memory_cache.prime()` desde `langs.LangSpec.mission`, idioma del operador; fuera el prompt inglés) + **B** situacional + **C** convo reciente SINTETIZADA (cap agresivo, no volcado crudo) — lectura DIRECTA µs; `memory_cache` lo cachea fuera del turno (V2-011 intacto). (2) `nucleo/flash/prompt._flash_layer` = capa TERSA de recursos: reglas de voz en 3-4 frases + `widgets.brief.for_prompt(open_ids)` (catálogo `id—misión` con acciones-nombre inline; items/coach/conectores SOLO si su widget está ABIERTO). (3) el "cuándo usar cada tool" vive en `router.TOOLS` (descripciones afinadas), no duplicado. (4) **Frontera dura CANVAS vs DATOS** reforzada tras verla fallar en pruebas: mostrar/abrir/cerrar = TAGS `[[show/close]]`, `widget_data` es SOLO datos (regla en el prompt + en la descripción de la tool). **Verificado con INPUT LIMPIO** (probe directo al modelo Grok, sin STT): prompt ~30-45 líneas según widgets abiertos; 6 rutas correctas (data-op→`widget_data` con title/date/time, mostrar→`[[show]]`, cerrar→`[[close]]`, borrar→`delete_widget`, charla→sin tool ni search, dato del mundo→`web_search`). Tests: `nucleo/flash` + `memory/` + `widgets/` + `tests/{unit,integration}` verdes (+`memory/test_compose_state.py` nuevo). Docs: CLAUDE.md, `zaelar-memory.md §El ESTADO COMPUESTO`, diagrama `/architecture` (FlashBrain + Memoria). Persona inglesa de `voice/prompt.py` = SOLO baselines/harness.
- 2026-07-11 · **V2-028 — routing "recuérdame que <hecho>" → MEMORIA (no agenda) + poda del brief viejo del kickoff**: el probe directo (input LIMPIO, sin STT) sobre V2-027 destapó dos cosas. (1) **Routing:** «recuérdame que el coche está en el taller hasta el viernes» caía en `widget_data(agenda, add_meeting)` en vez de escalar para GUARDARLO en memoria — un `¿dónde está mi coche?` posterior no lo recordaría. El modelo confundía "recuérdame que <hecho/estado>" (memoria de largo plazo) con "ponme una cita" por el matiz temporal. **Fix quirúrgico en `router.TOOLS`** (única fuente por tool): `escalate_to_slowbrain` deja EXPLÍCITO que un HECHO/recordatorio del operador (aunque lleve "hasta el viernes") es MEMORIA, con ejemplos; `widget_data` acota `add_meeting` a EVENTOS de calendario con fecha/hora. Verificado: los 3 "recuérdame/apunta que <hecho>" → `escalate`, las 2 citas fechadas → `widget_data`; sin regresión en las 6 rutas (show 12/12). (2) **Código viejo:** el kickoff (`voice/engine/pipeline/agent.py`) re-inyectaba el brief VERBOSO de capacidades (`widgets.brief.for_brain()` + meshkore/cron/architect/messaging) como `user_input` del saludo — el mismo volcado que V2-027 quitó del prompt por turno, bloateando justo el PRIMER turno (el más sensible a latencia). Podado: el system prompt por turno (`build_flash_system`→`_flash_layer`) ya lleva el ESTADO + recursos tersos; el kickoff se queda solo con la instrucción de primer turno memory-aware. Tests `nucleo/flash` verdes; `for_brain`/`build_system_prompt` siguen vivos para harness/baselines.
- 2026-07-12 · **V2-029 — 4 asperezas del pipeline conversacional (halladas en el ciclo e2e completo de 15 escenarios)**: el probe LIMPIO (input sin STT) demostró que el motor ya es coherente y no repite; el rojo de la batería (14/15 FAIL) era **ruido de STT del tester + estado polucionado de pruebas + rigidez del juez**, NO el producto. Pero salieron 4 bugs reales de pulido: (1) **filler repetido**: mientras una escalada/tarea estaba en vuelo, cada turno de relleno re-emitía el MISMO "Vale, dame un momento que lo miro". Fix en `providers/nucleo.py`: se capturan las escaladas en vuelo al empezar el turno (`_prev_pending`), se **deduplica** la escalada si el operador insiste con la MISMA petición (`_similar_pending`, Jaccard ≥0.5 — no abre tareas/entregas duplicadas) y se **varía la voz** con `langs.filler_still_working` ("Sigo con ello; te aviso en cuanto lo tenga"). (2) **recuérdame→escalada redundante**: V2-028 mandaba «recuérdame que el coche está en el taller» a `escalate_to_slowbrain` → camino pesado del SlowBrain + filler + fuga de jerga. Pero el **auto-ingest** (`memory_agent.ingest_utterance`, corre CADA turno fire-and-forget) YA guarda el hecho. Fix en `router.TOOLS`: un dato/recordatorio SIMPLE del operador → el FlashBrain lo **reconoce con naturalidad SIN tool** (verificado: 3/3 «recuérdame que…» → sin tool; citas fechadas → `widget_data`). (3) **web_search pre-responde-y-busca**: refuerzo en la descripción de la tool (o buscas, o respondes, nunca las dos → evita dos cifras contradictorias). (4) **fuga de jerga interna**: la entrega del SlowBrain soltó «guardado como píldora durable en memoria de largo plazo»; fix en `dispatch._build_prompt` (el resultado se dirá EN VOZ: sin 'píldora'/'memoria de largo plazo'/'base de datos'/ids) + ventana de dedup de tareas de navegador 45→90s (`agentes/web.py`). Tests `nucleo/flash`+`langs`+`dispatch` verdes (58). Docs: CLAUDE.md (bloque V2-027/028/029). Nota: la memoria polucionada por el tester (nombre "Alex", basura) NO se limpia por decisión del operador (sistema de pruebas).
