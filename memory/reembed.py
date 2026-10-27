"""memory/reembed.py — embedding-model signature + maintenance RE-EMBED (V2-030 · Phase 3).

El embedding es CONFIGURABLE (sección `memory.embed_provider/embed_model`, model-agnostic: local hoy, cloud
mañana). Pero los vectores de `vec_memories` viven en el ESPACIO del modelo que los creó: si se cambia de modelo
(o de dimensión) SIN reconstruirlos, el retriever compara la query (modelo nuevo) contra vectores (modelo viejo)
→ recall roto EN SILENCIO. Este módulo es la red de seguridad:

  - `signature()`      — huella del backend+modelo+dim en uso ahora mismo.
  - `stored_signature()` / `stamp()` — la huella con la que se indexó la BD (sidecar `<db>.embedsig`).
  - `check()`          — compara; si NO casa y ya hay vectores, AVISA fuerte (nunca mezclar espacios). Off-hot-path.
  - `reembed()`        — recalcula TODOS los vectores con el backend actual; si cambió la dim, recrea `vec_memories`.
                         Job de MANTENIMIENTO (no hot path). Tras correrlo, re-sella la firma.

  - `migrate()`        — THE ONE DOOR for a change of embedding model (V2-824): re-embeds every pill AND every
                         paraphrase in the new space, reseals the signature, clears the stale `embed_pending`
                         markers and verifies no foreign vector is left. Fired by the panel (`server/config_api.py`
                         when `memory.embed_*` changes) and by `config/profiles.apply` (local ↔ cloud).

Nothing migrates on its own: `check()` runs at boot to WARN, and an existing database keeps its sealed space until
the user changes the model on purpose. A boot that finds the signatures apart is a misconfiguration to say out
loud (a missing key demotes the backend, and migrating INTO a fallback space would be the V2-103 defect on
purpose), never a reason to rewrite the memory.
"""
from __future__ import annotations

import logging
import time as _t

from . import db as _db
from . import embeddings as _emb
from . import schema as _schema
from . import writer as _writer

logger = logging.getLogger("zaelar.memory.reembed")


def _sig_path():
    return _db.db_path().with_suffix(_db.db_path().suffix + ".embedsig")


def signature() -> str:
    """ACTIVE embedding fingerprint: backend + model + dimension. Changing any invalidates the vectors."""
    backend = _emb.active_backend()
    model = _emb._active_model_name() if backend != "hash" else "hash"
    return f"{backend}:{model or backend}:{_emb.dim()}"


def stored_signature() -> str | None:
    p = _sig_path()
    try:
        return p.read_text(encoding="utf-8").strip() if p.exists() else None
    except Exception:
        return None


def stamp(sig: str | None = None) -> None:
    """Stamp the signature used to index the database (after a fresh insert or a re-embed)."""
    try:
        _sig_path().write_text(sig or signature(), encoding="utf-8")
    except Exception as e:
        logger.debug("could not stamp the embedding signature: %s", e)


def _vec_count() -> int:
    db = _db.get_db()
    if not db.vec_available:
        return 0
    try:
        return db.query_one("SELECT COUNT(*) c FROM vec_memories")["c"]
    except Exception:
        return 0


#: (instante, veredicto, backend con el que se calculó). El BACKEND forma parte de la clave, no es un
#: adorno: el veredicto es sobre el espacio ACTIVO, así que sobrevivir a un cambio de backend es servir
#: la respuesta de otra pregunta (V2-484).
_SPACE_CACHE: tuple[float, bool, object] = (0.0, True, None)


def space_ok(ttl: float = 60.0) -> bool:
    """Does the ACTIVE embedding space match the one the DB is indexed with? Cached for `ttl` seconds because
    both the write path (per insert) and the READ path (per recall) consult it.

    FAIL-OPEN by design: no stored signature (a fresh DB, or one from before V2-030) or any error means "assume
    coherent" — this must never be the reason a read returns nothing.

    Why it lives here and not in `writer.py` (where it started, 2026-08-18): the writer already refused to insert
    a vector on a mismatch (`_mark_embed_pending`, V2-103), but the READER had no equivalent check and would
    happily embed the query in the WRONG space and fuse pure noise into the RRF. Two callers, one question, so
    one cached answer — two independent 60s caches of the same predicate would have drifted apart exactly when it
    mattered, during the window where one of them is wrong.

    THE BACKEND IS PART OF THE KEY (V2-484). Time alone was not enough: the verdict is about the ACTIVE space,
    and for up to `ttl` seconds after the backend changed this returned the verdict for the PREVIOUS one. That
    is the fail-open the 15 foreign vectors in the operator's live index came through — reproduced end to end:
    warm the cache while Ollama answers, let the backend fall to hash seconds later (Ollama busy AND fastembed
    not loaded), and `insert_memory` stores a literal `_hash_embed` into an index sealed
    `ollama:embeddinggemma:768`, with `embed_pending` unset, so nothing downstream can tell it happened.

    The backend is read RAW off the module rather than through `active_backend()`, on purpose: that accessor
    resolves, and resolving can probe. A guard consulted on every insert and every recall must not be able to
    put a network call in front of them."""
    global _SPACE_CACHE
    now = _t.time()
    backend = getattr(_emb, "_backend", None)
    if now - _SPACE_CACHE[0] < ttl and _SPACE_CACHE[2] == backend:
        return _SPACE_CACHE[1]
    try:
        stored = stored_signature()
        ok = stored is None or stored == signature()
    except Exception:  # noqa: BLE001
        ok = True
    _SPACE_CACHE = (now, ok, backend)
    return ok


