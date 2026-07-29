---
id: V2-006
title: SlowBrain — interfaz CodeAgent + dispatcher + agente de MEMORIA ★
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [nucleo, memory, config]
depends_on: [V2-002, V2-004]
wall_order: 6
created: 2026-07-09
updated: 2026-07-09
commit_shas: [c26e1aeb44e9b468014466a910ca214733e68d20, d2b26903c08e3fb5ce6addd0e32816225bace365]
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

Construir el **SlowBrain**: la deliberación async como constelación de agentes **Claude Code**, detrás de una
interfaz `CodeAgent` **sustituible** (Codex mañana), con **modelo por invocación**. En esta iniciativa: la
interfaz + el dispatcher (compone el prompt dinámico) + el **agente de MEMORIA ★** (da SOLO lo necesario). Los
agentes de trabajo y el cableado del escalado llegan en V2-007. Ver pestaña **SlowBrain** de `/architecture`.

## Qué se construye

### 1. Interfaz `CodeAgent` (sustituible, modelo por invocación)
- `nucleo/agentes/base.py` — `CodeAgent.run(spec)` con `spec = {prompt, model, tools, cwd, timeout}`.
  **El modelo va en el spec, NUNCA en env global** (concurrencia de sesiones).
- `nucleo/agentes/claude_code.py` — adaptador por defecto: `claude -p` headless (patrón ya usado en
  `widgets/generator.py`). Captura stdout/estructura, timeout, cwd aislado.
- `nucleo/agentes/codex.py` — adaptador alternativo (misma firma; stub verificable). Selección por config.

### 2. Dispatcher (`nucleo/dispatch.py`)
- Compone el **PROMPT DINÁMICO** = contexto mínimo (del agente de memoria) + la tarea → al agente que toque.
- Recibe el `escalate(task)` del FlashBrain (por el bus, `escalate.requested`).
- Un despacho a la vez por dominio donde tenga sentido (evitar carreras); resto en paralelo.

### 3. Agente de MEMORIA ★ (`nucleo/memory_agent.py`)
- Da **SOLO lo necesario** para el prompt (no vuelca todo): heurística barata el 90% (score rel+rec+imp del
  retriever) + un router LLM barato solo si es ambiguo.
- Es el ÚNICO que escribe a `memory/` desde el SlowBrain (resultados, hechos, resúmenes) — vía la cola async.
- Mantiene la tabla `state` junto al consolidador.

## Tareas

- [x] `nucleo/agentes/base.py` — `CodeAgent` (ABC) + dataclass `AgentSpec{prompt,model,tools,cwd,timeout}` + tests.
- [x] `nucleo/agentes/claude_code.py` — adaptador `claude -p` (headless, timeout, cwd) + test con un prompt trivial.
- [x] `nucleo/agentes/codex.py` — adaptador stub con la misma firma + selección por config.
- [x] `nucleo/dispatch.py` — compone prompt dinámico (memoria + tarea), consume `escalate.requested` del bus + tests.
- [x] `nucleo/memory_agent.py` — recall de contexto mínimo (heurística + router barato) + escritura a memoria + tests.
- [x] Config v2: selección de code-agent (claude|codex) + defaults de modelo por tipo de tarea.
- [x] Prueba: `dispatch(task)` → memory_agent da contexto mínimo → un Claude Code corre con modelo del spec → resultado.

## Aceptación

- `CodeAgent.run(spec)` corre un Claude Code headless con el modelo del spec (no de env) y devuelve resultado estructurado.
- El dispatcher compone un prompt = contexto mínimo del agente de memoria + tarea, y elige agente.
- El agente de memoria devuelve SOLO lo relevante (no todo el store) y escribe resultados a memoria.
- Cambiar el code-agent a `codex` por config no rompe la firma (stub responde).

## Riesgos

- Arrancar Claude Code por tarea es lento (segundos) → por eso es SlowBrain (async, off-voz). El FlashBrain nunca
  espera a un CodeAgent en el hot path.
