# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-18 18:25**

`✅ PASS` = judge overall ≥ 4 · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

| | scenario | tier | overall | last run | sandbox | verdict |
|---|---|---|---|---|---|---|
| ✅ | `build-workout-tracker-widget` | 1 | 5 | 2026-08-18 18:20 | yes | Está listo para producción: el entregable (widget) es observable y funcional, aunque el flujo de espera fue ruidoso. |
| ❌ | `quick-fact-opening-hours` | 1 | 2 | 2026-08-18 18:25 | yes | No está listo para producción: el modelo responde sobre hechos dinámicos sin verificar su fuente y omite partes de la pregunta, lo cual es un riesgo crítico … |
| ❌ | `remember-and-remind-deadline` | 1 | 1 | 2026-08-18 18:20 | yes | NO está listo para producción: el bloqueador nº1 es la 'alucinación de cumplimiento' (el asistente dice que hizo algo que el mecanismo confirma que no hizo),… |
| ❌ | `restaurant-tonight-madrid` | 1 | 1 | 2026-08-18 18:20 | yes | No está listo para producción: el asistente falló el bloque principal de éxito al no realizar ningún intento de reserva observable y alucinar la política del… |
| ❌ | `three-tasks-at-once` | 4 | 2 | 2026-08-18 18:00 | yes | No está listo para producción: el bloqueador nº1 es la desconexión total entre el discurso (que promete paralelismo) y el mecanismo real (que ejecuta en seri… |

**1 passing · 4 failing · 0 infra** of 5 scenarios with a recorded result.

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 2 | code, generic, web |
