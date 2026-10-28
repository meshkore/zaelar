"""memory/viewer.py — the BOUNDED, AGGREGATE reads behind the memory viewer (V2-808, V2-814).

The viewer is a monitor of the memory, not a browser of its rows: it shows totals and how the memory relates
things, never the stored text. So nothing here returns a row:

  * totals are COUNTs, never `len()` of a list;
  * the graph is AGGREGATED here — concepts with their counts and concept↔concept weights — bounded by a time
    window, a scan cap and the node budget the client sends;
  * one concept is its numbers and the concepts it shares memories with.

Read-only: nothing here reinforces, rewrites or touches a weight.
"""
from __future__ import annotations

import threading
import time
from itertools import combinations

from . import db as _db

#: Rows the graph aggregation reads at most (newest first) — the window is bounded even when «all time» is asked.
SCAN_CAP = 20000
#: Node budget bounds — the client's device tier picks a value inside them.
BUDGET_MIN, BUDGET_MAX = 50, 3000
#: Concepts drawn at most once the graph collapses to its top level — past this the labels are noise.
CONCEPT_CAP = 400
#: Cards the «Cards» tab gets per layer at most, and the characters of one card's text.
CARDS_CAP, CARD_TEXT = 300, 280
#: Seconds the window aggregation is reused (several calls for one screen — graph, then a concept page).
_CACHE_S = 10.0

_OWN_KINDS_SQL = "kind NOT IN ('concept','conv','msg')"
_cache: dict = {}
_cache_lock = threading.Lock()


def clamp_budget(budget) -> int:
    try:
        n = int(budget)
    except (TypeError, ValueError):
        n = 300
    return max(BUDGET_MIN, min(n, BUDGET_MAX))


# ── totals ──────────────────────────────────────────────────────────────────────────────────────────────────
def counts(week_s: int = 7 * 86400) -> dict:
    """Every memory total the overview prints, as COUNTs. Cheap: indexed columns only."""
    db = _db.get_db()
    since = int(time.time()) - week_s

    def one(sql, args=()):
        r = db.query_one(sql, args)
        return int(r[0] or 0) if r else 0

    return {
        "facts": one(f"SELECT COUNT(*) FROM memories WHERE valid=1 AND {_OWN_KINDS_SQL}"),
        "facts_short": one(f"SELECT COUNT(*) FROM memories WHERE valid=1 AND level='short' AND {_OWN_KINDS_SQL}"),
        "facts_week": one(f"SELECT COUNT(*) FROM memories WHERE valid=1 AND {_OWN_KINDS_SQL} AND created>=?",
                          (since,)),
        "concepts": one("SELECT COUNT(*) FROM memories WHERE valid=1 AND kind='concept'"),
        "relations": one("SELECT COUNT(*) FROM edges"),
        "conversation": one("SELECT COUNT(*) FROM memories WHERE valid=1 AND kind='conv'"),
        "conversation_oldest": one("SELECT COALESCE(MIN(created),0) FROM memories WHERE valid=1 AND kind='conv'"),
        "message_pills": one("SELECT COUNT(*) FROM memories WHERE valid=1 AND kind='msg'"),
    }


def per_day(days: int = 30) -> list[dict]:
    """New rows per local day over the last `days` (own lane and inbound-message lane apart)."""
    days = max(1, min(int(days or 30), 366))
    since = int(time.time()) - days * 86400
    rows = _db.get_db().query(
        "SELECT date(created,'unixepoch','localtime') d, SUM(kind='msg') m, SUM(kind!='msg') o FROM memories "
        "WHERE valid=1 AND kind NOT IN ('concept','conv') AND created>=? GROUP BY d ORDER BY d", (since,))
    return [{"day": r["d"], "own": int(r["o"] or 0), "messages": int(r["m"] or 0)} for r in rows]


