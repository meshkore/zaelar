"""memory/writer — the ONE writer of the memory (V2-002 · T45).

Every DB mutation passes through here, invoked only by the consumer of `memory/queue.py` (one consumer → zero write
collisions; readers use WAL without blocking). Each insert computes its embedding (`memory/embeddings`) and syncs
three representations: the `memories` row, the vector in `vec_memories` (if sqlite-vec is available) and the
keyword index `fts_memories` (FTS5 with `content='memories'` → an external index kept by hand). Functions are
SYNCHRONOUS on `db.get_db()` (serialised by its RLock); ordering comes from the queue.

⚠️ `insert_memory` and the guards it calls (`_embed_sig_ok`, `_find_semantic_dup`, the concept nodes) live HERE:
tests patch them on `memory.writer` and expect `insert_memory` to see the patch, which only holds while caller and
callee share this module's globals. The rest:
  policy.py       dedup calibration, normalisation, critical-health detector, importance, slots, clock, packing
  ops.py          reinforce / link / pin / supersede / demote / delete, the pending marker, spoken corrections
  paraphrases.py  the write-time paraphrase index
"""
import json

from .. import db as _db
from .. import embeddings as _emb
from .. import slots as _slots
from .ops import (  # noqa: F401
    REINFORCE_STEP, _apply_correction_supersedes, _mark_embed_pending, delete_memory, demote_summarized, link,
    reinforce, set_pinned, supersede)
