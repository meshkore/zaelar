# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-29 20:07**

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
| 🔒 | `book-barber-slot__us` | 1 | 2 | `deepseek-v4-flash` | 2026-08-28 08:22 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirma haber encontrado y reservado la barbería habitual sin ningún respaldo en el sistema (ho… |
| 🔒 | `book-hotel-night-known__es` | 1 | 2 | ? | 2026-08-21 14:05 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó haber identificado el hotel correcto y prometió una reserva sin respaldo en los datos r… |
| 🔒 | `book-hotel-night-known__us` | 1 | 2 | `deepseek-v4-flash` | 2026-08-28 08:41 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó una reserva confirmada que no existía, y solo se retractó cuando el usuario le obligó a… |
| ✅ | `build-a-video-playlist-from-links` | 1 | 4 | — | 2026-08-28 23:36 | yes | El caso funciona a nivel de gestión de lista, pero no está listo para producción hasta que el asistente reconozca y comunique los fallos de reproducción ('pl… |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | ? | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| 🔒 | `buy-known-product__us` | 1 | 3 | `deepseek-v4-flash` | 2026-08-28 08:56 | yes | No está listo para producción: el bloqueador nº1 es que zaelar dejó al usuario esperando más de 5 minutos ante una tarea encallada sin decirle 'sin avanzar' … |
| 🔒 | `cancel-subscription-before-charge__es` | 1 | 3 | ? | 2026-08-21 13:53 | yes | No está listo para producción: el bloqueador nº1 es el éxito falso del turno 2 («Hecho» sin cancelación real), que rompe la confianza en una acción irreversi… |
| 🔒 | `cancel-subscription-before-charge__us` | 1 | 2 | `glm-5.3` | 2026-08-28 07:08 | yes | El caso no está listo para producción. El fallo crítico es la incapacidad para cumplir la promesa de crear un recordatorio (ni siquiera se escribió en el sis… |
| ✅ | `dentist-appointment-into-agenda` | 1 | 4 | — | 2026-08-29 15:06 | yes | El caso está casi listo para producción, pero requiere mejorar la lógica de deduplicación para evitar crear citas repetidas cuando se ajustan detalles de una… |
| ✅ | `dentist-appointment-into-agenda__us` | 1 | 5 | — | 2026-08-29 15:10 | yes | Listo para producción: zaelar ejecutó la escritura en la agenda, creó el recordatorio por defecto con contenido resuelto y confirmó sin ambigüedades. |
| 🔒 | `find-theatre-tickets__es` | 1 | 3 | ? | 2026-08-20 18:28 | yes | El caso no está listo para producción: el bloqueador nº1 es que zaelar ocultó un muro conocido durante un turno y prometió acciones sin respaldo observable, … |
| 🔒 | `find-theatre-tickets__us` | 1 | 2 | `deepseek-v4-flash` | 2026-08-28 09:14 | yes | No está listo para producción: el bloqueador nº1 es que zaelar ocultó el estado real de la tarea (encallada y con error interno) detrás de respuestas vagas y… |
| ⚠️ | `knows-who-i-am-without-being-told-again` | 1 | 2 | — | 2026-08-29 20:07 | yes | **INFRA — recall semántico DEGRADADO en esta ronda (backend: fastembed)** · (veredicto no medible: No está listo para producción para este caso de uso; el bl… |
| ⚠️ | `pay-known-bill__us` | 1 | 3 | `glm-5.3` | 2026-08-28 07:49 | yes | **INFRA — sin cuota en z.ai → relevo a deepseek: 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (veredicto no … |
| ✅ | `play-music-and-build-playlist` | 1 | 5 | — | 2026-08-28 22:00 | yes | Listo para producción: el asistente sonó de música real usando YouTube, gestionó la lista y el nombre solicitados sin fricción, y el mecanismo respaldó cada … |
| ✅ | `quick-fact-opening-hours` | 1 | 4 | ? | 2026-08-21 01:38 | yes | El caso de uso está listo para producción en cuanto a resultado y naturalidad, pero el bloqueador nº1 es el mecanismo: se escaló a un flujo con navegador cua… |
| ✅ | `remember-and-remind-deadline` | 1 | 4 | ? | 2026-08-27 11:11 | yes | El caso está resuelto en lo esencial — cita escrita en agenda para el jueves 3 y aviso programado para el miércoles 2 antes del evento — pero el prompt del r… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | ? | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| 🔒 | `renew-gym-membership__us` | 1 | 3 | `deepseek-v4-flash` | 2026-08-28 08:06 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no entrega lo que el sistema ya le ha puesto delante (resultados encontrados y notas empujadas… |
| 🔒 | `reorder-prescription__us` | 1 | 2 | `glm-5.3` | 2026-08-28 07:27 | yes | El caso de uso NO está listo para producción: la parte técnica (mecanismo) funciona y localiza los datos, pero el modelo falla gravemente al no entregar esos… |
| 🔒 | `restaurant-tonight-madrid` | 1 | 2 | ? | 2026-08-27 07:20 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no cierra la tarea ni entrega resultados concretos en tiempo útil — el worker se atascó 3+ min… |
| 🔒 | `restaurant-tonight-nyc__us` | 1 | 2 | `glm-5.3` | 2026-08-28 06:46 | yes | No está listo para producción: falló el objetivo principal (no reservó ni presentó opciones) y cometió un fallo grave de confianza al prometer una llamada te… |
| ✅ | `watch-a-video-not-listen-to-it` | 1 | 5 | ? | 2026-08-27 14:33 | yes | El caso está resuelto con éxito total: zaelar identificó correctamente el contenido como vídeo (evitando la regresión de música), cargó el widget de YouTube … |
| 🔒 | `best-pediatric-dentists__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 09:26 | yes | No está listo para producción: el bloqueador nº1 es que zaelar retiene resultados que ya tiene en su prompt y no entrega ratings ni intenta la reserva, dejan… |
| ❌ | `best-plumber-same-day__es` | 2 | 3 | `deepseek-v4-flash` | 2026-08-28 05:39 | yes | El caso no está listo para producción. El bloqueador nº1 es la incapacidad del modelo para sincronizar su narrativa con el estado real del sistema (negación … |
| ❌ | `best-plumber-same-day__us` | 2 | 3 | `claude-opus-4-8[1m]+deepseek-v4-flash` | 2026-08-28 11:10 | yes | El entregable existe y la recomendación de Ace Plumbing & Rooter está bien verificada (reseñas, teléfono, licencia, horario), pero este caso no está listo pa… |
| ❌ | `best-rated-rental-car__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 06:11 | yes | No está listo para producción: el bloqueador nº1 es que zaelar anunció entregas y pasos que no existían (hoja vacía, worker atascado) y no entregó los result… |
| ❌ | `best-rated-rental-car__us` | 2 | 2.4 | `claude-opus-4-8[1m]+deepseek-v4-flash` | 2026-08-28 11:37 | yes | No está listo para producción: entregó ofertas reales con precio y fuente en la hoja, pero no la valoración que la petición pedía explícitamente ("best-rated… |
| ✅ | `cheapest-monitor` | 2 | 4 | ? | 2026-08-26 01:21 | yes | El caso está casi listo para producción porque el resultado final se consiguió con éxito y la adaptación al usuario fue excelente; el bloqueador principal es… |
| ❌ | `cheapest-monitor__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-29 14:08 | yes | No está listo para producción: el flujo falló en la entrega por latencia y bloqueos externos no comunicados, dejando al usuario sin el producto solicitado a … |
| ❌ | `compare-broadband-plans__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 06:23 | yes | El caso no está listo para producción: el asistente encuentra datos reales pero falla en la toma de decisión y cierre, quedándose atrapado en bucles de búsqu… |
| 🔒 | `compare-flights-madrid-lisboa` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 04:43 | yes | No está listo para producción: el bloqueador nº1 es que zaelar vuelca filas crudas de la hoja en lugar de construir una comparación legible con el requisito … |
| 🔒 | `compare-flights-sf-austin__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 09:44 | yes | No está listo para producción: el bloqueador nº1 es que zaelar presentó vuelos y precios como encontrados sin que el mecanismo hubiera extraído nada, y despu… |
| ❌ | `compare-insurance-quotes__es` | 2 | 3 | `claude-opus-4-8[1m]+deepseek-v4-flash` | 2026-08-28 11:52 | yes | No está listo para producción: la comparativa llegó con un precio mal citado (Pelayo 165 frente a 202), sin una recomendación final cerrada y tras más de sie… |
| ❌ | `compare-insurance-quotes__us` | 2 | 1 | `deepseek-v4-flash` | 2026-08-28 10:01 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó un éxito falso con cotizaciones inventadas mientras el worker seguía encallado y la hoj… |
| ❌ | `compare-phone-plans__us` | 2 | 3 | `deepseek-v4-flash` | 2026-08-28 10:09 | yes | No está listo para producción: el bloqueador nº1 es que narró resultados como verificados mientras el worker llevaba 4 minutos sin avanzar y con un error int… |
| ⚠️ | `find-a-future-release-and-remind-me` | 2 | 4 | `deepseek-v4-flash` | 2026-08-29 19:25 | yes | **INFRA — recall semántico DEGRADADO en esta ronda (backend: fastembed)** · (veredicto no medible: El caso es funcional y los mecanismos clave (búsqueda y pr… |
| ✅ | `find-best-hotel-city__es` | 2 | 4 | ? | 2026-08-25 10:22 | yes | Caso funcional pero con delivery de datos incompleto en la primera iteración; requiere afinar la extracción de atributos (valoración) para evitar que el usua… |
| ⚠️ | `find-best-hotel-city__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-29 20:06 | yes | **INFRA — recall semántico DEGRADADO en esta ronda (backend: fastembed)** · (veredicto no medible: No está listo para producción. El bloqueador principal es … |
| ❌ | `find-concert-tickets__es` | 2 | 3.5 | `deepseek-v4-flash` | 2026-08-28 07:18 | yes | El caso no está listo para producción porque, aunque el comportamiento conversacional y la gestión de bloqueos fueron excelentes, falló el objetivo del usuar… |
| ❌ | `find-direct-flight-budget__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 07:38 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tuvo 8 vuelos reales con nombre y precio en su prompt y no entregó ni uno, respondiendo con ge… |
| ✅ | `find-videos-on-a-topic-no-ai-slop` | 2 | 4 | — | 2026-08-28 22:57 | yes | El caso está casi listo para producción, pero debe mejorar la sincronización entre el relato del agente y el estado real del widget, así como garantizar que … |
| ✅ | `hotel-under-15-days` | 2 | 4 | ? | 2026-08-26 01:06 | yes | El caso es FUNCIONAL y está listo para producción porque zaelar encontró, filtró y desplegó opciones reales de forma correcta; el bloqueador principal no es … |
| ❌ | `kid-friendly-activity-nearby__es` | 2 | 1 | — | 2026-08-28 07:55 | yes | No está listo para producción: el bloqueador nº1 es que zaelar agendó una idea genérica sin buscar ni presentar opciones reales con precio y fuente, dejando … |
| ❌ | `rental-car-automatic-airport__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 08:13 | yes | No está listo para producción: el bloqueador nº1 es que la búsqueda tarda más que la conversación y zaelar no entrega los resultados que ya tiene en su promp… |
| ❌ | `search-buy-bicycle__es` | 2 | 3 | `deepseek-v4-flash` | 2026-08-28 08:31 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tuvo delante durante tres turnos la instrucción explícita de contar el bloqueo y los resultado… |
| ❌ | `search-buy-bicycle__us` | 2 | 2 | `glm-5.3` | 2026-08-28 06:31 | yes | No está listo: falló el resultado (hoja vacía) y la transparencia (ocultó bloqueos 403 prometiendo éxito), requiriendo mejoras en el reporte de estado del wo… |
| ✅ | `search-buy-camera__es` | 2 | 4 | ? | 2026-08-27 14:54 | yes | El caso es funcional y el sistema encontró opciones reales (Canon EOS 4000D con 2.019 disparos, Nikon D800 con 15.000) que se entregaron visualmente, pero el… |
| ✅ | `search-buy-camera__us` | 2 | 4 | `deepseek-v4-flash` | 2026-08-28 05:32 | yes | El caso es funcional y los datos son reales (lo cual es crítico), pero adolece de lentitud en la entrega y parcialidad en el resumen; corregir el timing de p… |
| ✅ | `search-buy-guitar__es` | 2 | 4 | `deepseek-v4-flash` | 2026-08-28 03:49 | yes | **⚠️ el juez dice que NO está listo, aunque la nota pase** · No está listo para producción: el bloqueador nº1 es que el sistema no mostró a zaelar las filas … |
| ✅ | `search-buy-motorcycle__es` | 2 | 4 | `deepseek-v4-flash` | 2026-08-28 04:00 | yes | **⚠️ el juez dice que NO está listo, aunque la nota pase** · No está listo para producción: el bloqueador nº1 es que zaelar negó cuatro veces resultados que … |
| ⚠️ | `search-buy-used-car` | 2 | 2 | `claude-opus-4-8[1m]+deepseek-v4-flash` | 2026-08-28 10:57 | yes | **INFRA — sin cuota en deepseek → relevo a licencia-claude: 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (ve… |
| ⚠️ | `search-buy-used-car__us` | 2 | 2 | `claude-opus-4-8[1m]+deepseek-v4-flash` | 2026-08-28 12:09 | yes | **INFRA — sin cuota en deepseek → relevo a licencia-claude: 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (ve… |
| ✅ | `search-secondhand-monitor__es` | 2 | 4 | ? | 2026-08-27 10:51 | yes | El caso se completa con resultados reales y bien montados en la hoja, pero zaelar negó resultados que ya tenía delante y ocultó un bloqueo del sitio: el bloq… |
| ✅ | `search-secondhand-monitor__us` | 2 | 4 | ? | 2026-08-27 21:01 | yes | El caso está listo para producción en términos funcionales (el usuario obtiene sus monitores), pero el código del worker requiere revisión para corregir erro… |
| ✅ | `show-real-photo-of-a-new-car__es` | 2 | 4 | — | 2026-08-28 19:00 | yes | Sí está listo para producción porque cumple el objetivo principal (fotos reales en el visor correcto con atribución) y el mecanismo es sólido, aunque debe me… |
| ✅ | `show-real-photo-of-a-new-car__us` | 2 | 5 | — | 2026-08-28 19:16 | yes | Sí está listo para producción este caso de uso: resolvió la consulta de forma inmediata, usando el visor correcto y con atribución visible, sin bloqueos ni e… |
| ❌ | `things-to-do-nearby-weekend__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 08:49 | yes | No está listo para producción: el bloqueador nº1 es que zaelar entregó enlaces a páginas de programa como si fueran el resultado concreto que el usuario pidi… |
| ❌ | `weekend-barber-availability__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 06:36 | yes | No está listo para producción: el bloqueador principal es la incapacidad del worker para extraer y escribir la disponibilidad real en la hoja de resultados, … |
| ❌ | `weekend-adventure-sports-bilbao__es` | 3 | 3 | `deepseek-v4-flash` | 2026-08-28 10:41 | yes | No está listo para producción: el bloqueador nº1 es la adaptación — preguntó preferencias que ya tenía en memoria y ofreció actividades de altura a una perso… |
| ❌ | `weekend-motor-events__es` | 3 | 2 | `deepseek-v4-flash` | 2026-08-28 09:07 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tenía 7 resultados reales delante y solo entregó 2 por su nombre, dejando sin decir los museos… |
| ❌ | `weekend-plan-barcelona__es` | 3 | 2 | `deepseek-v4-flash` | 2026-08-28 10:24 | yes | No está listo para producción: el bloqueador nº1 es que zaelar retuvo 6 de 8 resultados reales que tenía delante y entregó solo 2, mientras repetía la misma … |
| ✅ | `three-tasks-at-once` | 4 | 4 | ? | 2026-08-20 17:53 | yes | Este caso de uso está listo para producción: la concurrencia real de tres tareas de tipos distintos, la atribución casi siempre correcta y la fluidez del hil… |
| ❌ | `two-searches-two-sheets` | 4 | 2 | `deepseek-v4-flash` | 2026-08-28 06:58 | yes | No listo. El sistema ejecutó la concurrencia técnicamente (2 workers, 2 hojas), pero zaelar falló en la gestión de los estados: cerró mal sin preguntar y mez… |

**21 passing · 20 failing · 6 infra** of 47 scenarios we can actually finish.

Plus **1 🌍 parked** for an environmental wall a user in that country would not hit (the sibling twin proves the capability). Visible, not counted, each with its reason:
- `cheapest-monitor__us` — Amazon geolocaliza por IP: aun con un perfil en-US limpio sirve «Deliver to Spain» y precios de España. El gemelo ES está verde (4/5), así que la capacidad está probada; desde una IP de EEUU el muro no existe.

Plus **16 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `best-pediatric-dentists__us`, `book-barber-slot__us`, `book-hotel-night-known__es`, `book-hotel-night-known__us`, `buy-known-product__us`, `cancel-subscription-before-charge__es`, `cancel-subscription-before-charge__us`, `compare-flights-madrid-lisboa`, `compare-flights-sf-austin__us`, `find-theatre-tickets__es`, `find-theatre-tickets__us`, `renew-gym-membership__es`, `renew-gym-membership__us`, `reorder-prescription__us`, `restaurant-tonight-madrid`, `restaurant-tonight-nyc__us`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 62 | 47 | 21 |
| 🔑 credentials | 54 | 17 | 0 |
| 🚧 capability | 27 | 0 | 0 |

## Coverage of the RUNNABLE list — 47 of 62 ever run (15 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 8 | 8 | 7 |
| 1 | us | 1 | 1 | 1 |
| 2 | es | 22 | 22 | 9 |
| 2 | us | 11 | 19 | 3 |
| 3 | es | 3 | 5 | 0 |
| 3 | us | 0 | 2 | 0 |
| 4 | es | 2 | 2 | 1 |
| 7 | es | 0 | 2 | 0 |
| 7 | us | 0 | 1 | 0 |

## Cases with no real data behind them — what they are graded on

Operator's rule (2026-08-18): renewing a gym membership can never work with no gym, no account and no membership — *«eso no es un fallo del use case»*. So the OUTCOME is withdrawn from judgement while the CONDUCT is not: saying precisely what is missing scores full marks, and claiming it was done is still the gravest failure. `no_booking` cases keep their SEARCH half graded in full — only closing the booking is out of reach. Same in ES and US.

| scenario | scope | what is missing |
|---|---|---|
| `best-pediatric-dentists__us` | no_booking | cerrar la cita (teléfono o cuenta) |
| `book-barber-slot__us` | no_booking | cerrar la cita (teléfono o cuenta) |
| `book-hotel-night-known__es` | no_booking | cerrar la reserva (cuenta y tarjeta) |
| `book-hotel-night-known__us` | no_booking | cerrar la reserva (cuenta y tarjeta) |
| `buy-known-product__us` | no_account | una cuenta con lista de deseos y un medio de pago |
| `cancel-subscription-before-charge__es` | no_account | una suscripción real y acceso a esa cuenta |
| `cancel-subscription-before-charge__us` | no_account | una suscripción real y acceso a esa cuenta |
| `compare-flights-madrid-lisboa` | no_booking | comprar el vuelo (cuenta y tarjeta) |
| `compare-flights-sf-austin__us` | no_booking | comprar el vuelo (cuenta y tarjeta) |
| `find-theatre-tickets__es` | no_booking | comprar las entradas (cuenta y tarjeta) |
| `find-theatre-tickets__us` | no_booking | comprar las entradas (cuenta y tarjeta) |
| `pay-known-bill__us` | no_account | una factura real y acceso al proveedor/banco |
| `renew-gym-membership__es` | no_account | una cuota de gimnasio real y una cuenta en su web |
| `renew-gym-membership__us` | no_account | una cuota de gimnasio real y una cuenta en su web |
| `reorder-prescription__us` | no_account | una farmacia habitual y una receta real |
| `restaurant-tonight-madrid` | no_booking | cerrar la mesa (teléfono o cuenta en la plataforma) |
| `restaurant-tonight-nyc__us` | no_booking | cerrar la mesa (teléfono o cuenta en la plataforma) |

## Where the work on each failing case happens

Includes 🔒 capped cases whose REACHABLE half fell short: the cap keeps them out of the score, not out of the work.

One initiative per use case — that initiative IS the workspace for it, and it carries the transcript, the mechanism report and the reproduce command. Both folders are gitignored («ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.

| scenario | initiative (the workspace) | fix task |
|---|---|---|
| `best-pediatric-dentists__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `best-plumber-same-day__es` | `.meshkore/roadmap/initiatives/V2-228-uc-best-plumber-same-day-es.md` | `` |
| `best-plumber-same-day__us` | `.meshkore/roadmap/initiatives/V2-407-uc-best-plumber-same-day-us.md` | `` |
| `best-rated-rental-car__es` | `.meshkore/roadmap/initiatives/V2-230-uc-best-rated-rental-car-es.md` | `` |
| `best-rated-rental-car__us` | `.meshkore/roadmap/initiatives/V2-408-uc-best-rated-rental-car-us.md` | `` |
| `book-barber-slot__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `book-hotel-night-known__us` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `buy-known-product__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cancel-subscription-before-charge__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-broadband-plans__es` | `.meshkore/roadmap/initiatives/V2-231-uc-compare-broadband-plans-es.md` | `` |
| `compare-flights-madrid-lisboa` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-flights-sf-austin__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-insurance-quotes__es` | `.meshkore/roadmap/initiatives/V2-229-uc-compare-insurance-quotes-es.md` | `` |
| `compare-insurance-quotes__us` | `.meshkore/roadmap/initiatives/V2-446-uc-compare-insurance-quotes-us.md` | `.meshkore/modules/nucleo/tasks/T492-uc-compare-insurance-quotes-us-fix.md` |
| `compare-phone-plans__us` | `.meshkore/roadmap/initiatives/V2-447-uc-compare-phone-plans-us.md` | `.meshkore/modules/nucleo/tasks/T493-uc-compare-phone-plans-us-fix.md` |
| `find-concert-tickets__es` | `.meshkore/roadmap/initiatives/V2-263-uc-find-concert-tickets-es.md` | `` |
| `find-direct-flight-budget__es` | `.meshkore/roadmap/initiatives/V2-265-uc-find-direct-flight-budget-es.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `find-theatre-tickets__us` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `kid-friendly-activity-nearby__es` | `.meshkore/roadmap/initiatives/V2-266-uc-kid-friendly-activity-nearby-es.md` | `` |
| `renew-gym-membership__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `rental-car-automatic-airport__es` | `.meshkore/roadmap/initiatives/V2-267-uc-rental-car-automatic-airport-es.md` | `` |
| `reorder-prescription__us` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `restaurant-tonight-nyc__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `search-buy-bicycle__es` | `.meshkore/roadmap/initiatives/V2-268-uc-search-buy-bicycle-es.md` | `` |
| `search-buy-bicycle__us` | `.meshkore/roadmap/initiatives/V2-410-uc-search-buy-bicycle-us.md` | `` |
| `things-to-do-nearby-weekend__es` | `.meshkore/roadmap/initiatives/V2-312-uc-things-to-do-nearby-weekend-es.md` | `` |
| `two-searches-two-sheets` | `.meshkore/roadmap/initiatives/V2-264-uc-two-searches-two-sheets.md` | `` |
| `weekend-adventure-sports-bilbao__es` | `.meshkore/roadmap/initiatives/V2-217-uc-weekend-adventure-sports-bilbao-es.md` | `` |
| `weekend-barber-availability__es` | `.meshkore/roadmap/initiatives/V2-232-uc-weekend-barber-availability-es.md` | `` |
| `weekend-motor-events__es` | `.meshkore/roadmap/initiatives/V2-272-uc-weekend-motor-events-es.md` | `` |
| `weekend-plan-barcelona__es` | `.meshkore/roadmap/initiatives/V2-216-uc-weekend-plan-barcelona-es.md` | `` |

## Rondas en las que NO le dijimos lo que ya tenía

Turnos posteriores a que la hoja tuviera filas con nombre en los que el prompt de zaelar **no decía que hubiera nada**. En esos turnos, un «sigo buscando» no es retener ni negar: es repetir lo que le pusimos delante. Parte del rojo de estas filas es nuestro.

| scenario | turnos ciegos |
|---|---|
| `best-plumber-same-day__es` | 10 |
| `search-buy-camera__us` | 4 |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | code, generic, web |
| `two-searches-two-sheets` | 2 | web |
