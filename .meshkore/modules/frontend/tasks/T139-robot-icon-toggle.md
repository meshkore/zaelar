---
id: T139
title: "Icono 🤖 (robot) bajo el orbe junto a 🔊/📝: toggle always↔wake-word, estado visual, aplica en vivo"
status: done
priority: high
owner: ricart
category: frontend
initiative: V2-016
depends_on: []
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [2cd7617]
---

# T139 — Icono 🤖 (robot) bajo el orbe junto a 🔊/📝: toggle always↔wake-word, estado visual, aplica en vivo

Tercer control sin marco en `frontend/app/components/Orb.js`, junto a 🔊/📝. Toggle de dos estados con
`createSignal` local: OFF/gris = `always` (escucha y responde a todo, default), ON/azul = `wakeword` (solo actúa
con «zaelar/harvis»). Refleja el modo REAL al cargar (`api.getSettings()` → knob `attention_mode`) y al pulsar
escribe EN VIVO por la MISMA costura del ⚙ (`POST /api/settings` → `config/settings.update()`), con revert
optimista si falla. Tooltip por estado ("Escucha siempre" / "Solo con «zaelar»"), tema `--hb-*` (clases
`.orbic .on/.off`), sin hex. done 2026-07-09 · commit 2cd7617.
