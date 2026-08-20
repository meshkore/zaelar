# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-20 16:16**

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
| ⚠️ | `book-hotel-night-known__es` | 1 | — | 2026-08-20 16:10 | yes | INFRA: HTTP Error 503: Service Unavailable |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| 🔒 | `cancel-subscription-before-charge__es` | 1 | 2 | 2026-08-20 15:46 | yes | No está listo para producción: supo decir con precisión qué le faltaba (el acceso a la cuenta) y ofrecer el login, pero luego cayó en el fallo más grave al n… |
| 🔒 | `find-theatre-tickets__es` | 1 | 2 | 2026-08-20 15:24 | yes | El caso no está listo para producción: el bloqueador nº1 es que el sistema falló silenciosamente por un error de permisos ('blocked cd'), dejando al usuario … |
| ❌ | `quick-fact-opening-hours` | 1 | 3 | 2026-08-20 16:00 | yes | No está listo para producción: aunque dio la hora y el precio en el mismo turno, la respuesta se contradice sobre el precio y el mecanismo escaló a un worker… |
| ❌ | `remember-and-remind-deadline` | 1 | 3 | 2026-08-20 15:49 | yes | No está listo para producción: el bloqueador nº1 es que el `prompt` del cron lleva la frase cruda del usuario, así que el recordatorio hará que el agente vue… |
| 🔒 | `renew-gym-membership__es` | 1 | 4 | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| 🔒 | `restaurant-tonight-madrid` | 1 | 2 | 2026-08-20 15:01 | yes | No está listo para producción este caso de uso; el bloqueador nº1 es la incapacidad del navegador para superar filtros anti-robot (CAPTCHA) en los principale… |
| ❌ | `cheapest-monitor` | 2 | 1 | 2026-08-20 16:16 | yes | No está listo para producción: el bloqueador nº1 es que no se entregó ningún resultado real (cero búsquedas web, cero opciones en pantalla), y encima se narr… |
| ❌ | `search-buy-camera__es` | 2 | 1 | 2026-08-20 15:16 | yes | No está listo para producción. El bloqueador principal es la estabilidad del Worker de navegador: el sistema agotó el tiempo de espera (timeout) sin generar … |

**1 passing · 4 failing · 1 infra** of 6 scenarios we can actually finish.

Plus **4 🔒 capped** (need the user's own credentials; measured for honesty only, not counted above — 1 of them behaving impeccably up to the wall): `cancel-subscription-before-charge__es`, `find-theatre-tickets__es`, `renew-gym-membership__es`, `restaurant-tonight-madrid`.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 47 | 5 | 1 |
| 🔑 credentials | 54 | 5 | 0 |
| 🚧 capability | 24 | 0 | 0 |

## Coverage of the RUNNABLE list — 5 of 47 ever run (42 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 3 | 3 | 1 |
| 2 | es | 2 | 19 | 0 |
| 2 | us | 0 | 18 | 0 |
| 3 | es | 0 | 4 | 0 |
| 3 | us | 0 | 2 | 0 |
| 4 | es | 0 | 1 | 0 |

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
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `quick-fact-opening-hours` | `.meshkore/roadmap/initiatives/V2-204-uc-quick-fact-opening-hours.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `search-buy-camera__es` | `.meshkore/roadmap/initiatives/V2-206-uc-search-buy-camera-es.md` | `.meshkore/modules/nucleo/tasks/T454-uc-search-buy-camera-es-fix.md` |
