---
id: W-002
title: "W-1 · data.py fuera del event loop — threadpool acotado + timeout duro + respuesta degradada"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# W-002 — Aislar la ejecución de `data.py` del event loop del servidor (INI-006 · W-1 / T-17)

## Qué se hizo

`widgets/server_api.py` ejecutaba `view_data()` / `apply_action()` / `coach_context()` **síncronos dentro de
rutas async**, en el mismo event loop que el pipeline de voz: un widget con un fetch lento (contrato: hasta 6s)
o un bucle infinito bloqueaba el servidor entero — zaelar se quedaba mudo. Solo `/generate` y `/modify` iban
off-loop.

Fix (materializa el invariante (a) — *un widget nunca puede romper el resto del sistema*):

- **Threadpool dedicado y acotado** (`_POOL`, 4 workers, `widget-data`), separado del executor por defecto.
- **Timeout duro** (`WIDGETS_DATA_TIMEOUT`, def. 8s — el contrato de widgets capa los fetches a 6s) vía
  `asyncio.wait_for`; al vencer → **respuesta degradada** `{"error": "widget '<id>' timed out …"}` (el frontend
  ya trata `data.error` cerrando solo ese widget).
- **Excepciones del hook → degradadas** también (`{"error": …}` en vez de 500).
- El **import del módulo** (`widgets/<id>/data.py`) también corre dentro del worker thread — el código top-level
  de un data.py puede ser tan lento/roto como sus hooks.
- Semántica preservada: sin data module → 404; `view_data()` sin kwarg `q` → fallback; `/context` degrada a
  `{"context": ""}`.

Límite conocido y aceptado: un hook colgado retiene su thread hasta retornar (los threads no se matan), pero el
pool es acotado y dedicado → el peor caso es la capa de widgets degradada, nunca el loop de voz bloqueado. El
"ideal" de INI-006 (subprocess pool con límites CPU/mem) queda como mejora futura si hiciera falta enforcement
de stdlib-only (relacionado con la Parte 2).

## Ficheros tocados

- `widgets/server_api.py` — `_POOL`/`_TIMEOUT`/`_MISSING`, `_call_widget()`, `_run_widget()`; rutas
  `/widgets/{wid}/data`, `/widgets/{wid}/action`, `/widgets/{wid}/context` reescritas sobre el pool.

## Verificación

- Test dirigido (scratchpad `test_w1.py`, widget desechable con `view_data()` que duerme 30s y
  `apply_action()` que lanza): con el widget colgado, `/widgets` responde en **10ms** (loop libre); el colgado
  degrada a `{"error": "... timed out after 8s"}` a los 8.0s; el hook que lanza devuelve
  `{"error": "... RuntimeError: boom"}` (no 500); módulo inexistente → 404; `/context` degrada a `""`.
- `make run-hermes` arranca sano (`/api/brain` → hermes, warm agent listo); `/widgets/agenda/data` y
  `/widgets/agenda/context` responden en ~15ms por la ruta nueva.
