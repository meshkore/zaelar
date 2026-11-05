"""memory/history.py — where a remembered line CAME FROM, and the conversation record as a source (V2-802/V2-803).

Two reads, both direct SQL (no model, no embedding), both declared on the facade (`memory.api`):

  · `provenance(ids)` — for rows a recall returned: when each was written, at what level, of what kind, and from
    which source (`meta.source`: voice, a worker, whatsapp, email, conv…) and entity. A recall that only says
    «- text» cannot tell an inbound marketing email from a fact the operator dictated, so whoever reads it
    cannot say «it is on record» honestly (V2-802 failure 6).

  · `conversation(hours, query)` — the operator's own past conversation, verbatim, for a time window and/or a
    query: each line with its timestamp and who said it. This is the ONE reader for «what did I tell you
    yesterday» (V2-803 T-01/T-02); recall only sees the pills extraction chose to keep, and extraction can miss.

Why the conversation buffer (`kind='conv'`) and not the bus `events` log: the `transcript` events carry EVERY
final STT line, including ambient speech that was never addressed to zaelar (a TV in the room), and nothing on
the event itself says which lines were turns. The `conv` row is written once per turn the brain actually
answered (`turn_after.py`), with the operator's words and the reply as structured fields (`meta.u`/`meta.a`).
What it lacks is a work-session id; the transport layer adds that from observability (`server/memory_routes.py`),
so this module keeps reading only its own table. Its reach is the buffer's TTL (2 days today) — retention as a
declared setting is V2-803 T-03, not this reader.
"""
from __future__ import annotations

import json
from datetime import datetime

from . import db as _db
from .clock import now as _clock_now

#: The widest window `conversation()` accepts, in hours. The buffer itself keeps less; this only bounds a caller.
MAX_HOURS = 24.0 * 30
#: Lane names a provenance row is labelled with — the same three a recall can be filtered by.
LANE_MEMORY = "memory"
LANE_CONVERSATION = "conversation"
LANE_MESSAGE = "message"


def iso(ts) -> str:
    """Epoch seconds → local ISO time to the minute ('' when unknown)."""
    try:
        t = float(ts)
    except (TypeError, ValueError):
        t = None
    if t is None or t <= 0:
        return ""
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="minutes")


def _meta(raw) -> dict:
    m: dict = {}
    if raw:
        try:
            m = json.loads(raw) or {}
        except (TypeError, ValueError):
            m = {"_unreadable": True}
    return m if isinstance(m, dict) else {}


def lane_of(kind: str | None) -> str:
    """Which lane a row belongs to, by its kind — the same split `retriever.LANE_*` searches by."""
    if kind == "msg":
        return LANE_MESSAGE
    if kind == "conv":
        return LANE_CONVERSATION
    return LANE_MEMORY


def provenance(ids) -> dict[int, dict]:
    """{id: {id, created, created_ts, level, kind, slot, source, entity, lane}} for the given row ids.

    `created` is local ISO time; `source` is `meta.source` as the writer stamped it (None when the row predates
    the stamp — said as unknown, never guessed)."""
    want = [int(i) for i in (ids or []) if str(i).lstrip("-").isdigit()]
    if not want:
        return {}
    ph = ",".join("?" * len(want))
    rows = _db.get_db().query(
        f"SELECT id, created, level, kind, slot, meta FROM memories WHERE id IN ({ph})", tuple(want))
    out: dict[int, dict] = {}
    for r in rows:
        m = _meta(r["meta"])
        out[int(r["id"])] = {
            "id": int(r["id"]), "created": iso(r["created"]), "created_ts": r["created"], "level": r["level"],
            "kind": r["kind"], "slot": r["slot"] or "", "source": m.get("source"), "entity": m.get("entity"),
            "contact_id": m.get("contact_id"),   # V2-854 F3: the contact this row is about, when the writer knew it
            "lane": lane_of(r["kind"]),
        }
    return out


def _matching_conv_ids(query: str, since: int) -> set[int] | None:
    """Conversation rows in the window that match `query` through the SAME lexical channel recall uses (FTS5 with
    the retriever's stemming). None = the query carries no searchable term (read the whole window instead)."""
    from .retriever import _fts_query
    q = _fts_query(query or "")
    if not q:
        return None
    db = _db.get_db()
    if db.fts_available:
        rows = db.query(
            "SELECT m.id AS id FROM fts_memories f JOIN memories m ON m.id = f.rowid "
            "WHERE fts_memories MATCH ? AND m.kind='conv' AND m.valid=1 AND m.created >= ?", (q, since))
        return {int(r["id"]) for r in rows}
    # No FTS on this build: plain containment over the same terms, so the reader still answers.
    terms = [t.strip('"').rstrip("*").lower() for t in q.split(" OR ")]
    rows = db.query("SELECT id, text FROM memories WHERE kind='conv' AND valid=1 AND created >= ?", (since,))
    return {int(r["id"]) for r in rows if any(t and t in (r["text"] or "").lower() for t in terms)}


def conversation(hours: float = 24.0, query: str = "", limit: int = 40, max_chars: int = 6000) -> list[dict]:
    """The operator's own past conversation, VERBATIM, oldest first: `[{id, ts, at, who, text}]` where `who` is
    'operator' or 'assistant' and `at` is local ISO time.

    Bounded twice — by `hours` (clamped to `MAX_HOURS`) and by size (`limit` turns, `max_chars`); when the bound
    bites, the NEWEST turns are the ones kept. With a `query`, only turns matching it (lexically, as recall does)
    are returned; a query with no match returns [] — «not found» is an answer. Only valid rows: a reset that
    cleared the conversation (`clear_conversation`) stays cleared here too."""
    try:
        h = float(hours)
    except (TypeError, ValueError):
        h = 24.0
    h = min(max(h, 0.0), MAX_HOURS) or 24.0
    since = int(_clock_now() - h * 3600)
    match = _matching_conv_ids(query, since) if (query or "").strip() else None
    if match is not None and not match:
        return []
    rows = _db.get_db().query(
        "SELECT id, text, meta, created FROM memories WHERE kind='conv' AND valid=1 AND created >= ? "
        "ORDER BY created DESC, id DESC", (since,))
    picked: list[tuple] = []
    used = 0
    for r in rows:                                     # newest → oldest; trimmed, then reversed
        if match is not None and int(r["id"]) not in match:
            continue
        m = _meta(r["meta"])
        u, a = (m.get("u") or "").strip(), (m.get("a") or "").strip()
        if not u and not a:                            # an old row without structured fields: its text as is
            u = (r["text"] or "").strip()
        seg = len(u) + len(a)
        if picked and (used + seg > max_chars or len(picked) >= int(limit)):
            break
        picked.append((int(r["id"]), r["created"], u, a))
        used += seg
    out: list[dict] = []
    for mid, ts, u, a in reversed(picked):
        if u:
            out.append({"id": mid, "ts": ts, "at": iso(ts), "who": "operator", "text": u})
        if a:
            out.append({"id": mid, "ts": ts, "at": iso(ts), "who": "assistant", "text": a})
    return out
