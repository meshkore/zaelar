# Test bot de memoria — harness de evolución continua (V2-013)

Un "bot" que role-play una PERSONA hablando con zaelar a lo largo de una conversación LARGA (objetivo **1000
pasos**) y, por CADA paso, verifica que la **memoria tipo humana** hace lo correcto: al **guardar**, que el dato
cae donde debe (ESTADO / CORTO / LARGO / DESCARTE); al **preguntar**, que la lectura como la del **FlashBrain**
devuelve el dato. Es nuestro LongMemEval casero: guía la evolución del módulo de memoria hasta que funcione como
la de una persona.

## Piezas

- `cases.py`/`cases2.py`/`cases3.py` — corpus históricos extensos. `cases4.py` es la batería focalizada visible
  primero en el Observatory: conversación natural multi-hecho, descarte, correcciones y recall diferido.
  Cada caso histórico = `save` (con `in`=capas esperadas, `[]`=descarte) o
  `query` (con `via`=fuente esperada, `want`=subcadenas que deben aparecer). Una PERSONA coherente y acumulativa.
- `runner.py` — el MOTOR. Una BD **AISLADA por corpus** (`memory/_data/zaelar.membot*.db`, NUNCA el perfil real).
  Ejecuta la ruta REAL de escritura (`memory_agent.ingest_utterance` → CORAZÓN LLM configurado) y la ruta REAL de lectura del FlashBrain
  (`memory_cache._compose` estado+perfil-durable+corto + `compose_recall` con su gate `needs_recall`). Verifica,
  informa y persiste progreso.
- `CATALOG.md` — REGISTRO legible autogenerado desde `cases.py`: cada request + qué esperamos al grabar y al
  consultar. Se regenera en cada corrida.
- `RESEARCH.md` — bitácora VIVA del state-of-the-art (Mem0/Zep/Letta/MemPalace…) que alimenta el diseño.
- Informes/progreso: `.meshkore/logs/membot/` (`progress.json` + `report-*.json`).

## Uso

```bash
./.venv/bin/python -m tests run memory --case memory::group::1.4::v4 --no-open
./.venv/bin/python -m tests.memory.e2e.bot.runner --corpus v4 --fresh --range 0 15
./.venv/bin/python -m tests.memory.e2e.bot.runner --corpus v1 --fresh --next 10
./.venv/bin/python -m tests.memory.e2e.bot.runner --corpus v4 --catalog
```

El CORAZÓN usa el proveedor configurado para memoria (por defecto `gpt-4.1-mini` vía OpenAI; puede apuntarse a
Ollama local). El runner carga `.env` explícitamente sin sobrescribir variables ya exportadas y publica en cada
caso la fuente real (`llm` o `heuristic`). Los casos `require_llm` fallan si el proveedor no respondió: nunca se
acepta silenciosamente una heurística como prueba de extracción semántica. Los embeddings siguen la configuración
normal. Las BD del bot están gitignored bajo `memory/_data/` y no tocan `zaelar.db` real.

## El CICLO de evolución (manual del loop autónomo)

Cada iteración (el agente, con criterio humano):

1. **Genera las siguientes 10** cases realistas en `cases.py` (varía: identidad, gustos, hechos durables, cosas
   efímeras, descartes, y preguntas de recall — incluidas preguntas tipo "¿qué deportes te gustan?" como en una
   charla persona-a-persona; y recall temporal: "aquel viaje del mes pasado", "la búsqueda de coche de la semana
   pasada", "un mensaje de hace meses"). Deduce por cada una qué es importante y dónde debe ir.
2. **Corre** `--fresh --range 0 HI` (replay lineal completo hasta el nuevo tope).
3. Si hay **fallos** → **itera el MÓDULO de memoria** (no el test): few-shot/modelo del procesador, importancia
   dinámica, slots, `needs_recall`, el bloque salient, el retriever/scoring, la consolidación… **Puedes cambiar
   también cómo el FlashBrain/SlowBrain usan la memoria** (es el objetivo: la mejor memoria del mundo). Re-corre.
4. Cuando la tanda queda **verde** → `pytest tests/ nucleo/` (sin regresión) → **commit estable** (checkpoint).
5. **De vez en cuando**, búsqueda web del state-of-the-art (anota en `RESEARCH.md`) y aplica lo que mejore.
6. Repite hasta 1000 verificadas. **No parar.**

## Punto de ROLLBACK (hook)

Checkpoint estable base de esta línea de trabajo: **commit `265359d`** ("V2-013 CORAZÓN de escritura + tests
central"). Si una iteración rompe la memoria: `git reset --hard <checkpoint>` al último commit verde. Cada tanda
verde deja su propio checkpoint — siempre hay un punto seguro al que volver.
