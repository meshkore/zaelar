---
id: INI-002
title: Canvas Widgets
status: done
owner: ricart
modules: [widgets, server]
updated: 2026-07-02
---

## Goal

Live data widgets on the canvas desktop: clock, agenda, weather, search results.

## Scope

- Widget generator (widgets/generator.py)
- Widget runtime (widgets/runtime.py)
- Per-widget data + JS: clock, agenda, meteo-soria, meteo-tarragona-grafico, results, search
- Widget server API (widgets/server_api.py)

## State

Active. Multiple widgets in production use locally.

**2026-07-02 (W-001) — hardening.** Cerrado el bucle create/modify→brain (`voice/brain_notes.py`), validación con
smoke-test de `view_data()`, anti-debris (create fallido borra folder + catálogo exige `widget.js`), store enseñado
al generador. Decisiones fijadas: storage **independiente por widget**, comunicación **mediada por el brain**,
JS+stdlib se mantiene. Modelo documentado en `zaelar-modules.md §Widgets`. Ver diario `W-001`.
