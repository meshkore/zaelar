---
id: T137
title: "Throttle del triaje de mensajería (no inyectar en cada turno; agrupar) + no abrir widgets desde audio no dirigido"
status: done
priority: high
owner: ricart
category: connectors
initiative: V2-015
depends_on: []
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [fe04f7e]
---

# T137 — Throttle del triaje de mensajería (no inyectar en cada turno; agrupar) + no abrir widgets desde audio no dirigido

Hecho: `connectors/messaging/notify.py::announce` ahora AGRUPA la nota `[SISTEMA]` al brain por ventana
(`_NOTE_GAP` 90s) — antes empujaba una por cada batch/turno de mensajes, inflando el prompt del FlashBrain y
contribuyendo a los turnos gigantes que enterraban los comandos. Saltarse una nota no pierde información (el
detalle vive siempre en el widget `mensajeria`). La parte "no abrir widgets desde audio no dirigido" la cubre el
gate de atención (T134): un turno ambiente retorna antes de despachar cualquier tag/acción. Choke-point único
(legacy duo y v2 nucleo pasan por el mismo `notify.announce`).
