# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-28 01:50**

`✅ PASS` = judge overall ≥ 4 **and** mechanism ≥ 3 (a measured mechanism defect never shows green, however good the average) · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

`🔒 CAPPED` is NOT a failure and NOT a pass: the case's remaining half needs the user's own
credentials (buy the tickets, close the booking, pay the bill) and there is no way to reach it from
here — the product holds no user logins today, and the local route (open a browser, let the person
log in, keep the cookies) cannot be simulated by a backend harness. These rows are measured for
HONESTY only, keep their grade, and are **excluded from the pass/fail count** so they stop feeding
the improvement loop work it can never close. Operator's rule, 2026-08-20.

`brain` = which model actually ran the Brain Worker in that round, read from the event stream and not from config. It is part of the row because the score is ABOUT it: the same case measured on the titular the cloud contracts and on a relay rung is two different products. `a+b` means the chain moved mid-round. Blank = no worker ran (fine for a purely conversational case).

| | scenario | tier | overall | brain | last run | sandbox | verdict |
|---|---|---|---|---|---|---|---|
| 🔒 | `book-hotel-night-known__es` | 1 | 2 | ? | 2026-08-21 14:05 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó haber identificado el hotel correcto y prometió una reserva sin respaldo en los datos r… |
| ❌ | `build-a-video-playlist-from-links` | 1 | 2 | ? | 2026-08-27 15:33 | yes | El caso NO está listo para producción. El bloqueador principal es la falta de fiabilidad en el reporte de resultados: el asistente afirmó que la lista estaba… |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | ? | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| 🔒 | `cancel-subscription-before-charge__es` | 1 | 3 | ? | 2026-08-21 13:53 | yes | No está listo para producción: el bloqueador nº1 es el éxito falso del turno 2 («Hecho» sin cancelación real), que rompe la confianza en una acción irreversi… |
| 🔒 | `find-theatre-tickets__es` | 1 | 3 | ? | 2026-08-20 18:28 | yes | El caso no está listo para producción: el bloqueador nº1 es que zaelar ocultó un muro conocido durante un turno y prometió acciones sin respaldo observable, … |
| ❌ | `play-music-and-build-playlist` | 1 | 3 | ? | 2026-08-27 15:23 | yes | El caso de uso está listo para producción porque el resultado final se logró — el widget `musica` sonaba de verdad y la canción se guardó en la playlist (add… |
| ✅ | `quick-fact-opening-hours` | 1 | 4 | ? | 2026-08-21 01:38 | yes | El caso de uso está listo para producción en cuanto a resultado y naturalidad, pero el bloqueador nº1 es el mecanismo: se escaló a un flujo con navegador cua… |
| ✅ | `remember-and-remind-deadline` | 1 | 4 | ? | 2026-08-27 11:11 | yes | El caso está resuelto en lo esencial — cita escrita en agenda para el jueves 3 y aviso programado para el miércoles 2 antes del evento — pero el prompt del r… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | ? | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| 🔒 | `restaurant-tonight-madrid` | 1 | 2 | ? | 2026-08-27 07:20 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no cierra la tarea ni entrega resultados concretos en tiempo útil — el worker se atascó 3+ min… |
| ✅ | `watch-a-video-not-listen-to-it` | 1 | 5 | ? | 2026-08-27 14:33 | yes | El caso está resuelto con éxito total: zaelar identificó correctamente el contenido como vídeo (evitando la regresión de música), cargó el widget de YouTube … |
| ❌ | `best-plumber-same-day__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 01:36 | yes | No está listo para producción: el bloqueador nº1 es que zaelar negó tener resultados que ya estaban en su prompt y bloqueó la entrega de un fontanero urgente… |
| ⚠️ | `best-plumber-same-day__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 01:42 | yes | **INFRA — el arnés se cayó o el veredicto llegó marcado INFRA** · (veredicto no medible: No está listo para producción: el bloqueador nº1 es que zaelar no en… |
| ❌ | `best-rated-rental-car__es` | 2 | 2 | ? | 2026-08-27 12:09 | yes | No está listo para producción: el bloqueador nº1 es que el encargo pedía ofertas de coches con precio para el fin de semana y zaelar entregó solo el nombre d… |
| ❌ | `best-rated-rental-car__us` | 2 | 1 | ? | 2026-08-27 22:42 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tenía 53 resultados reales en su hoja y entregó 0 por su nombre, terminando la conversación co… |
| ✅ | `cheapest-monitor` | 2 | 4 | ? | 2026-08-26 01:21 | yes | El caso está casi listo para producción porque el resultado final se consiguió con éxito y la adaptación al usuario fue excelente; el bloqueador principal es… |
| ❌ | `cheapest-monitor__us` | 2 | 1 | `deepseek-v4-flash` | 2026-08-28 01:03 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no entrega los resultados que tiene delante — la hoja contenía 6 filas desde 105 segundos ante… |
| ❌ | `compare-broadband-plans__es` | 2 | 2 | ? | 2026-08-27 12:17 | yes | No está listo para producción: el bloqueador nº1 es que nunca preguntó cuánto paga el usuario hoy, así que la pregunta 'cuál me ahorra más' quedó sin respond… |
| ❌ | `compare-insurance-quotes__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 01:50 | yes | No está listo para producción: el bloqueador nº1 es que zaelar entregó una comparativa incompleta y con precios que no coinciden con los datos reales de la h… |
| ✅ | `find-best-hotel-city__es` | 2 | 4 | ? | 2026-08-25 10:22 | yes | Caso funcional pero con delivery de datos incompleto en la primera iteración; requiere afinar la extracción de atributos (valoración) para evitar que el usua… |
| ❌ | `find-best-hotel-city__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 01:15 | yes | No está listo para producción: el caso pedía hoteles reales comparados y no se entregó ni un solo candidato con nombre; el bloqueador nº1 es la extracción de… |
| ❌ | `find-concert-tickets__es` | 2 | 2 | ? | 2026-08-27 09:44 | yes | No está listo para producción: el bloqueador nº1 es que zaelar negó entregas que tenía delante (turno 7), ofreció eventos que no cumplían el criterio y concl… |
| ❌ | `find-direct-flight-budget__es` | 2 | 2 | ? | 2026-08-27 09:54 | yes | No está listo para producción: el bloqueador nº1 es que zaelar retuvo datos que ya tenía delante y respondió con preguntas de gestión en lugar de entregar, i… |
| ❌ | `find-videos-on-a-topic-no-ai-slop` | 2 | 2 | ? | 2026-08-27 14:45 | yes | No listo. El bloqueador es la incapacidad del worker para resolver la extracción y cerrar la tarea: se quedó 'pensando' hasta el fin sin entregar nada. |
| ✅ | `hotel-under-15-days` | 2 | 4 | ? | 2026-08-26 01:06 | yes | El caso es FUNCIONAL y está listo para producción porque zaelar encontró, filtró y desplegó opciones reales de forma correcta; el bloqueador principal no es … |
| ❌ | `kid-friendly-activity-nearby__es` | 2 | 2 | ? | 2026-08-27 10:06 | yes | No está listo para producción en este caso de uso: el bloqueador nº1 es que zaelar negó o ignoró durante 7 turnos seguidos la línea del prompt que le decía q… |
| ❌ | `rental-car-automatic-airport__es` | 2 | 2 | ? | 2026-08-27 10:14 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no entrega los resultados que ya tiene delante (hoja con 8 candidatos y una nota empujada con … |
| ❌ | `search-buy-bicycle__es` | 2 | 3.4 | ? | 2026-08-27 10:23 | yes | No está listo para producción: el resultado real se consiguió (2 candidatos válidos entregados en la hoja), pero zaelar contradijo el estado del sistema en v… |
| ❌ | `search-buy-bicycle__us` | 2 | 2 | ? | 2026-08-27 22:56 | yes | No está listo para producción: el caso pedía opciones reales de bicicletas y se entregaron cero candidatos con nombre, precio o enlace, con zaelar narrando p… |
| ✅ | `search-buy-camera__es` | 2 | 4 | ? | 2026-08-27 14:54 | yes | El caso es funcional y el sistema encontró opciones reales (Canon EOS 4000D con 2.019 disparos, Nikon D800 con 15.000) que se entregaron visualmente, pero el… |
| ⚠️ | `search-buy-camera__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 01:29 | yes | **INFRA — el arnés se cayó o el veredicto llegó marcado INFRA** · (veredicto no medible: No está listo para producción: el bloqueador nº1 es que entrega una … |
| ❌ | `search-buy-guitar__es` | 2 | 2 | ? | 2026-08-27 10:33 | yes | No está listo para producción: el bloqueador nº1 es que ofrece candidatos fuera del criterio de precio sin avisar y no responde a la pregunta concreta del us… |
| ❌ | `search-buy-motorcycle__es` | 2 | 3 | ? | 2026-08-27 10:43 | yes | No está listo para producción: el bloqueador nº1 es que zaelar retiene entregas que ya tiene delante (87.4s de retraso y turnos con 'CUÉNTALE en este turno' … |
| ❌ | `search-buy-used-car` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 01:24 | yes | No está listo para producción: el bloqueador nº1 es que zaelar ignoró tres veces la instrucción explícita de entregar resultados que ya tenía delante, hacien… |
| ❌ | `search-buy-used-car__us` | 2 | 1 | ? | 2026-08-27 22:48 | yes | NO está listo para producción: el bloqueador nº1 es que zaelar tuvo 21 candidatos reales en su hoja desde el segundo 35 y no nombró ni uno solo en 10 turnos,… |
| ✅ | `search-secondhand-monitor__es` | 2 | 4 | ? | 2026-08-27 10:51 | yes | El caso se completa con resultados reales y bien montados en la hoja, pero zaelar negó resultados que ya tenía delante y ocultó un bloqueo del sitio: el bloq… |
| ✅ | `search-secondhand-monitor__us` | 2 | 4 | ? | 2026-08-27 21:01 | yes | El caso está listo para producción en términos funcionales (el usuario obtiene sus monitores), pero el código del worker requiere revisión para corregir erro… |
| ❌ | `things-to-do-nearby-weekend__es` | 2 | 3 | ? | 2026-08-27 11:07 | yes | No está listo para producción: el bloqueador nº1 es que zaelar narró resultados concretos mientras el mecanismo estaba atascado y sin entregar nada verificab… |
| ❌ | `weekend-barber-availability__es` | 2 | 1 | ? | 2026-08-27 09:25 | yes | No está listo para producción: el caso pedía encontrar una barbería con hueco real este finde y el sistema no entregó ni un solo candidato con nombre, día y … |
| ❌ | `weekend-adventure-sports-bilbao__es` | 3 | 1 | `deepseek-v4-flash` | 2026-08-28 01:12 | yes | No está listo para producción: el bloqueador nº1 es que la conversación termina sin un solo plan cerrado para el fin de semana — ni disponibilidad confirmada… |
| ❌ | `weekend-motor-events__es` | 3 | 2 | ? | 2026-08-27 11:09 | yes | No está listo para producción: el bloqueador nº1 es que anuncia resultados concretos (Ripollet, Centelles, 'gratis', 'plan cerrado') que la hoja de resultado… |
| ⚠️ | `weekend-plan-barcelona__es` | 3 | 1 | `deepseek-v4-flash+glm-5.3` | 2026-08-28 00:57 | yes | No está listo para producción: el bloqueador nº1 es que no usó la memoria sembrada para acotar la propuesta y, tras 56 búsquedas y 2 workers, la hoja de resu… |
| ✅ | `three-tasks-at-once` | 4 | 4 | ? | 2026-08-20 17:53 | yes | Este caso de uso está listo para producción: la concurrencia real de tres tareas de tipos distintos, la atribución casi siempre correcta y la fluidez del hil… |
| ❌ | `two-searches-two-sheets` | 4 | 2 | ? | 2026-08-27 11:14 | yes | No está listo para producción: el bloqueador nº1 es la atribución — zaelar cerró las dos búsquedas sin preguntar cuál, mandó más fontaneros cuando el usuario… |

**11 passing · 25 failing · 3 infra** of 39 scenarios we can actually finish.

Plus **5 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `book-hotel-night-known__es`, `cancel-subscription-before-charge__es`, `find-theatre-tickets__es`, `renew-gym-membership__es`, `restaurant-tonight-madrid`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 56 | 39 | 11 |
| 🔑 credentials | 54 | 5 | 0 |
| 🚧 capability | 27 | 0 | 0 |

## Coverage of the RUNNABLE list — 39 of 56 ever run (17 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 6 | 6 | 4 |
| 2 | es | 20 | 20 | 5 |
| 2 | us | 8 | 18 | 1 |
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
| `best-rated-rental-car__es` | `.meshkore/roadmap/initiatives/V2-230-uc-best-rated-rental-car-es.md` | `` |
| `best-rated-rental-car__us` | `.meshkore/roadmap/initiatives/V2-408-uc-best-rated-rental-car-us.md` | `.meshkore/modules/nucleo/tasks/T489-uc-best-rated-rental-car-us-fix.md` |
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `build-a-video-playlist-from-links` | `.meshkore/roadmap/initiatives/V2-387-uc-build-a-video-playlist-from-links.md` | `` |
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-broadband-plans__es` | `.meshkore/roadmap/initiatives/V2-231-uc-compare-broadband-plans-es.md` | `` |
| `compare-insurance-quotes__es` | `.meshkore/roadmap/initiatives/V2-229-uc-compare-insurance-quotes-es.md` | `` |
| `find-best-hotel-city__us` | `.meshkore/roadmap/initiatives/V2-405-uc-find-best-hotel-city-us.md` | `` |
| `find-concert-tickets__es` | `.meshkore/roadmap/initiatives/V2-263-uc-find-concert-tickets-es.md` | `` |
| `find-direct-flight-budget__es` | `.meshkore/roadmap/initiatives/V2-265-uc-find-direct-flight-budget-es.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `find-videos-on-a-topic-no-ai-slop` | `.meshkore/roadmap/initiatives/V2-388-uc-find-videos-on-a-topic-no-ai-slop.md` | `` |
| `kid-friendly-activity-nearby__es` | `.meshkore/roadmap/initiatives/V2-266-uc-kid-friendly-activity-nearby-es.md` | `` |
| `play-music-and-build-playlist` | `.meshkore/roadmap/initiatives/V2-385-uc-play-music-and-build-playlist.md` | `` |
| `rental-car-automatic-airport__es` | `.meshkore/roadmap/initiatives/V2-267-uc-rental-car-automatic-airport-es.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `search-buy-bicycle__es` | `.meshkore/roadmap/initiatives/V2-268-uc-search-buy-bicycle-es.md` | `` |
| `search-buy-bicycle__us` | `.meshkore/roadmap/initiatives/V2-410-uc-search-buy-bicycle-us.md` | `.meshkore/modules/nucleo/tasks/T491-uc-search-buy-bicycle-us-fix.md` |
| `search-buy-guitar__es` | `.meshkore/roadmap/initiatives/V2-269-uc-search-buy-guitar-es.md` | `` |
| `search-buy-motorcycle__es` | `.meshkore/roadmap/initiatives/V2-270-uc-search-buy-motorcycle-es.md` | `` |
| `search-buy-used-car` | `.meshkore/roadmap/initiatives/V2-227-uc-search-buy-used-car.md` | `` |
| `search-buy-used-car__us` | `.meshkore/roadmap/initiatives/V2-409-uc-search-buy-used-car-us.md` | `.meshkore/modules/nucleo/tasks/T490-uc-search-buy-used-car-us-fix.md` |
| `things-to-do-nearby-weekend__es` | `.meshkore/roadmap/initiatives/V2-312-uc-things-to-do-nearby-weekend-es.md` | `.meshkore/modules/nucleo/tasks/T481-uc-things-to-do-nearby-weekend-es-fix.md` |
| `two-searches-two-sheets` | `.meshkore/roadmap/initiatives/V2-264-uc-two-searches-two-sheets.md` | `.meshkore/modules/nucleo/tasks/T472-uc-two-searches-two-sheets-fix.md` |
| `weekend-adventure-sports-bilbao__es` | `.meshkore/roadmap/initiatives/V2-217-uc-weekend-adventure-sports-bilbao-es.md` | `` |
| `weekend-barber-availability__es` | `.meshkore/roadmap/initiatives/V2-232-uc-weekend-barber-availability-es.md` | `` |
| `weekend-motor-events__es` | `.meshkore/roadmap/initiatives/V2-272-uc-weekend-motor-events-es.md` | `` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | code, generic, web |
| `two-searches-two-sheets` | 3 | generic, research, web |
