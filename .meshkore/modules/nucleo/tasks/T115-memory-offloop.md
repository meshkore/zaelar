---
id: T115
title: "memory.query/embeddings y refuerzo fuera del event loop (to_thread / fire-and-forget)"
status: done
priority: high
owner: ricart
category: nucleo
initiative: V2-011
depends_on: [T114]
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09
commit_shas: [ede30d7]
---

# T115 — Nunca bloquear el event loop con I/O de memoria

Cualquier `memory.query()`/embeddings (HTTP a Ollama) y las escrituras de refuerzo (`reinforce_used=True`) que
queden se ejecutan en `asyncio.to_thread` o fire-and-forget, para que jamás bloqueen el streaming del TTS ni otro
turno concurrente. Verificar con la instrumentación de T113 que el loop no se bloquea durante un turno.

## Cierre (2026-07-09)

`nucleo/flash/prompt.py::_recall_block` → renombrado a `compose_recall` (público). `nucleo.py::_run` lo ejecuta
en `await asyncio.to_thread(compose_recall, text, timings)` → los embeddings HTTP a Ollama corren en un hilo, el
event loop NUNCA se para durante el turno (era la regresión de V2-004). `build_flash_system` recibe el
`recall_block` ya compuesto y solo hace lecturas de ms en el loop (caché de estado + briefs + live). El refuerzo
por uso (`reinforce`) y la escritura post-turno (`memory.write`) ya iban por la cola async de `memory/queue.py`
(loop-agnóstica, `submit()` desde cualquier hilo) → confirmado que no bloquean.
