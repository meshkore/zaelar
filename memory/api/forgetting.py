"""Forgetting at the operator's request, its exact undo, and the reset's two soft wipes (the conversational
buffer and a slot prefix). All SOFT (`valid=0`, kept for audit) unless `forget(hard=True)`."""
from .. import db as _db
from .. import writer as _writer
from ..clock import now as _clock_now
from .events import _emit

# Stopwords (articles/prepositions/POSSESSIVES) ignored when performing GRANULAR forgetting by content tokens:
# the operator says "forget my car's license plate" but the CORE stores "your car's license plate" → a contiguous
# LIKE fails because of the possessive. The token-AND fallback compares only content tokens (license plate, car).
_FORGET_STOP = {
    "de", "del", "la", "el", "los", "las", "un", "una", "unos", "unas", "lo", "que", "te", "me", "se",
    "mi", "mis", "tu", "tus", "su", "sus", "nuestro", "vuestra", "esa", "ese", "eso", "esta", "este", "esto",
    "en", "con", "por", "para", "sobre", "como", "más", "muy", "ya", "no",
    "todo", "toda", "todos", "todas", "cosa", "cosas",   # "forget EVERYTHING about X" = BROAD forgetting of X
}


def forget(match: str, *, hard: bool = False, include_pinned: bool = False) -> int:
    """FORGETTING AT THE OPERATOR'S REQUEST («forget the gift»). Invalidates (soft, `valid=0`) the VALID memories
    whose text contains `match` (case-insensitive): gone from recall, kept for AUDIT («what did I ask you to
    forget?»). `hard=True` really deletes (irreversible). `pinned` untouchable unless `include_pinned=True`. Direct
    (no queue: the operator expects the effect now). Returns the count; emits memory.updated."""
    m = (match or "").strip()
    if not m:
        return 0
    db = _db.get_db()
    like = f"%{m.lower()}%"
    pin_clause = "" if include_pinned else "AND pinned=0"
    rows = db.query(f"SELECT id FROM memories WHERE valid=1 {pin_clause} AND lower(text) LIKE ?", (like,))
    ids = {r["id"] for r in rows}
    # The CONTENT-TOKEN match is always UNITED with the contiguous one (not a fallback): the writer canonicalises
    # possessives and drops articles, so the contiguous LIKE matches only one variant and the canonical pill would
    # SURVIVE. Requiring ALL tokens (AND) avoids over-deleting.
    import re as _re
    toks = [t for t in _re.findall(r"\w+", m.lower()) if len(t) >= 3 and t not in _FORGET_STOP]
    if toks:
        clause = " AND ".join("lower(text) LIKE ?" for _ in toks)
        rows = db.query(f"SELECT id FROM memories WHERE valid=1 {pin_clause} AND {clause}",
                        tuple(f"%{t}%" for t in toks))
        ids |= {r["id"] for r in rows}
    if not ids:
        return 0
    ids = list(ids)
    ph = ",".join("?" * len(ids))
    now = _clock_now()
    if hard:
        # DELEGATES to writer.delete_memory: a plain DELETE on the external-content `fts_memories` left the tokens
        # matchable (and extractable — a broken privacy promise). It deletes FTS WITH the text first (+vec +edges).
        for mid in ids:
            _writer.delete_memory(mid)
    else:
        db.execute(f"UPDATE memories SET valid=0, updated=?, invalidated_at=? WHERE id IN ({ph})",
                   (now, now, *ids))
    _emit("memory.updated", {"op": "forget", "ids": ids, "hard": hard})
    return len(ids)


