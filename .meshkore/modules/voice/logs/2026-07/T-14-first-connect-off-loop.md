---
id: T-14
title: "T-14 · primer connect sin stall — get_shared_acp() vía asyncio.to_thread"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-14 — Evitar el stall del event loop en el primer connect (INI-006 · A2)

## Qué se hizo

En `voice/agent.py` (`run_bot`, rama `BRAIN=hermes`) el primer connect llamaba `get_shared_acp()` **síncrono
dentro de la corutina**: arrancar el warm agent son ~2-3s de subprocess + handshake ACP, y durante ese tiempo el
event loop entero (SSE, widgets, otra pestaña, el resto del connect) quedaba congelado.

Fix: `hermes_acp = await asyncio.to_thread(get_shared_acp)`. La función ya era thread-safe (`_start_lock` en
`brains/hermes/runtime.py` — la bridge de MeshKore ya la llamaba desde worker threads), así que el cambio es
solo sacar el boot del loop.

## Ficheros tocados

- `voice/agent.py` — una línea + comentario en la rama hermes de `run_bot`.

## Verificación

- Test dirigido (scratchpad `test_t14.py`): boot REAL del agente compartido vía `asyncio.to_thread` con un
  heartbeat concurrente midiendo stalls del loop → boot 3.34s, **peor stall del loop 1ms** (antes: 3.3s de
  bloqueo total).
- `make test` OK (imports + prompt); `make run-hermes` arranca sano (`/api/brain` → hermes, 0 errores).
