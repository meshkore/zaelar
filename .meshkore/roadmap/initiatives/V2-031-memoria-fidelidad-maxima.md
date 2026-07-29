---
id: V2-031
title: Memoria de FIDELIDAD MÁXIMA — subir el techo de recall (embedding SOTA local + auto-mejora continua)
epic: v2-colmena
status: in_progress
priority: critical
owner: ricart
modules: [memory, nucleo, tester]
depends_on: [V2-013, V2-019, V2-030]
wall_order: 31
created: 2026-07-12
updated: 2026-07-12
---

## Goal

La memoria es la BASE de un agente a largo plazo: **no debería fallar**. V2-030 metió el reranker (recall@1
41.6→56.2% local), pero el techo REAL —`found@10` ~82%, lo que el retriever siquiera trae— sigue bajo. Un 82% de
recuperabilidad es inaceptable para la pieza sobre la que se apoya todo. Esta iniciativa lleva el modo **LOCAL a su
máxima expresión de recall/fidelidad**, con la arquitectura **model-agnostic** ya montada (V2-030) para correr los
MISMOS modelos en nuestro **VPS con GPU** cuando escale, y los modelos **externos caros SOLO documentados** para un
tier premium (nunca default — no es sostenible).

**Métrica norte:** `found@10` (techo del retriever) y `recall@1/@3` (calidad final), medidos por
`tests/e2e/memory/bot/scale_eval.py` sobre la BD aislada del bot. **Objetivo:** found@10 82→**≥92%**, recall@1
56→**≥75%** en LOCAL, sin coste externo recurrente.

## Principio de tiers (localizado en contexto, decisión del operador)

1. **LOCAL (default, gratis)** — nuestra GPU/CPU hoy; mañana los MISMOS pesos en nuestro **VPS con GPU**. Es el
   modo que hay que exprimir. Cero coste recurrente.
2. **Externo por API (opcional, tier premium)** — solo si un cliente paga un "super premium". Documentado, NUNCA
   default. Debe conocerse el SOTA para poder ofrecerlo, pero se evita por sostenibilidad de coste.
La abstracción de V2-030 (`config/v2.py §memory`, provider por invocación) hace que cambiar de tier sea config, no
refactor.

## Encaje con lo YA construido (no reinventar)

- **V2-030** dejó: `memory/rerank.py` (reranker model-agnostic, local por defecto), `memory/reembed.py` (re-embed +
  firma de modelo), `config/v2.py §memory` (embed/rerank provider configurable), `scale_eval.py` (harness de recall
  a escala). ESTA iniciativa construye ENCIMA.
- **V2-019** dejó el consolidador cableado al loop (promote/dedup/decay/evict deterministas). T4 le añade la capa
  SEMÁNTICA (el hook `summarize_fn` hoy no-op).
- **`EMBED_DIM=768`** está HARDCODEADO en `memory/schema.py` → T1 lo hace **provider-driven** (un modelo de 1024d
  como bge-m3 exige dim dinámica + re-embed).

## Tareas (EN ORDEN — cada una se mide con scale_eval, se documenta y se comitea)

### T1 — Embedding SOTA local (sube el techo `found@10`) ⚙ EN CURSO
El bi-encoder es el que decide QUÉ entra al top-N; es el techo de todo lo demás. **Dim provider-driven** (schema/db/
embeddings) + benchmark de candidatos locales vs embeddinggemma(768):
- **bge-m3** (Ollama/fastembed, 1024d) — SOTA multilingüe de recuperación, muy fuerte en ES.
- **multilingual-e5-large** (fastembed, 1024d) · **snowflake-arctic-embed-l** (1024d) · **Qwen3-Embedding-0.6B**
  (MTEB top multilingüe, vía HF/Ollama community) si cabe en presupuesto GPU/RAM.
Re-embed del corpus con cada uno (`memory/reembed.py`) → `scale_eval` → elegir el mejor local que quepa. **Gate:**
found@10 ≥90%. Coste GPU/RAM anotado (contención con STT/TTS).

### T2 — Recuperación más profunda + índice de PARÁFRASIS al escribir (sube found@10 sin depender del modelo)
- Pool de candidatos más profundo (k 40→~100) y calibración RRF.
- **Paráfrasis al ESCRIBIR** (off-hot-path, en el CORAZÓN `mem_processor`): indexar 1-2 reformulaciones por píldora
  durable → más superficie de recuperación para el vocab-gap (T150 "instrumento"→"guitarra") SIN LLM en la lectura.
- Pseudo-relevance feedback ligero (opcional).