from .paraphrases import drop_paraphrases, index_paraphrases  # noqa: F401
from .policy import (  # noqa: F401
    _CRITICAL_HEALTH_RE, _IMPORTANCE_BY_KIND, _INGESTION_LIMIT_RE, _MOMENTARY_RE, _SEMANTIC_DEDUP_CALIBRATED_BACKENDS,
    SEMANTIC_DEDUP_MAX_DIST, _is_critical_health, _norm, _now, _pack, _semantic_dedup_on, _stamp_critical,
    canon_slot)


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
    supersedes: list[int] | None = None,
) -> int:
    """Inserts a memory (PILL: canonical datum + `slot` + `meta`) + its vector + its FTS row. Returns the id.

    **Supersede/dedup by SLOT (V2-013, exact, no LLM)**: given `slot` (canonical key of a singular fact, e.g.
    `operator.name`), the CURRENT memory with that slot is checked:
      - same normalised text → the same datum repeated: `reinforce` it, no duplicate; returns the existing id.
      - different → the fact changed: insert the new one and mark the old `valid=0, superseded_by=new`
        («the latest RULES»).
    Computes the embedding when none is passed."""
    db = _db.get_db()
    now = _now()
    if importance is None:
        importance = _IMPORTANCE_BY_KIND.get(kind, 0.5)

    slot = canon_slot(slot)                     # one slot language (LLM alias → canonical)
    # MEDICAL SAFETY GUARD: an allergy/intolerance NEVER keeps a SINGULAR (identity) slot — a later datum of the
    # same slot would erase it. The slot is dropped (it stays ADDITIVE), it is pinned with high importance, and
    # meta.critical='health' makes the STATE surface it ALWAYS (outside salient_long's cap).
    if _is_critical_health(text):
        if slot in _slots.identity_slots():
            slot = None
        pinned = True
        importance = max(float(importance), 0.95)
        meta = _stamp_critical(meta)
    meta_json = meta if isinstance(meta, (str, type(None))) else json.dumps(meta, ensure_ascii=False)
    # The TRUST CLASS is part of a fact's identity for both dedup doors below: by text alone an untrusted write
    # could REINFORCE a trusted pill, or fold a trusted write INTO a quarantined row that synthesis and by_concepts
    # never see. Slots are not gated here: `remember_external` vets which slots an untrusted writer may touch.
    try:
        _trust = (json.loads(meta_json).get("trust") or "") if meta_json else ""
    except Exception:  # noqa: BLE001
        _trust = ""
    prev_ids: list[int] = []
    if slot:
        # ALL current rows of the slot (not LIMIT 1), expanded by ALIAS: if 2+ current rows of one singular fact
        # coexist (an old unnormalised alias, unforget, legacy), the NEXT write collapses them all — self-healing,
        # without waiting for the consolidator's `heal_slots`. Tie-break by id: `updated` has 1 s resolution.
        _keys = _slots.equivalent_keys(slot) or [slot]
        _ph = ",".join("?" * len(_keys))
        rows = db.query(
            f"SELECT id, text FROM memories WHERE slot IN ({_ph}) AND valid=1 ORDER BY updated DESC, id DESC",
            tuple(_keys))
        if rows:
            if _norm(rows[0]["text"]) == _norm(text):
                keep = int(rows[0]["id"])
                reinforce([keep])               # same datum → reinforce, no duplicate
                _link_concepts(db, keep, concepts, level, kind)  # ensures the graph edges (idempotent)
                stale = [int(r["id"]) for r in rows[1:]]
                if stale:                       # lagging duplicates of the same slot → collapse them anyway
                    ph = ",".join("?" * len(stale))
                    db.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                               f"WHERE id IN ({ph})", (keep, now, now, *stale))
                _apply_correction_supersedes(db, keep, supersedes, now)
                return keep
            prev_ids = [int(r["id"]) for r in rows]   # datum changed → supersede ALL current rows after inserting

    # EXACT dedup on write (V2-103): durable + slotless → the SAME text (case-normalised) already current is
    # reinforced instead of duplicated. Independent of the embedding backend (never fails silently); the SEMANTIC
    # dedup below still covers paraphrases. `conv` is out on purpose: the buffer may repeat «sí»/«vale» verbatim.
    if not slot and kind != "conv":
        exact = db.query_one(
            "SELECT id FROM memories WHERE valid=1 AND kind != 'conv' AND LOWER(text)=LOWER(?) "
            "AND COALESCE(json_extract(meta, '$.trust'), '') = ? ORDER BY id DESC LIMIT 1",
            (text, _trust),
        )
        if exact is not None:
            dup_id = int(exact["id"])
            reinforce([dup_id])
            _link_concepts(db, dup_id, concepts, level, kind)
            _apply_correction_supersedes(db, dup_id, supersedes, now)
            return dup_id

    # SEMANTIC dedup (T125): durable + slotless → a near-identical memory by MEANING is reinforced instead of
    # duplicated. Reuses the computed embedding.
    if not slot and level in ("mid", "long") and db.vec_available and _semantic_dedup_on():
        if embedding is None:
            embedding = _emb.embed(text)
        dup = _find_semantic_dup(db, embedding, trust=_trust)
        if dup is not None:
            reinforce([dup])
            _link_concepts(db, dup, concepts, level, kind)   # the repeated fact keeps/gains its concept edges
            _apply_correction_supersedes(db, dup, supersedes, now)
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
        # External FTS5 (content='memories'): kept by hand, rowid = the memory's id.
        if db.fts_available:
            cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (mid, text))
        if prev_ids:                            # EVERY current fact with this slot becomes superseded
            ph = ",".join("?" * len(prev_ids))
            cur.execute(f"UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? "
                        f"WHERE id IN ({ph})", (mid, now, now, *prev_ids))
    _apply_correction_supersedes(db, mid, supersedes, now)
    # The embedding is computed outside the cursor's write lock (it can be slow), then a short vec insert.
    # The CONVERSATIONAL buffer (`kind='conv'`, every turn, TTL 2d) is NOT embedded: it is read by recency, never
    # by vector, and embedding it cost a GPU call per turn. `consolidator.promote` excludes it so a conv never ends
    # up durable without a vector.
    # VECTOR-SPACE ENFORCEMENT: never insert a vector from ANOTHER space — a mismatched signature (same dim, zero
    # errors, corrupted recall) or a live degradation to hash. The pill stays WITHOUT a vector and gets
    # `meta.embed_pending` (FTS still finds it; the sleep re-embeds it). ⚠️ The marker's value is the REASON, a
    # string (`"sig_mismatch"`, `"degraded"`…) — NEVER 1: `embed_pending = 1` returns ZERO on a contaminated DB.
    # Query it as the product does: `IS NOT NULL`.
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
            # The SECOND check DECIDES (V2-484). The first runs before the vector exists, but the backend is
            # resolved INSIDE `_emb.embed()`: it can fall to a CONFIGURED `hash` there, which `last_degraded`
            # deliberately does not flag — the two guards would defer to each other and none would hold. The
            # first check only saves paying for an embedding that would be thrown away.
            elif embedding is None and not _embed_sig_ok():
                pending_reason = "sig_mismatch"
                vec = None
        if vec is not None:
            try:
                db.execute("INSERT INTO vec_memories (memory_id, embedding) VALUES (?, ?)", (mid, _pack(vec)))
            except Exception:
                pending_reason = "insert_failed"   # pill committed without a vector → repairable, not orphaned
        if pending_reason is not None:
            _mark_embed_pending(db, mid, pending_reason)

    _link_concepts(db, mid, concepts, level, kind)
    return mid


