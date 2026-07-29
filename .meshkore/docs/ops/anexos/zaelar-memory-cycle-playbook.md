# Anexo — Playbook del CICLO DE 1000 (re-verificación de la memoria)

> Documento reutilizable: cómo repetir DESDE CERO el ciclo que lleva la memoria de zaelar a **≥1000 requests
> verificadas en verde** (ESTADO/CORTO/LARGO + 26 tipologías más), en un loop autónomo. Última corrida:
> **2026-07-12 — GOLD 1032/1032, 9 bugs de código arreglados**. Resultados fechados en
> `tests/e2e/memory/bot/resultados/<fecha>-ciclo-1000/`.

## Qué prueba (y por qué)

El **test-bot de memoria** (`tests/e2e/memory/bot/`) role-play una PERSONA que habla con zaelar durante una
conversación LARGA (1032 pasos) y, por cada paso, verifica que la memoria HUMANA hace lo correcto por el **camino
REAL** (escritura por el CORAZÓN LLM local `ingest_utterance`; lectura como la del FlashBrain `_brain_view` =
`memory_cache._compose` + `compose_recall`, SIN LLM). No mide lo que el bot DICE sino lo que la memoria HACE.

**29 dimensiones (A–Y + Z/AA/AB/AC)** — mapa en `TAXONOMY.md`. Núcleo: **ESTADO** (A, Y), **CORTO** (B), **LARGO**
(C). Resto: dedup/supersede (D), descarte/abstención (E), grafo/categoría (F), multi-fuente (G), cuarentena (H),
intereses (I), temporal (J), escala (K), olvido/consolidación (L), contradicciones (M), privacidad/olvido (N),
rutinas (O), adversarial (P), cross-source (Q), multilingüe (R), episódica (S), vocab-gap (T), multi-hop (U),
verbosidad (V), instrucciones permanentes (W), invalidación implícita (X), y las SOTA 2026: memoria→acción (Z),
anti-alucinación (AA), validez temporal/as-of (AB), identidad cross-sesión (AC). Fundamento SOTA en `RESEARCH.md`.

## Cómo se ejecuta

```bash
./.venv/bin/python -m tests.e2e.memory.bot.runner --coverage        # cobertura por dimensión (elegir hueco)
./.venv/bin/python -m tests.e2e.memory.bot.runner --next 80         # avanza 80 sobre la BD acumulada (persona coherente)
./.venv/bin/python -m tests.e2e.memory.bot.runner --fresh --range 0 1032   # pasada de ORO (replay lineal limpio)
./.venv/bin/python -m tests.e2e.memory.bot.runner --catalog         # regenera CATALOG.md
```

**DOS corpus (auditoría 2026-07-14):** `--corpus v1` (def) = la GOLD histórica `cases.py` (persona Ricart, 1032);
`--corpus v2` = el corpus NUEVO `cases2.py` (persona Amaia Etxeberria de Logroño — genericidad/multi-operador +
las 4 dimensiones nuevas AD–AG: señal `change` multiidioma, colapso de linajes por alias de slot, escritura de
workers `remember_external`, y `heal_slots`). BD/progreso/catálogo AISLADOS por corpus → correr uno no pisa al
otro. Tipos de paso nuevos: `worker_write`, `slot_count`, `heal_slots`. `python -m …runner --corpus v2 --fresh --range 0 N`.

Requiere **Ollama local** (CORAZÓN `qwen2.5:*`, embeddings `embeddinggemma`). BD **AISLADA**
(`memory/_data/zaelar.membot.db`, gitignored) — nunca el perfil real. Reporte JSON + progreso en
`.meshkore/logs/membot/`. La GOLD tarda ~30–75 min (los casos dim-K de escala siembran miles de embeddings);
lánzala con `python -u` (unbuffered) para ver el progreso, y vigila que no se cuelgue en I/O (0% CPU sleeping).

## El CICLO (loop autónomo `/loop 10m`, estrategia AVANZAR-PRIMERO)

Cada iteración (10 min): **guard anti-solape** (`pgrep -f memory.bot.runner`; solo UN runner) → avanza una ola de
80 (`--next 80`) → **triaja SOLO los ❌ de esa ola** → `pytest -k memory` verde → commit → entrada en INI-013. Al
llegar a `done_upto ≥ corpus` entra en **MODO GOLD**: `--fresh --range 0 <N>` en background, triaja su report,
RE-lanza, hasta **0 ❌** → entregables + PARA el loop.

