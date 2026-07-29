---
id: V2-002
title: Memoria v2 — núcleo local (memory/ top-level · SQLite + sqlite-vec + FTS5 + retriever + olvido)
epic: v2-colmena
status: done
priority: high
owner: ricart
modules: [memory, bus]
depends_on: [V2-001]
wall_order: 2
created: 2026-07-09
updated: 2026-07-09
completed_at: 2026-07-09T02:11:09.243Z
commit_sha: 74b3bf9f803b67fbf79c3829f89c70d13ea41d29
---
## Goal

Construir la **memoria central** como módulo top-level `memory/` (hermano de `voice/`, `widgets/`), **standalone
y completamente testeado ANTES de que ningún cerebro la use**. Es el substrato compartido: la escriben FlashBrain,
el agente de memoria y los widgets; la lee el retriever en la ruta caliente (ms). 100% local, un solo fichero,
cero infra externa.

> **Diseño completo (no reabrir):** `.meshkore/docs/architecture/zaelar-memory.md` + pestaña **Memoria** de
> `/architecture`. Esta iniciativa CONSTRUYE ese diseño. Decisión v2: la memoria es `memory/` top-level, **NO**
> `nucleo/memoria/` → primera tarea = realinear paths del diagrama y la doc.

## Qué se construye (según zaelar-memory.md)

- `memory/db.py` — conexión SQLite `zaelar.db` (WAL), carga de `sqlite-vec`, migraciones de schema.
- `memory/schema.py` — DDL: `state` · `memories` · `vec_memories` (vec0 FLOAT[768]) · `fts_memories` (fts5) ·
  `edges` · `episodic` · `journal` (tal cual el doc).
- `memory/queue.py` — cola async (asyncio.Queue): TODAS las escrituras entran aquí.
- `memory/writer.py` — **único escritor** → BD; calcula embeddings LOCALES al insertar (embeddinggemma 768 vía
  Ollama; fallback `fastembed` ONNX si no hay Ollama). Sin coste por inserción.
- `memory/retriever.py` — ruta caliente: `state.read()` siempre + vector(k=40) ∥ fts(k=40) → RRF(k=60) →
  `score = α·rel + β·rec + γ·imp + δ·uso` → `graph_expand` opcional → trunca al budget de tokens.
- `memory/graph.py` — aristas (`link`, `expand`).
- `memory/state.py` — tabla fija (lectura µs, escritura por agente de memoria/consolidador).
- `memory/episodic.py` — ficheros/PDF: resumen embebido buscable + carga lazy del binario. (En V2-003 absorbe files/.)
- `memory/consolidator.py` — job "sueño": comprime corto→medio→largo, deduplica, resuelve conflictos, decay
  `I(t)=I₀·e^(−λt)` (λ≈0.001/día), borrado por peso SOLO si se excede el límite, nunca los pinned.
- `memory/api.py` — fachada pública: `write/query/state/reinforce/pin/unpin/link/load_episode/consolidate`.
  Rutas: `write/reinforce/link` = async (cola/eventos); `query/state/load_episode` = directa (hot path).
- Datos: `zaelar.db` (gitignored).

## Tareas

- [ ] Realinear paths a `memory/` en el diagrama Memoria (`frontend/pages/architecture.html::buildMemArch`) y en
      `zaelar-memory.md` (§Módulos y §API) — decisión top-level. Doc-sync.
- [ ] `requirements.txt`: `sqlite-vec==0.1.9`; documentar embeddinggemma vía Ollama + fallback `fastembed==0.8.0`.
- [ ] `memory/db.py` + `memory/schema.py` — abrir zaelar.db (WAL), cargar sqlite-vec, crear tablas + tests.
- [ ] `memory/queue.py` + `memory/writer.py` — un solo escritor, embeddings locales al insertar + tests.
- [ ] Embeddings: cliente local (Ollama embeddinggemma 768) con fallback fastembed; test de dimensión/idioma es.
- [ ] `memory/retriever.py` — vec ∥ fts → RRF → score ponderado → graph_expand; test de fusión y orden.
- [ ] `memory/state.py` — read/write de la tabla fija + test (µs, sin búsqueda).
- [ ] `memory/consolidator.py` — compresión/dedup/conflictos/decay/eviction + tests (incl. pinned nunca borrado).
- [ ] `memory/graph.py` — link/expand + test.
- [ ] `memory/episodic.py` — resumen embebido + load lazy (esqueleto; bytes en V2-003).
- [ ] `memory/api.py` — fachada + emite señal `memory.updated` por el `bus/` + test de roundtrip write→query.

