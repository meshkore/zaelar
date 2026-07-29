---
id: T113
title: "Instrumentar el desglose de latencia del turno nucleo (memory/LLM/TTS) en /debug"
status: done
priority: high
owner: ricart
category: nucleo
initiative: V2-011
depends_on: []
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [ce078f0]
---

# T113 — Instrumentar el desglose de latencia del turno del FlashBrain

Medir, por turno, el tiempo de: `memory.state()`, `memory.query()`+embeddings, `live_state()`, TTFT del LLM y
primer audio de TTS. Emitirlo por el observer (`voice/observer.py`) / DebugBus para verlo en `/debug`. Objetivo:
atribuir la latencia con DATOS antes de tocar nada (base de V2-011). No cambia comportamiento, solo observa.

## Cierre (2026-07-09)

`build_flash_system(..., timings=dict)` y `_memory_block(..., timings=dict)` rellenan el desglose por fase
(`mem_state_ms`, `mem_query_ms`, `briefs_ms`, `live_ms`, `build_ms`); `voice/engine/llm/providers/nucleo.py::_run`
lo emite como evento `timing` y lo adjunta al evento `brain` de la respuesta (visible en `/debug`).

**Baseline medido (tester `memory`, ANTES de optimizar):** el retriever síncrono ES la regresión —
`mem_query_ms` = 452 / 164 / 112 / 215 ms por turno (embeddings HTTP a Ollama, bloqueando el event loop antes
del LLM); `mem_state_ms` ≈ 0.1 ms, `briefs_ms` ≈ 1–2 ms, `live_ms` ≈ 0 ms. Es decir, TODO el coste de armar el
prompt es `memory.query()`, y bloquea el loop.
