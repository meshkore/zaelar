---
id: T-20
title: "T-20 · auditoría de contrato del widget cluster-registro"
status: done
priority: medium
owner: ricart
initiative: INI-006
created: 2026-07-02
updated: 2026-07-02
---

# T-20 — Auditar el widget de cluster (INI-006)

## Qué se hizo

INI-006 apuntaba a `widgets/cluster-informe/` — ese folder era **debris** de una generación muerta a medias y
ya lo limpió W-001. El widget real y vivo es **`widgets/cluster-registro/`** (commiteado). Auditoría de contrato:

- ✅ **Contrato de carpeta**: `manifest.json` completo (id/version/title/description/whenToUse/keywords/entry) +
  `widget.js` + `data.py` + `notes.md`.
- ✅ **widget.js**: módulo ES sin build, sin deps externas, exporta `render(el, data, ctx)`; **todo el texto va
  por `textContent`** (convención de la casa — nada de interpolar HTML), incluido el texto que viene de peers.
  Estados vacío/error degradados en el propio widget.
- ✅ **data.py**: stdlib-only (`json`, `time`, `pathlib`), lee logs locales de `.meshkore/logs/`, **nunca lanza**
  (error → `{"error": …}`), cap de 400 turnos para payload ligero.
- ✅ **Keywords**: sin colisiones con el resto del catálogo (las colisiones existentes son entre
  meteo-soria/meteo-tarragona/search/agenda — se tratan en W-4).
- 🔧 Único defecto encontrado y corregido: `import os` sin usar en `data.py`.

## Ficheros tocados

- `widgets/cluster-registro/data.py` — quitar import sin uso.

## Verificación

- Smoke local: `view_data()` → dict con 358 turnos, cluster `arena`.
- Servidor vivo: `GET /widgets/cluster-registro/data` responde el payload correcto por la ruta nueva (W-1).
