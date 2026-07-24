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
