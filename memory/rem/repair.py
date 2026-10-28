"""REM phase 1 — vector repair: drop vectors from a foreign space, clear stale `embed_pending` markers, re-embed
pills without a vector, and SAY when the pass could not start or could not finish."""
from __future__ import annotations

import json
import os

from loguru import logger

from .. import db as _db
from .. import writer as _writer
from .common import _cos, _unpack

#: A stored vector IS the hash of its own text. Both sides are L2-normalised, so a genuine match is 1.0 exactly;
#: the margin is only there so float round-trips through `struct` cannot turn a match into a miss.
_FOREIGN_MATCH = 0.999

#: Consecutive rows whose embed fell back to the emergency hash before the pass gives up (V2-497). A degraded
#: backend is PROCESS-WIDE, so carrying on repeats the same failed call per row. Not 1: a saturated backend is
#: deliberately re-probed on the very next call, so a single blip must not end a pass that could still heal.
_DEGRADED_STREAK_STOP = 3


def _repair_limit_default() -> int:
    """Repair budget per sleep (§memory.rem_repair_limit, same pattern as `rem_every_hours`). A local, free job
    (no LLM): 200/day could not drain a backlog of hundreds (V2-103). Without config, 1000/sleep."""
    env = os.getenv("ZAELAR_REM_REPAIR_LIMIT")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    try:
        from config import v2 as _v2
        return max(1, int((_v2.get("memory") or {}).get("rem_repair_limit") or 1000))
    except Exception:
        return 1000


def _looks_padded(v: list[float]) -> bool:
    """Does this vector come from a SMALLER space, zero-padded up to the index dimension? (V2-485)

    `_fit_dim` pads with zeros, so trailing zeros half the vector long mean the producing model had at most half
    these dimensions (e.g. 384 non-zeros in a 768 index sealed for embeddinggemma = fastembed). This is the half
    the hash fingerprint cannot reach: a different REAL model is not reproducible from the text, but its SHAPE is.

    Deliberately coarse (`dim // 2`): a 512-dim model padded to 768 is NOT caught. Widening it would start
    guessing about vectors that are merely sparse, and a false positive throws away a good vector."""
    tail = 0
    for x in reversed(v):
        if x != 0.0:
            break
        tail += 1
    return tail >= len(v) // 2


def _drop_foreign_vectors(db, limit: int) -> int:
    """Delete vectors from a FOREIGN space (the HASH backend, or zero-padded) in an index sealed for a real
    embedding model (V2-482).

    `repair_embeddings` only looks for rows with NO vector (what the write guard leaves). A row whose foreign
    vector got past that guard HAS one, so it would never be repaired — and it is the worse half: noise fused into
    every RRF, invisible to the `embed_pending` count, and it can never be merged by `semantic_dedup` (whose
    threshold is calibrated on the real model), leaving live copies of one fact decaying alone.

    Only the hash space (and padding) is detectable, which is the point: hash is the emergency degradation target,
    so it is the space that leaks. A no-op when hash IS the sealed space, or when nothing is sealed. Marking
    `embed_pending` makes a failure to re-embed COUNTABLE in `hygiene()`.

    ⚠️ Dropping is only HALF an operation when the backend is down: the re-embed that follows may heal nothing
    (V2-497). The drop still stands (foreign noise is worse than an absence FTS covers), and `repair_embeddings`
    — not this pass — says what actually happened."""
    from .. import embeddings as _emb
    from .. import reembed as _reembed
    sealed = _reembed.stored_signature()
    if not sealed or sealed.startswith("hash:"):
        return 0
    # In an index sealed with fastembed a padded vector IS the native one: only the hash fingerprint counts there.
    padding_is_foreign = not sealed.startswith("fastembed:")
    rows = db.query(
        "SELECT m.id, m.text, v.embedding FROM memories m JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND m.kind NOT IN ('conv') LIMIT ?", (limit,))
    gone = 0
    por_clase = {"hash": 0, "rellenado": 0}
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        try:
            stored = _unpack(r["embedding"])
            hashed = _emb._l2_normalize(_emb._fit_dim(_emb._hash_embed(txt, len(stored)), len(stored)))
            es_hash = _cos(stored, hashed) >= _FOREIGN_MATCH
            if not es_hash and not (padding_is_foreign and _looks_padded(stored)):
                continue
            db.execute("DELETE FROM vec_memories WHERE memory_id=?", (r["id"],))
            _writer._mark_embed_pending(db, r["id"], "foreign_space")
            gone += 1
            por_clase["hash" if es_hash else "rellenado"] += 1
        except Exception:  # noqa: BLE001
            continue
    if gone:
        # The CLASS is broken down on purpose: a `hash` vector comes from a stale permission (V2-484) and a padded
        # one from an unguarded path (V2-485) — one label would send the next diagnosis to the wrong door.
        detalle = ", ".join(f"{n} {k}" for k, n in por_clase.items() if n)
        logger.warning(f"memoria: {gone} vectores de espacio ajeno ({detalle}) retirados de un índice "
                       f"«{sealed}» — quedan a la espera de re-embeberse (lo dice la fase de reparación)")
        try:
            from voice import health_state
            health_state.record("memory", "degraded",
                                f"{gone} vectores de otro espacio retirados del índice: el recall semántico "
                                f"estaba fusionando ruido en esas píldoras")
        except Exception:  # noqa: BLE001
            pass
    return gone


