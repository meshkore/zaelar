# Use-case scoreboard — what actually works right now

**Generated** by `tests/use_cases/e2e/agent/status.py`; do not edit by hand — it is rewritten by
every run of `python -m tests.use_cases.e2e.agent.run`. Source of truth: `status.json` next to it.

Last updated: **2026-08-20 01:21**

`✅ PASS` = judge overall ≥ 4 · `❌ FAIL` = ran and fell short · `⚠️ INFRA` = harness/network problem,
says nothing about the use case itself. `sandbox` = ran against an isolated engine (own DB/port), not
the operator's live one.

| | scenario | tier | overall | last run | sandbox | verdict |
|---|---|---|---|---|---|---|
| ✅ | `book-barber-slot__es` | 1 | 4 | 2026-08-19 01:51 | yes | El comportamiento de zaelar es correcto: no inventó nada, pidió los datos que faltaban y se detuvo en el muro con claridad; el bloqueador nº1 para cerrar el … |
| ❌ | `book-hotel-night-known__es` | 1 | 2 | 2026-08-20 01:01 | yes | El caso NO está listo para producción. El bloqueador nº1 es la incapacidad del sistema para detectar y comunicar un fallo de navegación irreconciliable (CAPT… |
| ✅ | `build-workout-tracker-widget` | 1 | 5 | 2026-08-20 01:01 | yes | Sí, está listo para producción. La ejecución es impecable: generó el widget real, sin latencias excesivas, con una interacción natural y las señales del sist… |
| ⚠️ | `buy-known-product__es` | 1 | — | 2026-08-18 20:51 | yes | INFRA: 'list' object has no attribute 'strip' |
| ❌ | `cancel-subscription-before-charge__es` | 1 | 2 | 2026-08-20 01:21 | yes | No está listo para producción. El bloqueador nº1 es la desconexión total entre la narrativa de zaelar (que afirma tener el control y la lista de tareas en ma… |
| ❌ | `find-theatre-tickets__es` | 1 | 2 | 2026-08-20 01:01 | yes | No está listo para producción. El bloqueador nº1 es la incapacidad del 'worker' para reconocer que ha llegado a la página destino y extraer los datos (parsin… |
| ❌ | `pay-known-bill__es` | 1 | 2 | 2026-08-19 19:12 | yes | No está listo. El bloqueador nº1 es la desconexión total entre el 'narrador' (texto) y el 'actor' (mecanismo): zaelar afirma trabajar cuando el sistema está … |
| ✅ | `quick-fact-opening-hours` | 1 | 5 | 2026-08-19 02:03 | yes | Sí, está listo para producción: zaelar resolvió la consulta con éxito máximo en el primer turno, usando la vía eficiente (búsqueda web) sin desperdiciar recu… |
| ❌ | `remember-and-remind-deadline` | 1 | 1 | 2026-08-20 01:01 | yes | El caso NO está listo para producción: el agente miente sobre el resultado prometido (agenda) y falla en capturar la intención real del usuario frente a su '… |
| ❌ | `renew-gym-membership__es` | 1 | 2 | 2026-08-20 01:01 | yes | No está listo para producción. El agente ha generado una simulación de conversación competente mientras el sistema subyacente no hacía nada, lo que constituy… |
| ❌ | `reorder-prescription__es` | 1 | 3 | 2026-08-19 19:46 | yes | El caso no está listo para producción debido a una desconexión entre el 'estado de tarea done' reportado y la ausencia de señales reales de navegación ('miss… |
| ❌ | `restaurant-tonight-madrid` | 1 | 3 | 2026-08-20 01:01 | yes | El caso es funcional pero ineficiente; el bloqueador principal no es la capacidad técnica, sino la estrategia de feedback y resiliencia ante fallos de carga … |
| ❌ | `cheapest-monitor` | 2 | 1 | 2026-08-20 01:21 | yes | El caso NO está listo para producción. El bloqueador nº1 es la falta de integridad en el resultado: el sistema entregó un producto, precio y tienda falsos (n… |
| ❌ | `three-tasks-at-once` | 4 | 3 | 2026-08-19 19:40 | yes | No está listo para producción. El bloqueo nº1 es la incapacidad del orquestador para mantener vivas las 3 tareas concurrentes solicitadas por el usuario (fal… |

**3 passing · 10 failing · 1 infra** of 14 scenarios with a recorded result.

## Segments — what can be carried out END TO END today

`✅ completable` = nothing missing, run it. `🔑 credentials` = the OPERATOR unblocks it (an account, a card, a phone, a real bill/flight/prescription to act on). `🚧 capability` = WE unblock it (sending on WhatsApp/Telegram, resolving a contact, placing a call, a peer agent to negotiate with) — no credential would help. Classification: `tests/use_cases/e2e/agent/segments.py`.

| segment | scenarios | run | passing |
|---|---|---|---|
| ✅ completable | 47 | 5 | 2 |
| 🔑 credentials | 54 | 9 | 1 |
| 🚧 capability | 24 | 0 | 0 |

## Coverage of the RUNNABLE list — 5 of 47 ever run (42 never run)

An unrun case is **not** a passing one. This is the walk's progress board, and its denominator is the `completable` segment only — a blocked case is not pending work, it is waiting on something outside the harness.

| tier | locale | run | of | passing |
|---|---|---|---|---|
| 1 | es | 3 | 3 | 2 |
| 2 | es | 1 | 19 | 0 |
| 2 | us | 0 | 18 | 0 |
| 3 | es | 0 | 4 | 0 |
| 3 | us | 0 | 2 | 0 |
| 4 | es | 1 | 1 | 0 |

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
| `book-hotel-night-known__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `cancel-subscription-before-charge__es` | `.meshkore/roadmap/initiatives/V2-176-uc-narrar-trabajo-que-no-ocurre.md` | `` |
| `cheapest-monitor` | `.meshkore/roadmap/initiatives/V2-177-uc-cheapest-monitor.md` | `.meshkore/modules/nucleo/tasks/T425-uc-cheapest-monitor-fix.md` |
| `find-theatre-tickets__es` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `pay-known-bill__es` | `.meshkore/roadmap/initiatives/V2-154-uc-pay-known-bill-es.md` | `` |
| `remember-and-remind-deadline` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `renew-gym-membership__es` | `.meshkore/roadmap/initiatives/V2-173-uc-renew-gym-membership-es.md` | `.meshkore/modules/nucleo/tasks/T421-uc-renew-gym-membership-es-fix.md` |
| `reorder-prescription__es` | `.meshkore/roadmap/initiatives/V2-158-uc-reorder-prescription-es.md` | `` |
| `restaurant-tonight-madrid` | `.meshkore/roadmap/initiatives/V2-167-uc-tareas-que-nunca-terminan.md` | `` |
| `three-tasks-at-once` | `.meshkore/roadmap/initiatives/V2-155-uc-three-tasks-at-once.md` | `` |

## Multi-flow scenarios (concurrency measured live, from `/api/tasks`)

| scenario | max concurrent tasks | distinct worker kinds |
|---|---|---|
| `three-tasks-at-once` | 2 | code, generic, research |
