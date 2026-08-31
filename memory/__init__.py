"""memory/ — zaelar v2 "Hive" CENTRAL MEMORY (EPIC-v2-hive, INI V2-002).

**Top-level** module (sibling of `voice/`, `widgets/`, `bus/`), NOT part of the brain: it is the **shared substrate**
written by FlashBrain, the SlowBrain memory agent, and widgets, and read by the retriever on the hot path (ms).
**Human-like**, **100% local** memory, a single SQLite file `zaelar.db` (WAL) — no server or broker (cross-platform;
mobile in the future).

> Full design (do not reopen): `.meshkore/docs/architecture/zaelar-memory.md`. This initiative (V2-002) BUILDS that
> design; the public/curated diagram version lives in `web/` under `/technology/memory`.

Pieces (built throughout V2-002):
  - `db.py`          — SQLite connection (WAL) + sqlite-vec loading + migrations.
  - `schema.py`      — DDL: state · memories · vec_memories · fts_memories · edges · episodic · journal.
  - `queue.py`       — async queue: ALL writes enter here.
  - `writer.py`      — SINGLE writer -> DB; local embeddings on insert.
  - `embeddings.py`  — local embeddings client (Ollama embeddinggemma 768 · fastembed fallback).
  - `retriever.py`   — hot path: vec ∥ fts -> RRF -> weighted score -> graph_expand.
  - `state.py`       — fixed state table (µs read, no search).
  - `graph.py`       — edges (link/expand).
  - `episodic.py`    — files/PDF: searchable embedded summary + lazy binary load.
  - `consolidator.py`— "sleep" job: compression/dedup/conflicts/decay/eviction.
  - `api.py`         — public facade (write/query/state/reinforce/pin/unpin/link/load_episode/consolidate).

Data: `memory/_data/zaelar.db` (gitignored). Override through `ZAELAR_DB`.
"""
