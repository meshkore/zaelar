---
id: T-13
title: "T-13 · /api/hermes/update reinicia el agente Hermes compartido (no deja el binario viejo vivo)"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-13 — `/api/hermes/update` debe reiniciar el agente compartido (INI-006 · A1)

## Qué se hizo

`POST /api/hermes/update` paraba las sesiones de voz (`active.stop_all`) pero **no** el warm agent compartido
(`brains/hermes/runtime.py`), que no es una sesión de voz: tras el "✓" el proceso seguía corriendo el binario
**viejo**. Además `_acp_healthcheck()` arrancaba un **2º Hermes concurrente** desechable (un `HermesACP()`
nuevo) junto al compartido.

Fix en `brains/hermes/update_api.py`:

- En el stream del update, tras `active.stop_all`, se llama `runtime.shutdown_shared()` (off-loop con
  `asyncio.to_thread`) **antes** de lanzar `hermes update`.
- `_acp_healthcheck()` ahora usa `runtime.get_shared_acp()`: el health-check **ES** el arranque del nuevo agente
  compartido sobre el binario recién actualizado — si pasa, zaelar ya está corriendo el Hermes nuevo; si falla,
  emite el error con la versión previa y la instrucción de rollback (comportamiento existente).
- Si el propio `hermes update` falla, el agente compartido queda parado y se auto-repara perezosamente en el
  siguiente turno (`get_shared_acp` es self-healing) con el binario sin cambiar.

## Ficheros tocados

- `brains/hermes/update_api.py` — `shutdown_shared()` antes del update; `_acp_healthcheck()` sobre el runtime
  compartido en vez de un `HermesACP` desechable.

## Verificación

- Test dirigido (scratchpad `test_t13.py`: binario `hermes` falso + `HermesACP` instrumentado + agente
  compartido "viejo" sembrado): el viejo se para ANTES del subprocess de update; el health-check arranca un
  agente NUEVO que queda como `runtime._acp` (ningún stop posterior = no fue un desechable); SSE termina en
  `step: done · "updated and verified"`.
- `make run-hermes` arranca sano: `/api/brain` → hermes, `/api/hermes/status` → v0.17.0, 0 errores en el log.
