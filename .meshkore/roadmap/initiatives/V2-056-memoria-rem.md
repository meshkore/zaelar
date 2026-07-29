# V2-056 — Memoria: robustez F1 + sueño PROFUNDO «fase REM» + memoria→acción (tool recall + dossier v2)

> **Estado: CONSTRUIDO 2026-07-20** · rama `feat/v2-056-memoria-rem` · doc canónica actualizada:
> `zaelar-memory.md` (+ `zaelar-architecture.md §8`, diagrama `/architecture`, `CLAUDE.md`).
> Detonante: **incidente operativo 2026-07-17→19** — el CORAZÓN de escritura estuvo **2 días caído EN SILENCIO**
> (key rancia de env al endpoint equivocado) mientras todo se escribía por la heurística cruda, Y el espacio
> vectorial quedó MEZCLADO (embeddings fastembed bge-EN conviviendo con embeddinggemma). Purga manual de 29
> píldoras basura. Auditoría completa: `~/.meshkore/tmp/auditoria-memoria-20260719.html`.

## Objetivo

Que la memoria no vuelva a degradarse en silencio (salud de 1ª clase + fail-open que no ensucia), que se
**ordene/relacione/sintetice sola cada noche** (fase REM: la reflexión que faltaba desde V2-013), y que el
FlashBrain **actúe sobre lo que recuerda** (tool `recall` — V2-022 aplicado a la memoria; dossier v2 del worker).
Modelos del módulo elegidos POR BENCHMARK, no por inercia (`zaelar-model-benchmarks.md §12`).

## Qué se construyó

1. **CORAZÓN de escritura → `gpt-4.1-mini` vía OpenAI por config** (`config/v2.py §memory.mem_processor_*`),
   confirmado por bench §12 (**98.3%** sobre 16 casos, `tests/e2e/memory/bot/distiller_bench.py`); qwen2.5:7b
   local queda como OPCIÓN (86.2%). Key resuelta **POR ENDPOINT** (`nucleo/mem_processor.py::_key`, fix del
   incidente). **SALUD de 1ª clase**: racha de fallos → alerta observer + aviso de recuperación + `status()`.
2. **Sueño PROFUNDO «fase REM»** (`memory/rem.py`, NUEVO): ciclo diario disparado por `nucleo/loop.py` tras el
   sueño ligero — (1) `repair_embeddings` (re-embebe píldoras `embed_pending`/sin vector), (2) `semantic_dedup`
   (coseno ≥0.86 calibrado + guarda de cifras en conflicto; ecos de una tarea colapsan, `valid=0+superseded_by`,
   histórico intacto), (3) `synthesize` (grupos por CONCEPTO del grafo → 1 INSIGHT/grupo, `kind='insight'`,
   `slot=insight:<concepto>` → se REESCRIBE por sueño; hook LLM **INYECTADO** desde `nucleo/memllm.py` — la
   memoria no importa cerebros), (4) `hygiene` (% escritura heurística 24h → ALERTA si >50%). Config
   `§memory.rem_model/rem_base_url/rem_api_key/rem_every_hours` (default `gpt-4.1-mini`, bench síntesis 100%).
   Kill-switch `ZAELAR_REM`. Marcador persistente `sys_kv.rem_last_run`.
3. **`nucleo/memllm.py`** (NUEVO): router interno de modelos POR TAREA del módulo de memoria (tarea `rem` +
   futuras), key por endpoint, UA de navegador para AIMLAPI.
4. **Tool `recall`** en `nucleo/flash/router.py::TOOLS` (V2-022 aplicado a memoria: el MODELO decide recordar).
   Ruta ligera hermana de `web_search` en `voice/engine/llm/providers/nucleo.py` (`compose_recall` off-loop +
   2º pase). La heurística `needs_recall` queda como PREFETCH, ampliada con fraseos de planificación
   (vacaciones/viaje/organízame/resérvame…).
5. **`compose_context` v2** (`nucleo/memory_agent.py`) — DOSSIER del worker multi-eje: perfil (sin misión) +
   reglas del operador + ⚠️ `critical_facts` SIEMPRE + recall + `by_concepts` (T178/T183 por fin cableada) +
   agenda próxima; solo durables; todo en `asyncio.to_thread`.
