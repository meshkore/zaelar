---
id: T138
title: "Verificación con el tester (ambiente NO actúa; dirigido sí) + señal UI ambient/atendiendo + revisión de alineación"
status: done
priority: high
owner: ricart
category: voice
initiative: V2-015
depends_on: [T135, T136, T137]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [addf5e7]
---

# T138 — Verificación con el tester (ambiente NO actúa; dirigido sí) + señal UI ambient/atendiendo + revisión de alineación

Verificado en vivo (zaelar arriba, BRAIN=nucleo, Ollama up) con `tester.run --goal … --turns 3 --no-open --hold 0`:

- Turno AMBIENTE ("vale, la reunión de marketing es el jueves a las cinco", sin wake-word, ventana cerrada) →
  1 solo evento `ambient` (reason=ambient), **0 widgets abiertos, 0 escaladas, 0 respuesta**. ✓
- Turno DIRIGIDO ("oye zaelar…" — el STT lo garbló a "Harvey", que la lista de variantes fonéticas de wake-word
  SÍ captó) → atendido: prompt + reply. ✓
- Turno siguiente ("adiós", sin wake-word pero dentro de la ventana) → atendido por `active_window`. ✓

Señal observable: evento `ambient` en `voice/observer.py` → `.meshkore/logs/timeline-latest.jsonl` + SSE `/events`
(visible en `/debug`). Revisión de alineación pasada (docs + diagrama + roadmap). Ver ## Bitácora de V2-015.
