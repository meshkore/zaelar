---
id: T-31
title: "T-31 · Tags [[architect.ask]]/[[architect.new]] en el protocolo silencioso + brief en kickoff"
status: done
priority: medium
owner: ricart
initiative: INI-010
created: 2026-07-05
updated: 2026-07-05
---

# T-31 — Tags Architect en voice/ (INI-010)

## Qué se hizo

- `voice/tag_protocol.py`: `ARCH_ASK_RE` (`[[architect.ask:<proyecto>]]<texto>[[/architect.ask]]`, ids con
  puntos/guiones) y `ARCH_NEW_RE` (`[[architect.new]]{json}[[/architect.new]]`), con sus loops de strip y
  entradas en el hold anti-split del streaming (una tag partida entre chunks jamás se habla ni se pierde).
- `voice/agent.py kickoff()`: brief del Architect añadido al brief de capacidades del primer turno (guarded —
  un brief roto nunca rompe la voz).

El retorno del resultado reutiliza `voice/proactive` y `voice/brain_notes` sin cambios.

## Verificación

Tests de parsing/hold en `tests/connectors/unit/architect/test_architect.py` (incluye split por chunks de 7 chars);
suite de voz en verde (73/73 global).
