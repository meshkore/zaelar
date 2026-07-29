---
id: DIAG-turn-signals
title: "Diagnóstico de señales de turno perdidas + refresh del diagrama /architecture"
status: done
priority: medium
owner: ricart
initiative: INI-009
created: 2026-07-03
updated: 2026-07-05
---

# Frontend: evidencia de señales perdidas + diagrama al día

## Qué se hizo

1. **`vad.js` / `session.js`** — una señal de turno (`vala-turn`) que no puede enviarse ya NUNCA falla en
   silencio: va a consola y al timeline del servidor vía `clientLog` ("vala-turn 'start' LOST", "data channel
   CLOSED mid-session"). Con esto se cazó en producción que el data channel muere en red móvil — el dato que
   justificó que el TurnBroker (voice) no dependa solo de esas señales.
2. **`pages/architecture.html`** — auditado contra el código tras INI-006/007 y actualizado: nota de seguridad
   con los endurecimientos de INI-007 (tirith segunda capa, redacción SSE, media saliente, anti DNS-rebind),
   gate de house-rules del generador, `cron_api.py`, `ConnStatus`, `notes.md` en la anatomía de widget, y
   **sello de fecha/hora de actualización dentro del propio SVG** (esquina inferior derecha; se actualiza a mano
   al revisar el diagrama — regla anotada en el código).

## Ficheros

`frontend/app/services/vad.js` · `frontend/app/services/session.js` · `frontend/pages/architecture.html`.

## Verificación

Los client-logs aparecieron en las sesiones 20:08/20:14/20:21 (evidencia real de canal caído). `/architecture`
sirve 200 con el sello "Actualizado: 2026-07-03 · 13:06 — v0.9.19 (post INI-006/INI-007)"; JS validado con
`node --check`.
