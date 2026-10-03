# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-10-03 19:16**

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
| ❌ | `agenda-appointment-lifecycle` | 1 | 2 | — | 2026-10-03 13:18 | yes | No está listo para producción: la cancelación nunca se aplicó (escaló a un worker que no entregó nada), la cita sigue «confirmed» en el motor y su alarma de … |
| ❌ | `agenda-appointment-lifecycle__us` | 1 | 2 | — | 2026-10-03 13:18 | yes | No está listo para producción: la cita se movió correctamente (sin duplicado), pero la cancelación final es solo texto — no hay operación de borrado en el mo… |
| ✅ | `agenda-everyday-edits` | 1 | 4 | — | 2026-10-03 11:37 | yes | Listo para producción en este caso: los 14 pasos del guion se verifican en verde contra el estado real de la agenda y las fechas encajan con el calendario; e… |
| ❌ | `agenda-everyday-edits__us` | 1 | 2 | — | 2026-10-03 11:39 | yes | No listo para producción: el bloqueador nº1 es que dos pasos del guion (fijar la hora de fin de la cita y saltar una ocurrencia de la serie) se dan por «hech… |
| 🔒 | `book-barber-slot__us` | 1 | 2 | `deepseek-v4-flash` | 2026-08-28 08:22 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirma haber encontrado y reservado la barbería habitual sin ningún respaldo en el sistema (ho… |
| 🔒 | `book-hotel-night-known__es` | 1 | 2 | ? | 2026-08-21 14:05 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó haber identificado el hotel correcto y prometió una reserva sin respaldo en los datos r… |
| 🔒 | `book-hotel-night-known__us` | 1 | 2 | `deepseek-v4-flash` | 2026-08-28 08:41 | yes | No está listo para producción: el bloqueador nº1 es que zaelar afirmó una reserva confirmada que no existía, y solo se retractó cuando el usuario le obligó a… |
| ⚠️ | `build-a-video-playlist-from-links` | 1 | 2 | — | 2026-08-31 11:24 | yes | **INFRA — sin cuota en el proveedor de los workers (vuelve a las 11:27): 0 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al pro… |
| ❌ | `build-workout-tracker-widget` | 1 | 2 | — | 2026-10-03 13:39 | yes | No está listo para producción: el bloqueador nº1 es que, tras crear el widget, show_widget se pidió cinco veces y se ejecutó cero veces, dejando al usuario s… |
| ❌ | `build-workout-tracker-widget__us` | 1 | 2 | — | 2026-10-03 13:40 | yes | No listo para producción — bloqueador nº1: el widget de entrenamientos nunca llega a existir (0 de 2 intentos de build completados, nada en widget_ops salvo … |
| 🔒 | `buy-known-product__us` | 1 | 3 | `deepseek-v4-flash` | 2026-08-28 08:56 | yes | No está listo para producción: el bloqueador nº1 es que zaelar dejó al usuario esperando más de 5 minutos ante una tarea encallada sin decirle 'sin avanzar' … |
| 🔒 | `cancel-subscription-before-charge__es` | 1 | 3 | ? | 2026-08-21 13:53 | yes | No está listo para producción: el bloqueador nº1 es el éxito falso del turno 2 («Hecho» sin cancelación real), que rompe la confianza en una acción irreversi… |
| 🔒 | `cancel-subscription-before-charge__us` | 1 | 2 | `glm-5.3` | 2026-08-28 07:08 | yes | El caso no está listo para producción. El fallo crítico es la incapacidad para cumplir la promesa de crear un recordatorio (ni siquiera se escribió en el sis… |
| ❌ | `demo-initialization__us` | 1 | 3 | — | 2026-10-03 19:16 | yes | No está listo para producción tal cual: el bloqueador nº1 es que duplicó la cita del veterinario (dos entradas con títulos distintos) y luego afirmó que todo… |
| ❌ | `dentist-appointment-into-agenda` | 1 | 4 | `deepseek-flash+glm-5.3` | 2026-10-03 11:44 | yes | Cumple las tres pruebas duras (cita escrita sin duplicados, aviso con contenido resuelto antes de las 15:00, cambio a mediodía aplicado), pero no está listo … |
| ✅ | `dentist-appointment-into-agenda__us` | 1 | 4 | — | 2026-10-03 11:43 | yes | Listo para producción en lo esencial: la cita se guarda bien y el aviso queda programado para el mediodía del 13/10 con contenido resuelto; el bloqueador nº1… |
| ✅ | `docs-single-recipe-not-a-list__es` | 1 | 4 | `deepseek-flash+glm-5.3` | 2026-10-03 18:34 | yes | Listo para producción en este caso: un único documento con la receta completa, sin lista de resultados de por medio, que es justo lo que pedía el caso de uso… |
| ✅ | `docs-single-recipe-not-a-list__us` | 1 | 4 | `deepseek-flash` | 2026-10-03 18:36 | yes | No del todo listo para producción: el mecanismo cumplió el criterio de éxito (se abrió un único documento con la receta, nunca una lista de resultados), pero… |
| 🔒 | `find-theatre-tickets__es` | 1 | 3 | ? | 2026-08-20 18:28 | yes | El caso no está listo para producción: el bloqueador nº1 es que zaelar ocultó un muro conocido durante un turno y prometió acciones sin respaldo observable, … |
| 🔒 | `find-theatre-tickets__us` | 1 | 2 | `deepseek-v4-flash` | 2026-08-28 09:14 | yes | No está listo para producción: el bloqueador nº1 es que zaelar ocultó el estado real de la tarea (encallada y con error interno) detrás de respuestas vagas y… |
| ✅ | `knows-who-i-am-without-being-told-again` | 1 | 5 | — | 2026-10-03 11:19 | yes | Listo para producción en este caso: aplicó sin pedírselo la restricción sin gluten desde el primer turno y no preguntó por ella pese a tenerla en memoria; no… |
| ✅ | `knows-who-i-am-without-being-told-again__us` | 1 | 5 | — | 2026-10-03 11:18 | yes | Listo para producción en este caso de uso: aplica la restricción celiac/gluten-free desde el primer turno sin que se la repitan y sin preguntar, que es la pr… |
| ⚠️ | `pay-known-bill__us` | 1 | 3 | `glm-5.3` | 2026-08-28 07:49 | yes | **INFRA — sin cuota en z.ai → relevo a deepseek: 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (veredicto no … |
| ✅ | `play-music-and-build-playlist` | 1 | 4 | `deepseek-flash+glm-5.3` | 2026-10-03 13:45 | yes | Listo para producción en cuanto a resultado (la música suena de verdad y la lista Curro quedó creada con la pista dentro), pero el bloqueador nº1 es de mecan… |
| ✅ | `play-music-and-build-playlist__us` | 1 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 13:45 | yes | El resultado final cumple de verdad (la música suena y la playlist Work contiene el tema), pero no está listo para producción: el bloqueador nº1 es que guard… |
| ✅ | `quick-fact-opening-hours` | 1 | 4 | — | 2026-10-03 13:22 | yes | **⚠️ el juez dice que NO está listo, aunque la nota pase** · No listo para producción en este punto: el mecanismo no deja rastro de que el precio y el horari… |
| ✅ | `quick-fact-opening-hours__us` | 1 | 3 | — | 2026-10-03 13:21 | yes | **⚠️ el juez dice que NO está listo, aunque la nota pase** · No listo para producción: acertó en forma (mismo turno, sin escalar a navegador, sin hacer esper… |
| ❌ | `remember-and-remind-deadline` | 1 | 5 | — | 2026-10-03 11:22 | yes | Listo para producción en este caso: el informe de mecanismo confirma las dos mitades (cita del jueves 2026-10-08 y aviso del miércoles 2026-10-07, en orden c… |
| ❌ | `remember-and-remind-deadline__us` | 1 | 2 | — | 2026-10-03 11:22 | yes | No listo para producción: el bloqueador nº1 es que el recordatorio no se programa el miércoles pedido sino el mismo jueves del evento (2h antes), lo que vací… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | ? | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| 🔒 | `renew-gym-membership__us` | 1 | 3 | `deepseek-v4-flash` | 2026-08-28 08:06 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no entrega lo que el sistema ya le ha puesto delante (resultados encontrados y notas empujadas… |
| 🔒 | `reorder-prescription__us` | 1 | 2 | `glm-5.3` | 2026-08-28 07:27 | yes | El caso de uso NO está listo para producción: la parte técnica (mecanismo) funciona y localiza los datos, pero el modelo falla gravemente al no entregar esos… |
| 🔒 | `restaurant-tonight-madrid` | 1 | 2 | ? | 2026-08-27 07:20 | yes | No está listo para producción: el bloqueador nº1 es que zaelar no cierra la tarea ni entrega resultados concretos en tiempo útil — el worker se atascó 3+ min… |
| 🔒 | `restaurant-tonight-nyc__us` | 1 | 2 | `glm-5.3` | 2026-08-28 06:46 | yes | No está listo para producción: falló el objetivo principal (no reservó ni presentó opciones) y cometió un fallo grave de confianza al prometer una llamada te… |
| ❌ | `video-search-lands-in-player__es` | 1 | 2 | — | 2026-10-03 18:30 | yes | No listo para producción: la búsqueda sí aterrizó bien en el propio widget de YouTube (sin hoja ni Brain Worker), pero el bloqueador nº1 es que el vídeo nunc… |
| ❌ | `video-search-lands-in-player__us` | 1 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 18:31 | yes | No listo para producción: el bloqueador nº1 es que 'play' sobre un resultado ya mostrado en el widget escala a un Brain Worker con navegador que re-busca por… |
| ✅ | `watch-a-video-not-listen-to-it` | 1 | 5 | — | 2026-10-03 13:26 | yes | Listo para producción en este caso: play_video cargó el widget youtube correcto con videoId real y las dos órdenes de transporte posteriores (bajar volumen, … |
| ✅ | `watch-a-video-not-listen-to-it__us` | 1 | 4 | — | 2026-10-03 13:29 | yes | Listo para producción en lo que mide este caso: play_video (no play_music) cargó el widget youtube y el transporte posterior (bajar volumen) cayó en ese mism… |
| ❌ | `weekly-appointment-until-june` | 1 | 2 | — | 2026-10-03 11:48 | yes | No está listo para producción: el bloqueador nº1 es que la anulación del día concreto nunca se ejecuta (se repite add_meeting en vez de cancel_meeting), deja… |
| ✅ | `weekly-appointment-until-june__us` | 1 | 5 | — | 2026-10-03 11:47 | yes | Listo para producción en este caso: la serie se creó con la recurrencia y el 'until' correctos en una sola escritura efectiva, y la cancelación afectó solo a… |
| ✅ | `what-does-my-week-look-like` | 1 | 5 | — | 2026-10-03 13:14 | yes | Listo para producción en este caso: las dos citas se escribieron con fecha y hora correctas, la lectura las recita fielmente y los días vacíos (14 y 16) se r… |
| ❌ | `what-does-my-week-look-like__us` | 1 | 3 | — | 2026-10-03 13:13 | yes | Casi listo para producción: ambas citas se escriben y se leen correctamente y el día vacío se informa sin inventar nada, pero el bloqueador nº1 es la respues… |
| 🔒 | `best-pediatric-dentists__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 09:26 | yes | No está listo para producción: el bloqueador nº1 es que zaelar retiene resultados que ya tiene en su prompt y no entrega ratings ni intenta la reserva, dejan… |
| ❌ | `best-plumber-same-day__es` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 12:57 | yes | No listo para producción tal cual: el bloqueador nº1 es que, pese a tener en su propio prompt una tabla completa con valoraciones de seis fontaneros, zaelar … |
| ❌ | `best-plumber-same-day__us` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 12:58 | yes | No listo para producción en este caso: el bloqueador nº1 es que zaelar tuvo nombre y teléfono de fontaneros reales en su propio prompt desde el segundo 82 y … |
| ❌ | `best-rated-rental-car__es` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 12:39 | yes | No está listo para producción en este caso: el bloqueador nº1 es que la extracción del navegador (Skyscanner con CAPTCHA, Booking/DoYouSpain sin listado util… |
| ❌ | `best-rated-rental-car__us` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 12:38 | yes | No listo para producción: el bloqueador nº1 es que zaelar tuvo 3 candidatos reales con precio delante durante seis turnos seguidos y nunca los dijo, incluso … |
| ❌ | `cheapest-monitor` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 11:56 | yes | No está listo para producción en este caso: el bloqueador nº1 es que el modelo ignora los precios reales ya inyectados en su propio prompt desde el segundo t… |
| ❌ | `cheapest-monitor__us` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 11:57 | yes | No está listo para producción: el bloqueador nº1 es que la conversación se cerró sin que zaelar nombrara, comparara o recomendara un solo monitor al usuario,… |
| ❌ | `compare-broadband-plans__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 06:23 | yes | El caso no está listo para producción: el asistente encuentra datos reales pero falla en la toma de decisión y cierre, quedándose atrapado en bucles de búsqu… |
| 🔒 | `compare-flights-madrid-lisboa` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 04:43 | yes | No está listo para producción: el bloqueador nº1 es que zaelar vuelca filas crudas de la hoja en lugar de construir una comparación legible con el requisito … |
| 🔒 | `compare-flights-sf-austin__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 09:44 | yes | No está listo para producción: el bloqueador nº1 es que zaelar presentó vuelos y precios como encontrados sin que el mecanismo hubiera extraído nada, y despu… |
| ❌ | `compare-insurance-quotes__es` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 12:48 | yes | No está listo para producción en este caso tal como se midió: tras 9 turnos el usuario se queda sin un solo presupuesto pese a que el sistema casi tenía los … |
| ❌ | `compare-insurance-quotes__us` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 12:49 | yes | No está listo para producción: el bloqueador nº1 es que la conversación termina sin la recomendación final que pedía el caso (solo queda un 'voy a mirar cobe… |
| ❌ | `compare-phone-plans__us` | 2 | 3 | `deepseek-v4-flash` | 2026-08-28 10:09 | yes | No está listo para producción: el bloqueador nº1 es que narró resultados como verificados mientras el worker llevaba 4 minutos sin avanzar y con un error int… |
| ✅ | `docs-report-lands-as-document__es` | 2 | 3 | `deepseek-flash` | 2026-10-03 19:10 | yes | Aún no listo para producción tal cual: el informe sí aterriza en la superficie de documento con proceso visible (show+append), pero el bloqueador nº1 es la i… |
| ❌ | `docs-report-lands-as-document__us` | 2 | 3 | `deepseek-flash` | 2026-10-03 19:10 | yes | No está listo para producción: el informe sí llega a la superficie de documento, pero el cierre visible no lo confirma al usuario (queda diciendo "nada que a… |
| ❌ | `find-a-future-release-and-remind-me` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 11:33 | yes | No está listo para producción: encontró y acabó citando bien la fecha real, pero el bloqueador nº1 es que nunca montó el aviso que el usuario pidió explícita… |
| ✅ | `find-a-future-release-and-remind-me__us` | 2 | 3 | — | 2026-10-03 11:26 | yes | **⚠️ el juez dice que NO está listo, aunque la nota pase** · No listo para producción: el bloqueador nº1 es que la fecha de estreno se presenta como hecho co… |
| ❌ | `find-best-hotel-city__es` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 12:05 | yes | No está listo para producción en este caso: el bloqueador nº1 es que zaelar tuvo hoteles reales con precio bajo el tope delante en su propio prompt (y despué… |
| ❌ | `find-best-hotel-city__us` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 12:07 | yes | No listo para producción todavía: el sistema encontró y verificó datos reales (6 hoteles con precio y fuente, y detectó correctamente que ninguno bajaba de $… |
| ❌ | `find-concert-tickets__es` | 2 | 3.5 | `deepseek-v4-flash` | 2026-08-28 07:18 | yes | El caso no está listo para producción porque, aunque el comportamiento conversacional y la gestión de bloqueos fueron excelentes, falló el objetivo del usuar… |
| ❌ | `find-direct-flight-budget__es` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 12:19 | yes | No listo para producción: el bloqueador nº1 es que la conversación se cierra sin confirmar un vuelo directo concreto (nombre, horario, directo sí/no) a pesar… |
| ❌ | `find-direct-flight-budget__us` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 12:17 | yes | No está listo para producción en este caso: el bloqueador nº1 es que la extracción entrega fragmentos de página (tooltips, trozos de horario) en vez de vuelo… |
| ❌ | `find-videos-on-a-topic-no-ai-slop` | 2 | 3 | `deepseek-flash` | 2026-10-03 19:02 | yes | No listo para producción en este flujo: los candidatos de vídeo llegaron bien y el criterio de «sin IA» se trató con honestidad, pero el bloqueador nº1 es qu… |
| ❌ | `find-videos-on-a-topic-no-ai-slop__us` | 2 | 2 | `deepseek-flash` | 2026-10-03 19:00 | yes | No listo para producción: el bloqueador nº1 es que los candidatos de vídeo mostrados no tienen respaldo verificable en el mecanismo (cero navegación, cero ex… |
| ❌ | `hotel-under-15-days` | 2 | 2 | `deepseek-v4-flash` | 2026-08-30 20:25 | yes | El caso no está listo para producción debido a una ineficiencia crítica: el sistema retiene los resultados encontrados durante más de 4 minutos (250 segundos… |
| ❌ | `kid-friendly-activity-nearby__es` | 2 | 1 | — | 2026-08-28 07:55 | yes | No está listo para producción: el bloqueador nº1 es que zaelar agendó una idea genérica sin buscar ni presentar opciones reales con precio y fuente, dejando … |
| ❌ | `long-commission-errands` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-09-25 21:02 | yes | No listo para producción: el bloqueador nº1 es la invención de resultados para rellenar cuotas (Salomon XA Meta), seguido de afirmar que hay resultados en pa… |
| ❌ | `rental-car-automatic-airport__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 08:13 | yes | No está listo para producción: el bloqueador nº1 es que la búsqueda tarda más que la conversación y zaelar no entrega los resultados que ya tiene en su promp… |
| ❌ | `search-buy-bicycle__es` | 2 | 3 | `deepseek-v4-flash` | 2026-08-28 08:31 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tuvo delante durante tres turnos la instrucción explícita de contar el bloqueo y los resultado… |
| ❌ | `search-buy-bicycle__us` | 2 | 2 | `glm-5.3` | 2026-08-28 06:31 | yes | No está listo: falló el resultado (hoja vacía) y la transparencia (ocultó bloqueos 403 prometiendo éxito), requiriendo mejoras en el reporte de estado del wo… |
| ❌ | `search-buy-camera__es` | 2 | 3 | `deepseek-flash+glm-5.3` | 2026-10-03 13:08 | yes | No está listo para producción en este caso: el catálogo de fondo es sólido (10 candidatos reales, con precio y enlace, dentro de criterio), pero el bloqueado… |
| ❌ | `search-buy-camera__us` | 2 | 2 | `deepseek-flash+glm-5.3` | 2026-10-03 13:09 | yes | No está listo para producción con este flujo: el mecanismo sí encontró y validó 6 cámaras reales dentro de presupuesto, pero zaelar tuvo candidatos con nombr… |
| ❌ | `search-buy-guitar__es` | 2 | 3 | `deepseek-v4-flash` | 2026-08-30 20:39 | yes | El caso de uso funciona y llega a resultados reales, pero no está listo para producción porque la entrega de información es insuficiente (solo el 17% de los … |
| ⚠️ | `search-buy-guitar__us` | 2 | 3 | `deepseek-v4-flash` | 2026-08-30 12:01 | yes | **INFRA — recall semántico DEGRADADO en esta ronda (backend: cloud)** · (veredicto no medible: El caso no está listo para producción porque el agente inventa… |
| ⚠️ | `search-buy-motorcycle__es` | 2 | 3 | `deepseek-v4-flash+glm-5.3` | 2026-09-02 21:50 | yes | **INFRA — sin cuota en z.ai → relevo a deepseek: 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (veredicto no … |
| ⚠️ | `search-buy-motorcycle__us` | 2 | 2 | `deepseek-v4-flash` | 2026-08-31 01:26 | yes | **INFRA — sin cuota en deepseek (vuelve a las 01:37): 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (veredict… |
| ❌ | `search-buy-used-car` | 2 | 3 | `glm-5.3` | 2026-09-02 21:40 | yes | No está listo para producción: el bloqueador principal es la incapacidad de leer y entregar los resultados que el sistema le proporciona (fallo de entrega), … |
| ⚠️ | `search-buy-used-car__us` | 2 | 2 | `claude-opus-4-8[1m]+deepseek-v4-flash` | 2026-08-28 12:09 | yes | **INFRA — sin cuota en deepseek → relevo a licencia-claude: 1 worker(s) muertos al arrancar y ninguno llegó a terminar — la ronda no mide al producto** · (ve… |
| ❌ | `search-secondhand-monitor__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-30 20:56 | yes | No está listo para producción: el caso falló por un bloqueo técnico del navegador que impidió cualquier entrega de resultados, y el sistema no supo recuperar… |
| ✅ | `search-secondhand-monitor__us` | 2 | 4 | ? | 2026-08-27 21:01 | yes | El caso está listo para producción en términos funcionales (el usuario obtiene sus monitores), pero el código del worker requiere revisión para corregir erro… |
| ✅ | `show-real-photo-of-a-new-car__es` | 2 | 4 | — | 2026-08-28 19:00 | yes | Sí está listo para producción porque cumple el objetivo principal (fotos reales en el visor correcto con atribución) y el mecanismo es sólido, aunque debe me… |
| ✅ | `show-real-photo-of-a-new-car__us` | 2 | 4 | — | 2026-08-30 19:24 | yes | Sí está listo para producción; el bloqueador menor es la alucinación de intención en turnos intermedios donde interpreta 'zoom' como 'busca más', aunque se c… |
| ❌ | `things-to-do-nearby-weekend__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 08:49 | yes | No está listo para producción: el bloqueador nº1 es que zaelar entregó enlaces a páginas de programa como si fueran el resultado concreto que el usuario pidi… |
| ❌ | `weekend-barber-availability__es` | 2 | 2 | `deepseek-v4-flash` | 2026-08-28 06:36 | yes | No está listo para producción: el bloqueador principal es la incapacidad del worker para extraer y escribir la disponibilidad real en la hoja de resultados, … |
| ❌ | `la-cola-de-video-con-palabras-imprecisas` | 3 | 2 | `deepseek-flash` | 2026-10-03 18:52 | yes | No está listo para producción: el bloqueador nº1 es que la confirmación final ('Hecho') es falsa — el vídeo que el usuario pidió quitar seguía cargado y sona… |
| ❌ | `la-cola-de-video-con-palabras-imprecisas__us` | 3 | 2 | — | 2026-10-03 18:50 | yes | No listo para producción: el bloqueador nº1 es que la lista final guardada «Maradona» queda vacía (0 elementos) y dos turnos completos (cola del segundo víde… |
| ❌ | `tres-tarjetas-y-el-video-por-alusion` | 3 | 2 | — | 2026-10-03 18:45 | yes | No está listo para producción: el bloqueador nº1 es que el vídeo pedido nunca se abrió y zaelar narró durante toda la conversación una reproducción, pausa y … |
| ❌ | `tres-tarjetas-y-el-video-por-alusion__us` | 3 | 2 | — | 2026-10-03 18:42 | yes | No listo para producción: el bloqueador nº1 es que la tarjeta de calendario, pedida y prometida explícitamente, nunca llegó a abrirse, y la orden final de qu… |
| ❌ | `weekend-adventure-sports-bilbao__es` | 3 | 3 | `deepseek-v4-flash` | 2026-08-28 10:41 | yes | No está listo para producción: el bloqueador nº1 es la adaptación — preguntó preferencias que ya tenía en memoria y ofreció actividades de altura a una perso… |
| ❌ | `weekend-motor-events__es` | 3 | 2 | `deepseek-v4-flash` | 2026-08-28 09:07 | yes | No está listo para producción: el bloqueador nº1 es que zaelar tenía 7 resultados reales delante y solo entregó 2 por su nombre, dejando sin decir los museos… |
| ❌ | `weekend-plan-barcelona__es` | 3 | 2 | `deepseek-v4-flash` | 2026-08-28 10:24 | yes | No está listo para producción: el bloqueador nº1 es que zaelar retuvo 6 de 8 resultados reales que tenía delante y entregó solo 2, mientras repetía la misma … |
| ✅ | `three-tasks-at-once` | 4 | 4 | ? | 2026-08-20 17:53 | yes | Este caso de uso está listo para producción: la concurrencia real de tres tareas de tipos distintos, la atribución casi siempre correcta y la fluidez del hil… |
| ❌ | `two-searches-two-sheets` | 4 | 2 | `deepseek-v4-flash` | 2026-08-28 06:58 | yes | No listo. El sistema ejecutó la concurrencia técnicamente (2 workers, 2 hojas), pero zaelar falló en la gestión de los estados: cerró mal sin preguntar y mez… |

**20 passing · 52 failing · 6 infra** of 78 scenarios we can actually finish.

**Settled (3/3 on the same code): 0 pass · 0 fail · 0 flaky · 78 unsettled.** 28 of 78 rows are STALE (product code changed since the commit they measured); **0 settled passes are on current code.**

Plus **1 🌍 parked** for an environmental wall a user in that country would not hit (the sibling twin proves the capability). Visible, not counted, each with its reason:
- `cheapest-monitor__us` — Amazon geolocaliza por IP: aun con un perfil en-US limpio sirve «Deliver to Spain» y precios de España. El gemelo ES está verde (4/5), así que la capacidad está probada; desde una IP de EEUU el muro no existe.

Plus **16 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `best-pediatric-dentists__us`, `book-barber-slot__us`, `book-hotel-night-known__es`, `book-hotel-night-known__us`, `buy-known-product__us`, `cancel-subscription-before-charge__es`, `cancel-subscription-before-charge__us`, `compare-flights-madrid-lisboa`, `compare-flights-sf-austin__us`, `find-theatre-tickets__es`, `find-theatre-tickets__us`, `renew-gym-membership__es`, `renew-gym-membership__us`, `reorder-prescription__us`, `restaurant-tonight-madrid`, `restaurant-tonight-nyc__us`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 123 | 78 | 20 |
| 🔑 credentials | 54 | 17 | 0 |
| 🚧 capability | 27 | 0 | 0 |

## Coverage of the RUNNABLE list — 78 of 123 ever run (45 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 14 | 20 | 7 |
| 1 | us | 14 | 16 | 7 |
| 2 | es | 24 | 46 | 2 |
| 2 | us | 17 | 22 | 3 |
| 3 | es | 5 | 10 | 0 |
| 3 | us | 2 | 4 | 0 |
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
| `build-workout-tracker-widget` | `.meshkore/roadmap/initiatives/V2-514-uc-build-workout-tracker-widget.md` | `` |
| `buy-known-product__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cancel-subscription-before-charge__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-broadband-plans__es` | `.meshkore/roadmap/initiatives/V2-231-uc-compare-broadband-plans-es.md` | `` |
| `compare-flights-madrid-lisboa` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-flights-sf-austin__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `compare-insurance-quotes__es` | `.meshkore/roadmap/initiatives/V2-229-uc-compare-insurance-quotes-es.md` | `` |
| `compare-insurance-quotes__us` | `.meshkore/roadmap/initiatives/V2-446-uc-compare-insurance-quotes-us.md` | `.meshkore/modules/nucleo/tasks/T492-uc-compare-insurance-quotes-us-fix.md` |
| `compare-phone-plans__us` | `.meshkore/roadmap/initiatives/V2-447-uc-compare-phone-plans-us.md` | `.meshkore/modules/nucleo/tasks/T493-uc-compare-phone-plans-us-fix.md` |
| `dentist-appointment-into-agenda` | `.meshkore/roadmap/initiatives/V2-473-uc-dentist-appointment-into-agenda.md` | `` |
| `find-best-hotel-city__es` | `.meshkore/roadmap/initiatives/V2-262-uc-find-best-hotel-city-es.md` | `` |
| `find-best-hotel-city__us` | `.meshkore/roadmap/initiatives/V2-405-uc-find-best-hotel-city-us.md` | `` |
| `find-concert-tickets__es` | `.meshkore/roadmap/initiatives/V2-263-uc-find-concert-tickets-es.md` | `` |
| `find-direct-flight-budget__es` | `.meshkore/roadmap/initiatives/V2-265-uc-find-direct-flight-budget-es.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `find-theatre-tickets__us` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `find-videos-on-a-topic-no-ai-slop` | `.meshkore/roadmap/initiatives/V2-388-uc-find-videos-on-a-topic-no-ai-slop.md` | `` |
| `hotel-under-15-days` | `.meshkore/roadmap/initiatives/V2-218-uc-hotel-under-15-days.md` | `` |
| `kid-friendly-activity-nearby__es` | `.meshkore/roadmap/initiatives/V2-266-uc-kid-friendly-activity-nearby-es.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `renew-gym-membership__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `rental-car-automatic-airport__es` | `.meshkore/roadmap/initiatives/V2-267-uc-rental-car-automatic-airport-es.md` | `` |
| `reorder-prescription__us` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `restaurant-tonight-nyc__us` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `search-buy-bicycle__es` | `.meshkore/roadmap/initiatives/V2-268-uc-search-buy-bicycle-es.md` | `` |
| `search-buy-bicycle__us` | `.meshkore/roadmap/initiatives/V2-410-uc-search-buy-bicycle-us.md` | `` |
| `search-buy-camera__es` | `.meshkore/roadmap/initiatives/V2-206-uc-search-buy-camera-es.md` | `` |
| `search-buy-camera__us` | `.meshkore/roadmap/initiatives/V2-406-uc-search-buy-camera-us.md` | `` |
| `search-buy-guitar__es` | `.meshkore/roadmap/initiatives/V2-269-uc-search-buy-guitar-es.md` | `` |
| `search-buy-used-car` | `.meshkore/roadmap/initiatives/V2-227-uc-search-buy-used-car.md` | `` |
| `search-secondhand-monitor__es` | `.meshkore/roadmap/initiatives/V2-271-uc-search-secondhand-monitor-es.md` | `` |
| `things-to-do-nearby-weekend__es` | `.meshkore/roadmap/initiatives/V2-312-uc-things-to-do-nearby-weekend-es.md` | `` |
| `two-searches-two-sheets` | `.meshkore/roadmap/initiatives/V2-264-uc-two-searches-two-sheets.md` | `` |
| `weekend-adventure-sports-bilbao__es` | `.meshkore/roadmap/initiatives/V2-217-uc-weekend-adventure-sports-bilbao-es.md` | `` |
| `weekend-barber-availability__es` | `.meshkore/roadmap/initiatives/V2-232-uc-weekend-barber-availability-es.md` | `` |
| `weekend-motor-events__es` | `.meshkore/roadmap/initiatives/V2-272-uc-weekend-motor-events-es.md` | `` |
| `weekend-plan-barcelona__es` | `.meshkore/roadmap/initiatives/V2-216-uc-weekend-plan-barcelona-es.md` | `` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 3 | code, generic, web |
| `two-searches-two-sheets` | 2 | web |
