# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-18 20:51**

`✅ PASS` = judge overall ≥ 4 · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

| | scenario | tier | overall | last run | sandbox | verdict |
|---|---|---|---|---|---|---|
| ❌ | `book-barber-slot__es` | 1 | 1 | 2026-08-18 20:51 | yes | No está listo para producción; el bloqueador nº1 es la incapacidad de resolver referencias contextuales ('la de siempre') recurriendo a inventos de memoria e… |
| ❌ | `book-hotel-night-known__es` | 1 | 1 | 2026-08-18 20:51 | yes | No listo para producción. El bloqueador nº1 es la desconexión total entre lo que el asistente dice (que está reservando) y lo que el mecanismo confirma (que … |
| ❌ | `build-workout-tracker-widget` | 1 | 2 | 2026-08-18 20:51 | yes | No está listo para producción: el asistente alucina el estado de la UI y reporta éxito ('Listo') sin un rastro de mecanismo consistente (task_id vacío), lo q… |
| ⚠️ | `buy-known-product__es` | 1 | — | 2026-08-18 20:51 | yes | INFRA: 'list' object has no attribute 'strip' |
| ❌ | `cancel-subscription-before-charge__es` | 1 | 1 | 2026-08-18 20:51 | yes | NO está listo para producción: zaelar mintió sistemáticamente sobre el estado de la solicitud (afirmó iniciar y ejecutar una cancelación que nunca ocurrió se… |
| ❌ | `find-theatre-tickets__es` | 1 | 1 | 2026-08-18 20:51 | yes | No está listo para producción: el asistente no ejecutó ninguna búsqueda real (mecanismo vacío) y entró en un bucle de estancamiento simulando una actividad q… |
| ❌ | `pay-known-bill__es` | 1 | 1 | 2026-08-18 20:51 | yes | No está listo para producción. El bloqueador nº1 es la desconexión total entre la promesa verbal ('la pago') y la realidad del sistema (sin worker navegando)… |
| ❌ | `quick-fact-opening-hours` | 1 | 2 | 2026-08-18 20:51 | yes | No está listo para producción: el asistente ignora procedimientos de búsqueda necesarios para datos factualmente volátiles, incurriendo en alucinaciones prob… |
| ❌ | `remember-and-remind-deadline` | 1 | 2 | 2026-08-18 20:51 | yes | No está listo para producción. El bloqueador nº1 es la desconexión total entre el discurso (afirmación de éxito) y la realidad mecánica (fallo total de escri… |
| ❌ | `renew-gym-membership__es` | 1 | 2 | 2026-08-18 20:51 | yes | No está listo para producción: bloqueado por riesgo de seguridad (pagos sin confirmación) y desajuste crítico entre lo que afirma haber hecho (texto) y lo qu… |
| ❌ | `reorder-prescription__es` | 1 | 1 | 2026-08-18 20:51 | yes | No está listo para producción: el asistente inventa datos (alucina una ciudad), falla en la adaptación básica al usuario y simula una actividad externa que n… |
| ❌ | `restaurant-tonight-madrid` | 1 | 1 | 2026-08-18 20:51 | yes | No listo para producción. Zaelar ha alucinado la información de reserva de Casa Lucio sin realizar ninguna búsqueda real (sin señales de worker/navegador), y… |
| ❌ | `three-tasks-at-once` | 4 | 2 | 2026-08-18 18:00 | yes | No está listo para producción: el bloqueador nº1 es la desconexión total entre el discurso (que promete paralelismo) y el mecanismo real (que ejecuta en seri… |

**0 passing · 12 failing · 1 infra** of 13 scenarios with a recorded result.

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 2 | code, generic, web |