# The raw utterance as a second retrieval path (V2-114 F4.2) was BUILT, MEASURED and REMOVED: it LOST on our corpus
# and LoCoMo (single-hop −7.2pp, temporal ±0) at +48% read p50 and ~2x the DB. Not again without new numbers; the
# paraphrase index is a DIFFERENT, working mechanism.


def _embed_sig_ok() -> bool:
    """Does the ACTIVE backend's signature match the one stamped on the index? Delegates to `reembed.space_ok()`:
    the READ path asks the same question, and two independent caches of it could disagree."""
    try:
        from .. import reembed as _reembed
        return _reembed.space_ok()
    except Exception:  # noqa: BLE001
        return True     # fail-open: with no verdict, vector writes are not blocked


def _link_concepts(db, mid: int, concepts: list[str] | None, level: str, kind: str) -> None:
    """CONCEPT GRAPH (V2-013 T126): creates/reuses a CONCEPT node (kind='concept', findable by FTS/vector) and links
    pill↔concept both ways in `edges`, so a category query matches the node and `graph_expand` surfaces the cluster
    — no LLM. IDEMPOTENT: also called when a repeated fact is reinforced, so an untagged fact gains its edges. Cap 3."""
    if level not in ("mid", "long") or kind == "concept":
        return
    cs = [c for c in (concepts or []) if c]
    if not cs:
        # The LLM sometimes OMITS `concepts`, leaving a durable pill unreachable by a category query. DETERMINISTIC
        # backstop: derive them from the TEXT (the same `derive_concepts` the rest of the system uses).
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
            link(cid, mid, "about", 1.0)         # both ways → graph_expand from the node brings the pills


def _get_or_create_concept(db, name: str) -> int | None:
    """A SINGLETON concept node per name (kind='concept', a graph hub). Reuses the existing one (by normalised text)
    or creates it with its FTS row + vector so a category query finds it. No slot (supersede would kill it) and no
    semantic dedup (it must not merge with a pill). Best-effort → None on failure."""
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
            # The SAME gate as a pill (V2-484): this path once inserted vectors with no check at all (padded
            # fastembed vectors, all on concept nodes). The node is created anyway (a hub `_link_concepts` needs);
            # only its VECTOR is deferred, marked so `repair_embeddings` recovers it and `hygiene()` counts it.
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


def _find_semantic_dup(db, vec: list[float], trust: str = "") -> int | None:
    """The nearest DURABLE valid memory by MEANING: its id if the distance ≤ threshold, else None. Best-effort: any
    vector-backend failure → None (a normal insert). Only within the SAME trust class: an untrusted near-duplicate
    never reinforces a trusted lineage, nor the reverse."""
    try:
        rows = db.query(
            "SELECT memory_id, distance FROM vec_memories WHERE embedding MATCH ? ORDER BY distance LIMIT 5",
            (_pack(vec),),
        )
    except Exception:
        return None
    for r in rows:
        if r["distance"] is None or r["distance"] > SEMANTIC_DEDUP_MAX_DIST:
            break                               # ordered by distance: if the best misses, all do
        m = db.query_one(
            "SELECT id FROM memories WHERE id=? AND valid=1 AND level IN ('mid','long') "
            "AND COALESCE(json_extract(meta, '$.trust'), '') = ?",
            (r["memory_id"], trust),
        )
        if m is not None:
            return int(m["id"])
    return None


# operations the queue can dispatch: op -> callable
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