**NO re-verificar prefijos tras cada ola** (el escritor LLM es no-determinista, ~1–2 % de casos flip-flop entre
corridas frescas; re-verificar en bucle churnearía).

### Clasificación de cada ❌ (la decisión clave)

- **(a) BUG REAL de memoria** → arreglar el **CÓDIGO** como mejora (`nucleo/mem_processor.py`,
  `nucleo/memory_agent.py`, `memory/api.py`, `memory/retriever.py`, `memory/writer.py`, `memory/consolidator.py`,
  `nucleo/flash/*`). **NUNCA ablandar el test.** Añadir guard test de regresión.
- **(b) FLAKY** (pasaba antes en fresco, falla ahora sin cambio de código → canonicalización variable del CORAZÓN)
  → **ancla ROBUSTA**: token estable + query con puente léxico o miembro PRIMARIO de la categoría (verificar con un
  probe `_brain_view`, no re-correr toda la ola).
- **(c) TEST-FLAW** (ancla mal, colisión de substring, expectativa de capa/recall irreal) → corregir el caso.

Distinguir bien es el corazón del ciclo: un bug se arregla en código; un flaky/test-flaw se endurece el ancla.

### Cada cuánto evalúa y se CUESTIONA

- **Cada ~50 pasos**: releer `EXIGENCIA.md` y auditar 2–3 casos al azar (control de calidad).
- **Cada ~100 pasos**: 1 WebSearch de un benchmark/diseño de memoria SOTA → anotar en `RESEARCH.md` y aplicar lo que
  mejore.
- **En cada GOLD**: la pasada de oro fresca es el juez final; su report se triaja hasta 0 ❌.

## Fenómenos CONOCIDOS (no confundir con bugs)

1. **No-determinismo del CORAZÓN**: qwen2.5 (aun a temp 0) canonicaliza el mismo input con fraseo distinto entre
   corridas → anclas al token estable + queries con puente. Es el origen del ~1–2 % flaky.
2. **Recall-a-escala**: a cientos de memorias el embedding LOCAL (embeddinggemma) se degrada (aviso T176) → un hecho
   GUARDADO puede no aflorar sin solape léxico. Es límite del modelo, no bug (SOTA: HippoRAG-v2 54 % en
   FactConsolidation). Se prueba con preguntas naturales que nombran la entidad / usan el término concreto.
3. **Colisión de ancla**: markers de 3 letras ("aja") colisionan con palabras comunes ("trAbAJA") → anclar a frase
   distintiva o token único.

## Cómo repetir desde cero

1. `--coverage` para ver el corpus y las capas. Paso 0 de ALINEACIÓN: ¿cubre los cambios de las últimas 48 h?
   (git log --since). Si falta, añadir el escenario ANTES.
2. Lanzar el loop `/loop 10m <prompt del ciclo>` (rama dedicada `feat/memoria-<algo>`). Avanzar-primero.
3. Al cerrar la GOLD en verde: archivar el report en `resultados/<fecha>-ciclo-1000/`, regenerar la tabla HTML
   (`~/.meshkore/tmp/zaelar-ciclo-1000-memoria.html`), documentar en INI-013, y **revisión de alineación**.

## Artefactos de la corrida 2026-07-12

- GOLD **1032/1032** · report `resultados/20260712-ciclo-1000/gold-report.json`.
- Tabla HTML de las 1032 requests (tipología·capa·ancla·resultado): `~/.meshkore/tmp/zaelar-ciclo-1000-memoria.html`.
- **9 bugs de código** arreglados (todos con verificación; la mayoría con guard test): backstop de salud
  (operación) · backstop de salud (fisioterapia) · backfill de conceptos al grafo · descarte determinista de relleno
  · backstop de ubicación habitual de objetos · unforget con fallback token-AND · eviction protege hechos salientes
  (SOTA) · backstop de perfil durable biográfico · forget/unforget unen contiguo+token-AND.
- Bitácora por ola: INI-013 (§ Ciclo de 1000, 2026-07-12).
