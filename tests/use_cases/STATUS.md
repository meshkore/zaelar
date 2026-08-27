# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-27 08:54**

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
| ❌ | `remember-and-remind-deadline` | 1 | 2 | 2026-08-27 08:06 | yes | No está listo para producción: el aviso quedó programado para hoy en lugar del miércoles 2, así que el recordatorio no cumplirá su función; el bloqueador nº1… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| 🔒 | `restaurant-tonight-madrid` | 1 | 2 | 2026-08-27 07:20 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no cierra la tarea ni entrega resultados concretos en tiempo útil — el worker se atascó 3+ min… |
| ❌ | `best-plumber-same-day__es` | 2 | 3 | 2026-08-27 08:54 | yes | No está listo para producción: el resultado final es válido (lista real con teléfonos y una recomendación con valoración confirmada), pero el bloqueador nº1 … |
| ❌ | `best-rated-rental-car__es` | 2 | 1 | 2026-08-26 01:47 | yes | El caso NO está listo para producción. El bloqueador nº1 es el fallo crítico en el mecanismo de extracción del navegador, que devolvió datos basura ('disclai… |
| ✅ | `cheapest-monitor` | 2 | 4 | 2026-08-26 01:21 | yes | El caso está casi listo para producción porque el resultado final se consiguió con éxito y la adaptación al usuario fue excelente; el bloqueador principal es… |
| ❌ | `compare-broadband-plans__es` | 2 | 2 | 2026-08-26 01:53 | yes | No está listo. El bloqueador nº1 es la incapacidad de cerrar la transacción: zaelar acumula datos válidos en el sistema y en el prompt (precios reales de Dig… |
| ❌ | `compare-insurance-quotes__es` | 2 | 2 | 2026-08-26 01:39 | yes | No está listo para producción. El bloqueador nº1 es el fallo grave en el mecanismo de extracción del navegador: el sistema no pudo leer ni un solo precio ni … |
| ✅ | `find-best-hotel-city__es` | 2 | 4 | 2026-08-25 10:22 | yes | Caso funcional pero con delivery de datos incompleto en la primera iteración; requiere afinar la extracción de atributos (valoración) para evitar que el usua… |
| ❌ | `find-concert-tickets__es` | 2 | 2 | 2026-08-25 11:48 | yes | No está listo para producción. El bloqueador nº1 es la incapacidad de zaelar para reconocer y reportar fallos técnicos explícitos (cuota agotada), lo que le … |
| ❌ | `find-direct-flight-budget__es` | 2 | 2 | 2026-08-25 10:42 | yes | El caso no está listo para producción. El sistema es capaz de realizar la navegación y mostrar resultados visualmente, pero falla en adaptarse a las correcci… |
| ✅ | `hotel-under-15-days` | 2 | 4 | 2026-08-26 01:06 | yes | El caso es FUNCIONAL y está listo para producción porque zaelar encontró, filtró y desplegó opciones reales de forma correcta; el bloqueador principal no es … |
| ❌ | `kid-friendly-activity-nearby__es` | 2 | 3 | 2026-08-25 12:25 | yes | El caso está funcional (la hoja se llenó y la respuesta final fue útil), pero la eficiencia es inaceptable para producción debido a la reiteración de búsqued… |
| ❌ | `rental-car-automatic-airport__es` | 2 | 2 | 2026-08-25 10:04 | yes | El caso NO está listo para producción: el flujo de navegación se atasca en interacciones de UI sin extraer datos a la hoja de resultados, resultando en esper… |
| ❌ | `search-buy-bicycle__es` | 2 | 3 | 2026-08-25 21:25 | yes | El caso está funcional (el mecanismo trajo resultados reales y se mostraron), pero NO está listo para producción como experiencia premium debido a las 'fugas… |
| ❌ | `search-buy-camera__es` | 2 | 3 | 2026-08-27 08:16 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó un dato decisivo (18.400 disparos) sin respaldo del mecanismo y presentó coches como re… |
| ❌ | `search-buy-guitar__es` | 2 | 3 | 2026-08-25 21:52 | yes | El caso funciona y encuentra opciones reales, pero no está listo para producción porque la lógica de filtrado incluyó accesorios no deseados como si fueran e… |
| ❌ | `search-buy-motorcycle__es` | 2 | 2 | 2026-08-25 21:15 | yes | El caso no está listo para producción. El bloqueador principal es la incapacidad del sistema para filtrar ruido estructural (hoteles/recambios) dentro de un … |
| ❌ | `search-buy-used-car` | 2 | 2 | 2026-08-27 08:47 | yes | No está listo para producción: el bloqueador nº1 es que zaelar presentó candidatos sin los datos que definen el criterio 'no muy viejo' (año y kilómetros) y … |
| ❌ | `search-secondhand-monitor__es` | 2 | 3 | 2026-08-25 21:35 | yes | No está listo. El bloqueador nº1 es la conducta de retención de resultados (zaelar tiene los datos y decide no mostrarlos para mantener una ficción de búsque… |
| ❌ | `things-to-do-nearby-weekend__es` | 2 | 2 | 2026-08-26 12:02 | yes | No está listo para producción: el bloqueador nº1 es que el worker arrastró el objetivo erróneo ('niños', fechas inventadas) incluso después de la corrección … |
| ❌ | `weekend-barber-availability__es` | 2 | 2 | 2026-08-25 20:51 | yes | El caso falla: el agente prometió reiteradamente una cita con confirmación inminente que nunca existió (agenda vacía, trabajos sin finalizar), ocultando fall… |
| ❌ | `weekend-adventure-sports-bilbao__es` | 3 | 2 | 2026-08-27 08:38 | yes | No está listo para producción: el bloqueador nº1 es que zaelar prometió horarios y disponibilidad para dos personas el sábado en tres turnos consecutivos y n… |
| ❌ | `weekend-motor-events__es` | 3 | 3 | 2026-08-21 16:35 | yes | No está listo para producción: el bloqueador nº1 es que inventó un evento sin fuente verificada y la hoja de resultados acabó con un solo candidato sin fuent… |
| ⚠️ | `weekend-plan-barcelona__es` | 3 | 2 | 2026-08-27 08:27 | yes | No está listo para producción: el bloqueador nº1 es que afirma datos concretos (ferratas, tiendas, accesos) sin haberlos verificado en ninguna fuente, y la h… |
| ✅ | `three-tasks-at-once` | 4 | 4 | 2026-08-20 17:53 | yes | Este caso de uso está listo para producción: la concurrencia real de tres tareas de tipos distintos, la atribución casi siempre correcta y la fluidez del hil… |
| ❌ | `two-searches-two-sheets` | 4 | 3 | 2026-08-21 14:43 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no gestiona la ambigüedad entre dos tareas vivas (no preguntó cuál cerrar y negó su existencia… |

**6 passing · 20 failing · 1 infra** of 27 scenarios we can actually finish.

Plus **5 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `book-hotel-night-known__es`, `cancel-subscription-before-charge__es`, `find-theatre-tickets__es`, `renew-gym-membership__es`, `restaurant-tonight-madrid`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 54 | 27 | 6 |
| 🔑 credentials | 54 | 5 | 0 |
| 🚧 capability | 27 | 0 | 0 |

## Coverage of the RUNNABLE list — 27 of 54 ever run (27 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 3 | 5 | 2 |
| 2 | es | 19 | 19 | 3 |
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
| `compare-broadband-plans__es` | `.meshkore/roadmap/initiatives/V2-231-uc-compare-broadband-plans-es.md` | `.meshkore/modules/nucleo/tasks/T468-uc-compare-broadband-plans-es-fix.md` |
| `compare-insurance-quotes__es` | `.meshkore/roadmap/initiatives/V2-004-uc-compare-insurance-quotes-es.md` | `.meshkore/modules/nucleo/tasks/T312-uc-compare-insurance-quotes-es-fix.md` |
| `find-concert-tickets__es` | `.meshkore/roadmap/initiatives/V2-263-uc-find-concert-tickets-es.md` | `` |
| `find-direct-flight-budget__es` | `.meshkore/roadmap/initiatives/V2-265-uc-find-direct-flight-budget-es.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `kid-friendly-activity-nearby__es` | `.meshkore/roadmap/initiatives/V2-266-uc-kid-friendly-activity-nearby-es.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `rental-car-automatic-airport__es` | `.meshkore/roadmap/initiatives/V2-267-uc-rental-car-automatic-airport-es.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `search-buy-bicycle__es` | `.meshkore/roadmap/initiatives/V2-268-uc-search-buy-bicycle-es.md` | `` |
| `search-buy-camera__es` | `.meshkore/roadmap/initiatives/V2-206-uc-search-buy-camera-es.md` | `` |
| `search-buy-guitar__es` | `.meshkore/roadmap/initiatives/V2-269-uc-search-buy-guitar-es.md` | `` |
| `search-buy-motorcycle__es` | `.meshkore/roadmap/initiatives/V2-270-uc-search-buy-motorcycle-es.md` | `` |
| `search-buy-used-car` | `.meshkore/roadmap/initiatives/V2-227-uc-search-buy-used-car.md` | `` |
| `search-secondhand-monitor__es` | `.meshkore/roadmap/initiatives/V2-271-uc-search-secondhand-monitor-es.md` | `` |
| `things-to-do-nearby-weekend__es` | `.meshkore/roadmap/initiatives/V2-312-uc-things-to-do-nearby-weekend-es.md` | `.meshkore/modules/nucleo/tasks/T481-uc-things-to-do-nearby-weekend-es-fix.md` |
| `two-searches-two-sheets` | `.meshkore/roadmap/initiatives/V2-264-uc-two-searches-two-sheets.md` | `.meshkore/modules/nucleo/tasks/T472-uc-two-searches-two-sheets-fix.md` |
| `weekend-adventure-sports-bilbao__es` | `.meshkore/roadmap/initiatives/V2-217-uc-weekend-adventure-sports-bilbao-es.md` | `` |
| `weekend-barber-availability__es` | `.meshkore/roadmap/initiatives/V2-232-uc-weekend-barber-availability-es.md` | `.meshkore/modules/nucleo/tasks/T469-uc-weekend-barber-availability-es-fix.md` |
| `weekend-motor-events__es` | `.meshkore/roadmap/initiatives/V2-272-uc-weekend-motor-events-es.md` | `.meshkore/modules/nucleo/tasks/T480-uc-weekend-motor-events-es-fix.md` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | code, generic, web |
| `two-searches-two-sheets` | 4 | generic, web |