def _clear_stale_pending(db) -> int:
    """Drop `meta.embed_pending` from rows that already CARRY a vector (`reembed()` and direct inserts restore
    vectors without popping the marker).

    `repair_embeddings` only selects vector-LESS rows, so it can never reach these: the marker would be counted as
    pending forever — a permanently inflated number is a health signal nobody trusts. Runs AFTER
    `_drop_foreign_vectors` and behind the same signature gate, so any vector still standing here is native."""
    rows = db.query(
        "SELECT m.id, m.meta FROM memories m JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND json_extract(m.meta, '$.embed_pending') IS NOT NULL")
    cleared = 0
    for r in rows:
        try:
            meta = json.loads(r["meta"] or "{}")
            if meta.pop("embed_pending", None) is None:
                continue
            db.execute("UPDATE memories SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), r["id"]))
            cleared += 1
        except Exception:  # noqa: BLE001
            continue
    if cleared:
        logger.info(f"memory: {cleared} stale embed_pending markers cleared (their vectors already exist)")
    return cleared


def repair_embeddings(limit: int | None = None) -> int:
    """Re-embeds valid pills without a vector (or `meta.embed_pending`). Only when the active backend's signature
    matches the index (never repairs with vectors of another space). Returns the count repaired."""
    if limit is None:
        limit = _repair_limit_default()
    db = _db.get_db()
    # Each door says WHICH door it was: an exit that never reaches a row must not return a silent 0.
    if not db.vec_available:
        _report_repair_blocked(db, "sqlite-vec is not loaded: there is no vector index to repair into")
        return 0
    if not _writer._embed_sig_ok():
        _report_repair_blocked(db, "the active embedding backend is not the one that sealed the index")
        return 0
    # BEFORE the SELECT, never after: a foreign vector is exactly what hides its own row from it (V2-482).
    _drop_foreign_vectors(db, limit)
    _clear_stale_pending(db)
    from .. import embeddings as _emb
    rows = db.query(
        "SELECT m.id, m.text, m.meta FROM memories m LEFT JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND m.kind NOT IN ('conv') AND v.memory_id IS NULL LIMIT ?",
        (limit,),
    )
    fixed = 0
    degradadas = 0     # rows whose embed fell to the emergency hash: the real backend did not answer
    racha = 0
    for r in rows:
        try:
            vec = _emb.embed(r["text"])
            if getattr(_emb, "last_degraded", False):
                # backend fell to hash — better no vector than a vector from another space
                degradadas += 1
                racha += 1
                if racha >= _DEGRADED_STREAK_STOP:
                    break
                continue
            racha = 0
            # The signature is checked AGAIN, per row (V2-484): this is a loop, and a backend resolving to a
            # configured `hash` mid-way is not declared by `last_degraded` — the entry permission would still
            # stand, and the repair pass would write foreign vectors over the rows it just cleaned.
            if not _writer._embed_sig_ok():
                continue
            db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
                       (r["id"], _writer._pack(vec)))
            meta = json.loads(r["meta"] or "{}")
            if meta.pop("embed_pending", None) is not None:
                db.execute("UPDATE memories SET meta=? WHERE id=?",
                           (json.dumps(meta, ensure_ascii=False), r["id"]))
            fixed += 1
        except Exception:
            continue
    _report_repair_backlog(len(rows), fixed, degradadas)
    return fixed


