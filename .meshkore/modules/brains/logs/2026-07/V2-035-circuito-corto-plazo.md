---
id: V2-035-corto-plazo
title: "Circuito de corto plazo del FlashBrain + fixes de diálogo (estado fiable, ventana sembrada, 2º pase reciente)"
status: done
priority: high
owner: ricart
initiative: V2-035
created: 2026-07-14
updated: 2026-07-14
---

# Circuito de CORTO PLAZO de interacción con el operador (V2-035)

## Qué se hizo
Sesión manual 2026-07-14: zaelar no sabía el nombre (intermitente) aunque estaba en el estado, "abría" widgets no
pedidos y tenía un diálogo absurdo (respondía al tema del turno anterior). Diagnóstico turno a turno del
`timeline-latest.jsonl` → causas raíz confirmadas con datos, no suposición:

- **Nombre intermitente:** el estado SÍ viaja (verificado "Ricard" en el prompt real). Bug en `memory_cache._store`:
  un `compose_state()` que falla un instante (BD bajo contención) devolvía `('','')` y **pisaba el bloque bueno con
  vacío**. Fix: **suelo de identidad sagrado** — nunca sobrescribir estado bueno con vacío (reintenta con `dirty`).
- **Ventana vacía al reconectar:** `brain._window` (últimos turnos verbatim) arrancaba vacía por instancia → se
  perdía "de qué hablábamos" al reiniciar. Fix: **sembrarla** de `memory.recent_window` (nuevo reader, lee el
  buffer conversacional `kind='conv'` con `meta.u`/`meta.a`). Cableado en voz (`nucleo.py::_run`) y probe.
- **Falta 2º pase de corto:** solo existía `needs_recall` (dato DURABLE, embeddings). Fix: `prompt.needs_recent`
  (es/en) → `compose_recent_block` inyecta el buffer AMPLIADO verbatim FUERA del event loop, bajo demanda; charla
  normal ligera. Telemetría `recent_fired`.
- **Widgets "abiertos solos" + negación:** `open_widgets` del cerebro desincronizado del DOM tras reinicio con la
  página abierta. Fix: `session-lk.js` re-reporta el canvas real al (re)conectar + regla de prompt (open_widgets es
  la verdad de la pantalla; no negar; responder al tema ACTUAL).

## Ficheros tocados
- `nucleo/flash/memory_cache.py` (suelo de identidad), `memory/api.py` (`recent_window`), `nucleo/flash/prompt.py`
  (`needs_recent`/`compose_recent_block`/`build_flash_system(recent_block=)` + regla de widgets),
  `voice/engine/llm/providers/nucleo.py` (siembra de ventana + 2º pase + `meta.u/a` en el buffer conv),
  `nucleo/flash/probe.py` (mismo cableado B+C, fiel a la voz), `frontend/app/services/session-lk.js` (reconciliación
  de canvas), `.meshkore/docs/architecture/zaelar-memory.md`, `CLAUDE.md`.

## Verificación
- 27 tests verdes: `nucleo/flash/test_prompt.py`, `nucleo/flash/test_memory_cache.py`, `memory/test_compose_state.py`.
- `needs_recent` 8/8; gating `recent_fired` F/T/F; coste del 2º pase ~1.4ms.
- Probe en vivo: identidad sólida ("Te llamas Ricard"), T2 recupera el intercambio reciente exacto, "gracias" no
  dispara el 2º pase. Suelo de identidad: fallo transitorio mantiene el nombre; reset legítimo vacía.
