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

## Catalog coverage — 5 of 119 scenarios ever run (114 never run)

An unrun case is **not** a passing one. This is the walk's progress board.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 4 | 12 | 1 |
| 1 | us | 0 | 9 | 0 |
| 2 | es | 0 | 22 | 0 |
| 2 | us | 0 | 21 | 0 |
| 3 | es | 0 | 6 | 0 |
| 3 | us | 0 | 6 | 0 |
| 4 | es | 1 | 7 | 0 |
| 4 | us | 0 | 6 | 0 |
| 5 | es | 0 | 6 | 0 |
| 5 | us | 0 | 6 | 0 |
| 6 | es | 0 | 5 | 0 |
| 6 | us | 0 | 5 | 0 |
| 7 | es | 0 | 4 | 0 |
| 7 | us | 0 | 4 | 0 |

## Where the work on each failing case happens

One initiative per use case — that initiative IS the workspace for it, and it carries the transcript, the mechanism report and the reproduce command. Both folders are gitignored («ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.

| scenario | initiative (the workspace) | fix task |
|---|---|---|
| `quick-fact-opening-hours` | `.meshkore/roadmap/initiatives/V2-120-uc-quick-fact-opening-hours.md` | `.meshkore/modules/nucleo/tasks/T311-uc-quick-fact-opening-hours-fix.md` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-121-uc-remember-and-remind-deadline.md` | `.meshkore/modules/nucleo/tasks/T312-uc-remember-and-remind-deadline-fix.md` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-119-uc-restaurant-tonight-madrid.md` | `.meshkore/modules/nucleo/tasks/T310-uc-restaurant-tonight-madrid-fix.md` |
| `three-tasks-at-once` | `.meshkore/roadmap/initiatives/V2-118-uc-three-tasks-at-once.md` | `.meshkore/modules/nucleo/tasks/T309-uc-three-tasks-at-once-fix.md` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 2 | code, generic, web |
