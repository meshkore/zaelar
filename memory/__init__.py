"""memory/ — MEMORIA CENTRAL de zaelar v2 «Colmena» (EPIC-v2-colmena, INI V2-002).

Módulo **top-level** (hermano de `voice/`, `widgets/`, `bus/`), NO parte del cerebro: es el **substrato
compartido** que escriben FlashBrain, el agente de memoria del SlowBrain y los widgets, y que lee el
retriever en la ruta caliente (ms). Memoria **tipo humana**, **100% local**, un solo fichero SQLite
`zaelar.db` (WAL) — sin servidor ni broker (multiplataforma; móvil a futuro).

> Diseño completo (no reabrir): `.meshkore/docs/architecture/zaelar-memory.md`. Esta iniciativa (V2-002)
> CONSTRUYE ese diseño; la versión pública/curada del diagrama vive en `web/` bajo `/technology/memory`.

Piezas (se construyen a lo largo de V2-002):
  - `db.py`          — conexión SQLite (WAL) + carga de sqlite-vec + migraciones.
  - `schema.py`      — DDL: state · memories · vec_memories · fts_memories · edges · episodic · journal.
  - `queue.py`       — cola async: TODAS las escrituras entran aquí.
  - `writer.py`      — ÚNICO escritor → BD; embeddings locales al insertar.
  - `embeddings.py`  — cliente de embeddings locales (Ollama embeddinggemma 768 · fallback fastembed).
  - `retriever.py`   — ruta caliente: vec ∥ fts → RRF → score ponderado → graph_expand.
  - `state.py`       — tabla fija de estado (lectura µs, sin búsqueda).
  - `graph.py`       — aristas (link/expand).
  - `episodic.py`    — ficheros/PDF: resumen embebido buscable + carga lazy del binario.
  - `consolidator.py`— job "sueño": compresión/dedup/conflictos/decay/eviction.
  - `api.py`         — fachada pública (write/query/state/reinforce/pin/unpin/link/load_episode/consolidate).

Datos: `memory/_data/zaelar.db` (gitignored). Override por `ZAELAR_DB`.
"""