# ── the graph, aggregated ───────────────────────────────────────────────────────────────────────────────────
def _concept_labels() -> dict[int, set[str]]:
    """pill id → the persisted concept labels it hangs from (edges in either direction)."""
    db = _db.get_db()
    out: dict[int, set[str]] = {}
    for sql in ("SELECT e.to_id p, c.text l FROM edges e JOIN memories c ON c.id=e.from_id "
                "WHERE c.kind='concept' AND c.valid=1 LIMIT ?",
                "SELECT e.from_id p, c.text l FROM edges e JOIN memories c ON c.id=e.to_id "
                "WHERE c.kind='concept' AND c.valid=1 LIMIT ?"):
        for r in db.query(sql, (SCAN_CAP * 4,)):
            lab = (r["l"] or "").strip().lower()
            if lab:
                out.setdefault(int(r["p"]), set()).add(lab)
    return out


def _window(days: int, lanes: tuple[str, ...]) -> list[dict]:
    """The pills of the window, each with its concepts. Cached a few seconds per (database, days, lanes), and
    only while nothing was written: the newest id and update stamp are part of the key."""
    db = _db.get_db()
    mark = db.query_one("SELECT MAX(id), MAX(updated) FROM memories")
    key = (id(db), int(days), lanes, tuple(mark) if mark else ())
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_S:
            return hit[1]
    from memory.concepts import derive_concepts
    where, args = ["valid=1", "kind NOT IN ('concept','conv')"], []
    if "messages" not in lanes:
        where.append("kind != 'msg'")
    if days > 0:
        where.append("created >= ?"); args.append(int(time.time()) - int(days) * 86400)
    rows = db.query(
        "SELECT id, level, kind, text, weight, meta, created FROM memories WHERE " + " AND ".join(where)
        + " ORDER BY id DESC LIMIT ?", (*args, SCAN_CAP))
    persisted = _concept_labels()
    pills = []
    for r in rows:
        level = "short" if r["level"] == "short" else "long"
        cs = persisted.get(int(r["id"])) if level == "long" else None
        cs = sorted(cs) if cs else derive_concepts(r["text"] or "")
        if cs:
            pills.append({"id": int(r["id"]), "level": level, "kind": r["kind"], "w": float(r["weight"] or 0),
                          "created": int(r["created"] or 0), "c": cs})
    with _cache_lock:
        _cache[key] = (now, pills)
        for k in [k for k, v in _cache.items() if now - v[0] >= _CACHE_S]:
            _cache.pop(k, None)
    return pills


def _lanes(lanes) -> tuple[str, ...]:
    got = {x.strip() for x in str(lanes or "own").split(",") if x.strip() in ("own", "messages")}
    return tuple(sorted(got or {"own"}))


def _layers(layers) -> set[str]:
    return {x.strip() for x in str(layers or "short,long").split(",") if x.strip() in ("short", "long")} or {"short", "long"}


def graph(*, days: int = 30, layers: str = "short,long", lanes: str = "own", budget: int = 300) -> dict:
    """The concept graph of a window, bounded by `budget` nodes (concepts + memories).

    Everything fits → every concept AND every memory of the window is drawn. It does not fit → only the TOP level
    is drawn: the concepts (the most used first, at most `budget` and `CONCEPT_CAP`), no memory dots, and
    `collapsed` says so. Concept↔concept links count the pills two concepts share, over the WHOLE window (not only
    the shown pills), strongest first, at most six per shown concept."""
    budget = clamp_budget(budget)
    lys = _layers(layers)
    pills = [p for p in _window(max(0, int(days or 0)), _lanes(lanes)) if p["level"] in lys]
    count: dict[str, int] = {}
    short: dict[str, int] = {}
    last: dict[str, int] = {}
    pair: dict[tuple[str, str], int] = {}
    for p in pills:
        for c in p["c"]:
            count[c] = count.get(c, 0) + 1
            if p["level"] == "short":
                short[c] = short.get(c, 0) + 1
            last[c] = max(last.get(c, 0), p["created"])
        for a, b in combinations(p["c"], 2):
            pair[(a, b)] = pair.get((a, b), 0) + 1
    n_attached = sum(1 for p in pills if p["c"])
    collapsed = len(count) + n_attached > budget
    k = min(len(count), budget, CONCEPT_CAP) if collapsed else len(count)
    top = [c for c, _ in sorted(count.items(), key=lambda kv: (-kv[1], kv[0]))[:k]]
    shown = set(top)
    concepts = [{"key": c, "label": c, "count": count[c], "short": short.get(c, 0), "last": last.get(c, 0)}
                for c in top]
    links = sorted(([a, b, w] for (a, b), w in pair.items() if a in shown and b in shown),
                   key=lambda x: -x[2])[: 6 * max(1, k)]
    room = 0 if collapsed else max(0, budget - k)
    attached = [p for p in pills if any(c in shown for c in p["c"])]
    attached.sort(key=lambda p: (-p["w"], -p["created"]))
    mems = [{"id": p["id"], "c": [c for c in p["c"] if c in shown], "level": p["level"], "kind": p["kind"],
             "w": round(p["w"], 3)} for p in attached[:room]]
    return {
        "concepts": concepts,
        "links": [{"a": a, "b": b, "w": w} for a, b, w in links],
        "memories": mems,
        "total": {"concepts": len(count), "memories": len(attached), "nodes": len(count) + len(attached)},
        "shown": {"concepts": len(concepts), "memories": len(mems), "nodes": len(concepts) + len(mems)},
        "budget": budget,
        "scanned": len(pills),
        "capped": len(pills) >= SCAN_CAP,
        "collapsed": collapsed,
    }


