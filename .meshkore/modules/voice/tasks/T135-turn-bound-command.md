---
id: T135
title: "Fin de turno acotado + preservación de comando: cap longitud/silencio; al recortar priorizar el comando explícito (no truncar un cierra/para)"
status: done
priority: high
owner: ricart
category: voice
initiative: V2-015
depends_on: [T134]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [efc6a3a]
---

# T135 — Fin de turno acotado + preservación de comando: cap longitud/silencio; al recortar priorizar el comando explícito (no truncar un cierra/para)

Hecho: `voice/attention.py::clamp_input(text, max_len)` sustituye el `text[-max_in:]` a ciegas del provider —
si el turno excede `ZAELAR_FAST_MAX_INPUT` (1600) y contiene una cláusula de comando explícito
(cierra/abre/muestra/para…), la ANTEPONE al recorte para que nunca quede fuera (era como el "cierra los widgets"
acababa truncado en un turno de 14k chars). Cableado en `nucleo.py::_run`. Tests en `voice/test_attention.py`
(comando al principio de un turno gigante se preserva; sin comando trunca normal).
