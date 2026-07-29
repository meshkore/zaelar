---
id: MK-002
title: "Fix — zaelar se quedaba mudo tras un barge-in (turnos ACP encolados)"
status: done
priority: critical
owner: ricart
initiative: INI-005
created: 2026-07-01
updated: 2026-07-01
---

# MK-002 — Fix del regreso a mudo por barge-in

## Síntoma (reportado: "la conversación no es fluida ni bidireccional")

En `.meshkore/logs/sessions/20260701-124529.jsonl`: **11 turnos de usuario transcritos, 0 respuestas del
brain**. El timeline repetía `⤵️ Hermes control (not spoken) · Queued for the next turn. (N queued)` con N
subiendo 1→2→…→8. La voz de entrada funcionaba (STT transcribía), pero zaelar no contestaba. Se disparaba
**después de un barge-in** (interrumpir al bot hablando por encima).

## Causa raíz (confirmada contra el binario real, no por teoría)

`hermes acp` (v0.17.0) procesa **un turno a la vez**. `session/cancel` marca un flag e `interrupt()` pero **no
aborta al instante ni pone `is_running=False` de forma síncrona** (verificado en el fuente del adapter ACP de
Hermes). El código nuevo del canal MeshKore (agente compartido `runtime.py` + `cancel()` en barge-in) enviaba
el siguiente `session/prompt` **inmediatamente tras el cancel**, sin esperar a que el turno interrumpido
drenara. Resultado: Hermes respondía `"Queued for the next turn. (N)"` y mezclaba los `agent_message_chunk`
tardíos del turno viejo en el nuevo stream. La capa de voz suprime "Queued" → **mudo permanente**.

Esto **regresó** el auto-recobro del diseño original: antes (agente por sesión, sin cancel) el turno
interrumpido simplemente terminaba en background y Hermes quedaba libre para el siguiente.

## Qué se arregló

`brains/hermes/acp_client.py` — un `threading.Lock` de turno (`_turn_lock`) que garantiza **un turno ACP a la
vez**: `_ask_once` cancela el turno en vuelo y **espera a que drene** (adquiere el lock) antes de enviar el
nuevo prompt. Mantiene sincronizados el modelo de turnos del cliente y el de Hermes → nunca entra en estado
"Queued". El barge-in sigue funcionando; ahora se auto-recupera en vez de atascarse. El fix vive en el cliente
ACP (dueño del contrato "un turno a la vez"), independiente de la capa asyncio/pipecat.

## Ficheros tocados
- `brains/hermes/acp_client.py` — `_turn_lock` + serialización en `_ask_once` (+ `cancel()` como notificación).

## Verificación (2026-07-01)

Repro aislado contra el `hermes acp` real (harness de barge-in: turno largo → `session/cancel` → siguiente
prompt):
- **Antes:** siguiente turno → `'.\nQueued for the next turn. (1 queued)8'` (basura + control) ❌
- **Después:** `'Hello, nice to meet you.'` limpio ✅
- **Camino normal** (3 turnos secuenciales): `apple` / `banana` / `cherry`, 2–3.5s c/u, sin deadlock ✅
- Servidor reiniciado con el fix: `GET /api/brain → {"brain":"hermes"}`, arranque sin errores.
- Pendiente: prueba manual en navegador con voz real (no conducible headless).
