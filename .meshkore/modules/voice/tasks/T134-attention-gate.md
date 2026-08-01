---
id: T134
title: "Gate de atención (ZAELAR_ATTENTION default smart): wake-word + ventana de conversación; turno no dirigido → ambient, sin acción ni respuesta"
status: done
priority: high
owner: ricart
category: voice
initiative: V2-015
depends_on: []
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [efc6a3a, addf5e7]
---

# T134 — Gate de atención (ZAELAR_ATTENTION default smart): wake-word + ventana de conversación; turno no dirigido → ambient, sin acción ni respuesta

Hecho: nuevo `voice/attention.py` (módulo puro, sin deps pesadas) — `mode()` (`ZAELAR_ATTENTION` =
`smart`|`wakeword`|`ptt`|`always`, default `smart`), `evaluate(text)` (wake-word "zaelar"+variantes fonéticas
o ventana de conversación activa `ZAELAR_ATTENTION_WINDOW`, def 30s), `note_directed()`/`reset()`/`set_ptt()`.
Cableado en `voice/engine/llm/providers/nucleo.py::_run`: un turno no dirigido emite `ambient` (observer) y
RETORNA antes de drenar notas/escalar/actuar. `agent.py` marca chat/paste como dirigido (`note_directed`),
resetea la ventana al arrancar sesión y recibe el PTT por el topic `zaelar-ptt`. Config por la UI: knobs
`attention_mode`/`attention_window` en `config/settings.py` (⚙, aplican al instante). Tests: `tests/voice/unit/test_attention.py`.