def layer_counts(*, days: int = 30) -> dict:
    """The filter chips' numbers: rows of each layer/lane inside the window (COUNTs)."""
    where, args = "valid=1 AND kind NOT IN ('concept','conv')", []
    if days and int(days) > 0:
        where += " AND created >= ?"; args.append(int(time.time()) - int(days) * 86400)
    r = _db.get_db().query_one(
        f"SELECT SUM(kind!='msg' AND level='short') s, SUM(kind!='msg' AND level!='short') l, SUM(kind='msg') m "
        f"FROM memories WHERE {where}", tuple(args))
    return {"short": int(r["s"] or 0), "long": int(r["l"] or 0), "messages": int(r["m"] or 0)}


def concept(key: str, *, days: int = 30, layers: str = "short,long", lanes: str = "own") -> dict:
    """One concept: how many memories hold it and the concepts it shares them with — never the memories' text.

    The viewer is a monitor of how the memory RELATES things (V2-814); the rows themselves are not shown.
    """
    key = (key or "").strip().lower()
    lys = _layers(layers)
    mine = [p for p in _window(max(0, int(days or 0)), _lanes(lanes)) if p["level"] in lys and key in p["c"]]
    related: dict[str, int] = {}
    for p in mine:
        for c in p["c"]:
            if c != key:
                related[c] = related.get(c, 0) + 1
    return {
        "key": key, "label": key, "count": len(mine),
        "short": sum(1 for p in mine if p["level"] == "short"),
        "last": max((p["created"] for p in mine), default=0),
        "related": [{"key": c, "count": w} for c, w in sorted(related.items(), key=lambda kv: -kv[1])[:8]],
    }


def cards(limit: int = 100) -> dict:
    """The «Cards» tab (V2-815): the newest cards of each layer, the state, and one small concept map per layer.

    Bounded three ways: at most `limit` (≤ `CARDS_CAP`) cards per layer, each text cut at `CARD_TEXT`, and each
    concept map a ring of at most 24 concepts. The totals are COUNTs, so the header can say «shown / total»."""
    from . import api as _api
    n = max(1, min(int(limit or 100), CARDS_CAP))
    body = _api.map(n)
    keep = ("id", "level", "kind", "text", "importance", "weight", "access_count", "last_access", "ttl_days",
            "pinned", "created", "updated")
    for layer in ("short", "long"):
        body["layers"][layer] = [{**{k: m.get(k) for k in keep}, "text": (m.get("text") or "")[:CARD_TEXT]}
                                 for m in body["layers"][layer]]
    body.pop("edges", None)
    cg = {}
    for layer in ("short", "long"):
        g = graph(days=0, layers=layer, budget=BUDGET_MIN)
        top = g["concepts"][:24]
        shown = {c["key"] for c in top}
        cg[layer] = {"nodes": [{"key": c["key"], "label": c["label"], "count": c["count"]} for c in top],
                     "links": [{"a": l["a"], "b": l["b"], "weight": l["w"]} for l in g["links"]
                               if l["a"] in shown and l["b"] in shown][:72],
                     "total": g["total"]["concepts"]}
    body["concept_graph"] = cg
    return body
