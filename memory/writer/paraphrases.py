"""The write-time PARAPHRASE index (V2-031 T2): index a durable pill's rephrasings, and drop them with the pill."""
from .. import db as _db
from .policy import _now, _pack


def drop_paraphrases(memory_id: int) -> int:
    """Delete a memory's paraphrase rows AND their vectors. Returns how many were removed.

    Two defects, not hygiene:
      1. **Right to be forgotten.** A hard delete that leaves the text VERBATIM in `paraphrase_index.text` would
         make «deleted» false in the one place it must not be — a paraphrase is a rewrite of the operator's datum.
      2. **Orphans that keep matching.** `vec_paraphrases` is keyed by the synthetic PK, so a deleted memory's
         vectors would keep winning KNN slots for a `memory_id` that no longer exists — silently spending pool
         budget («recall got worse» months later).
    Both hard-delete paths (`writer.delete_memory`, `consolidator`'s eviction) call this — there is no third."""
    if not memory_id:
        return 0
    db = _db.get_db()
    try:
        rows = db.query("SELECT id FROM paraphrase_index WHERE memory_id=?", (int(memory_id),))
    except Exception:  # noqa: BLE001
        return 0        # table absent (a DB from before the channel existed) — nothing to clean
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
    """V2-031 T2: indexes 1-2 REPHRASINGS of a durable pill — closes the vocabulary gap («instrument» in the query,
    «guitar» in the datum) with no LLM on the read. In its OWN tables (`paraphrase_index` + `vec_paraphrases`,
    synthetic PK), never `vec_memories` (one vector per `memory_id`). The retriever fuses them into RRF mapped back
    to the real `memory_id`; they are never results themselves nor count for dedup. Off the hot path (called from
    `memory/rem/`). Fail-open: a degraded backend → 0 indexed."""
    if not memory_id or not texts:
        return 0
    from .. import embeddings as _emb
    if getattr(_emb, "last_degraded", False):
        return 0  # same rule as repair_embeddings(): better no vector than one in the wrong space
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
                break  # degraded mid-batch → stop, never mix vector spaces
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