def check() -> dict:
    """Compare the active and stamped signatures. If they differ and vectors exist, issue a strong warning
    (recall is at risk). If vectors exist without a stamp (a pre-V2-030 database), stamp the current one
    (assuming consistency). Off-hot-path."""
    cur = signature()
    stored = stored_signature()
    n = _vec_count()
    if stored is None:
        if n:
            stamp(cur)          # BD heredada: asumimos que los vectores son de este modelo; sella para futuras.
        return {"ok": True, "signature": cur, "stored": None, "vectors": n, "action": "stamped_legacy" if n else "none"}
    if stored != cur and n:
        logger.warning("⚠️ memoria: el modelo de embedding CAMBIÓ (%s → %s) pero hay %d vectores del modelo viejo. "
                       "El recall semántico está en RIESGO hasta re-indexar. Corre `python -m memory.reembed`.",
                       stored, cur, n)
        return {"ok": False, "signature": cur, "stored": stored, "vectors": n, "action": "reembed_needed"}
    return {"ok": True, "signature": cur, "stored": stored, "vectors": n, "action": "none"}


def reembed(batch: int = 128) -> dict:
    """Recompute ALL vectors with the CURRENT backend. If the dimension changed, recreate `vec_memories`.
    MAINTENANCE job (slow, off-hot-path). Returns a report and re-stamps the signature when finished."""
    db = _db.get_db()
    if not db.vec_available:
        return {"ok": False, "reason": "sqlite-vec no disponible"}
    rows = db.query("SELECT id, text FROM memories WHERE valid=1")
    total = len(rows)
    logger.info("re-embed: %d recuerdos con %s…", total, signature())

    # dimensión nueva → recrear la tabla vec con la dim del embedding ACTIVO (provider-driven, V2-031).
    db.execute("DROP TABLE IF EXISTS vec_memories")
    db.execute(_schema.vec_memories_ddl(_emb.dim()))

    done = 0
    for i in range(0, total, batch):
        chunk = rows[i:i + batch]
        vecs = _emb.embed_batch([r["text"] for r in chunk])
        # A DEGRADED RE-EMBED IS WORSE THAN NO RE-EMBED (2026-08-30). `embed_batch` never fails to return
        # vectors: if the titular does not answer it falls back to hashing and says so in `last_degraded`.
        # Without this stop the loop put LEXICAL vectors into the semantic index and then stamped the cloud
        # provider's signature over them — leaving the database lying about its own space, which is precisely
        # what the seal exists to prevent. It stops WITHOUT stamping: the old signature stays, `check()` keeps
        # warning, and the job can simply be run again.
        if _emb.last_degraded:
            logger.error("re-embed ABORTED at %d/%d: the embedding backend is degraded — the signature is NOT "
                         "sealed and the vector table is left incomplete. Fix the credential and re-run.",
                         done, total)
            return {"ok": False, "reason": "backend degraded halfway through the re-embed",
                    "reindexed": done, "total": total}
        for r, v in zip(chunk, vecs):
            try:
                db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)",
                           (r["id"], _writer._pack(v)))
                done += 1
            except Exception as e:
                logger.debug("re-embed: fallo en id=%s: %s", r["id"], e)
                # COUNTABLE, not silent: the row stays without a vector and REM's repair pass picks it up.
                _writer._mark_embed_pending(db, r["id"], "migration")
    paraphrases = _reembed_paraphrases(db, batch)
    if paraphrases.get("ok") is False:
        return {"ok": False, "reason": paraphrases.get("reason"), "reindexed": done, "total": total}
    stamp()
    logger.info("re-embed OK: %d/%d vectores reindexados (+%d paráfrasis)", done, total, paraphrases.get("reindexed", 0))
    return {"ok": True, "reindexed": done, "total": total, "paraphrases": paraphrases.get("reindexed", 0),
            "signature": signature()}


