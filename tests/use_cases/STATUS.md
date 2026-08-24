# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-24 12:03**

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
| 🔒 | `book-hotel-night-known__es` | 1 | 2 | 2026-08-21 14:05 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó haber identificado el hotel correcto y prometió una reserva sin respaldo en los datos r… |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| 🔒 | `cancel-subscription-before-charge__es` | 1 | 3 | 2026-08-21 13:53 | yes | No está listo para producción: el bloqueador nº1 es el éxito falso del turno 2 («Hecho» sin cancelación real), que rompe la confianza en una acción irreversi… |
| 🔒 | `find-theatre-tickets__es` | 1 | 3 | 2026-08-20 18:28 | yes | El caso no está listo para producción: el bloqueador nº1 es que zaelar ocultó un muro conocido durante un turno y prometió acciones sin respaldo observable, … |
| ✅ | `quick-fact-opening-hours` | 1 | 4 | 2026-08-21 01:38 | yes | El caso de uso está listo para producción en cuanto a resultado y naturalidad, pero el bloqueador nº1 es el mecanismo: se escaló a un flujo con navegador cua… |
| ❌ | `remember-and-remind-deadline` | 1 | 3 | 2026-08-20 15:49 | yes | No está listo para producción: el bloqueador nº1 es que el `prompt` del cron lleva la frase cruda del usuario, así que el recordatorio hará que el agente vue… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| ⚠️ | `restaurant-tonight-madrid` | 1 | 1 | 2026-08-21 03:27 | no | No está listo para producción: el caso no se resolvió y el bloqueador número 1 es la falta de respuesta del canal (7 turnos mudos), agravada por la ausencia … |
| ❌ | `best-plumber-same-day__es` | 2 | 3 | 2026-08-21 11:56 | yes | No está listo para producción: el bloqueador nº1 es que se entregó un resultado parcial (2 de 13 candidatos) con una valoración inventada (4,7 sobre 5) sin r… |
| ❌ | `best-rated-rental-car__es` | 2 | 2 | 2026-08-20 22:01 | yes | No está listo para producción: el bloqueador nº1 es que la búsqueda falló por errores internos del worker y zaelar nunca informó del fallo, dejando al usuari… |
| ⚠️ | `cheapest-monitor` | 2 | 3 | 2026-08-23 22:48 | yes | El caso se completó con 4 candidatos reales en la hoja de resultados, pero el anuncio prematuro en el turno 10 (antes de que el worker escribiera) y la falta… |
| ⚠️ | `compare-broadband-plans__es` | 2 | — | 2026-08-21 02:28 | yes | INFRA: la cadena de proveedores estaba agotada (DeepSeek HTTP 402 Insufficient Balance x4, z.ai sin cuota hasta el 25 Aug). Los CUATRO turnos de zaelar salie… |
| ❌ | `compare-insurance-quotes__es` | 2 | 3 | 2026-08-21 02:03 | yes | No está listo para producción: el bloqueador nº1 es que se entregó un precio (250-350 €/año para Línea Directa) sin respaldo del mecanismo —ninguna extracció… |
| ❌ | `find-best-hotel-city__es` | 2 | 3 | 2026-08-21 14:17 | yes | No está listo para producción: el bloqueador nº1 es que no se entregó ningún hotel válido bajo el tope de 120€ (el resultado final es incompleto), agravado p… |
| ❌ | `find-concert-tickets__es` | 2 | 3 | 2026-08-21 14:34 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tuvo resultados reales en la hoja desde el turno 5 y los negó tres veces seguidas (turnos 5, 7… |
| ❌ | `find-direct-flight-budget__es` | 2 | 2 | 2026-08-21 14:49 | yes | No está listo para producción: el bloqueador nº1 es que el mecanismo de extracción del navegador no produjo ni un solo resultado real (n_found=0) y el agente… |
| ❌ | `hotel-under-15-days` | 2 | 3 | 2026-08-21 13:59 | yes | El caso se resolvió parcialmente: hay dos hoteles reales de 4 estrellas con precio y enlace en la hoja, pero la entrega se ensucia con una experiencia duplic… |
| ❌ | `kid-friendly-activity-nearby__es` | 2 | 2 | 2026-08-21 14:57 | yes | No está listo para producción: el bloqueador nº1 es que no se entregó ningún resultado real (la hoja quedó vacía) y zaelar narró un éxito falso prometiendo u… |
| ❌ | `rental-car-automatic-airport__es` | 2 | 2 | 2026-08-21 15:19 | yes | No está listo para producción: el bloqueador nº1 es que no se entregó ningún resultado real —la hoja quedó vacía y la tarea que se ejecutó (fontanero en Madr… |
| ⚠️ | `search-buy-bicycle__es` | 2 | 2 | 2026-08-24 11:41 | yes | Este caso de uso no está listo para producción: el bloqueador nº1 es que el agente no entregó ningún resultado real al usuario a pesar de tener candidatos en… |
| ⚠️ | `search-buy-camera__es` | 2 | 2 | 2026-08-24 11:56 | yes | No está listo para producción: el bloqueador nº1 es que el worker encontró 6 candidatos reales que cumplían los criterios y zaelar no los entregó — la hoja d… |
| ⚠️ | `search-buy-guitar__es` | 2 | 3 | 2026-08-24 12:03 | yes | El caso se completó con resultados reales en la hoja (21 candidatos con enlace), pero la entrega fue tardía y parcial en el último turno; el bloqueador princ… |
| ❌ | `search-buy-motorcycle__es` | 2 | 2 | 2026-08-21 15:42 | yes | No está listo para producción: el bloqueador nº1 es que no se entregó ningún resultado real (la hoja quedó vacía) y zaelar narró normalidad sobre una tarea c… |
| ❌ | `search-buy-used-car` | 2 | 2 | 2026-08-20 21:38 | yes | No está listo para producción: el bloqueador nº1 es que zaelar encontró 6 anuncios reales y no entregó ninguno, dejando al usuario sin resultado pese a tener… |
| ⚠️ | `search-secondhand-monitor__es` | 2 | 2 | 2026-08-24 11:49 | yes | No está listo para producción: el bloqueador nº1 es que el resultado correcto (monitor LG UltraGear a 150€) existía en el sistema y nunca se entregó al usuar… |
| ⚠️ | `things-to-do-nearby-weekend__es` | 2 | — | 2026-08-21 16:19 | yes | INFRA: <urlopen error [Errno 8] nodename nor servname provided, or not known> |
| ❌ | `weekend-barber-availability__es` | 2 | 2 | 2026-08-20 22:15 | yes | No está listo para producción: el bloqueador nº1 es que zaelar inventó la ubicación del usuario ('centro de Madrid') en lugar de preguntarla, y encima el wor… |
| ❌ | `weekend-adventure-sports-bilbao__es` | 3 | 1 | 2026-08-20 18:13 | yes | No está listo para producción: ignoró la memoria sembrada al proponer actividades con altura a una persona con vértigo, confundió la fecha del fin de semana … |
| ❌ | `weekend-motor-events__es` | 3 | 3 | 2026-08-21 16:35 | yes | No está listo para producción: el bloqueador nº1 es que inventó un evento sin fuente verificada y la hoja de resultados acabó con un solo candidato sin fuent… |
| ❌ | `weekend-plan-barcelona__es` | 3 | 2 | 2026-08-20 18:06 | yes | No está listo para producción: el bloqueador nº1 es que no entregó ningún resultado real —ni opciones, ni hoja de resultados— pese a tener las preferencias e… |
| ✅ | `three-tasks-at-once` | 4 | 4 | 2026-08-20 17:53 | yes | Este caso de uso está listo para producción: la concurrencia real de tres tareas de tipos distintos, la atribución casi siempre correcta y la fluidez del hil… |
| ❌ | `two-searches-two-sheets` | 4 | 3 | 2026-08-21 14:43 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no gestiona la ambigüedad entre dos tareas vivas (no preguntó cuál cerrar y negó su existencia… |

**3 passing · 17 failing · 8 infra** of 28 scenarios we can actually finish.

Plus **4 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `book-hotel-night-known__es`, `cancel-subscription-before-charge__es`, `find-theatre-tickets__es`, `renew-gym-membership__es`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 52 | 27 | 3 |
| 🔑 credentials | 54 | 5 | 0 |
| 🚧 capability | 27 | 0 | 0 |

## Coverage of the RUNNABLE list — 27 of 52 ever run (25 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 3 | 3 | 2 |
| 2 | es | 19 | 19 | 0 |
| 2 | us | 0 | 18 | 0 |
| 3 | es | 3 | 5 | 0 |
| 3 | us | 0 | 2 | 0 |
| 4 | es | 2 | 2 | 1 |
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
| `compare-insurance-quotes__es` | `.meshkore/roadmap/initiatives/V2-004-uc-compare-insurance-quotes-es.md` | `.meshkore/modules/nucleo/tasks/T312-uc-compare-insurance-quotes-es-fix.md` |
| `find-best-hotel-city__es` | `.meshkore/roadmap/initiatives/V2-262-uc-find-best-hotel-city-es.md` | `.meshkore/modules/nucleo/tasks/T470-uc-find-best-hotel-city-es-fix.md` |
| `find-concert-tickets__es` | `.meshkore/roadmap/initiatives/V2-263-uc-find-concert-tickets-es.md` | `.meshkore/modules/nucleo/tasks/T471-uc-find-concert-tickets-es-fix.md` |
| `find-direct-flight-budget__es` | `.meshkore/roadmap/initiatives/V2-265-uc-find-direct-flight-budget-es.md` | `.meshkore/modules/nucleo/tasks/T473-uc-find-direct-flight-budget-es-fix.md` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `hotel-under-15-days` | `.meshkore/roadmap/initiatives/V2-218-uc-hotel-under-15-days.md` | `` |
| `kid-friendly-activity-nearby__es` | `.meshkore/roadmap/initiatives/V2-266-uc-kid-friendly-activity-nearby-es.md` | `.meshkore/modules/nucleo/tasks/T474-uc-kid-friendly-activity-nearby-es-fix.md` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `rental-car-automatic-airport__es` | `.meshkore/roadmap/initiatives/V2-267-uc-rental-car-automatic-airport-es.md` | `.meshkore/modules/nucleo/tasks/T475-uc-rental-car-automatic-airport-es-fix.md` |
| `search-buy-motorcycle__es` | `.meshkore/roadmap/initiatives/V2-270-uc-search-buy-motorcycle-es.md` | `.meshkore/modules/nucleo/tasks/T478-uc-search-buy-motorcycle-es-fix.md` |
| `search-buy-used-car` | `.meshkore/roadmap/initiatives/V2-227-uc-search-buy-used-car.md` | `.meshkore/modules/nucleo/tasks/T464-uc-search-buy-used-car-fix.md` |
| `two-searches-two-sheets` | `.meshkore/roadmap/initiatives/V2-264-uc-two-searches-two-sheets.md` | `.meshkore/modules/nucleo/tasks/T472-uc-two-searches-two-sheets-fix.md` |
| `weekend-adventure-sports-bilbao__es` | `.meshkore/roadmap/initiatives/V2-217-uc-weekend-adventure-sports-bilbao-es.md` | `.meshkore/modules/nucleo/tasks/T461-uc-weekend-adventure-sports-bilbao-es-fix.md` |
| `weekend-barber-availability__es` | `.meshkore/roadmap/initiatives/V2-232-uc-weekend-barber-availability-es.md` | `.meshkore/modules/nucleo/tasks/T469-uc-weekend-barber-availability-es-fix.md` |
| `weekend-motor-events__es` | `.meshkore/roadmap/initiatives/V2-272-uc-weekend-motor-events-es.md` | `.meshkore/modules/nucleo/tasks/T480-uc-weekend-motor-events-es-fix.md` |
| `weekend-plan-barcelona__es` | `.meshkore/roadmap/initiatives/V2-216-uc-weekend-plan-barcelona-es.md` | `.meshkore/modules/nucleo/tasks/T460-uc-weekend-plan-barcelona-es-fix.md` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | code, generic, web |
| `two-searches-two-sheets` | 4 | generic, web |
