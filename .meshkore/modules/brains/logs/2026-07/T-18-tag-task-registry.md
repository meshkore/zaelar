---
id: T-18
title: "T-18 · registro de tasks para los tags cluster/cron del llm_processor"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-18 — Registro de tasks para tags cluster/cron (INI-006 · A5)

## Qué se hizo

`brains/hermes/llm_processor.py _widget_emit()` despachaba los tags `[[cluster.*]]` y `[[cron.*]]` con
`asyncio.create_task(...)` **sin guardar la referencia**: asyncio solo mantiene weak refs a las tasks, así que
el GC podía descartar la acción en vuelo — un `cluster.send` o un `cron.create` emitido por voz podía no
ejecutarse nunca, en silencio.

Fix: `_TAG_TASKS` (set a nivel de módulo) + `_spawn_tag_task(coro, label)` que registra la task (referencia
fuerte), la descarta en el done-callback y **loguea la excepción** si la acción falló (antes se perdía hasta el
"exception was never retrieved" del GC).

## Ficheros tocados

- `brains/hermes/llm_processor.py` — `_TAG_TASKS` + `_spawn_tag_task()`; los dos `create_task` de
  `_widget_emit` pasan por el registro.

## Verificación

- Test dirigido (scratchpad `test_t18.py`): la task queda registrada mientras corre y sobrevive un
  `gc.collect()`; se descarta al completar; una acción que lanza se descarta y loguea
  `"cron tag task failed: tag-boom"`.
- `make run-hermes` arranca sano (`/api/brain` → hermes, 0 errores en log).
