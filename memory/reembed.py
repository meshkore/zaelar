"""memory/reembed.py — firma del modelo de embedding + RE-EMBED de mantenimiento (V2-030 · Fase 3).

El embedding es CONFIGURABLE (sección `memory.embed_provider/embed_model`, model-agnostic: local hoy, cloud
mañana). Pero los vectores de `vec_memories` viven en el ESPACIO del modelo que los creó: si se cambia de modelo
(o de dimensión) SIN reconstruirlos, el retriever compara la query (modelo nuevo) contra vectores (modelo viejo)
→ recall roto EN SILENCIO. Este módulo es la red de seguridad:

  - `signature()`      — huella del backend+modelo+dim en uso ahora mismo.
  - `stored_signature()` / `stamp()` — la huella con la que se indexó la BD (sidecar `<db>.embedsig`).
  - `check()`          — compara; si NO casa y ya hay vectores, AVISA fuerte (nunca mezclar espacios). Off-hot-path.
  - `reembed()`        — recalcula TODOS los vectores con el backend actual; si cambió la dim, recrea `vec_memories`.
                         Job de MANTENIMIENTO (no hot path). Tras correrlo, re-sella la firma.

No se dispara re-embed automático (decisión del ciclo V2-030: solo abstracción + reranker). `check()` se llama en
el arranque para AVISAR; el operador/dev corre `reembed()` a conciencia cuando cambia el modelo.
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
    """Huella del embedding ACTIVO: backend + modelo + dimensión. Cambiar cualquiera invalida los vectores."""
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
    """Sella la firma con la que está indexada la BD (tras insertar de cero o tras un re-embed)."""
    try:
        _sig_path().write_text(sig or signature(), encoding="utf-8")
    except Exception as e:
        logger.debug("no se pudo sellar la firma de embedding: %s", e)


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
    """Compara la firma activa con la sellada. Si difieren y HAY vectores → aviso fuerte (recall en riesgo). Si no
    hay firma sellada pero hay vectores (BD previa a V2-030), la sella con la actual (asume coherente). Off-hot-path."""
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
    """Recalcula TODOS los vectores con el backend ACTUAL. Si cambió la dimensión, recrea `vec_memories`. Job de
    MANTENIMIENTO (lento, off-hot-path). Devuelve un informe. Tras terminar, re-sella la firma."""
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
    stamp()
    logger.info("re-embed OK: %d/%d vectores reindexados", done, total)
    return {"ok": True, "reindexed": done, "total": total, "signature": signature()}


if __name__ == "__main__":  # `python -m memory.reembed` → re-embed manual de mantenimiento
    import json
    print(json.dumps(reembed(), ensure_ascii=False, indent=2))
