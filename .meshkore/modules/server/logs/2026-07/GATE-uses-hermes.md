---
id: GATE-uses-hermes
title: "Gates de features Hermes generalizados a uses_hermes() (hermes + duo)"
status: done
priority: low
owner: ricart
initiative: INI-008
created: 2026-07-05
updated: 2026-07-05
---

# server: gates por capacidad, no por nombre de brain

## Qué se hizo

Los montajes condicionales de features de Hermes (cron ticker, routers `/api/hermes/*` + `/api/cron`, reasoner
de cluster) comparaban `active_brain() == "hermes"`. Con el cerebro `duo` (que corre Hermes por debajo) eso
habría dejado sin cron/self-update/reasoner a un run duo. Se generalizó a `brains.uses_hermes()` — la regla de
"capacidades específicas de brain montadas condicionalmente" se mantiene, pero ahora expresa la capacidad real
(¿este brain corre el agente Hermes?) y no un nombre.

## Ficheros

`server/__init__.py` (lifespan + create_app) · `brains/reasoner.py` · `brains/__init__.py` (helper).

## Verificación

Con `BRAIN=duo`: `/api/hermes/status` → `{"available":true,"version":"v0.17.0"}`, `/api/cron` → 200, log de
arranque muestra "MeshKore reasoner: Hermes (shared warm agent)" y el cron ticker activo.
