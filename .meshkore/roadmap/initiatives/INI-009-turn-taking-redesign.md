---
id: INI-009
title: Rediseño de la capa de turnos (TurnBroker + TurnGate)
status: done
owner: ricart
modules: [voice]
updated: 2026-07-05
depends_on: INI-008
---

## Goal

La conversación por voz se sentía rota en condiciones reales (coche, cascos, ruido moderado): zaelar respondía a
cada fragmento de una idea, un "ok"/"gracias" la cortaba en seco, y el turno dependía de señales frágiles del
navegador. El operador pidió explícitamente **rediseño de arquitectura, no parches** (2026-07-05).

## Diagnóstico (con datos de la sesión 20260705-202813)

1. **Troceo**: el turno se cerraba a la primera pausa de ~1.1s del VAD del navegador + 0.6s del aggregator. Una
   idea con pausas de pensamiento → 3 mini-turnos → 3 respuestas a fragmentos ("esos registros estamos guardando"
   → respuesta → "todos los eventos detecciones…" → otra respuesta).
2. **Backchannel mataba al bot — bug matemático**: barge-in = timer ciego de 800ms cancelable solo por el stop del
   navegador; pero el stop tarda 1100ms de silencio en dispararse. 800 < 1100 ⇒ **el timer JAMÁS podía cancelarse
   a tiempo** ⇒ todo lo dicho sobre la voz del bot (incluido "Gracias.") lo cortaba Y recibía respuesta.
3. **Fragilidad de transporte**: el turno era 100% señales del navegador por el data channel; en red móvil se
   caía ("data channel CLOSED mid-session", "vala-turn 'start' LOST") → turnos atascados (rescate fijo de 3s
   añadido el 07-03 como parche).
4. Colateral cerebro duo: escalaba desahogos a Hermes y adoptaba nombres de transcripciones ruidosas ("Van").

## Rediseño (aplicado)

- **`voice/endpointing.py`** — lógica de decisión PURA y testeada: hold dinámico (`1.2s` base, crece con la
  longitud de lo hablado hasta `2.2s`), regla de commit (con corroboración del stop del navegador o +1s sin él —
  la auto-recuperación queda integrada, ya no es un rescate aparte), léxico de backchannels de alta precisión, y
  acumulador de voz sostenida para el barge-in. Knobs por env: `TURN_HOLD_BASE/MAX/GROWTH`, `TURN_NO_STOP_EXTRA`,
  `VOICE_RMS_FLOOR`, `BARGE_RMS`, `BARGE_GAP_MS`, `BARGE_GIVEUP_MS`.
- **`TurnBroker`** (sustituye a `ClientVADInjector`; alias compat) — autoridad única del turno que FUSIONA el VAD
  del navegador (pista rápida) con la energía real del micro medida en el servidor (siempre disponible). Una pausa
  no cierra: ventana de retención; si la voz vuelve, mismo turno (Whisper transcribe la frase entera → también
  mejora la precisión con ruido). Barge-in por **voz sostenida real** (energía continua ≥ `BARGE_IN_MS` con huecos
  ≤ `BARGE_GAP_MS`): un "gracias" (~600ms de voz) no corta; hablar encima de verdad corta igual de rápido.
- **`TurnGate`** (nuevo, tras el STT) — un backchannel puro dicho mientras el bot habla (o justo al acabar, o que
  provocó el barge-in) se consume: ni corta la conversación ni gana respuesta.
- **Triaje duo endurecido** (`brains/duo/prompt.py`): nunca escalar quejas/charla sobre el sistema; nunca adoptar
  nombres de transcripciones dudosas; fragmentos sin sentido → respuesta brevísima o pedir repetición.

## Validación

`tests/voice/unit/test_endpointing.py` — 9 tests que REPRODUCEN las secuencias reales de la sesión 20:28 (troceo a 0.7s,
"Gracias" a 600ms, stop perdido, comando corto, divagación larga) — todos en verde. Smoke de integración del
`TurnBroker` con la secuencia completa: 1 idea con pausa = 1 solo commit; backchannel sobre el bot = 0 cortes.

## Seguimiento

- Ajustar los knobs con sesiones reales del operador (el timeline registra `turn COMMIT · Xs of speech · hold=Ys`).
- Posible siguiente paso si el ruido sigue pegando al STT: `STT_PROVIDER=deepgram` (nova) para entornos móviles.