def _reembed_paraphrases(db, batch: int = 128) -> dict:
    """The paraphrase channel lives in ITS OWN vector table (`vec_paraphrases`, V2-031 T2) and the old re-embed
    left it in the previous model's space — a third of the RRF fusing foreign vectors after every migration.
    Same contract as the pill loop: abort WITHOUT stamping if the backend degrades."""
    try:
        rows = db.query("SELECT id, text FROM paraphrase_index")
    except Exception:  # noqa: BLE001
        return {"ok": True, "reindexed": 0}
    db.execute("DROP TABLE IF EXISTS vec_paraphrases")
    db.execute(_schema.vec_paraphrases_ddl(_emb.dim()))
    done = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        vecs = _emb.embed_batch([r["text"] for r in chunk])
        if _emb.last_degraded:
            logger.error("re-embed ABORTED on the paraphrases at %d/%d: backend degraded — not sealed", done, len(rows))
            return {"ok": False, "reason": "backend degraded while re-embedding the paraphrases", "reindexed": done}
        for r, v in zip(chunk, vecs):
            try:
                db.execute("INSERT INTO vec_paraphrases (id, embedding) VALUES (?, ?)", (r["id"], _writer._pack(v)))
                done += 1
            except Exception as e:  # noqa: BLE001
                logger.debug("re-embed: paraphrase %s failed: %s", r["id"], e)
    return {"ok": True, "reindexed": done}


def _forget_space_verdicts() -> None:
    """A migration moves the space, so every cached answer about it is stale: the backend resolution in
    `embeddings` (so the NEW config resolves) and the `space_ok()` verdict both callers consult."""
    global _SPACE_CACHE
    _emb.reset()
    _SPACE_CACHE = (0.0, True, None)


def migration_needed() -> dict:
    """Pure check, no side effect beyond resolving the backend: does the ACTIVE space differ from the sealed one
    while vectors exist? `check()` says the same thing with a warning; this one is for a caller deciding."""
    cur, stored, n = signature(), stored_signature(), _vec_count()
    return {"needed": bool(stored and stored != cur and n), "signature": cur, "stored": stored, "vectors": n}


def migrate(*, reason: str = "") -> dict:
    """Changing the embedding model is a MIGRATION, not a failover (V2-824). This is the one door.

    Steps, in order: forget the cached verdicts → compare the active signature with the sealed one → when they
    differ and vectors exist, `reembed()` (drops and recreates BOTH vector tables, so nothing from the old space
    can survive by construction), then clear the `embed_pending` markers of rows that now carry a vector, then
    count what is still foreign (`rem._drop_foreign_vectors`, which must find nothing). A database with no
    vectors is only stamped. Same signature → nothing to do.

    A degraded backend ABORTS without stamping (`reembed()` already does) — the old seal stays, the writer keeps
    deferring and `check()` keeps warning, which is the honest state: half a migration is worse than none."""
    _forget_space_verdicts()
    need = migration_needed()
    cur, stored, n = need["signature"], need["stored"], need["vectors"]
    report: dict = {"ok": True, "from": stored, "to": cur, "vectors": n, "reason": reason}
    if stored == cur:
        report["action"] = "none"
        return report
    if not n:
        stamp(cur)
        _forget_space_verdicts()
        report["action"] = "stamped"
        return report
    logger.warning("memoria: MIGRACIÓN del espacio de embeddings %s → %s (%d vectores) — %s", stored, cur, n, reason)
    rep = reembed()
    report.update({k: rep.get(k) for k in ("reindexed", "total", "paraphrases", "reason") if k in rep})
    if not rep.get("ok"):
        report.update({"ok": False, "action": "aborted"})
        _report(report)
        return report
    _forget_space_verdicts()
    db = _db.get_db()
    from . import rem as _rem
    report["pending_cleared"] = _rem._clear_stale_pending(db)
    report["foreign_left"] = _rem._drop_foreign_vectors(db, 1_000_000)
    report["action"] = "migrated"
    report["ok"] = report["foreign_left"] == 0
    _report(report)
    return report


def _report(report: dict) -> None:
    """Say it where the operator looks: the log, the bus and the health light (amber only when it went wrong)."""
    logger.info("memoria: migración de embeddings → %s", report)
    try:
        import bus
        bus.emit_sync("memory.reembed", dict(report))
    except Exception as e:  # noqa: BLE001
        logger.debug("migration report: bus emit failed: %s", e)
    if not report.get("ok"):
        try:
            from voice import health_state
            health_state.record("memory", "degraded",
                                f"embedding migration {report.get('from')} → {report.get('to')} did not finish: "
                                f"{report.get('reason') or report.get('action')} — the old space is still sealed")
        except Exception as e:  # noqa: BLE001
            logger.debug("migration report: health light failed: %s", e)


if __name__ == "__main__":  # `python -m memory.reembed` → the migration door, by hand (`--force` = re-embed anyway)
    import json
    import sys
    if "--force" in sys.argv:
        print(json.dumps(reembed(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps(migrate(reason="manual"), ensure_ascii=False, indent=2))