- Coste: modelo por invocación permite un modelo barato por defecto para trabajo mecánico.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T77 — `nucleo/agentes/base.py`: la interfaz `CodeAgent` (ABC) que desacopla el SlowBrain del proveedor. `RunSpec{model,tools,cwd,timeout,deny_tools,env}` (== `{prompt,model,tools,cwd,timeout}` del diseño, con `prompt` posicional para que un mismo spec de política sirva a N prompts) + `RunResult{ok,output,error,meta}` + `run(prompt, *, spec)` abstracto. Reglas duras codificadas: **modelo POR INVOCACIÓN** (`spec.model`, nunca env global), `deny_tools=True` para input NO confiable (V2-010), `tools` = allowlist. Cubierto por `nucleo/agentes/test_agentes.py` (ABC no instanciable, defaults).
- 2026-07-09 · T78 — `nucleo/agentes/claude_code.py`: adaptador REAL sobre `claude -p` headless. `async` de verdad (`asyncio.create_subprocess_exec` + `wait_for(timeout)`, no bloqueante) porque el SlowBrain corre off-voz en el loop del server; prompt por STDIN; `--model spec.model` (modelo por invocación), `--allowedTools` por política (deny_tools → NINGUNA; si no, `spec.tools` o `Read` por defecto), `--output-format json` → parseo del campo `result`. `_find_claude` PROPIO (no acopla el SlowBrain al circuito de `widgets/`). Nunca lanza: CLI ausente/timeout/exit≠0 → `RunResult(ok=False)`. Verificado contra un **CLI falso** (registra argv+stdin): modelo por invocación, deny-tools=sin tools, timeout, exit≠0.
- 2026-07-09 · T79 — `nucleo/agentes/codex.py`: segundo adaptador (misma firma, `codex exec`, modelo por invocación, `--sandbox read-only` si deny_tools) — sin CLI de Codex devuelve un `RunResult(ok=False)` LIMPIO (cambiar de proveedor no rompe la firma ni el dispatcher). `nucleo/agentes/__init__.py::get_agent(provider)` = **factoría por config** (lee `config/v2 › code_agent.provider`; proveedor desconocido → default con aviso). Test: codex sin CLI responde sin lanzar; `get_agent()` elige por env/config.
- 2026-07-09 · T82 — `config/v2.py`: sección `code_agent` ampliada con `model_{memory,web,code}` (defaults de modelo POR TIPO DE TAREA) + helper `code_agent_model(kind)` (cascada `model_<kind>`→`model`→default del proveedor) + env fallbacks (`CODE_AGENT_MODEL_{MEMORY,WEB,CODE}`). Aditivo (convive con la config actual). Cubierto por `config/test_v2.py` (invariante de no-fuga de secretos intacta).
- 2026-07-09 · T81 — `nucleo/memory_agent.py`: el agente de MEMORIA ★. `compose_context(prompt,budget)` da SOLO lo necesario = `memory.state()` (perfil, SIEMPRE) + recall RRF (`memory.query`) truncado al presupuesto; **heurística barata el 90%** (el score del retriever ordena) + **router LLM barato** (modelo POR INVOCACIÓN, best-effort, se salta sin credencial) SOLO si el recall es ambiguo (`_is_ambiguous`: query cortísima o resultados flojos < 0.35). `remember(item)` = **ÚNICO escritor** a `memory/` desde el SlowBrain (write por cola + `state_patch`); `maintain_state()` para el perfil. 6 tests verdes (`nucleo/test_memory_agent.py`).
- 2026-07-09 · T80+T83 — `nucleo/dispatch.py`: el dispatcher. `dispatch(Task)` → `compose_context` (memoria) → **PROMPT DINÁMICO** [contexto+tarea] → `agentes.get_agent()` con **modelo POR INVOCACIÓN** del tipo de tarea (`code_agent_model(kind)`) + política de tools por confianza (`deny_tools=not trusted`, V2-010) → `memory_agent.remember` del resultado. Nunca lanza. `run_listener(stop)` consume `escalate.requested` del bus (FlashBrain→SlowBrain), despacha y marca `escalate.finish` (cableado al lifespan + entrega por voz/UI = V2-007). 6 tests verdes (`nucleo/test_dispatch.py`, incl. integración T83: contexto de memoria en el prompt, modelo del spec no de env, deny-tools a input no confiable, resultado guardado, listener resuelve el escalado del bus).
- 2026-07-09 · **V2-006 CERRADA** — Aceptación cumplida: (a) `CodeAgent.run(spec)` corre un Claude Code headless con el **modelo del spec** (no de env) y devuelve resultado estructurado (`RunResult`) — verificado contra un CLI falso (`--model` en argv, prompt por STDIN, JSON parseado); (b) el dispatcher compone prompt = contexto mínimo del agente de memoria + tarea y elige agente por config; (c) el agente de memoria devuelve SOLO lo relevante (estado + recall, no todo el store) y escribe resultados a memoria (único escritor); (d) cambiar el code-agent a `codex` por config no rompe la firma (stub responde `RunResult(ok=False)` sin lanzar). Suite `nucleo/ bus/ memory/ config/ connectors/messaging/ voice/` = **205 passed** (0 regresiones); arranque en vivo `/api/brain`=`duo` intacto (SlowBrain standalone, aún NO cableado a la voz/lifespan — eso es V2-007/V2-009). **state.json = artefacto del daemon MeshKore** (no editable a mano de forma persistente; el daemon reconcilia `status`/`completed_at`/`commit_shas` al releer los .md con las tareas T77–T83 [x] + esta línea; no hay generador local ejecutable). Siguiente: **V2-007 — SlowBrain agentes de trabajo + escalado** (`depends_on: [V2-006]` satisfecho).
