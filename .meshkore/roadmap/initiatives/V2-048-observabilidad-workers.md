# V2-048 — Observabilidad RICA de los Brain Workers (DÓNDE + QUÉ usa cada paso)

**Estado:** Fase 1 + Fase 2 CONSTRUIDAS y pusheadas · **Fecha:** 2026-07-17 · **Ancla:** EPIC-v2-colmena · V2-038
(Brain Workers) · V2-044 (trazabilidad)

> ⚠️ Los DOS primeros commits rotularon el asunto **V2-047 por error** (número ya usado por «robustez-sesión
> 23:15»); el código, los tests y esta iniciativa usan **V2-048**. No es un force-push por dos palabras de historia.

## Detonante (operador, 2026-07-16)

Mirando la columna de observabilidad durante una tarea de worker (reservar cita de ITV), el operador vio que se
lanzaba un proceso y se veían sus pasos, **pero los pasos eran genéricos**: «consultando la memoria…», «ejecutando
un paso…», «buscando cita…». No se veía **DÓNDE** ocurre cada cosa (¿navegador? ¿web? ¿memoria? ¿código?) ni **QUÉ
usa** en cada paso (qué tool, qué URL, qué query, qué modelo). Cita literal:

> «la herramienta o el widget o el proceso de cloud code con su idea o lo que sea tiene que reflejarse también en la
> observabilidad… no solo como tarea, sino dónde está, dónde se está haciendo todo eso y qué está usando en cada una
> de esas tareas… Piénsate muy bien qué más podemos añadir… todo lo que podemos ir guardando. Eso al final es
> fundamental para luego ir arreglando y mejorando el sistema.»

## Diagnóstico

El stream-json del worker (`nucleo/workers/claude_session.py::_map`) recibe cada `tool_use` **entero** — nombre de
la tool + `input` completo (`command`, `url`, `query`, `file_path`, ref del navegador…) — y lo **colapsaba en una
frase coarse** vía `_tool_phase()`, TIRANDO toda la estructura. El `result` traía `usage` (tokens) y `cost` y también
se **descartaban** (`session.py` solo guardaba `summary`+`ok`). Los puentes (`nav_cli`/`act_api`, `mem_cli`,
`worker_bridge`) **no emitían casi nada** a observabilidad (solo `show/close` de widget). El frontend (`DebugPanel.js`)
YA sabe pintar `model` (chip), `prompt_tokens`/`completion_tokens` (chip de tamaño), `layer` (chip), `span`
(anidado worker:N) y el chip de trace — el trabajo era **backend: dejar de tirar los datos y emitirlos con los
campos que el panel ya entiende**.

## Solución construida

### Fase 1 — el backbone (claude_session + session)
Cada `tool_use` emite ahora, además de la fase coarse (que sigue alimentando `rec.phase` → prompt «PROCESOS DE
FONDO»), un **`step` estructurado** `{where, action, target}`:

- **`claude_session._tool_step(name, input)`** — clasifica el LUGAR y extrae el OBJETIVO concreto:
  - tools nativas: `WebSearch`→web(query) · `WebFetch`→web(url) · `Read`→archivo(path) · `Write`/`Edit`→código(path)
    · `Grep`/`Glob`→archivo(pattern).
  - `Bash` acotado a un puente → se ATRIBUYE por el comando: `nav_cli`→**navegador** (verbo + URL / ref `[12]` /
    texto tecleado) · `mem_cli`→**memoria** (recall query / remember `[slot]`) · `worker_bridge`→**zaelar**
    (ask/act/say) · `agent_report`→**None** (no duplica la fase legible de hbnote).
- **`session.py::_emit_step`** mapea el `where` a una fila con la **CATEGORÍA por lugar** (`_PLACE`): memoria→`memory`
  (púrpura, filtro Memoria) · navegador→`navegador` (filtro Navegador) · web→`search` · código/archivo/zaelar/
  sistema→`task`. Así los pasos del worker **se integran en los MISMOS filtros** que los eventos de primera clase,
  no en un cajón aparte. La fase coarse pasa a `quiet=True` (no duplica fila) pero `rec.phase` se mantiene.
- **Fila de nacimiento** (`_emit_meta_row`, kind `worker_start`): `worker · <backend>` + **modelo** (chip) + **capa**
  (chip) → qué MOTOR/MODELO conduce la tarea.
- **Fila final** (chip `end`): **tokens** input/output (chip de tamaño) + **coste USD** + modelo.

Todo va por `observer.emit` → se **PERSISTE** (timeline/session jsonl) además de verse en vivo. Sella trace/span por
el ContextVar ambiente (el `run()` del worker corre dentro de la task trazada). +3 tests (`test_workers.py`).

### Fase 2 — el RESULTADO del navegador (act_api)
El `step` da la INTENCIÓN (navigate → url) desde el comando; lo que **solo sabe el browser** es el RESULTADO. Tras
cada `navigate/click/type/scroll` `widgets/navegador/act_api.py` emite una fila **«🧭 página»** con `título · url`
resultantes, y tras `extract` una fila **«🧭 resultados»** con el nº de anuncios. Label distinto del step → sin
colisión con el flood-dedup del kind `navegador`. Trace/span del worker dueño de la pestaña vía
`dispatch.record_by_nav_task` (el handler HTTP corre en el loop del server sin contexto de trace).

## Qué se ve ahora (ejemplo ITV)
```
worker · claude_code   [haiku-4.5] [web]   El operador necesita reservar ITV…
🧠 memoria   recall «ubicación del operador»
🧭 navegador navigate → https://sitios.dgt.es/cita-itv
🧭 página    Cita previa ITV · sitios.dgt.es/cita-itv
🧭 navegador type [7] «Soria»
🧭 resultados 8 estaciones/resultados en la página
↩ zaelar     ask «¿matrícula del coche?»
fin  $0.0142   [1420 in · 380 out]
```

## Futuro (no bloqueante)
- **mem_cli recall → nº de hits / top-slot** (hoy solo la intención; el resultado vive en la memory API).
- **worker_bridge act use_tool web_search → resultado** (query ya visible como intención).
- **assistant text deltas** como «pensando» opt-in (hoy deliberadamente NO se emiten, monólogo interno).
- **chip de tool** explícito en la fila del step (hoy `tool` viaja en `extra`, se guarda pero no se pinta).

## Ficheros
`nucleo/workers/claude_session.py` (`_tool_step`/`_bash_step`/`_nav_target` + `step`/`model` en `_map`) ·
`nucleo/workers/session.py` (`_emit_step`/`_emit_meta_row`/`_PLACE` + tokens/coste en la fila final) ·
`nucleo/dispatch.py` (`record_by_nav_task`) · `widgets/navegador/act_api.py` (`_emit_nav`) ·
`nucleo/workers/test_workers.py` (+3 tests). Doc: `zaelar-observability.md §Pasos del worker`.
