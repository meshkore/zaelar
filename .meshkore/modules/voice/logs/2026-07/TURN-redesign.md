---
id: TURN-redesign
title: "Rediseño de la capa de turnos: TurnBroker + TurnGate (troceo, backchannel, canal frágil)"
status: done
priority: high
owner: ricart
initiative: INI-009
created: 2026-07-05
updated: 2026-07-05
---

# Rediseño de la capa de turnos (el operador pidió rediseño, no parches)

## Síntomas (sesiones reales en coche, 2026-07-05)

1. zaelar respondía a CADA fragmento de una idea (troceo por pausa de ~1.1s del VAD del navegador).
2. Un "ok"/"Gracias" sobre la voz del bot lo cortaba Y recibía respuesta.
3. Con el canal de datos caído (red móvil), el turno se quedaba atascado (rescate fijo de 3s como parche previo).

## Causa raíz clave (bug matemático, sesión 20260705-202813)

El barge-in era un timer ciego de **800ms** cancelable SOLO por el stop del navegador — pero ese stop tarda
**1100ms** de silencio (redemption de Silero) en dispararse. `800 < 1100` ⇒ el cancel **jamás** llegaba a tiempo
⇒ todo lo dicho mientras el bot hablaba (backchannels incluidos) disparaba el corte. Confirmado en los logs:
cada "barge-in armed" acababa en "FIRED".

## Qué se hizo

- **`voice/endpointing.py`** (nuevo) — decisiones PURAS: hold dinámico (1.2s base → 2.2s según lo hablado),
  `should_commit` (con el stop del navegador como corroboración; sin él, +1s y cierra igual — la
  auto-recuperación queda integrada), léxico de backchannels, acumulador de voz sostenida. Knobs por env.
- **`TurnBroker`** (sustituye a `ClientVADInjector`, alias compat) — autoridad única: fusiona señales del
  navegador (pista) con la ENERGÍA real del micro medida en el servidor (siempre presente). Pausa → ventana de
  retención, no cierre; la voz que vuelve es el mismo turno (Whisper transcribe la frase entera → más precisión
  con ruido). Barge-in = voz sostenida REAL (energía continua ≥800ms, huecos ≤250ms).
- **`TurnGate`** (nuevo, tras el STT) — backchannel puro sobre (o justo tras) la voz del bot → se consume: ni
  corta ni gana respuesta.
- `voice/agent.py` — pipeline: `input → EchoSuppressor → TurnBroker → stt → TurnGate → ClientTextInjector → …`;
  log de arranque del modelo real del brain (antes mostraba `LLM_MODEL` env, engañoso con BRAIN=hermes/duo).

## Ficheros

`voice/endpointing.py` (nuevo) · `voice/turn_control.py` (rediseño) · `voice/test_endpointing.py` (nuevo) ·
`voice/agent.py` · `frontend/app/services/{vad,session}.js` (diagnóstico: pérdidas de señal de turno y muerte del
data channel quedan en el timeline — así se cazó la causa).

## Verificación

`voice/test_endpointing.py`: **9 tests que reproducen las secuencias reales** de la sesión 20:28 (troceo a 0.7s,
"Gracias" a 600ms de voz, stop perdido, comando corto, divagación larga) — 9/9 en verde. Smoke de integración del
broker: 1 idea con pausa = 1 solo commit; backchannel sobre el bot = 0 cortes. Sistema reiniciado y corriendo.

## Seguimiento

Afinar knobs con sesiones reales (el timeline registra `turn COMMIT · Xs of speech · hold=Ys`). Si el ruido sigue
pegando al STT: `STT_PROVIDER=deepgram`.
