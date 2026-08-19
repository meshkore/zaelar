# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-19 19:46**

`✅ PASS` = judge overall ≥ 4 · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

| | scenario | tier | overall | last run | sandbox | verdict |
|---|---|---|---|---|---|---|
| ✅ | `book-barber-slot__es` | 1 | 4 | 2026-08-19 01:51 | yes | El comportamiento de zaelar es correcto: no inventó nada, pidió los datos que faltaban y se detuvo en el muro con claridad; el bloqueador nº1 para cerrar el … |
| ❌ | `book-hotel-night-known__es` | 1 | 2 | 2026-08-19 18:56 | yes | No está listo para producción. El bloqueador nº1 es la desconexión total entre el reporte verbal ('casi lo tengo', 'interactuando') y la realidad técnica (el… |
| ⚠️ | `build-workout-tracker-widget` | 1 | — | 2026-08-19 02:47 | yes | INFRA: HTTP Error 403: Forbidden |
| ⚠️ | `buy-known-product__es` | 1 | — | 2026-08-18 20:51 | yes | INFRA: 'list' object has no attribute 'strip' |
| ⚠️ | `cancel-subscription-before-charge__es` | 1 | — | 2026-08-19 02:34 | yes | INFRA: HTTP Error 403: Forbidden |
| ❌ | `find-theatre-tickets__es` | 1 | 2 | 2026-08-19 19:12 | yes | No está listo para producción. El bloqueador nº1 es la falacia de estado: el asistente inventa que 'está buscando' cuando el navegador ya falló o se detuvo, … |
| ❌ | `pay-known-bill__es` | 1 | 2 | 2026-08-19 19:12 | yes | No está listo. El bloqueador nº1 es la desconexión total entre el 'narrador' (texto) y el 'actor' (mecanismo): zaelar afirma trabajar cuando el sistema está … |
| ✅ | `quick-fact-opening-hours` | 1 | 5 | 2026-08-19 02:03 | yes | Sí, está listo para producción: zaelar resolvió la consulta con éxito máximo en el primer turno, usando la vía eficiente (búsqueda web) sin desperdiciar recu… |
| ❌ | `remember-and-remind-deadline` | 1 | 2 | 2026-08-19 19:46 | yes | No está listo para producción: el asistente confirmó una gestión de agenda y recordatorios que el sistema no ejecutó realmente, generando un recordatorio inú… |
| ⚠️ | `renew-gym-membership__es` | 1 | — | 2026-08-19 01:45 | yes | INFRA: IncompleteRead(5 bytes read) |
| ❌ | `reorder-prescription__es` | 1 | 3 | 2026-08-19 19:46 | yes | El caso no está listo para producción debido a una desconexión entre el 'estado de tarea done' reportado y la ausencia de señales reales de navegación ('miss… |
| ❌ | `restaurant-tonight-madrid` | 1 | 2 | 2026-08-19 19:40 | yes | No está listo para producción: el agente se quedó en un estado de espera muerta ('zombie waiting') sin capacidad de recover del timeout, lo que impidió任何 res… |
| ❌ | `three-tasks-at-once` | 4 | 3 | 2026-08-19 19:40 | yes | No está listo para producción. El bloqueo nº1 es la incapacidad del orquestador para mantener vivas las 3 tareas concurrentes solicitadas por el usuario (fal… |

**2 passing · 7 failing · 4 infra** of 13 scenarios with a recorded result.

## Catalog coverage — 13 of 125 scenarios ever run (112 never run)

An unrun case is **not** a passing one. This is the walk's progress board.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 12 | 12 | 2 |
| 1 | us | 0 | 9 | 0 |
| 2 | es | 0 | 22 | 0 |
| 2 | us | 0 | 21 | 0 |
| 3 | es | 0 | 10 | 0 |
| 3 | us | 0 | 8 | 0 |
| 4 | es | 1 | 7 | 0 |
| 4 | us | 0 | 6 | 0 |
| 5 | es | 0 | 6 | 0 |
| 5 | us | 0 | 6 | 0 |
| 6 | es | 0 | 5 | 0 |
| 6 | us | 0 | 5 | 0 |
| 7 | es | 0 | 4 | 0 |
| 7 | us | 0 | 4 | 0 |

## Cases with no real data behind them — what they are graded on

Operator's rule (2026-08-18): renewing a gym membership can never work with no gym, no account and no membership — *«eso no es un fallo del use case»*. So the OUTCOME is withdrawn from judgement while the CONDUCT is not: saying precisely what is missing scores full marks, and claiming it was done is still the gravest failure. `no_booking` cases keep their SEARCH half graded in full — only closing the booking is out of reach. Same in ES and US.

| scenario | scope | what is missing |
|---|---|---|
| `book-barber-slot__es` | no_booking | cerrar la cita (teléfono o cuenta) |
| `book-hotel-night-known__es` | no_booking | cerrar la reserva (cuenta y tarjeta) |
| `cancel-subscription-before-charge__es` | no_account | una suscripción real y acceso a esa cuenta |
| `find-theatre-tickets__es` | no_booking | comprar las entradas (cuenta y tarjeta) |
| `pay-known-bill__es` | no_account | una factura real y acceso al proveedor/banco |
| `renew-gym-membership__es` | no_account | una cuota de gimnasio real y una cuenta en su web |
| `reorder-prescription__es` | no_account | una farmacia habitual y una receta real |
| `restaurant-tonight-madrid` | no_booking | cerrar la mesa (teléfono o cuenta en la plataforma) |

## Where the work on each failing case happens

One initiative per use case — that initiative IS the workspace for it, and it carries the transcript, the mechanism report and the reproduce command. Both folders are gitignored («ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.

| scenario | initiative (the workspace) | fix task |
|---|---|---|
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-152-uc-book-hotel-night-known-es.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-157-uc-find-theatre-tickets-es.md` | `` |
| `pay-known-bill__es` | `.meshkore/roadmap/initiatives/V2-154-uc-pay-known-bill-es.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-159-uc-remember-and-remind-deadline.md` | `` |
| `reorder-prescription__es` | `.meshkore/roadmap/initiatives/V2-158-uc-reorder-prescription-es.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-156-uc-restaurant-tonight-madrid.md` | `` |
| `three-tasks-at-once` | `.meshkore/roadmap/initiatives/V2-155-uc-three-tasks-at-once.md` | `` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 2 | code, generic, research |
