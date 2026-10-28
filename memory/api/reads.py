"""Direct reads with no retriever and no model: by source, by concept, by slot prefix, the bounded snapshot
(`map`), and the background-slot rule every surface that shows pills to a model applies."""
import re

from .. import db as _db
from .. import state as _state
from .. import viewer

_SLOT_WORD_MIN = 4

#: Rows per layer `map()` returns at most (V2-808). The viewer reads `memory/viewer.py`; this stays for the
#: callers that want a snapshot of state + the newest pills (test probes, the loop cycle), and is bounded too.
MAP_CAP = 500


def recent_by_source(source: str | None = None, entity: str | None = None, limit: int = 20,
                     max_chars: int = 2000) -> list[dict]:
    """DIRECT READ by INDEXED TYPE (µs, no LLM): the newest inbound data (`kind='msg'`) from a SOURCE — optionally
    from one ENTITY — via `json_extract` on `meta.source`/`meta.entity`. «What came in on WhatsApp?» without the
    retriever; N connectors only change `source`. `source=None` → everything inbound. Returns
    [{id,text,source,entity,trust,created,level}], newest first. Tolerates an empty DB."""
    db = _db.get_db()
    where = ["valid=1", "kind='msg'"]
    params: list = []
    if source:
        where.append("json_extract(meta,'$.source')=?"); params.append(source)
    if entity:
        # pylower = Unicode lower (SQLite lower() is ASCII-only and would not match 'Álvaro' with its .lower())
        where.append("pylower(json_extract(meta,'$.entity'))=?"); params.append(str(entity).lower())
    params.append(int(limit))
    rows = db.query(f"SELECT id, text, meta, created, level FROM memories WHERE {' AND '.join(where)} "
                    f"ORDER BY updated DESC, id DESC LIMIT ?", tuple(params))
    out, used = [], 0
    for r in rows:
        txt = (r["text"] or "").strip()
        if not txt:
            continue
        if used + len(txt) > max_chars and out:
            break
        try:
            import json as _json
            m = _json.loads(r["meta"]) if r["meta"] else {}
        except Exception:
            m = {}
        out.append({"id": r["id"], "text": txt, "source": m.get("source"), "entity": m.get("entity"),
                    "trust": m.get("trust"), "created": r["created"], "level": r["level"]})
        used += len(txt)
    return out


def by_concepts(concepts: list[str], *, limit: int = 6) -> list[dict]:
    """CONCEPT-BASED READ (T126 graph, no LLM): DURABLE facts linked to `concepts` through pill↔concept edges. For
    aggregation by category («what trips have I made?») and implicit cross-topic application (a «restaurant»
    surfaces «coeliac» through the shared concept). Respects valid + QUARANTINE (untrusted out), excludes concept
    nodes, orders by weight/importance. Returns [{id,text,level,kind,weight,importance}]."""
    names = [(c or "").strip().lower() for c in (concepts or []) if (c or "").strip()]
    if not names:
        return []
    db = _db.get_db()
    ph = ",".join("?" * len(names))
    cids = [r["id"] for r in db.query(
        f"SELECT id FROM memories WHERE kind='concept' AND valid=1 AND lower(text) IN ({ph})", tuple(names))]
    if not cids:
        return []
    ph2 = ",".join("?" * len(cids))
    rows = db.query(
        f"""SELECT m.id, m.text, m.level, m.kind, m.weight, m.importance
            FROM edges e JOIN memories m ON m.id = e.to_id
            WHERE e.from_id IN ({ph2}) AND e.type='about'
              AND m.valid=1 AND m.kind != 'concept' AND m.level IN ('mid','long')
              AND (json_extract(m.meta,'$.trust') IS NULL OR json_extract(m.meta,'$.trust') != 'untrusted')
            GROUP BY m.id
            ORDER BY m.weight DESC, m.importance DESC
            LIMIT ?""", (*cids, int(limit)))
    return [dict(r) for r in rows]


