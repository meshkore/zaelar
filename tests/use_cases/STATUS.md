# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-20 15:08**

`✅ PASS` = judge overall ≥ 4 **and** mechanism ≥ 3 (a measured mechanism defect never shows green, however good the average) · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

| | scenario | tier | overall | last run | sandbox | verdict |
|---|---|---|---|---|---|---|
| ❌ | `book-hotel-night-known__es` | 1 | 2 | 2026-08-20 13:42 | yes | El caso no está listo para producción porque el sistema miente sobre el estado de la reserva (alucina éxito) y carece de resiliencia básica para superar un b… |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| ✅ | `cancel-subscription-before-charge__es` | 1 | 5 | 2026-08-20 13:49 | yes | Listo para producción. La conducta es impecable: identifica con precisión qué falta (acceso/cuenta) y qué necesita el usuario para lograrlo, sin inventar un … |
| ❌ | `find-theatre-tickets__es` | 1 | 2 | 2026-08-20 15:06 | yes | El caso NO está listo para producción. El bloqueador nº1 es la incapacidad del sistema para detectar y reportar bloqueos externos (anti-botting) y errores in… |
| ❌ | `quick-fact-opening-hours` | 1 | 2 | 2026-08-20 15:08 | yes | No está listo para producción. El bloqueador principal es la generación de información fáctica falsa sin consultar fuentes externas; zaelar está inventando d… |
| ❌ | `remember-and-remind-deadline` | 1 | 3 | 2026-08-20 14:43 | yes | El caso de uso NO está listo para producción. El bloqueador principal es la incapacidad del sistema para garantizar que el recordatorio se produzca ANTES del… |
| ❌ | `renew-gym-membership__es` | 1 | 4 | 2026-08-20 14:51 | yes | El caso tiene un manejo de conversación excelente y claridad en los límites, pero el navegador no se activó como se prometió; la ejecución técnica está desin… |
| ❌ | `restaurant-tonight-madrid` | 1 | 2 | 2026-08-20 15:01 | yes | No está listo para producción este caso de uso; el bloqueador nº1 es la incapacidad del navegador para superar filtros anti-robot (CAPTCHA) en los principale… |
| ❌ | `cheapest-monitor` | 2 | 1 | 2026-08-20 14:57 | yes | El caso no está listo para producción: el sistema es incapaz de completar una búsqueda básica de productos debido a fallos de red y manejo de errores, result… |

**2 passing · 7 failing · 0 infra** of 9 scenarios with a recorded result.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 47 | 4 | 1 |
| 🔑 credentials | 54 | 5 | 1 |
| 🚧 capability | 24 | 0 | 0 |

## Coverage of the RUNNABLE list — 4 of 47 ever run (43 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 3 | 3 | 1 |
| 2 | es | 1 | 19 | 0 |
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

One initiative per use case — that initiative IS the workspace for it, and it carries the transcript, the mechanism report and the reproduce command. Both folders are gitignored («ni nuestro pasado ni nuestro futuro se publican»), so these paths are local-only.

| scenario | initiative (the workspace) | fix task |
|---|---|---|
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `cheapest-monitor` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `quick-fact-opening-hours` | `.meshkore/roadmap/initiatives/V2-204-uc-quick-fact-opening-hours.md` | `.meshkore/modules/nucleo/tasks/T452-uc-quick-fact-opening-hours-fix.md` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `renew-gym-membership__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
