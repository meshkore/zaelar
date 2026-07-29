---
id: T-31
title: "T-31 · Dispatch de tags [[architect.*]] en Hermes y duo (rápido + deep)"
status: done
priority: medium
owner: ricart
initiative: INI-010
created: 2026-07-05
updated: 2026-07-05
---

# T-31 — Dispatch Architect en los brains (INI-010)

## Qué se hizo

Rama `action.startswith("architect.")` → `connectors.architect.dispatch_tag()` (fire-and-forget con strong-ref,
mismo patrón que cluster/cron) en los tres caminos del operador:

- `brains/hermes/llm_processor.py` `_widget_emit`
- `brains/duo/llm_processor.py` `_tag_emit` (capa rápida: puede relayar un ask directo) y `_deep_emit`
  (un turno deep de Hermes también puede encargar al Architect)

El brief del Architect se añade a `brains/duo/prompt.py _briefs()` (system por-turno del duo). Nunca se
dispatcha desde turnos de cluster (allow-list del bridge intacta).

## Verificación

`pytest connectors/architect/ brains/` en verde; e2e real contra el daemon (ver diario de connectors T-31).
