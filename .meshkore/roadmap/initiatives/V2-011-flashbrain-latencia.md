---
id: V2-011
title: FlashBrain — latencia sub-segundo (sacar la memoria del camino caliente)
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [nucleo, memory, voice]
depends_on: [V2-004]
wall_order: 11
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T11:32:13.372Z
commit_sha: 1eb506c1c072a6d600b20b3193c0fe506fcdeeef
---
## Goal

Recuperar la latencia del turno de voz que el sistema v1 (duo) ya tenía resuelta (~1s con Grok) y que el port a
`nucleo/` (V2-004) rompió (3-9s medidos con el tester el 2026-07-09). El modelo (grok-4-fast-non-reasoning) y las
frases-puente NO cambiaron; la regresión es de arquitectura del camino caliente.

## Diagnóstico (2026-07-09, con el tester en vivo + contraste git contra duo viejo)

Causa raíz: **el retriever completo de memoria corre SÍNCRONO en el camino caliente, por turno**, antes de la
llamada al LLM. `voice/engine/llm/providers/nucleo.py::_run` llama a `nucleo/flash/prompt.py::build_flash_system(
recall_query=text)`, que en `_memory_block()` hace `memory.query(text, reinforce_used=True)` → embeddings Ollama
(`embeddinggemma`, HTTP a :11434) + vec + FTS + RRF + graph_expand + **escrituras de refuerzo**, todo bloqueando
el event loop antes de que el LLM empiece. El duo viejo (`brains/duo/briefing.py`) NO hacía esto: pedía un briefing
UNA vez al arrancar y lo **cacheaba** (TTL 300s), inyectándolo como string en el prompt; el turno nunca esperaba al
retriever. Referencias: git `30eb01b^` (duo) + proyecto `voice-lab-2` (motor de voz de referencia).

## Qué se construye

Mover toda la recuperación/escritura de memoria FUERA del camino crítico del turno, conservando el recall real:
bloque de memoria cacheado por sesión (estado + recall) refrescado async, `memory.query`/embeddings y refuerzo en
un hilo (`asyncio.to_thread`) o fire-and-forget, y recall bajo demanda (no en cada frase). Instrumentar el desglose
de latencia por turno para atribuir con datos, no intuición.

## Tareas

- [x] T113 — Instrumentar el desglose de latencia del turno nucleo (memory.state, memory.query/embeddings, live_state, LLM TTFT, TTS) en `/debug`, para atribuir con datos.
- [x] T114 — Bloque de memoria CACHEADO por sesión (estado + recall) con TTL + refresco async, como el briefing viejo; el turno no espera al retriever.
- [x] T115 — Mover `memory.query`/embeddings y las escrituras de refuerzo (`reinforce_used`) fuera del event loop (`asyncio.to_thread` / fire-and-forget) — nunca bloquear el streaming del TTS.
- [x] T116 — Recall bajo demanda: consultar memoria específica solo cuando el turno lo pide (heurística/tool), en paralelo con la frase-puente, no en cada frase.
- [x] T117 — Verificación con el tester (conversation/memory/widget) + registro en `zaelar-model-benchmarks.md`: objetivo p50 < ~1.5s en charla, sin picos >3s; recall de memoria conservado.

## Aceptación

- El turno de charla del FlashBrain cierra en tiempo comparable al duo v1 (p50 < ~1.5s; sin picos de 8-9s en un "hola").
- El event loop NUNCA se bloquea por I/O de memoria durante un turno (verificado por instrumentación).
- El recall real (nombre del operador, un dato guardado) se conserva — probado con el escenario `memory` del tester.
- La latencia queda registrada con MEDICIÓN (no intuición) en `zaelar-model-benchmarks.md`.

## Riesgos

- Cachear la memoria puede servir un recall stale; mitigar con TTL corto + invalidación por la señal `memory.updated` del bus.
- Recall bajo demanda mal calibrado podría perder un recuerdo relevante; el escenario `memory` del tester es el gate.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 — T113: instrumentación del desglose de latencia por fase (evento `timing` en `/debug`). Baseline
  medido: `mem_query_ms` 112–452 ms/turno = TODO el coste del prompt, síncrono en el loop (confirmado el diagnóstico).
- 2026-07-09 — T114: `nucleo/flash/memory_cache.py` — bloque de estado cacheado por sesión (TTL 300 s, refresco
  async off-loop, invalidación por sink de `memory.updated`); prime en el entrypoint; el turno lee el string cacheado.
- 2026-07-09 — T115: recall (`compose_recall`) fuera del event loop (`asyncio.to_thread`); el loop nunca se para
  por I/O de memoria; refuerzo/write ya iban por la cola async.
- 2026-07-09 — T116: recall bajo demanda (`prompt.needs_recall`, heurística es/en); la charla no toca el retriever.
- 2026-07-09 — T117: verificado con el tester — memory p50 1139 ms (baseline 3726avg), widget p50 1031 ms (baseline
  5885avg), recall REAL conservado; números en `zaelar-model-benchmarks.md §4`.
- 2026-07-09 — Revisión de alineación PASADA (CLAUDE.md §nucleo + decisión de latencia, `zaelar-architecture.md`,
  `zaelar-modules.md §nucleo/§memoria`, diagrama `/architecture` pestañas Arquitectura/Memoria/Brain + sello). Iniciativa cerrada.
- 2026-07-12 — **Recaída de latencia/recursos diagnosticada EN VIVO + arreglada** (commit `perf(voz+memoria)`): (1)
  `VADMetrics` se logueaban ~2/s continuo (2 escrituras de fichero SÍNCRONAS/evento en el hilo de voz) → flood de
  eventos + latencia; se descartan (agent.py). (2) el **buffer conversacional** se embebía CADA turno
  (embeddinggemma/Ollama, GPU, compite con STT/TTS) sin usarse nunca → NO se embebe (`kind='conv'`, writer) y se
  excluye de `promote` (consolidator). (3) `_TRIVIA_SKIP_RE` ampliado (ah/eh/mmm/ya está/…) → menos corridas del
  procesador LLM local en turnos triviales. (4) puente `memory.updated`→SSE **coalescado** (debounce 400ms). (5)
  robustez a ruido LEJANO: gate RMS 0.012→0.02 + VAD activation 0.4→0.5 (rechaza voz/ruido a varios metros → menos
  turnos fantasma que gastan STT+memoria). Tests memory/nucleo/widgets/bus/config/voice verdes (dims A-X intactas).
