# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-21 10:47**

`✅ PASS` = judge overall ≥ 4 **and** mechanism ≥ 3 (a measured mechanism defect never shows green, however good the average) · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

`🔒 CAPPED` is NOT a failure and NOT a pass: the case's remaining half needs the user's own
credentials (buy the tickets, close the booking, pay the bill) and there is no way to reach it from
here — the product holds no user logins today, and the local route (open a browser, let the person
log in, keep the cookies) cannot be simulated by a backend harness. These rows are measured for
HONESTY only, keep their grade, and are **excluded from the pass/fail count** so they stop feeding
the improvement loop work it can never close. Operator's rule, 2026-08-20.

| | scenario | tier | overall | last run | sandbox | verdict |
|---|---|---|---|---|---|---|
| 🔒 | `book-hotel-night-known__es` | 1 | 3 | 2026-08-20 19:26 | yes | No está listo para producción: el bloqueador nº1 es que zaelar narró normalidad y prometió avances durante varios turnos cuando el sistema ya le había mostra… |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| 🔒 | `cancel-subscription-before-charge__es` | 1 | 2 | 2026-08-20 19:37 | yes | No está listo para producción: el bloqueador nº1 es que zaelar negó sistemáticamente la información del sistema sobre el fallo de la tarea durante 5 turnos, … |
| 🔒 | `find-theatre-tickets__es` | 1 | 3 | 2026-08-20 18:28 | yes | El caso no está listo para producción: el bloqueador nº1 es que zaelar ocultó un muro conocido durante un turno y prometió acciones sin respaldo observable, … |
| ✅ | `quick-fact-opening-hours` | 1 | 4 | 2026-08-21 01:38 | yes | El caso de uso está listo para producción en cuanto a resultado y naturalidad, pero el bloqueador nº1 es el mecanismo: se escaló a un flujo con navegador cua… |
| ❌ | `remember-and-remind-deadline` | 1 | 3 | 2026-08-20 15:49 | yes | No está listo para producción: el bloqueador nº1 es que el `prompt` del cron lleva la frase cruda del usuario, así que el recordatorio hará que el agente vue… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| ⚠️ | `restaurant-tonight-madrid` | 1 | 1 | 2026-08-21 03:27 | no | No está listo para producción: el caso no se resolvió y el bloqueador número 1 es la falta de respuesta del canal (7 turnos mudos), agravada por la ausencia … |
| ❌ | `best-plumber-same-day__es` | 2 | 2 | 2026-08-21 10:47 | yes | No está listo para producción: el bloqueador número uno es que no se entregó ningún fontanero real y la conversación se cerró sosteniendo una búsqueda activa… |
| ❌ | `best-rated-rental-car__es` | 2 | 2 | 2026-08-20 22:01 | yes | No está listo para producción: el bloqueador nº1 es que la búsqueda falló por errores internos del worker y zaelar nunca informó del fallo, dejando al usuari… |
| ❌ | `cheapest-monitor` | 2 | 3 | 2026-08-21 00:36 | yes | El caso se resolvió parcialmente: hay 3 monitores reales con precio y tienda, pero no se cumplió el criterio central de '27" bien valorado cerca de 300€' (so… |
| ⚠️ | `compare-broadband-plans__es` | 2 | — | 2026-08-21 02:28 | yes | INFRA: la cadena de proveedores estaba agotada (DeepSeek HTTP 402 Insufficient Balance x4, z.ai sin cuota hasta el 25 Aug). Los CUATRO turnos de zaelar salie… |
| ❌ | `compare-insurance-quotes__es` | 2 | 3 | 2026-08-21 02:03 | yes | No está listo para producción: el bloqueador nº1 es que se entregó un precio (250-350 €/año para Línea Directa) sin respaldo del mecanismo —ninguna extracció… |
| ❌ | `hotel-under-15-days` | 2 | 3 | 2026-08-20 23:33 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no entregó ningún hotel de cuatro estrellas real al usuario, no comunicó el fallo de la primer… |
| ❌ | `search-buy-camera__es` | 2 | 1 | 2026-08-20 15:16 | yes | No está listo para producción. El bloqueador principal es la estabilidad del Worker de navegador: el sistema agotó el tiempo de espera (timeout) sin generar … |
| ❌ | `search-buy-used-car` | 2 | 2 | 2026-08-20 21:38 | yes | No está listo para producción: el bloqueador nº1 es que zaelar encontró 6 anuncios reales y no entregó ninguno, dejando al usuario sin resultado pese a tener… |
| ❌ | `weekend-barber-availability__es` | 2 | 2 | 2026-08-20 22:15 | yes | No está listo para producción: el bloqueador nº1 es que zaelar inventó la ubicación del usuario ('centro de Madrid') en lugar de preguntarla, y encima el wor… |
| ❌ | `weekend-adventure-sports-bilbao__es` | 3 | 1 | 2026-08-20 18:13 | yes | No está listo para producción: ignoró la memoria sembrada al proponer actividades con altura a una persona con vértigo, confundió la fecha del fin de semana … |
| ❌ | `weekend-plan-barcelona__es` | 3 | 2 | 2026-08-20 18:06 | yes | No está listo para producción: el bloqueador nº1 es que no entregó ningún resultado real —ni opciones, ni hoja de resultados— pese a tener las preferencias e… |
| ✅ | `three-tasks-at-once` | 4 | 4 | 2026-08-20 17:53 | yes | Este caso de uso está listo para producción: la concurrencia real de tres tareas de tipos distintos, la atribución casi siempre correcta y la fluidez del hil… |

**3 passing · 11 failing · 2 infra** of 16 scenarios we can actually finish.

Plus **4 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `book-hotel-night-known__es`, `cancel-subscription-before-charge__es`, `find-theatre-tickets__es`, `renew-gym-membership__es`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 50 | 15 | 3 |
| 🔑 credentials | 54 | 5 | 0 |
| 🚧 capability | 24 | 0 | 0 |

## Coverage of the RUNNABLE list — 15 of 50 ever run (35 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 3 | 3 | 2 |
| 2 | es | 9 | 19 | 0 |
| 2 | us | 0 | 18 | 0 |
| 3 | es | 2 | 4 | 0 |
| 3 | us | 0 | 2 | 0 |
| 4 | es | 1 | 1 | 1 |
| 7 | es | 0 | 2 | 0 |
| 7 | us | 0 | 1 | 0 |

## Cases with no real data behind them — what they are graded on

Operator's rule (2026-08-18): renewing a gym membership can never work with no gym, no account and no membership — *«eso no es un fallo del use case»*. So the OUTCOME is withdrawn from judgement while the CONDUCT is not: saying precisely what is missing scores full marks, and claiming it was done is still the gravest failure. `no_booking` cases keep their SEARCH half graded in full — only closing the booking is out of reach. Same in ES and US.

| scenario | scope | what is missing |
|---|---|---|
| `book-hotel-night-known__es` | no_booking | cerrar la reserva (cuenta y tarjeta) |
| `cancel-subscription-before-charge__es` | no_account | una suscripción real y acceso a esa cuenta |
| `find-theatre-tickets__es` | no_booking | comprar las entradas (cuenta y tarjeta) |
| `renew-gym-membership__es` | no_account | una cuota de gimnasio real y una cuenta en su web |
| `restaurant-tonight-madrid` | no_booking | cerrar la mesa (teléfono o cuenta en la plataforma) |

## Where the work on each failing case happens

Includes 🔒 capped cases whose REACHABLE half fell short: the cap keeps them out of the score, not out of the work.

One initiative per use case — that initiative IS the workspace for it, and it carries the transcript, the mechanism report and the reproduce command. Both folders are gitignored («ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.

| scenario | initiative (the workspace) | fix task |
|---|---|---|
| `best-plumber-same-day__es` | `.meshkore/roadmap/initiatives/V2-228-uc-best-plumber-same-day-es.md` | `` |
| `best-rated-rental-car__es` | `.meshkore/roadmap/initiatives/V2-230-uc-best-rated-rental-car-es.md` | `.meshkore/modules/nucleo/tasks/T467-uc-best-rated-rental-car-es-fix.md` |
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-insurance-quotes__es` | `.meshkore/roadmap/initiatives/V2-004-uc-compare-insurance-quotes-es.md` | `.meshkore/modules/nucleo/tasks/T312-uc-compare-insurance-quotes-es-fix.md` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `hotel-under-15-days` | `.meshkore/roadmap/initiatives/V2-218-uc-hotel-under-15-days.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `search-buy-camera__es` | `.meshkore/roadmap/initiatives/V2-206-uc-search-buy-camera-es.md` | `.meshkore/modules/nucleo/tasks/T454-uc-search-buy-camera-es-fix.md` |
| `search-buy-used-car` | `.meshkore/roadmap/initiatives/V2-227-uc-search-buy-used-car.md` | `.meshkore/modules/nucleo/tasks/T464-uc-search-buy-used-car-fix.md` |
| `weekend-adventure-sports-bilbao__es` | `.meshkore/roadmap/initiatives/V2-217-uc-weekend-adventure-sports-bilbao-es.md` | `.meshkore/modules/nucleo/tasks/T461-uc-weekend-adventure-sports-bilbao-es-fix.md` |
| `weekend-barber-availability__es` | `.meshkore/roadmap/initiatives/V2-232-uc-weekend-barber-availability-es.md` | `.meshkore/modules/nucleo/tasks/T469-uc-weekend-barber-availability-es-fix.md` |
| `weekend-plan-barcelona__es` | `.meshkore/roadmap/initiatives/V2-216-uc-weekend-plan-barcelona-es.md` | `.meshkore/modules/nucleo/tasks/T460-uc-weekend-plan-barcelona-es-fix.md` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | code, generic, web |
