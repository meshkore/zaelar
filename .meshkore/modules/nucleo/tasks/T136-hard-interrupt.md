---
id: T136
title: "Interrupción DURA cierra/para/silencio/stop: atendida de inmediato aunque haya turno/cola en vuelo"
status: done
priority: high
owner: ricart
category: nucleo
initiative: V2-015
depends_on: [T134]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [efc6a3a]
---

# T136 — Interrupción DURA cierra/para/silencio/stop: atendida de inmediato aunque haya turno/cola en vuelo

Hecho: `voice/attention.py::hard_interrupt(text)` — patrón corto es/en, DETERMINISTA (no depende del LLM):
`close` (cerrar TODOS los widgets: verbo de cierre + "todo/widgets") · `stop` (silencio/calla/basta/stop, y
"para"/"espera" solo como imperativo corto para no chocar con la preposición "para"). En `nucleo.py::_run` se
comprueba ANTES del gate y sobre el texto COMPLETO (antes de recortar), así una interrupción se atiende siempre
y de inmediato aunque el turno sea gigante: `close` emite `[[close]]` al canvas ya; `stop` corta (el barge-in de
LiveKit ya paró el TTS) sin generar respuesta. Tests en `tests/voice/unit/test_attention.py`.