def unforget(match: str, *, include_pinned: bool = False) -> int:
    """UNFORGET: reverses a SOFT forget («no, remember X again»). Restores (`valid=1`) the INVALIDATED memories whose
    text contains `match` — the exact counterpart of `forget()`. Only soft-forgotten rows (hard ones are gone).
    Direct, emits memory.updated. Returns the count."""
    m = (match or "").strip()
    if not m:
        return 0
    db = _db.get_db()
    like = f"%{m.lower()}%"
    pin_clause = "" if include_pinned else "AND pinned=0"
    rows = db.query(f"SELECT id FROM memories WHERE valid=0 {pin_clause} AND lower(text) LIKE ?", (like,))
    ids = {r["id"] for r in rows}
    # The token-AND UNION, SYMMETRIC with forget(): without it the canonical variant stayed forgotten.
    import re as _re
    toks = [t for t in _re.findall(r"\w+", m.lower()) if len(t) >= 3 and t not in _FORGET_STOP]
    if toks:
        clause = " AND ".join("lower(text) LIKE ?" for _ in toks)
        rows = db.query(f"SELECT id FROM memories WHERE valid=0 {pin_clause} AND {clause}",
                        tuple(f"%{t}%" for t in toks))
        ids |= {r["id"] for r in rows}
    if not ids:
        return 0
    ids = list(ids)
    ph = ",".join("?" * len(ids))
    now = _clock_now()
    # invalidated_at back to NULL: the row is current again, so a later `as_of()` must see it valid from now.
    db.execute(f"UPDATE memories SET valid=1, updated=?, invalidated_at=NULL WHERE id IN ({ph})", (now, *ids))
    # ⚠️ Flipping `valid` is NOT enough for a row `consolidator.prune_invalid` already pruned OUT of the indexes
    # (vector + FTS deleted, `meta.pruned=1`): revived as-is no search could surface it. Re-add its FTS row here
    # (recall works at once through the keyword half), mark `embed_pending` for the nightly vector repair, and
    # drop the stamp. ONLY pruned rows: re-inserting FTS for an indexed row duplicates it (FTS5 has no upsert).
    import json as _json
    for r in db.query(f"SELECT id, text, meta FROM memories WHERE id IN ({ph})", tuple(ids)):
        try:
            meta = _json.loads(r["meta"] or "{}")
            if meta.pop("pruned", None) is None:
                continue
            meta["embed_pending"] = "revived"
            with db.cursor() as cur:
                cur.execute("INSERT INTO fts_memories (rowid, text) VALUES (?, ?)", (r["id"], r["text"]))
                cur.execute("UPDATE memories SET meta=? WHERE id=?",
                            (_json.dumps(meta, ensure_ascii=False), r["id"]))
        except Exception:  # noqa: BLE001
            continue
    _emit("memory.updated", {"op": "unforget", "ids": ids})
    return len(ids)


def clear_conversation() -> int:
    """Invalidates the VERBATIM conversational buffer (`level='short'`, `meta.source='conv'` — what
    `recent_window` reads and the voice provider re-seeds its window from after a reconnect).

    For the RESET: «the chat is erased» must include the seed, or the wiped conversation walks back in through the
    re-seeded window. SOFT (`valid=0`), forget doctrine. Touches ONLY conv records — facts, profile, triaged
    messages and worker results survive."""
    db = _db.get_db()
    rows = db.query("SELECT id FROM memories WHERE valid=1 AND level='short' "
                    "AND json_extract(meta,'$.source')='conv'")
    ids = [r["id"] for r in rows]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    db.execute(f"UPDATE memories SET valid=0, updated=? WHERE id IN ({ph})", (_clock_now(), *ids))
    _emit("memory.updated", {"op": "clear_conversation", "n": len(ids)})
    return len(ids)


def clear_slot_prefix(prefix: str) -> int:
    """Invalidates every pill whose SLOT starts with `prefix` (soft, `valid=0` — audit keeps them). The write
    twin of `by_slot_prefix`, with the same LIKE escaping (slots carry `_` naturally; unescaped, `task.` would
    also match `taskX`). Born for the reset wiping `task.*` — the durable «we are in the middle of X» pills.
    Generic on purpose: any namespaced catalogue can be retired by its prefix."""
    pref = (prefix or "").strip()
    if not pref:
        return 0
    db = _db.get_db()
    esc = pref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = db.query("SELECT id FROM memories WHERE valid=1 AND slot LIKE ? ESCAPE '\\'", (esc + "%",))
    ids = [r["id"] for r in rows]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    db.execute(f"UPDATE memories SET valid=0, updated=? WHERE id IN ({ph})", (_clock_now(), *ids))
    _emit("memory.updated", {"op": "clear_slot_prefix", "prefix": pref, "n": len(ids)})
    return len(ids)
