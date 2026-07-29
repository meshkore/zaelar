---
id: W-004
title: "W-3 · progreso de generación audible + journal de jobs que sobrevive reinicios"
status: done
priority: high
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# W-004 — Progreso de generación + supervivencia a reinicios (INI-006 · W-3)

## Qué se hizo

Los ~84s del `claude -p` (`generator.py`) solo mostraban spinner — al minuto parece muerto — y un reinicio del
server a media generación **perdía el job sin rastro**: el brain había dicho "lo estoy preparando" y nada
aterrizaba nunca (causa raíz nº1 de W-001).

1. **Progreso audible** (`server_api._run_generator()`): los `/generate` y `/modify` corren por un wrapper que,
   cada `WIDGETS_PROGRESS_SECS` (def. 30s), emite una nota de progreso vía `voice/proactive.notify` — la primera
   hablada, las siguientes solo UI (toast) para no dar la brasa por voz. El resultado sigue volviendo al brain
   como nota `[SISTEMA]` (`_report_to_brain`, ya existía).
2. **Journal de jobs en vuelo** (`generator.py`): `widgets/_data/_jobs.json` (escritura atómica, lock) — cada
   create/modify se registra al arrancar (`_job_start`) y se borra al terminar (`_job_end`, en `finally`). No es
   un store de widget: es el diario del generador (nombre con `_` que `safe_id()` nunca puede producir).
3. **Resume al arrancar** (`server_api.resume_interrupted_generations()`, colgado del lifespan en
   `server/__init__.py` con referencia fuerte en `app.state`): drena el journal y
   - **create** → si la carpeta llegó a completarse y valida, solo notifica; si no, descarta el folder a medias
     y **relanza** la generación (con progreso y reporte al brain);
   - **modify** → NO se re-ejecuta a ciegas (el edit pudo quedar a medias y el backup de rollback murió con el
     proceso viejo): nota `[SISTEMA]` para que el brain/operador lo re-pida.

## Ficheros tocados

- `widgets/generator.py` — journal `_jobs.json` + `_job_start/_job_end/take_pending_jobs`; create/modify lo usan.
- `widgets/server_api.py` — `_run_generator()` (progreso), rutas generate/modify sobre él,
  `resume_interrupted_generations()`; knob `WIDGETS_PROGRESS_SECS`.
- `server/__init__.py` — task de resume en el lifespan (strong ref en `app.state`).

## Verificación

- Test dirigido (scratchpad `test_w3.py`, agente fake lento + cadencia 0.4s): ≥2 notas de progreso emitidas
  durante la generación; el journal contiene el job en vuelo y queda vacío al terminar; resume con journal
  sembrado → el create interrumpido se relanza con su spec original, el modify interrumpido deja nota al brain,
  el journal se drena y los widgets existentes quedan intactos.
- `make run-hermes` sano; el resume de arranque corre limpio (no-op sin jobs pendientes).
