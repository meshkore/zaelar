# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-18 22:40**

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
| ❌ | `quick-fact-opening-hours` | 1 | 2 | 2026-08-18 22:40 | yes | No está listo para producción; ha fallado gravemente en mecanismo al omitir la búsqueda web requerida, confundiendo rapidez con invención de datos. |
| ❌ | `remember-and-remind-deadline` | 1 | 2 | 2026-08-18 22:40 | yes | No está listo para producción: el bloqueador nº1 es la incapacidad para persistir datos y programar alertas (Fallo de Ingest/Ejecución), lo que convierte al … |
| ❌ | `renew-gym-membership__es` | 1 | 2 | 2026-08-18 20:51 | yes | No está listo para producción: bloqueado por riesgo de seguridad (pagos sin confirmación) y desajuste crítico entre lo que afirma haber hecho (texto) y lo qu… |
| ❌ | `reorder-prescription__es` | 1 | 1 | 2026-08-18 20:51 | yes | No está listo para producción: el asistente inventa datos (alucina una ciudad), falla en la adaptación básica al usuario y simula una actividad externa que n… |
| ❌ | `restaurant-tonight-madrid` | 1 | 1 | 2026-08-18 22:40 | yes | No está listo para producción: el sistema falló en bloquear tiempos imposibles, sufrió una alucinación severa de contexto y no ejecutó la acción fallback (ll… |
| ❌ | `three-tasks-at-once` | 4 | 2 | 2026-08-18 22:40 | yes | No está listo para producción. El bloqueador nº1 es la incapacidad del mecanismo para mantener y mostrar una verdadera concurrencia de tareas de distinta nat… |

**0 passing · 12 failing · 1 infra** of 13 scenarios with a recorded result.

## Catalog coverage — 13 of 119 scenarios ever run (106 never run)

An unrun case is **not** a passing one. This is the walk's progress board.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 12 | 12 | 0 |
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
| `book-barber-slot__es` | `.meshkore/roadmap/initiatives/V2-130-uc-book-barber-slot-es.md` | `.meshkore/modules/nucleo/tasks/T318-uc-book-barber-slot-es-fix.md` |
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-131-uc-book-hotel-night-known-es.md` | `.meshkore/modules/nucleo/tasks/T319-uc-book-hotel-night-known-es-fix.md` |
| `build-workout-tracker-widget` | `.meshkore/roadmap/initiatives/V2-125-uc-build-workout-tracker-widget.md` | `.meshkore/modules/nucleo/tasks/T313-uc-build-workout-tracker-widget-fix.md` |
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-126-uc-cancel-subscription-before-charge-es.md` | `.meshkore/modules/nucleo/tasks/T314-uc-cancel-subscription-before-charge-es-fix.md` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-132-uc-find-theatre-tickets-es.md` | `.meshkore/modules/nucleo/tasks/T320-uc-find-theatre-tickets-es-fix.md` |
| `pay-known-bill__es` | `.meshkore/roadmap/initiatives/V2-128-uc-pay-known-bill-es.md` | `.meshkore/modules/nucleo/tasks/T316-uc-pay-known-bill-es-fix.md` |
| `quick-fact-opening-hours` | `.meshkore/roadmap/initiatives/V2-120-uc-quick-fact-opening-hours.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-121-uc-remember-and-remind-deadline.md` | `` |
| `renew-gym-membership__es` | `.meshkore/roadmap/initiatives/V2-129-uc-renew-gym-membership-es.md` | `.meshkore/modules/nucleo/tasks/T317-uc-renew-gym-membership-es-fix.md` |
| `reorder-prescription__es` | `.meshkore/roadmap/initiatives/V2-127-uc-reorder-prescription-es.md` | `.meshkore/modules/nucleo/tasks/T315-uc-reorder-prescription-es-fix.md` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-119-uc-restaurant-tonight-madrid.md` | `` |
| `three-tasks-at-once` | `.meshkore/roadmap/initiatives/V2-118-uc-three-tasks-at-once.md` | `` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | generic, web |
