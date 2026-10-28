"""REM phase 2 — SEMANTIC dedup, with no LLM: cosine over the vectors already paid for."""
from __future__ import annotations

import os

from .. import db as _db
from .. import writer as _writer
from .common import _NUM_RE, _cos, _now, _unpack

# CALIBRATED on the real DB: paraphrase echoes of one task score 0.82-0.90 on embeddinggemma (0.92 merged
# NOTHING). 0.86 + the conflicting-numbers guard (different figures/dates never merge) is the balance.
SEM_DEDUP_THRESHOLD = float(os.getenv("ZAELAR_REM_DEDUP_SIM", "0.86"))


def _conflicting_numbers(a: str, b: str) -> bool:
    """Two texts with DIFFERENT figures/dates are DIFFERENT facts even when the embedding sees them as near-equal
    ('dentist on Monday 3' vs 'dentist on Thursday 12') → never merge. Without figures in one of them there is no
    conflict (the one that has them is the more informative version)."""
    na, nb = set(_NUM_RE.findall(a)), set(_NUM_RE.findall(b))
    return bool(na and nb and na != nb)


def _sim_table(ids: list[int], vecs: dict[int, list[float]]):
    """One similarity lookup for the O(n²) scan in `semantic_dedup`. With numpy the whole table is a single float32
    matmul that RELEASES the GIL (~70 ms); the per-pair pure-Python dot product held the GIL for the whole scan
    (~28 s of stutter at `cap` 1500 inside the live process). The pure-Python fallback keeps the module working
    without numpy; any shape surprise (mixed dimensions) falls back too."""
    try:
        import numpy as np
        m = np.array([vecs[i] for i in ids], dtype=np.float32)
        s = m @ m.T
        pos = {mid: k for k, mid in enumerate(ids)}
        return lambda a, b: float(s[pos[a], pos[b]])
    except Exception:  # noqa: BLE001
        return lambda a, b: _cos(vecs[a], vecs[b])


def semantic_dedup(threshold: float = SEM_DEDUP_THRESHOLD, cap: int = 1500) -> int:
    """Merges near-identical durables by MEANING: echoes of one fact said N ways collapse into the heaviest; the
    rest become `valid=0, superseded_by` (history intact; light sleep prunes them from the indexes). ONLY slotless
    rows (slotted ones supersede exactly), never pinned over pinned, never critical kinds. `trust: untrusted` rows
    are OUT in both directions: an untrusted echo never invalidates a trusted pill and its shell never inherits a
    trusted lineage's edges (the same filter `_concept_groups` applies). O(n²) bounded by `cap`, one matmul."""
    db = _db.get_db()
    if not db.vec_available:
        return 0
    rows = db.query(
        "SELECT m.id, m.text, m.weight, m.access_count, m.pinned, m.kind, v.embedding FROM memories m "
        "JOIN vec_memories v ON v.memory_id = m.id "
        "WHERE m.valid=1 AND m.slot IS NULL AND m.level IN ('mid','long') "
        "AND m.kind NOT IN ('conv','concept','insight') "
        "AND (m.meta IS NULL OR m.meta NOT LIKE '%\"trust\": \"untrusted\"%') ORDER BY m.id DESC LIMIT ?",
        (cap,),
    )
    vecs = {r["id"]: _unpack(r["embedding"]) for r in rows}
    by_id = {r["id"]: r for r in rows}
    ids = sorted(vecs.keys())
    sim = _sim_table(ids, vecs)
    merged = 0
    gone: set[int] = set()
    for i, a in enumerate(ids):
        if a in gone:
            continue
        for b in ids[i + 1:]:
            if b in gone:
                continue
            if sim(a, b) < threshold:
                continue
            ra, rb = by_id[a], by_id[b]
            if _conflicting_numbers(ra["text"], rb["text"]):
                continue           # different figures/dates = different facts, not echoes
            # keep the "best" (pinned > weight > accesses > most recent)
            keep, drop = (ra, rb) if (ra["pinned"], ra["weight"], ra["access_count"], ra["id"]) >= \
                                     (rb["pinned"], rb["weight"], rb["access_count"], rb["id"]) else (rb, ra)
            if drop["pinned"]:
                continue           # never invalidate a pinned in favour of another
            with db.cursor() as cur:
                cur.execute("UPDATE OR IGNORE edges SET from_id=? WHERE from_id=?", (keep["id"], drop["id"]))
                cur.execute("UPDATE OR IGNORE edges SET to_id=? WHERE to_id=?", (keep["id"], drop["id"]))
                _now_ts = _now()
                cur.execute("UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? WHERE id=?",
                            (keep["id"], _now_ts, _now_ts, drop["id"]))
            _writer.reinforce([keep["id"]], step=0.0)
            gone.add(drop["id"])
            merged += 1
    return merged
