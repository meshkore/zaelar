---
id: T140
title: "Cambio de attention_mode en caliente + persistir en config/settings.json (sin reiniciar)"
status: done
priority: high
owner: ricart
category: config
initiative: V2-016
depends_on: [T139]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [2cd7617]
---

# T140 — Cambio de attention_mode en caliente + persistir en config/settings.json (sin reiniciar)

El cambio de `attention_mode` aplica EN CALIENTE sin endpoint nuevo: `config/settings.update()` (ya existente,
la costura del ⚙) escribe `config/settings.json` + `os.environ["ZAELAR_ATTENTION"]` de inmediato, y
`voice/attention.py::mode()` lee `ZAELAR_ATTENTION` cada turno → el siguiente turno respeta el modo sin
reconectar. Ciclo verificado por curl contra `POST /api/settings`: pulsar→`wakeword` (settings.json + knob
efectivo lo reflejan)→volver a `always`; persiste. `voice/test_attention.py` 34/34 verde. done 2026-07-09 ·
commit 2cd7617.
