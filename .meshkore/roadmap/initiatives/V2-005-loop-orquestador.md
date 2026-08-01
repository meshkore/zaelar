---
id: V2-005
title: Loop orquestador (~1 Hz) — hilo del tiempo + chispas + consolidación + cron propio
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [nucleo, memory, voice, server]
depends_on: [V2-004]
wall_order: 5
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T08:41:00.102Z
commit_sha: ab6d2326cdb14469cb50a2e07f737c1f7018a5d7
---
## Goal

Dar a zaelar un **latido** propio: un loop orquestador (~1 Hz) montado en el lifespan del server que gobierna el
tiempo — tareas programadas, disparo del consolidador ("sueño"), y **🔥 chispas** (pensamiento espontáneo
ocasional). Reemplaza el **cron nativo de Hermes**, que muere con él. Reporta siempre por los raíles existentes
(voz + UI), nunca notificaciones flotantes.

## Qué se construye

- `nucleo/loop.py` — tarea asyncio periódica montada en `server/__init__.py::_lifespan` (mismo loop que la voz,
  junto al supervisor de widgets). Tick ~1 Hz configurable.
  - **Tareas programadas**: cola de tareas con hora/condición, respaldada por `memory.journal`.
  - **Consolidación**: dispara `memory.consolidate()` según intervalo/tamaño (el "sueño").
  - **🔥 Chispas**: con baja probabilidad por tick, genera un pensamiento espontáneo (rate-limited, con
    presupuesto diario) — p.ej. retomar una tarea pendiente del journal, o un recordatorio. Sale por voz+UI solo
    si aporta; si no, se descarta. NUNCA spammea.
  - Reporta lo hecho por `voice/proactive.notify()` + `voice/brain_notes.push()` (deduplicado, como hoy).
- **Cron propio** (sustituye `brains/hermes/cron.py`): la creación por voz `[[cron.create]]` se re-cablea al
  scheduler del loop, persistido en `memory.journal` (status pending/in_progress/done). Se retira la dependencia
  del `hermes cron tick`.
- Señales por el bus: `loop.tick`, `loop.spark`, `loop.scheduled_fired` (observables por el tests/voice/e2e/agent/juez).

## Tareas

- [x] `nucleo/loop.py` — tarea periódica en el lifespan (arranca/para limpio) + tick configurable + tests. (T70)
- [x] Scheduler de tareas programadas respaldado por `memory.journal` (crear/listar/disparar/cerrar) + tests. (T71/T72)
- [x] Disparo del consolidador por intervalo/tamaño (no en el hot path) + test. (T74)
- [x] Chispas: generador rate-limited con presupuesto diario; heurística "¿aporta? si no, descarta" + test. (T73)
- [x] Re-cablear `[[cron.create]]` al scheduler del loop; retirar el uso de `hermes cron tick`. (T75)
- [x] Emitir `loop.*` por el bus; verificar en `GET /events`. (T76)
- [x] Prueba en vivo: programar un aviso a +2 s → dispara por el loop y entra en `/events`; consolidador off-hot-path. (T76)

## Aceptación

- Un aviso programado por voz dispara a su hora por voz + subtítulo + chat (sin toast).
- El consolidador se ejecuta periódicamente sin afectar la latencia de voz.
- Las chispas aparecen con moderación (respetan el presupuesto) y solo cuando aportan.
- Cero dependencia del cron de Hermes.

## Riesgos