## Aceptación

- `pytest memory/` verde: write→query devuelve lo insertado por relevancia; RRF fusiona; reinforce sube peso y
  resetea decay; consolidador comprime y NUNCA borra pinned; eviction solo sobre el límite.
- `memory.state()` devuelve un dict en µs sin tocar el índice.
- La BD es un solo `zaelar.db`, gitignored, sin proceso/infra externa.
- Ningún cerebro la usa todavía (standalone).

## Riesgos

- sqlite-vec debe cargarse en el `sqlite3` de Python (`enable_load_extension`); en macOS el `sqlite3` del sistema
  a veces no lo permite → usar el del venv / `pysqlite3-binary` si hace falta. Verificar temprano.
- Ollama puede no estar arrancado → el fallback fastembed (ONNX, sin server) debe cubrirlo.

## Bitácora
<!-- una línea fechada por tarea cerrada -->
- 2026-07-09 · T42 — doc-sync de la decisión top-level: los paths del diagrama Memoria (`architecture.html::buildMemArch` — `queue.py`/`writer.py`/`consolidator.py`) y la §Módulos de `zaelar-memory.md` pasan de `nucleo/memoria/` a **`memory/` top-level** (hermano de `voice/`, `widgets/`). Sello del diagrama → «EN CONSTRUCCIÓN · V2-002 · Actualizado: 2026-07-09»; estado del doc → EN CONSTRUCCIÓN. `sqlite-vec==0.1.9` verificado (carga en el sqlite3 del venv, `vec_version v0.1.9`); embeddinggemma (768) descargado en Ollama y verificado con texto en castellano.
- 2026-07-09 · T43 — `requirements.txt`: `sqlite-vec==0.1.9` fijado + sección «Memoria central v2» documentando embeddings locales (embeddinggemma 768 vía Ollama, fallback `fastembed==0.8.0` comentado, degradación determinista para tests sin red). Ollama no es paquete pip (servicio aparte).
- 2026-07-09 · T44 — `memory/schema.py` (DDL fiel al doc: state · memories+índices · edges+índices · episodic · journal · `vec_memories` vec0 FLOAT[768] · `fts_memories` fts5) + `memory/db.py` (`zaelar.db` WAL/synchronous=NORMAL, carga best-effort de sqlite-vec → `vec_available`, sonda FTS5 → `fts_available`, migración idempotente por `PRAGMA user_version`, conexión única serializada por RLock, singleton `get_db()`/`reset_db()`). MISMO path que `bus/log.py` (`ZAELAR_DB`/`memory/_data/zaelar.db`). 8 tests verdes (`memory/test_db.py`, incl. WAL, tablas, vec0 insert/MATCH, migración idempotente).
- 2026-07-09 · T45 — `memory/writer.py` (ÚNICO escritor: `insert_memory` sincroniza las 3 representaciones — fila `memories` + vector `vec_memories` + índice externo `fts_memories`; `reinforce` sube peso con techo 1.0 y resetea recencia; `link`/`set_pinned`/`supersede`/`delete_memory` mantienen vec+fts+edges; `OPS` despachable) + `memory/queue.py` (cola async, consumidor ÚNICO, `submit()` loop-agnóstico con fallback en-línea si no hay consumidor, un fallo no tumba al consumidor) + `memory/embeddings.py` (que el writer necesita). 9 tests verdes (`memory/test_writer_queue.py`).
- 2026-07-09 · T46 — `memory/embeddings.py`: embeddings LOCALES con cadena de backends — Ollama `embeddinggemma` 768 (default, multilingüe) → `fastembed` ONNX → **hashing determinista** (feature-hashing bag-of-words, cero deps/red, señal léxica) para que tests/entornos sin Ollama nunca se queden sin embeddings. Todos L2-normalizados (L2 de sqlite-vec ≈ coseno), siempre dim 768. Modelo por env (`ZAELAR_EMBED_MODEL`/`ZAELAR_EMBED_BACKEND`), sin env global de cerebro. 6 tests verdes (`memory/test_embeddings.py`; el de semántica en castellano corrió con embeddinggemma real y pasó).
- 2026-07-09 · T47 — `memory/retriever.py` (RUTA CALIENTE): `vec_search`(sqlite-vec k=40) ∥ `fts_search`(FTS5 bm25, prompt saneado a OR de tokens entrecomillados) → `rrf`(k=60) → `score = α·rel + β·rec + γ·imp + δ·uso` (.45/.25/.20/.10, recencia half-life 7d) → `graph_expand` (vecinos por `edges`, score descontado, sin duplicar) → trunca al límite. Degradación en cascada vec→fts→LIKE (nunca revienta). Refuerzo NO se escribe aquí (retriever puro): `search(reinforce=True)` emite `memory.reinforce` por el bus (loop-agnóstico). 6 tests verdes (`memory/test_retriever.py`: RRF, keyword, BD vacía, score por imp/recencia, graph_expand, señal de refuerzo).
- 2026-07-09 · T48 — `memory/state.py`: la tabla FIJA (fila única `state(id=1)`, JSON) que se inyecta SIEMPRE en el prompt sin búsqueda. `read()` = un SELECT por PK (µs) fusionado con defaults (castellano, `operator_name=None`); `write()` reemplaza fusionando sobre defaults; `patch()` = merge superficial (no pierde campos). 5 tests verdes (`memory/test_state.py`: default es, roundtrip, patch, fila única, lectura sin índice).
- 2026-07-09 · T49 — `memory/consolidator.py` (el "sueño"): `decay` (`weight*=e^(−λ·Δt)` desde last_access → el acceso resetea el decay), `evict` (borra el de MENOR peso NO-pinned SOLO al superar el límite; **NUNCA los pinned** — para si solo quedan pinned), `dedup` (fusiona texto idéntico normalizado, conserva el de mayor peso, reengancha aristas), `promote` (corto→mid→long por edad; hook `summarize_fn` para la compresión semántica de V2-006), `consolidate` (orquesta + informe). Conflictos temporales: mecanismo `writer.supersede` (auto-detección semántica queda para el agente de memoria, V2-006). 8 tests verdes (`memory/test_consolidator.py`, incl. pinned intocable y eviction solo sobre el límite).
- 2026-07-09 · T50 — `memory/graph.py`: cara de lectura/enlace del grafo (aristas `edges` en el mismo fichero). `link` (atajo directo → writer, único escritor), `neighbors` (salientes ordenadas por peso, filtro por tipo), `expand` (BFS acotado por profundidad, excluye los de partida, tolera ciclos) — lo usa el retriever para traer vecinos relevantes. 5 tests verdes (`memory/test_graph.py`).
- 2026-07-09 · T51 — `memory/episodic.py` (esqueleto): `register()` crea el RESUMEN buscable (memories kind='summary', embebido + fts vía el writer) + la fila `episodic`; `get()`/`by_memory()` metadatos; `load_text()`/`load_bytes()` carga LAZY desde `path` (None si no existe). El resumen participa en la búsqueda; el binario nunca entra en contexto por defecto. La absorción de `files/uploads/` (bytes al data-dir + re-cableado de la subida) queda para V2-003 (T53/T54). 4 tests verdes (`memory/test_episodic.py`).
- 2026-07-09 · T52 — `memory/api.py` (FACHADA pública): async por cola (`write`/`reinforce`/`pin`/`unpin`/`link`) vs directo hot-path (`query`/`state`/`load_episode`); `query()` compone estado (SIEMPRE) + recuerdos truncados al presupuesto de tokens y encola el refuerzo de los usados; cada mutación emite `memory.updated` por el bus; `start()`/`stop()` para el consumidor en el lifespan (cablea V2-003); `write_now()` síncrono para quien necesita el id. 7 tests verdes (`memory/test_api.py`: roundtrip write→query directo y por cola, presupuesto, estado, señal `memory.updated`, refuerzo escribe peso, consolidate). **Suite completa memory+bus+config+nucleo: 93 passed** (sin regresión).
- 2026-07-09 · **V2-002 CERRADA** — Aceptación cumplida: `pytest memory/` verde (58 tests: write→query por relevancia, RRF fusiona, reinforce sube peso y resetea decay, consolidador comprime y NUNCA borra pinned, eviction solo sobre el límite); `memory.state()` devuelve un dict por lectura de fila única (sin índice); la BD es un solo `zaelar.db` en `memory/_data/` (gitignored, cero infra externa, sqlite-vec cargado en el venv); ningún cerebro la usa todavía (standalone, no cableada al server/voz). `make run-duo` sigue con el cerebro actual (`/api/brain` = duo), cero regresión. `cluster.yaml` actualizado (memory · NÚCLEO CONSTRUIDO). **state.json es artefacto del daemon MeshKore** — no se edita a mano; el daemon converge `status`/`completed_at`/`commit_shas` de las tareas al re-leer los .md (algún `status` puede ir por detrás hasta el siguiente barrido). Siguiente: **V2-003 — Memoria integración** (files/→episódica, migración, widgets escriben).
