---
id: T114
title: "Bloque de memoria cacheado por sesión (estado + recall) con TTL + refresco async"
status: done
priority: high
owner: ricart
category: nucleo
initiative: V2-011
depends_on: [T113]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [d8033e3]
---

# T114 — Memoria cacheada por sesión (fuera del turno)

Recuperar el patrón del briefing v1 (`brains/duo/briefing.py`, TTL 300s): componer el bloque de memoria (estado +
recall) UNA vez y cachearlo por proceso/sesión con TTL corto; el turno lee el string cacheado, no espera al
retriever. Invalidar con la señal `memory.updated` del bus. `nucleo/flash/prompt.py::build_flash_system` deja de
disparar el retriever por turno.

## Cierre (2026-07-09)

Nuevo módulo `nucleo/flash/memory_cache.py`: bloque de ESTADO (nombre/trato/ubicación/temas/recientes desde
`memory.state()`) cacheado por proceso con TTL (`NUCLEO_MEM_CACHE_TTL`=300s) + refresco async (`asyncio.to_thread`,
nunca en el event loop) + invalidación por un **sink** del bus en `memory.updated` (síncrono, loop-agnóstico). El
turno lee `memory_cache.get()` al instante. `prompt.py::build_flash_system` ya NO compone el estado en el turno
(lo pide al caché); el recall queda separado (`_recall_block`, aún inline aquí — se saca del loop en T115). La
sesión precompone el bloque en el entrypoint (`agent.py`, `await memory_cache.prime()`) para que el primer turno
salude por nombre sin tocar el retriever. Tests: `test_memory_cache.py` (cachea estado, NUNCA llama a
`memory.query`, se invalida por `memory.updated`).