### T3 — Reranker local más fuerte + tuning (acerca recall@1 al techo found@10)
Benchmark `bge-reranker-v2-m3` / `Qwen3-Reranker-0.6B` vs el jina-v2 actual; tuning de `top_n`/`blend`. Elegir el
mejor local. Gate: recall@1 ≥ found@10 − 10pts.

### T4 — Consolidación SEMÁNTICA activa (cablear `summarize_fn`, descongestiona el espacio vectorial)
Fusionar píldoras casi-duplicadas por SIMILITUD de embedding (no solo texto exacto) en el consolidador
(`memory/consolidator.py`, hook ya existente). Menos ruido vectorial → mejor separación → mejor recall. Off-hot-path.

### T5 — Memoria AUTO-EVALUATIVA continua ("pieza que trabaja sobre la memoria para mejorarla") — la idea del operador
Un lazo de fondo tipo **sleep-time** (SOTA 2026: sleep-time compute, memoria reflexiva/auto-organizada A-MEM) que,
sin prisa y off-hot-path: (a) **auto-sondea** hechos guardados (genera preguntas desde las píldoras y comprueba si
son recuperables por el camino real), (b) **detecta fallos** de recuperación, (c) **REPARA** — refuerza peso, añade
aristas de grafo, indexa paráfrasis, marca para re-embed. Convierte la memoria en un sistema que se **mejora solo**
de forma continua. Observabilidad en el visor 🧠. Métrica: found@10 sube con el tiempo sin intervención.

### T6 — Catálogo SOTA + tiers en CONTEXTO (local · VPS-GPU propio · premium externo)
Documentar en `zaelar-memory.md` + `zaelar-model-benchmarks.md` el estado del arte de embeddings y rerankers 2026 por
tier: LOCAL (bge-m3/Qwen3-Embedding, jina/bge/Qwen3-reranker), **VPS-GPU propio** (los mismos, servidos por nosotros),
**premium externo** (Voyage-3, OpenAI text-embedding-3-large, Cohere rerank-3.5 / embed-4) con coste y cuándo se
justifican. Para poder ofrecer un tier premium sin re-investigar y para no caer en externos caros por defecto.

## Aceptación

- `found@10 ≥ 92%` y `recall@1 ≥ 75%` en LOCAL, medidos por `scale_eval` sobre la BD aislada, **sin coste externo**.
- Migración de embedding SEGURA (re-embed + firma, `memory/reembed.py`) — nunca mezclar espacios vectoriales.
- Invariantes de V2-013 intactos: **cero LLM en la lectura del turno**, ESTADO/CORTO µs, todo lo pesado off-hot-path.
- Cada T: medido con scale_eval, documentado (zaelar-memory.md/benchmarks/INI-013), comiteado. Sin push sin OK.
- Los modelos SOTA de cada tier quedan **localizados en el contexto** (T6).

## Bitácora
- 2026-07-12 · T1 arrancada (dim provider-driven + benchmark de embeddings locales). Ver entradas fechadas en INI-013.
- 2026-07-12 · **T1 HALLAZGO — el embedding NO es la palanca.** `bge-m3` (1024d SOTA) ≈ embeddinggemma (768) en
  found@10 (`zaelar-model-benchmarks.md §7`). El diagnóstico de los fallos mostró que la mayoría de "no recuperados"
  **NO están guardados** (write-side), no son fallos de retrieval. **Caveat de método detectado:** el bot siembra con
  embeddings `hash` (`runner.py:702`) → medir semántico exige re-embeber (`embed_bench.py`). **Re-priorización (con
  datos):** T1 (embedding) baja — se deja la abstracción provider-driven + `reembed.py`, pero no se persigue un
  embedding mayor. Sube el peso a: **T-write** (completitud de escritura del CORAZÓN, NUEVA #1) · **T2** (paráfrasis
  al escribir + pool) · **T5** (memoria auto-evaluativa que REPARA). Próximo paso: medición honesta sobre BD fresca de
  corpus completo re-embebida con embeddinggemma (semántico consistente) para fijar el baseline real de retrieval.
- 2026-07-12 · **T6 HECHO** (cero-GPU, durante prueba manual del operador): catálogo SOTA de embeddings+rerankers
  2026 por tier (LOCAL / VPS-GPU propio / PREMIUM externo) en `zaelar-model-benchmarks.md §8`. Además: tests de
  regresión de los cambios de escritura del operador (conv sin embed / durable por vector / trivia sin escritura,
  18 casos verdes) + `scale_eval` descompone write-miss vs retrieval-miss. Baseline honesto (Ollama-heavy) APLAZADO
  para no contender con la GPU de la prueba de voz en vivo.