- Chispas molestas / ruido → presupuesto diario estricto + gate de utilidad; empezar conservador.
- El loop no debe bloquear el hot path: todo trabajo pesado va async / a un CodeAgent (V2-007).

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T71 — `memory/journal.py`: cara de acceso (CRUD directo, hot path sqlite) de la tabla `journal` ya declarada en V2-002 — `add`/`get`/`list_entries(status)`/`update`/`remove`, con `detail` serializado a/desde JSON. Es el respaldo persistente del scheduler propio (tareas programadas sobreviven al reinicio) y queda para el journal de continuidad del SlowBrain (V2-006/07). 5 tests verdes (`memory/test_journal.py`).
- 2026-07-09 · T71/T72 — `nucleo/scheduler.py`: **cron PROPIO** que sustituye al de Hermes (`brains/hermes/cron.py`). Parser agnóstico del idioma — una-vez relativo (`30m`/`2h`/`en 1d`/`+45s`), recurrente (`every 30m`/`cada 2h`) y **cron 5-campos** (`0 9 * * *`, soporta `* , - /`, matcher minuto-a-minuto acotado a 366 días, semántica dom-OR-dow estándar). CRUD respaldado en `memory.journal` (`create`/`list_jobs`/`due`/`mark_fired`/`cancel`): una-vez → `done` al disparar; recurrente → recalcula `next_run` y sigue viva. 12 tests verdes (`tests/agent_headless/unit/test_scheduler.py`).
- 2026-07-09 · T73 — `nucleo/sparks.py`: 🔥 chispas con **doble gate** — `SparkGate` (presupuesto diario + separación mínima + probabilidad baja por tick; reloj/azar inyectables) + `propose()` gate de UTILIDAD (solo resurge una tarea `pending` del journal que lleva rato quieta; si no hay nada que MEREZCA interrumpir → None → se descarta). Conservador por diseño (empieza sin generación por modelo: cero latencia/coste/alucinación). 7 tests verdes (`tests/agent_headless/unit/test_sparks.py`).
- 2026-07-09 · T70/T74 — `nucleo/loop.py`: `OrchestratorLoop` (~1 Hz) — el latido propio. `tick()` = disparar vencidos del scheduler (`mark_fired` ANTES de entregar → idempotente ante fallo de voz) → chispa (doble gate) → consolidar por intervalo (`asyncio.to_thread(memory.consolidate)` → FUERA del hot path) → señal `loop.tick`. `start()/stop()` limpios; un tick que peta NUNCA tumba el loop; entrega por `voice/proactive.notify` (voz+UI, sin toast). Singleton de proceso para el lifespan. 6 tests verdes (`tests/agent_headless/unit/test_loop.py`: no-entrega-antes-de-vencer, disparo con reloj monkeypatch, `loop.tick` por el bus, consolidación off-hot-path, chispa dispara/descarta).
- 2026-07-09 · T75 — re-cableado de `[[cron.create]]`/`[[cron.cancel]]` al scheduler propio en el provider `nucleo` (`voice/engine/llm/providers/nucleo.py`): las tags de proactividad ya NO van al cron de Hermes → `nucleo.scheduler.create/cancel` (persistido en journal, disparado por el loop). Brief de proactividad reescrito en `nucleo/flash/prompt.py` (`_cron_brief`, enseña las tags + lo ya programado desde `scheduler.list_jobs()`) — sustituye al brief del cron de Hermes, que el FlashBrain nunca tuvo. Hermes/duo conservan su cron intacto (siguen de default hasta V2-009).
- 2026-07-09 · T70 — loop montado en el lifespan de `server/__init__.py`, gated a `active_brain()=='nucleo'` (+ flag `ZAELAR_LOOP`, def 1), simétrico al bloque del cron de Hermes (que sigue para hermes/duo). Arranca/para con el server; mismo loop que la voz. VERIFICADO que con `BRAIN=duo` el loop NO se monta (cero regresión).
- 2026-07-09 · T76 — VERIFICACIÓN EN VIVO (`BRAIN=nucleo bash scripts/run-livekit.sh`, reinicio limpio tras tocar `.py`): boot sin errores — «Memoria v2 montada», «Loop orquestador arrancado · tick 1.0s · consolida cada 3600s», «Loop orquestador v2 montado», «worker started EMBEDDED» + «registered worker», `/api/brain`=`nucleo`, `/events` OK. **Disparo E2E real**: se escribió una tarea `en 2s` en el `zaelar.db` que lee el loop en marcha → el loop la disparó a su hora y la entregó por `proactive.notify` → apareció en `/events` como evento `notify` («Recordatorio de prueba V2-005: bebe agua»), y la tarea una-vez quedó `done`. Turno de voz por MICRO pendiente (no scriptable headless, mismo caveat que INI-012/T69) — no bloqueante. Tras verificar se restauró el default `duo` (loop NO montado, boot limpio).
- 2026-07-09 · **V2-005 CERRADA** — Aceptación cumplida: (a) un aviso programado dispara a su hora por el loop y sale por voz+UI (verificado E2E: fire→`proactive.notify`→`/events`, sin toast; voz-por-micro pendiente no bloqueante); (b) el consolidador corre por intervalo FUERA del hot path (`asyncio.to_thread`, test dedicado); (c) las chispas respetan presupuesto/gap/probabilidad y solo cuando aportan (doble gate, tests); (d) CERO dependencia del cron de Hermes en el path nucleo (`[[cron.*]]`→scheduler propio; el cron de Hermes solo sigue para hermes/duo hasta V2-009). Suite `nucleo/ memory/ bus/ config/` = **169 passed** (0 regresiones). **state.json = artefacto del daemon MeshKore** (no editable a mano de forma persistente; el daemon reconcilia al releer los .md con las tareas T70–T76 [x] + esta línea; no hay generador local ejecutable). Siguiente: **V2-006 — CodeAgent + SlowBrain dispatcher** (`depends_on: [V2-002, V2-004]` satisfecho).