def by_slot_prefix(prefix: str, *, limit: int = 20, newest_first: bool = True) -> list[dict]:
    """The pills whose SLOT starts with `prefix` — a DIRECT read by key (µs, no embeddings nor reranker).

    Reads a namespaced CATALOGUE without paying semantic recall (V2-260): «which electricians do we have?» over
    `candidato:electricista:` is a SELECT by prefix, and success is precisely that the expensive path never fires.

    The prefix is ESCAPED for `LIKE` (`_`/`%` are wildcards and slots carry underscores). The caller supplies the
    separator: ending in `:` keeps `candidato:electricista:` from dragging in `candidato:electricista_industrial:`.
    Only `valid=1` (expiry is `ttl_days`, applied by the consolidator), and the same trust QUARANTINE as every
    read that may end up in a prompt."""
    pref = (prefix or "").strip()
    if not pref:
        return []
    esc = pref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    db = _db.get_db()
    order = "updated DESC, id DESC" if newest_first else "updated ASC, id ASC"
    rows = db.query(
        "SELECT id, level, kind, text, slot, importance, weight, created, updated FROM memories "
        "WHERE valid=1 AND slot LIKE ? ESCAPE '\\' "
        "AND (json_extract(meta,'$.trust') IS NULL OR json_extract(meta,'$.trust') != 'untrusted') "
        f"ORDER BY {order} LIMIT ?", (esc + "%", max(1, int(limit))))
    return [dict(r) for r in rows if (r["text"] or "").strip()]


def background_slot_off_topic(slot: str | None, prompt: str) -> bool:
    """True when `slot` is a BACKGROUND slot and the request never named it — the ONE rule, for every surface
    that renders pills to a model.

    Background/widget/cluster pills carry a namespaced slot (`<widget>:<key>`); the operator's own facts use dots
    (`operator.location`). To a model every surface reads as «what you know about this person», so `query()`
    applies this at the source and every surface inherits it. The passive block (`salient_long`) expresses the
    same verdict in SQL (`slot NOT LIKE '%:%'`) — equivalent, since with an empty prompt every namespaced slot is
    off-topic; filtering before ranking is just cheaper.

    CONDITIONAL, not a ban: a namespaced pill still passes when the request names its namespace or key
    («el tiempo en Soria»)."""
    if ":" not in (slot or ""):
        return False
    # The colon is a PROXY for «written by a background job». `insight:<concept>` shares the shape but is REM's
    # synthesis of the operator's own pills (V2-056) — excluding it would break the REM cycle's whole point
    # (`test_several_turns_then_rem_structurally_improves_memory`). `secret:*` is NOT excepted: never in a prompt.
    if str(slot).lower().startswith("insight:"):
        return False
    low = (prompt or "").lower()
    for part in re.split(r"[:._\-]+", str(slot).lower()):
        if len(part) >= _SLOT_WORD_MIN and re.search(rf"\b{re.escape(part)}\b", low):
            return False
    return True


def map(limit: int = 200) -> dict:
    """A BOUNDED snapshot of the memory (V2-014, bounded by V2-808): `state` + the newest valid pills of each layer
    (at most `limit`, capped at `MAP_CAP`), the edges among THOSE pills, and the totals as COUNTs. Read-only. It
    used to return every row and every edge on each call; the viewer now reads the paged, aggregated
    `memory/viewer.py` and nothing here grows with the store."""
    n = max(1, min(int(limit or 200), MAP_CAP))
    db = _db.get_db()
    cols = ("SELECT id, level, kind, text, importance, weight, access_count, last_access, ttl_days, "
            "pinned, valid, superseded_by, slot, meta, created, updated FROM memories WHERE valid=1 AND kind!='concept' ")
    short = [dict(r) for r in db.query(cols + "AND level='short' ORDER BY updated DESC LIMIT ?", (n,))]
    longterm = [dict(r) for r in db.query(cols + "AND level IN ('mid','long') ORDER BY updated DESC LIMIT ?", (n,))]
    ids = [m["id"] for m in short + longterm]
    edges = []
    if ids:
        ph = ",".join("?" * len(ids))
        edges = [dict(r) for r in db.query(
            f"SELECT from_id, to_id, type, weight FROM edges WHERE from_id IN ({ph}) OR to_id IN ({ph}) LIMIT ?",
            (*ids, *ids, 4 * n))]
    c = viewer.counts()
    one = lambda sql: int((db.query_one(sql) or [0])[0] or 0)  # noqa: E731
    n_short = one("SELECT COUNT(*) FROM memories WHERE valid=1 AND kind!='concept' AND level='short'")
    n_long = one("SELECT COUNT(*) FROM memories WHERE valid=1 AND kind!='concept' AND level IN ('mid','long')")
    return {
        "state": _state.read(),
        "layers": {"short": short, "long": longterm},
        "edges": edges,
        "counts": {"short": n_short, "long": n_long, "concepts": c["concepts"], "edges": c["relations"],
                   "total": n_short + n_long + c["concepts"]},
    }
