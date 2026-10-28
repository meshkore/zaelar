"""The writer's small mutations: reinforce, link, pin, supersede, demote what an insight summarises, delete,
the `embed_pending` marker, and a spoken correction reaching the slotless pill it corrects."""
import json

from loguru import logger

from .. import db as _db
from .paraphrases import drop_paraphrases
from .policy import _now

# reinforcement by use: each access raises the weight by this step (capped at 1.0) and RESETS recency.
REINFORCE_STEP = 0.1


def reinforce(ids: list[int], step: float = REINFORCE_STEP) -> None:
    """Reinforcement by use: access_count++, last_access=now, weight=min(1, weight+step). Access resets decay."""
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
    """Creates/updates a graph edge (idempotent by the PK (from_id, to_id, type))."""
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
    """The half of REM consolidation that was missing (V2-103): once a group is summarised into ONE insight, its raw
    pills stop competing at full weight. Multiplies `weight` by `factor` (floored at `floor`; access_count /
    last_access untouched, so natural decay continues) and stamps `meta.summarized_by`. **NEVER invalidates or
    deletes** — `valid`/`superseded_by` intact; `pinned` never touched. Returns the count demoted."""
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


def supersede(old_id: int, new_id: int) -> None:
    """Marks a memory as superseded by another (temporal conflict; the consolidator uses it too)."""
    db = _db.get_db()
    now = _now()
    db.execute(
        "UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? WHERE id=?",
        (int(new_id), now, now, int(old_id)),
    )


def delete_memory(mid: int) -> None:
    """Deletes a memory and its representations (vec/fts). Only the consolidator (and a hard forget) call this."""
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
            # External FTS5: explicit delete with the 'delete' syntax. ⚠️ A row already retired by
            # `consolidator.prune_invalid` (meta.pruned=1) must NOT get it again: repeating the special `delete`
            # on that rowid corrupts the FTS5 index (`database disk image is malformed`).
            cur.execute(
                "INSERT INTO fts_memories (fts_memories, rowid, text) VALUES ('delete', ?, ?)",
                (mid, row["text"]),
            )
        cur.execute("DELETE FROM memories WHERE id=?", (mid,))
        cur.execute("DELETE FROM edges WHERE from_id=? OR to_id=?", (mid, mid))
    if db.vec_available:
        db.execute("DELETE FROM vec_memories WHERE memory_id=?", (mid,))
    drop_paraphrases(mid)


def _mark_embed_pending(db, mid: int, reason: str) -> None:
    try:
        row = db.query_one("SELECT meta FROM memories WHERE id=?", (mid,))
        meta = json.loads(row["meta"] or "{}") if row else {}
        meta["embed_pending"] = reason
        db.execute("UPDATE memories SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), mid))
    except Exception:
        pass


def _apply_correction_supersedes(db, survivor_id: int, targets: list[int] | None, now: int) -> None:
    """A spoken correction reaches the pill it corrects (V2-565).

    The distiller may name, in `supersedes`, ids of recently written SLOTLESS pills the turn corrects — ids it was
    OFFERED, never invented: the ingest pipeline intersects them with `api.correction_targets()` first. Without it
    nothing could reach a mis-heard name stored as slotless prefs, because every supersede path keys on `slot`.

    Applied at the single write chokepoint, for every caller and every dedup exit (the survivor, whichever it is,
    becomes the successor). Guards live HERE: slotless targets only (identity/state unreachable by construction),
    currently valid, never the survivor itself, capped. Reversible: `valid=0` + `superseded_by`, never deleted."""
    for old in (targets or [])[:4]:
        try:
            old = int(old)
        except (TypeError, ValueError):
            continue
        if old == int(survivor_id):
            continue
        row = db.query_one("SELECT id FROM memories WHERE id=? AND valid=1 AND slot IS NULL "
                           "AND kind != 'conv'", (old,))
        if row is None:
            # Unknown, already invalid, slotted or conv → refused. Quiet on purpose: the ingest whitelist
            # already filtered, so a miss here is a benign race (the target got superseded in between).
            continue
        db.execute("UPDATE memories SET valid=0, superseded_by=?, updated=?, invalidated_at=? WHERE id=?",
                   (int(survivor_id), now, now, old))
        logger.info(f"memoria: corrección aplicada — #{old} queda superseded por #{survivor_id} (V2-565)")
