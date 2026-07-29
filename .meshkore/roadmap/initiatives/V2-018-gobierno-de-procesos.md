---
id: V2-018
title: Gobierno de procesos — el cerebro sabe qué corre y el operador lo puede PARAR (Reset duro)
epic: v2-colmena
status: next
priority: high
owner: ricart
modules: [nucleo, voice, widgets, frontend, memory, server]
depends_on: [V2-013]
wall_order: 18
created: 2026-07-10
updated: 2026-07-10
---

## Goal

Los procesos de fondo (tareas del navegador, escaladas al SlowBrain, generación de widgets) crecían sin control y
sin visibilidad: un objetivo imposible generó **30 escaladas / 8 aperturas de navegador** en bucle porque las notas
`[SISTEMA]` de una tarea fallida re-disparaban la escalada, y "cierra/para todo" solo cerraba tarjetas (cosmético) —
no mataba el trabajo vivo ni drenaba la cola de notas. Hay que dar al operador un **PARE DURO real** y, a futuro,
que el FlashBrain **sepa qué corre** y el frontend lo **muestre** (cero procesos invisibles).

## Qué se construye

- **Reset DURO desde el botón «Reset»** (T149, hecho): el botón del TopBar deja de ser un "limpia canvas" y pasa a
  ser un **pare deliberado** con **diálogo de confirmación**. Al confirmar, secuencia CAUTELOSA (orden exacto pedido
  por el operador):
  1. **CONGELAR** los contenedores de estado vivo (tareas del navegador + estado, escaladas, jobs de widgets) en un
     snapshot → **memoria de ESTADO** (`memory.set_state({trabajo_interrumpido})`; no corto ni largo — es el estado
     de qué se estaba haciendo).
  2. **REGISTRAR** la orden de parada → **memoria de CORTO plazo** (`memory.write(level='short')`).
  3. **MATAR** los procesos: `navegador tasks.cancel`, `escalate.reset`, `brain_notes.drain` (las notas que
     re-disparaban el bucle).
  4. Limpiar el canvas (cierra todos los widgets) + sesión + log.
- **Antibucle de escaladas** (T150, pendiente): una tarea que falla N veces no se re-escala; dedup de escaladas por meta.
- **Registro de procesos vivos + visibilidad en el frontend** (T151, pendiente): el FlashBrain lee "qué tienes en
  marcha"; cada proceso de fondo se ve (tarjeta que se mueve o "nube" alrededor del orbe). Cero procesos invisibles.

## Tareas

- [x] T149 — Reset DURO con confirmación (frontend) + secuencia congelar→registrar→matar (backend). `done` 2026-07-10.
- [ ] T150 — Antibucle: tarea del navegador que falla N veces no se re-escala; dedup de escaladas por meta; una nota `[SISTEMA]` de fallo no vuelve a la cola de escalada.
- [ ] T151 — Registro de procesos vivos (`nucleo`) + indicador de actividad en el frontend (nubes alrededor del orbe / tarjeta que se mueve). El FlashBrain lo enumera por voz.

## Aceptación

- El botón Reset pide confirmación; al aceptar, PARA todas las búsquedas/tareas/generaciones y limpia el canvas.
- El trabajo en curso queda CONGELADO en la memoria de estado (no se pierde) + hay un registro `[RESET]` en corto plazo.
- Un objetivo imposible ya no genera un bucle de re-aperturas del navegador.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-10 · T149 — `nucleo/reset.py::reset_all()` (congela navegador/escaladas/jobs → `set_state`; registro `[RESET]` → corto; mata con `tasks.cancel`/`escalate.reset`/`brain_notes.drain`, best-effort). Endpoint `POST /reset/hard` (separado del `/reset` ligero que usa el reconnect): reset_all + cierra todos los widgets + limpia sesión/log. Frontend: botón Reset → diálogo de confirmación (`store.resetConfirmOpen`, modal `.rc-*` en TopBar) → `session.resetHard()` (para voz + `/reset/hard` + limpia blobs de actividad). Verificado: reset_all en proceso deja el `[RESET]` en corto; `POST /reset/hard` devuelve `{frozen, killed, when}` y emite RESET+widget close.