def _pending_without_vector(db) -> int:
    """How many durable pills are waiting for a vector.

    Falls back to the whole durable set when the vector table itself cannot be read: with sqlite-vec absent
    every pill is waiting by definition, and a count that raised here would silence the very warning it was
    called to produce."""
    try:
        return db.query("SELECT COUNT(*) c FROM memories m LEFT JOIN vec_memories v ON v.memory_id = m.id "
                        "WHERE m.valid=1 AND m.kind NOT IN ('conv') AND v.memory_id IS NULL")[0]["c"]
    except Exception:  # noqa: BLE001
        try:
            return db.query("SELECT COUNT(*) c FROM memories WHERE valid=1 AND kind NOT IN ('conv')")[0]["c"]
        except Exception:  # noqa: BLE001
            return 0


def _report_repair_blocked(db, cause: str) -> None:
    """Say that the repair pass never even STARTED, and which door stopped it (V2-503).

    The entrance guards refuse correctly (repairing in a foreign space writes foreign vectors, V2-484), but their
    `return 0` was indistinguishable from a healthy machine with nothing to do. Silent when nothing is waiting.
    Never CLEARS the shared `memory` health key — that would wipe another piece's warning."""
    waiting = _pending_without_vector(db)
    if waiting <= 0:
        return
    logger.warning(f"memory: the sleep repair could not start — {waiting} pills are still without a vector: {cause}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded",
                            f"{waiting} pills without a vector: the repair pass could not start ({cause})")
    except Exception:  # noqa: BLE001
        pass


def _report_repair_backlog(esperando: int, reparadas: int, degradadas: int) -> None:
    """Say when the repair pass could NOT do its job (V2-497) — sibling of `_report_repair_blocked`.

    A returned 0 meant both «nothing was waiting» and «45 rows waited and the backend refused every one» (a
    saturated backend correctly DEFERS the vector; doing it silently, once a day, let damage sit indefinitely).
    Not cleared on a healthy pass: the `memory` health key is shared, so it ages out on its own TTL."""
    pendientes = esperando - reparadas
    if pendientes <= 0:
        return
    if degradadas:
        causa = (f"el backend de embeddings no contestó ({degradadas} caídas al hash de emergencia) — se "
                 f"difiere el vector para conservar el espacio; se reintenta en el próximo sueño")
    else:
        causa = "el permiso de escritura de vectores lo denegó la firma del índice, o el embed falló por fila"
    logger.warning(f"memoria: {pendientes} de {esperando} píldoras siguen SIN vector tras la reparación — {causa}")
    try:
        from voice import health_state
        health_state.record("memory", "degraded",
                            f"{pendientes} píldoras sin vector: la reparación del sueño no pudo re-embeberlas "
                            f"({'backend de embeddings caído o saturado' if degradadas else 'firma del índice'})")
    except Exception:  # noqa: BLE001
        pass