6. **F1 robustez del núcleo**: decay Ebbinghaus **POR VENTANA** (`sys_kv.decay_last_run` — antes sobre-decay
   ~24×/día; vida media real **693 días**), `prune_invalid` (cáscaras `valid=0` fuera de los índices vec/FTS, fila
   conservada), `forget(hard)` delega en `writer.delete_memory` (los fantasmas FTS5 rompían la privacidad),
   endpoints HTTP de memoria con `to_thread`, **ENFORCEMENT de firma de embedding** en el writer
   (`meta.embed_pending` si discordante/degradado — nunca un vector de otro espacio), `state.patch` con lock,
   índices compuestos+expresión, `sys_kv` en schema, fail-open heurístico degrada a short+TTL 3d (NUNCA durable
   crudo; redes deterministas rescatan salud/compromisos/rutinas), `_DESIRE_RE` v3, `_COMMAND_RE` media, gate
   P0b con eje `garble_guard` (`operator.treatment` reformulable).
7. **Embeddings**: restaurado `ollama/embeddinggemma` (auto), **re-embed 261/261**, tras el incidente de mezcla
   de espacios (fastembed bge-EN 2 días).
8. **Incidente operativo 2026-07-17→19** documentado (detonante, ver cabecera): CORAZÓN caído 2 días en silencio +
   espacio vectorial mezclado; purga de 29 píldoras basura.

## Benchmarks (§12, `zaelar-model-benchmarks.md`)

- **Destilador** (`distiller_bench.py`, 16 casos / 29 checks): `gpt-4.1-mini` **98.3%** (1.1s) — TITULAR;
  `qwen2.5:7b` local 86.2% (2.2s) — opción batería/privacidad, pierde precisión en descartes.
- **Síntesis REM** (`rem_synth_bench.py`): `gpt-4.1-mini` **100%** — default de `§memory.rem_model`.

## Pendientes (fuera de esta iniciativa)

- **Bench act-on-memory CONTINUO**: medir de forma recurrente que el FlashBrain USA la tool `recall` cuando toca
  (no solo que existe) — integrarlo en la batería del tester.
- **Entidades / contactos** = V2-052 (diseño, pendiente de OK del operador).
- **Tiempo de validez** de los hechos (staleness/invalidación implícita, T179): la píldora aún no lleva ventana de
  vigencia explícita.

## Batería de validación — 2026-07-20 (informe: .meshkore/logs/bateria-v2056/INFORME.md)

- **pytest global 527/527** ✅ · **membot v1 976→994/1032** tras 3 fixes de escritura (+18) · **v3 161/165** ·
  v2 524/650 (ancla-literal + techo recall, sin regresión) · **scale_eval**: recall@1 54.4% / @10 75.4% /
  write-completeness 81.8% / retrieval@10-del-guardado 91.7% (reranker local jina, corpus real gpt-4.1-mini).
- **3 bugs reales arreglados** (verificados por la re-run): cambios de vida cuarentenados (slots car/hardware/job
  garble_guard=False), secretos que el operador pide recordar (prompt del destilador), reglas condicionales
  («si es finde…») tratadas como efímeras.
- **Fallos restantes = fronteras SOTA conocidas** (T150 vocab-gap, T179 staleness, ancla-literal del corpus v2),
  no regresiones → palancas de trabajo futuro (REM ataca staleness/dedup; reranker+paráfrasis atacan vocab-gap).
- Benches de modelos del módulo (§12 benchmarks): destilador gpt-4.1-mini 98.3%, síntesis REM gpt-4.1-mini 100%.
- Fixes de harness (no producción): runner casos de escala (store>env + dedup O(N²) al sembrar); scale_eval --fresh.

**Estado: CONSTRUIDO y VALIDADO.** Pendiente de sesión futura: write-completeness (V2-031, la palanca nº1 real),
entidades/personas (V2-052), tiempo de validez para staleness (T179), CI + cron persistente para la batería.
