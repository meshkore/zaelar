"""Documentation translated to English."""
import json
import os
import re
import struct

from . import db as _db
from . import embeddings as _emb

# translated implementation note
REINFORCE_STEP = 0.1

# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# perder un dato.
SEMANTIC_DEDUP_MAX_DIST = float(os.getenv("MEM_DEDUP_MAX_DIST", "0.45"))
_SEMANTIC_DEDUP_CALIBRATED_BACKENDS = {"ollama"}   # translated implementation note


def _semantic_dedup_on() -> bool:
    if os.getenv("MEM_SEMANTIC_DEDUP", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    return _emb.active_backend() in _SEMANTIC_DEDUP_CALIBRATED_BACKENDS


_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    """Documentation translated to English."""
    return _WS.sub(" ", (text or "").strip().lower())


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_CRITICAL_HEALTH_RE = re.compile(
    r"\b(al[eé]rgic[oa]s?|alergia|anafila|intoleran(?:te|cia)|"
    r"allerg(?:ic|y)|intoleran(?:t|ce)|"
    r"celiac[oa]|cel[íi]ac[oa]|diab[eé]tic[oa]|diabetes|epil[eé]p|marcapasos|anticoagul|"
    r"asm[aá]tic[oa])\b", re.I)


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
#
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
_INGESTION_LIMIT_RE = re.compile(
    r"(?:\bno\s+(?:puede[ns]?|puedo|debe[ns]?|debo)\s+(?:comer|tomar|beber|ingerir|probar|consumir)\b"
    r"|\b(?:can(?:no|')?t|cannot|must\s+not|mustn'?t)\s+(?:eat|drink|have|take|consume)\b)", re.I)

# translated implementation note
_MOMENTARY_RE = re.compile(
    r"\b(hoy|ahora\s+mismo|ahora|esta\s+noche|este\s+rato|luego|m[aá]s\s+tarde|"
    r"today|tonight|right\s+now|later)\b", re.I)


def _is_critical_health(text: str) -> bool:
    t = text or ""
    if _CRITICAL_HEALTH_RE.search(t):
        return True
    return bool(_INGESTION_LIMIT_RE.search(t)) and not _MOMENTARY_RE.search(t)


def _stamp_critical(meta):
    """Marca meta.critical='health' preservando lo que hubiera (dict/JSON/None)."""
    if isinstance(meta, dict):
        return {**meta, "critical": "health"}
    if isinstance(meta, str) and meta.strip():
        try:
            d = json.loads(meta)
            if isinstance(d, dict):
                d["critical"] = "health"
                return d
        except Exception:
            pass
        return meta
    return {"critical": "health"}

# translated implementation note
_IMPORTANCE_BY_KIND = {
    "fact": 0.7,
    "pref": 0.7,
    "insight": 0.65,
    "summary": 0.55,
    "event": 0.5,
    "msg": 0.4,
}


def _now() -> int:
    from .clock import now
    return now()


def _pack(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# translated implementation note
# capas ya no pueden divergir). Slots desconocidos/namespaced pasan lowercased/stripped.
from . import slots as _slots


def canon_slot(slot: str | None) -> str | None:
    """Documentation translated to English."""
    return _slots.canonical(slot)


def insert_memory(
    text: str,
    *,
    level: str = "short",
    kind: str = "event",
    importance: float | None = None,
    weight: float = 0.5,
    ttl_days: float | None = None,
    pinned: bool = False,
    slot: str | None = None,
    meta: dict | str | None = None,
    concepts: list[str] | None = None,
    embedding: list[float] | None = None,
) -> int:
    """Documentation translated to English."""
    db = _db.get_db()
    now = _now()
    if importance is None:
        importance = _IMPORTANCE_BY_KIND.get(kind, 0.5)

    slot = canon_slot(slot)                     # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    if _is_critical_health(text):
        if slot in _slots.identity_slots():
            slot = None
        pinned = True
        importance = max(float(importance), 0.95)
        meta = _stamp_critical(meta)
    meta_json = meta if isinstance(meta, (str, type(None))) else json.dumps(meta, ensure_ascii=False)
    prev_ids: list[int] = []
    if slot:
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        _keys = _slots.equivalent_keys(slot) or [slot]
        _ph = ",".join("?" * len(_keys))
        rows = db.query(
            f"SELECT id, text FROM memories WHERE slot IN ({_ph}) AND valid=1 ORDER BY updated DESC, id DESC",
            tuple(_keys))
        if rows:
            if _norm(rows[0]["text"]) == _norm(text):
                keep = int(rows[0]["id"])
                reinforce([keep])               # translated implementation note
                _link_concepts(db, keep, concepts, level, kind)  # asegura aristas del grafo (idempotente)
                stale = [int(r["id"]) for r in rows[1:]]
                if stale:                       # translated implementation note
                    ph = ",".join("?" * len(stale))
                    db.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                               f"WHERE id IN ({ph})", (keep, now, now, *stale))
                return keep
            prev_ids = [int(r["id"]) for r in rows]   # translated implementation note

    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    if not slot and kind != "conv":
        exact = db.query_one(
            "SELECT id FROM memories WHERE valid=1 AND kind != 'conv' AND LOWER(text)=LOWER(?) "
            "ORDER BY id DESC LIMIT 1",
            (text,),
        )
        if exact is not None:
            dup_id = int(exact["id"])
            reinforce([dup_id])
            _link_concepts(db, dup_id, concepts, level, kind)
            return dup_id

    # translated implementation note
    # translated implementation note
    if not slot and level in ("mid", "long") and db.vec_available and _semantic_dedup_on():
        if embedding is None:
            embedding = _emb.embed(text)
        dup = _find_semantic_dup(db, embedding)
        if dup is not None:
            reinforce([dup])
            _link_concepts(db, dup, concepts, level, kind)   # translated implementation note
            return dup

    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO memories (level, kind, text, importance, weight, access_count,
                                     last_access, ttl_days, pinned, valid, slot, meta, created, updated, valid_at)
               VALUES (?,?,?,?,?,0,?,?,?,1,?,?,?,?,?)""",
            (level, kind, text, float(importance), float(weight), now,
             ttl_days, 1 if pinned else 0, slot, meta_json, now, now, now),
        )
        mid = cur.lastrowid
        # FTS5 externo (content='memories'): mantener a mano, rowid = id del recuerdo.
        if db.fts_available:
            cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (mid, text))
        if prev_ids:                            # translated implementation note
            ph = ",".join("?" * len(prev_ids))
            cur.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                        f"WHERE id IN ({ph})", (mid, now, now, *prev_ids))
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    # translated implementation note
    if db.vec_available and kind != "conv":
        pending_reason = None
        if not _embed_sig_ok():
            pending_reason = "sig_mismatch"
            vec = None
        else:
            vec = embedding if embedding is not None else _emb.embed(text)
            if embedding is None and getattr(_emb, "last_degraded", False):
                pending_reason = "degraded"
                vec = None
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            elif embedding is None and not _embed_sig_ok():
                pending_reason = "sig_mismatch"
                vec = None
        if vec is not None:
            try:
                db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", (mid, _pack(vec)))
            except Exception:
                pending_reason = "insert_failed"   # translated implementation note
        if pending_reason is not None:
            _mark_embed_pending(db, mid, pending_reason)

    _link_concepts(db, mid, concepts, level, kind)
    return mid


# The raw utterance as a second retrieval path (V2-031 T2 / V2-114 F4.2) was BUILT, MEASURED and REMOVED on
# 2026-08-19. Kept as an epitaph rather than silence, so nobody proposes it a third time without the numbers.
#
# The hypothesis was reasonable and came from a real measurement: on LoCoMo, distilling beats raw dialogue at
# multi-hop (+12.6pp) and open-domain (+15.4pp) and LOSES at temporal (-8.1pp) and single-hop (-2.8pp), because
# an answer that IS the literal wording of one turn does not survive being canonicalised. So: keep the pill as
# translated implementation note
#
# It lost on BOTH corpora, and on LoCoMo it lost precisely where it was supposed to win:
#
#   our corpus (tape A/B, 603 durables, 269 queries, identical corpus in both arms)
#     off  recall@1 69.8%  @3 85.9%  @5 89.7%  @10 92.4%  MRR .780  lat p50 533ms  DB 3.6MB
#     on   recall@1 68.3%  @3 85.9%  @5 88.9%  @10 91.6%  MRR .772  lat p50 787ms  DB 6.8MB
#
#   LoCoMo conv-0, distilled, 199 questions      overall  multi  temporal  open  single  adversarial
#     off                                         48.2%   43.8%   70.3%   38.5%  62.9%     14.9%
#     on                                          46.7%   37.5%   70.3%   38.5%  55.7%     23.4%
#
# translated implementation note
# +48% read latency at p50 and ~2x the database, and "reading must be maximum speed" is a hard invariant (V2-013).
# Why it fails: the raw utterance is a NOISIER copy of the pill, so a query can match the wording of the WRONG
# pill and inject a false positive into the fusion, while doubling the rows a brute-force KNN scans.
#
# The one real gain, and where it actually points: adversarial +8.5pp. That category is our WRITE-COMPLETENESS
# hole (63.8% of its questions get "NO INFORMATION AVAILABLE" from the answerer vs ~16% elsewhere), so literal
# material helps there only because the distiller dropped the fact in the first place. The fix that indicates is
# writing the fact properly, not indexing everything twice to paper over it.
#
# NOTE: `index_paraphrases`/`drop_paraphrases` STAY. That channel carries REM-generated paraphrases, it was
# verified working (F4.3, after being mute since it was built), and it is a different mechanism from this one.


def _embed_sig_ok() -> bool:
    """Does the ACTIVE backend's signature match the one stamped on the index?

    Delegates to `reembed.space_ok()` (2026-08-18): the READ path needs the same predicate, and keeping two
    independent 60s caches of one question meant they could disagree during precisely the window where one of
    them is wrong. Kept as a named function because it is the writer's vocabulary for it and it reads better at
    the call site than the module hop."""
    try:
        from . import reembed as _reembed
        return _reembed.space_ok()
    except Exception:  # noqa: BLE001
        return True     # fail-open: with no verdict, vector writes are not blocked


def _mark_embed_pending(db, mid: int, reason: str) -> None:
    try:
        row = db.query_one("SELECT meta FROM memories WHERE id=?", (mid,))
        meta = json.loads(row["meta"] or "{}") if row else {}
        meta["embed_pending"] = reason
        db.execute("UPDATE memories SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), mid))
    except Exception:
        pass


def _link_concepts(db, mid: int, concepts: list[str] | None, level: str, kind: str) -> None:
    """Documentation translated to English."""
    if level not in ("mid", "long") or kind == "concept":
        return
    cs = [c for c in (concepts or []) if c]
    if not cs:
        # translated implementation note
        # translated implementation note
        # translated implementation note
        # translated implementation note
        try:
            from memory.concepts import derive_concepts
            row = db.query_one("SELECT text FROM memories WHERE id=?", (mid,))
            cs = derive_concepts(row["text"]) if row and row["text"] else []
        except Exception:
            cs = []
    for c in list(cs)[:3]:
        cid = _get_or_create_concept(db, c)
        if cid and cid != mid:
            link(mid, cid, "about", 1.0)
            link(cid, mid, "about", 1.0)         # translated implementation note


def _get_or_create_concept(db, name: str) -> int | None:
    """Documentation translated to English."""
    n = _norm(name).strip()
    if not n:
        return None
    try:
        row = db.query_one(
            "SELECT id FROM memories WHERE kind='concept' AND valid=1 AND lower(text)=? LIMIT 1", (n,)
        )
        if row is not None:
            return int(row["id"])
        now = _now()
        with db.cursor() as cur:
            cur.execute(
                """INSERT INTO memories (level, kind, text, importance, weight, access_count,
                                         last_access, ttl_days, pinned, valid, slot, meta, created, updated, valid_at)
                   VALUES (?, 'concept', ?, 0.3, 0.5, 0, ?, NULL, 1, 1, NULL, NULL, ?, ?, ?)""",
                ("long", n, now, now, now, now),
            )
            cid = cur.lastrowid
            if db.fts_available:
                cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (cid, n))
        if db.vec_available:
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            # translated implementation note
            vec = _emb.embed(n)
            if getattr(_emb, "last_degraded", False):
                _mark_embed_pending(db, cid, "degraded")
            elif not _embed_sig_ok():
                _mark_embed_pending(db, cid, "sig_mismatch")
            else:
                db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", (cid, _pack(vec)))
        return int(cid)
    except Exception:
        return None


def _find_semantic_dup(db, vec: list[float]) -> int | None:
    """Documentation translated to English."""
    try:
        rows = db.query(
            "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 5",
            (_pack(vec),),
        )
    except Exception:
        return None
    for r in rows:
        if r["distance"] is None or r["distance"] > SEMANTIC_DEDUP_MAX_DIST:
            break                               # translated implementation note
        m = db.query_one(
            "SELECT id FROM memories WHERE id=? AND valid=1 AND level IN ('mid','long')",
            (r["memory_id"],),
        )
        if m is not None:
            return int(m["id"])
    return None


def reinforce(ids: list[int], step: float = REINFORCE_STEP) -> None:
    """Documentation translated to English."""
    if not ids:
        return
    db = _db.get_db()
    now = _now()
    with db.cursor() as cur:
        for mid in ids:
            cur.execute(
                """UPDATE memories
                   SET access_count = access_count + 1,
                       last_access  = ?,
                       weight       = MIN(1.0, weight + ?),
                       updated      = ?
                   WHERE id = ?""",
                (now, float(step), now, int(mid)),
            )


def link(from_id: int, to_id: int, type: str, weight: float = 1.0) -> None:
    """Documentation translated to English."""
    db = _db.get_db()
    db.execute(
        "INSERT OR REPLACE INTO edges (from_id, to_id, type, weight) VALUES (?,?,?,?)",
        (int(from_id), int(to_id), str(type), float(weight)),
    )


def set_pinned(mid: int, pinned: bool) -> None:
    db = _db.get_db()
    db.execute(
        "UPDATE memories SET pinned=?, updated=? WHERE id=?",
        (1 if pinned else 0, _now(), int(mid)),
    )


def demote_summarized(ids: list[int], insight_id: int, factor: float = 0.6, floor: float = 0.05) -> int:
    """Documentation translated to English."""
    if not ids:
        return 0
    db = _db.get_db()
    now = _now()
    done = 0
    with db.cursor() as cur:
        for mid in ids:
            row = cur.execute("SELECT weight, pinned, meta FROM memories WHERE id=?", (int(mid),)).fetchone()
            if row is None or row["pinned"]:
                continue
            new_weight = max(float(floor), float(row["weight"]) * float(factor))
            try:
                meta = json.loads(row["meta"] or "{}")
            except Exception:
                meta = {}
            meta["summarized_by"] = int(insight_id)
            cur.execute(
                "UPDATE memories SET weight=?, meta=?, updated=? WHERE id=?",
                (new_weight, json.dumps(meta, ensure_ascii=False), now, int(mid)),
            )
            done += 1
    return done


def drop_paraphrases(memory_id: int) -> int:
    """Documentation translated to English."""
    if not memory_id:
        return 0
    db = _db.get_db()
    try:
        rows = db.query("SELECT id FROM paraphrase_index WHERE memory_id=?", (int(memory_id),))
    except Exception:  # noqa: BLE001
        return 0        # translated implementation note
    if not rows:
        return 0
    ids = [r["id"] for r in rows]
    try:
        with db.cursor() as cur:
            cur.execute("DELETE FROM paraphrase_index WHERE memory_id=?", (int(memory_id),))
        if db.vec_available:
            ph = ",".join("?" * len(ids))
            db.execute(f"DELETE FROM vec_paraphrases WHERE id IN ({ph})", tuple(ids))
    except Exception:  # noqa: BLE001
        return 0
    return len(ids)


def index_paraphrases(memory_id: int, texts: list[str]) -> int:
    """Documentation translated to English."""
    if not memory_id or not texts:
        return 0
    from . import embeddings as _emb
    if getattr(_emb, "last_degraded", False):
        return 0  # translated implementation note
    db = _db.get_db()
    now = _now()
    done = 0
    for text in texts:
        text = (text or "").strip()
        if not text:
            continue
        try:
            vec = _emb.embed(text)
            if getattr(_emb, "last_degraded", False):
                break  # translated implementation note
            with db.cursor() as cur:
                cur.execute(
                    "INSERT INTO paraphrase_index (memory_id, text, created) VALUES (?, ?, ?)",
                    (int(memory_id), text, now),
                )
                pid = cur.lastrowid
                cur.execute(
                    "INSERT INTO vec_paraphrases (id, embedding) VALUES (?, ?)",
                    (pid, _pack(vec)),
                )
            done += 1
        except Exception:
            continue
    return done


def supersede(old_id: int, new_id: int) -> None:
    """Documentation translated to English."""
    db = _db.get_db()
    now = _now()
    db.execute(
        "UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? WHERE id=?",
        (int(new_id), now, now, int(old_id)),
    )


def delete_memory(mid: int) -> None:
    """Documentation translated to English."""
    import json as _json

    db = _db.get_db()
    mid = int(mid)
    row = db.query_one("SELECT text, meta FROM memories WHERE id=?", (mid,))
    already_pruned = False
    if row is not None:
        try:
            already_pruned = bool(_json.loads(row["meta"] or "{}").get("pruned"))
        except Exception:
            already_pruned = False
    with db.cursor() as cur:
        if db.fts_available and row is not None and not already_pruned:
            # translated implementation note
            # translated implementation note
            # consolidator.prune_invalid(meta.pruned=1). Repetir el comando
            # translated implementation note
            # (`database disk image is malformed`) durante una eviction posterior.
            cur.execute(
                "INSERT INTO fts_memories (fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                (mid, row["text"]),
            )
        cur.execute("DELETE FROM memories WHERE id=?", (mid,))
        cur.execute("DELETE FROM edges WHERE from_id=? OR to_id=?", (mid, mid))
    if db.vec_available:
        db.execute("DELETE FROM vec_memories WHERE memory_id=?", (mid,))
    drop_paraphrases(mid)


# operaciones despachables desde la cola: op -> callable
OPS = {
    "write": insert_memory,
    "reinforce": reinforce,
    "link": link,
    "pin": lambda mid: set_pinned(mid, True),
    "unpin": lambda mid: set_pinned(mid, False),
    "supersede": supersede,
    "delete": delete_memory,
    "demote_summarized": demote_summarized,
}
