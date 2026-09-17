"""widgets/rows.py — the GENERIC data door: any operation over a widget's rows, through the same funnel.

## Why this exists (operator, 2026-09-16)

> «Si el Brainworker puede acceder a los datos de la memoria de la agenda, puede perfectamente ver la
> estructura de los datos y borrarlo todo. […] Los guardarraíles, las tools, las hash tables de las acciones
> son para agilizar ciertas cosas. Pero el resto también tiene que ser posible.»

He is right about the goal and the shape had to be found. What a worker must NOT do is open
`widgets/_data/<id>/state.json` and write it, for four reasons measured on this tree:

  1. **Mirror.** The agenda IS the calendar (V2-643): `cancel_meeting` calls `gcal.delete_google`. A row
     deleted in the file stays in Google and `tick()` brings it back — those are the 46 that «resurrected»
     on 2026-09-15.
  2. **Screen.** `store.save` is what notifies the canvas. A file written from outside leaves the card
     showing yesterday.
  3. **One writer.** The store holds an in-process lock; a worker is another process. Two writers on one
     JSON is corruption, and the snapshot (`store.history`) only exists inside `save`.
  4. **The one guard that worked.** The V2-705 contract lives in `server_api._dispatch`. Going around it is
     going back to the 147 DELETEs.

So the freedom is real and it enters by the front door. **This module is a RESOLVER, not a second writer.**
It turns an expression over the data — «the meetings whose title contains crypto», «everything before
today» — into the rows it matches, and then runs the widget's OWN declared action once per row, selector
filled. The mirror, the canvas notification, the snapshot and the contract all come along for free because
nothing new writes anything. A collection with no declared action for that operation (a generated widget
with a plain list) falls back to writing the store through `save`, which is still the single writer.

That is the `party.py` shape applied to data: the model may express ANY operation it can reason about, and
the ENGINE decides what may happen. Freedom of reasoning, zero freedom of consequence.

## The gate is the RADIUS, not the verb

`cancel_meeting` was FAST and `clear_all` was CONFIRM, while a `cancel_meeting` with an empty payload WAS
`clear_all` — the friction sat on the NAME of the action instead of on how much it touches. Here it sits
where it belongs:

  · **nothing matched** → refused, with what the collection does hold. An expression that matches no row is
    a misunderstanding, and «no rows» must never quietly mean «no change» on a delete the operator is
    waiting to hear about.
  · **one row** → runs. `store.save` snapshots what it overwrites.
  · **more than one** → CONFIRM, and the question carries the COUNT and the first names, because «are you
    sure?» over an unnamed number is not a question anybody can answer.

## What `where` may say

Closed in OPERATORS, open in CONTENT — the same split as the harness's verifiers. A key may carry a
suffix: `title~` contains, `date>=` / `date<=` / `date>` / `date<` compare as strings (ISO dates sort
correctly), `status!` is not-equal, a bare key is equality, and a list value means «any of these». String
comparison folds case and accents, because the operator says «cryptonite» about a row spelled «Cryptonite».
Nothing here parses natural language: that is the model's half, and it has the schema to do it with.

## Saying «all of these EXCEPT those» (V2-720)

`where` alone can only say «these». The sentence a person actually speaks is «clear today except Ivan's
meeting», and until an exception had its own key it had to be smuggled into `where` as a not-equal — which
reads correctly for one name and INVERTS for a list. So the expression has three clauses: `where` takes,
`not`/`except` (one clause or several) leaves out, and `ids` — the id field as `rows.list` handed it back —
names the exact rows. That last one is the whole «prepare a group and work with it» shape: list what is
really there, pick from THAT, act on precisely those, one row at a time through the widget's own action.
The exception is applied last and wins over `ids`, because the safe reading of a contradiction on a
destructive call is the one that touches less.
"""
from __future__ import annotations

import time
import unicodedata

#: A read never returns an unbounded store (the agenda answered `read_widget` with 59 955 bytes once, and
#: the worker could not read the file it was handed — V2-692c). The model pages with `where`, not with luck.
MAX_ROWS = 60

#: Ops a collection accepts unless its manifest says otherwise.
ALL_OPS = ("list", "put", "patch", "delete")

NOTHING_MATCHED = "nothing_matched"
NEEDS_CONFIRM = "needs_confirm"
UNKNOWN_COLLECTION = "unknown_collection"
OP_NOT_ALLOWED = "op_not_allowed"

_SUFFIXES = ("~", ">=", "<=", "!=", "!", ">", "<")


def _fold(v) -> str:
    n = unicodedata.normalize("NFKD", str(v if v is not None else ""))
    return "".join(c for c in n if not unicodedata.combining(c)).strip().lower()


# ── what a widget DECLARES it holds ─────────────────────────────────────────────────────────────────────

def declared(widget_id: str) -> dict:
    """The collections this widget declares in its manifest, or {} — never guessed from the data.

    Inference was tried and dropped: on this tree `agenda.meetings` rows carry `id` OR `googleId` depending
    on where they came from, `mensajeria.items` key on `messageId`, and half the lists are empty at rest,
    so a reader would have had to guess the id field from whichever row happened to be first. A widget's
    manifest is where its shape is declared — the one place the operator's doctrine puts rails."""
    try:
        from . import runtime
        cols = (runtime.get(str(widget_id or "").strip().lower()) or {}).get("collections")
        return cols if isinstance(cols, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def spec(widget_id: str, collection: str) -> dict:
    return declared(widget_id).get(str(collection or "").strip()) or {}


def ops_for(widget_id: str, collection: str) -> tuple[str, ...]:
    declared_ops = spec(widget_id, collection).get("ops")
    if isinstance(declared_ops, list) and declared_ops:
        return tuple(str(o) for o in declared_ops)
    return ALL_OPS


def schema(widget_id: str) -> dict:
    """What `hbwidget read` hands the worker: per collection, its id field, what it can be filtered by, and
    which operations it takes. The STRUCTURE he asked the worker to be able to see — from the manifest plus
    the keys the live rows actually carry, so a field that exists is never invisible."""
    out: dict = {}
    for coll, cspec in declared(widget_id).items():
        rows = _rows(widget_id, coll)
        fields: list[str] = []
        for r in rows[:20]:
            for k in r:
                if k not in fields:
                    fields.append(k)
        out[coll] = {"id": cspec.get("id") or "id", "count": len(rows), "fields": fields,
                     "ops": list(ops_for(widget_id, coll)),
                     **({"mirror": cspec.get("mirror")} if cspec.get("mirror") else {})}
    return out


# ── the expression ──────────────────────────────────────────────────────────────────────────────────────

def _split(key: str) -> tuple[str, str]:
    k = str(key or "")
    for suf in _SUFFIXES:
        if k.endswith(suf) and len(k) > len(suf):
            return k[: -len(suf)], ("!=" if suf == "!" else suf)
    return k, "="


def _one(value, op: str, want) -> bool:
    if isinstance(want, (list, tuple, set)):
        # A list is «any of these» — except under a NEGATIVE operator, where it is «none of these» (V2-720).
        # `any()` there answered True for every row (every value differs from at least one of three names),
        # so `{"title!": [a, b, c]}` — «delete the day except those three» — selected the whole day, the three
        # keepers included. A group expression that quietly means its own opposite on a delete is the shape
        # that cost Ivan's ten o'clock; the two readings must not share a code path.
        return all(_one(value, op, w) for w in want) if op == "!=" else any(_one(value, op, w) for w in want)
    a, b = _fold(value), _fold(want)
    if op == "=":
        return a == b
    if op == "!=":
        return a != b
    if op == "~":
        return bool(b) and b in a
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    return a < b


def matches(row: dict, where: dict | None) -> bool:
    """Does this row satisfy every clause? An empty `where` matches everything — deliberately, because the
    callers that can act on «everything» are gated by RADIUS below, not by pretending they cannot say it."""
    if not isinstance(where, dict) or not where:
        return True
    for key, want in where.items():
        field, op = _split(key)
        if not _one(row.get(field), op, want):
            return False
    return True


def _rows(widget_id: str, collection: str) -> list[dict]:
    try:
        from . import store
        db = store.load(widget_id, {})
        rows = db.get(str(collection or "").strip())
        return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
    except Exception:  # noqa: BLE001
        return []


def excluded(row: dict, nots) -> bool:
    """Does this row match ANY of the exclusion clauses? Each clause is a `where` of its own, so «everything
    today except the meeting with Ivan and the dentist» is two clauses, not one impossible one."""
    for clause in (nots if isinstance(nots, (list, tuple)) else [nots]):
        if isinstance(clause, dict) and clause and matches(row, clause):
            return True
    return False


def group(widget_id: str, collection: str, payload: dict | None) -> list[dict]:
    """The rows an expression names — THE GROUP (V2-720).

    Three clauses, and a person's sentence usually needs two of them at once:

      · `where`  — what to take («date: today»). Empty takes the collection.
      · `not` / `except` — what to leave out of it, as one clause or several. This is the half that was
        missing: `where` alone can only say «these», and «all of today EXCEPT Ivan's» is the shape the
        operator actually speaks. Expressing it through `title!` worked for one name and inverted itself
        for a list, so the exception now has its own key and reads the same for one name or five.
      · `ids` — the exact rows, by the collection's declared id field, as `rows.list` handed them back.
        This is «prepare a group and then work with it»: list, pick, act on precisely those, one by one.

    `ids` narrows what `where` took; the exclusions are applied last, so an id that is also excluded stays
    out — the exception always wins, because on a destructive call the safe reading of a contradiction is
    the one that touches less."""
    pl = payload if isinstance(payload, dict) else {}
    coll = str(pl.get("collection") or pl.get("coll") or "").strip()
    where = pl.get("where") if isinstance(pl.get("where"), dict) else {}
    nots = pl.get("not") if pl.get("not") is not None else (
        pl.get("except") if pl.get("except") is not None else pl.get("without"))
    ids = pl.get("ids") if isinstance(pl.get("ids"), (list, tuple)) else None
    idf = str(spec(widget_id, coll).get("id") or "id")

    out = [r for r in _rows(widget_id, coll) if matches(r, where)]
    if ids is not None:
        wanted = [str(i) for i in ids]
        out = [r for r in out if any(_one(r.get(idf), "=", w) or _one(r.get("id"), "=", w) for w in wanted)]
    if nots:
        out = [r for r in out if not excluded(r, nots)]
    return out


def select(widget_id: str, collection: str, where: dict | None) -> list[dict]:
    return [r for r in _rows(widget_id, collection) if matches(r, where)]


def _label(cspec: dict, row: dict) -> str:
    key = str(cspec.get("label") or "title")
    return str(row.get(key) or row.get("title") or row.get("name") or row.get("id") or "?")[:60]


# ── the door ────────────────────────────────────────────────────────────────────────────────────────────

def _refuse(error: str, detail: str, **extra) -> dict:
    return {"ok": False, "error": error, "detail": detail, **extra}


def plan(widget_id: str, op: str, payload: dict | None) -> dict:
    """What this expression WOULD do, decided before anything happens: the rows it matches, whether it needs
    the operator's OK, and which declared action carries each row. Pure — it writes nothing, which is what
    lets the confirm gate ask an honest question and the tests check the gate without a store."""
    wid = str(widget_id or "").strip().lower()
    op = str(op or "").strip()
    pl = payload if isinstance(payload, dict) else {}
    coll = str(pl.get("collection") or pl.get("coll") or "").strip()

    cols = declared(wid)
    if not cols:
        return _refuse(UNKNOWN_COLLECTION, f"«{wid}» no declara colecciones de datos.", collections=[])
    if coll not in cols:
        return _refuse(UNKNOWN_COLLECTION,
                       f"«{coll or '∅'}» no es una colección de «{wid}». Tiene: {', '.join(sorted(cols))}.",
                       collections=sorted(cols))
    if op not in ops_for(wid, coll):
        return _refuse(OP_NOT_ALLOWED,
                       f"«{coll}» no admite «{op}» (admite {', '.join(ops_for(wid, coll))}).")

    cspec = cols[coll]
    rows = group(wid, coll, {**pl, "collection": coll})

    if op == "list":
        return {"ok": True, "op": op, "collection": coll, "n": len(rows),
                "rows": rows[:int(pl.get("limit") or MAX_ROWS)], "confirm": False}
    if op == "put":
        return {"ok": True, "op": op, "collection": coll, "n": 1, "rows": [], "confirm": False,
                "via": (cspec.get("via") or {}).get("put", "")}

    # patch / delete act on what MATCHED, so nothing matching is a misunderstanding, never a silent no-op.
    if not rows:
        have = [_label(cspec, r) for r in _rows(wid, coll)[:8]]
        return _refuse(NOTHING_MATCHED,
                       f"Ninguna fila de «{coll}» cumple eso, así que no he tocado nada."
                       + (f" Hay: {'; '.join(have)}." if have else ""),
                       options=have, collection=coll)

    return {"ok": True, "op": op, "collection": coll, "n": len(rows), "rows": rows,
            # THE RADIUS, and it is the whole gate. One row runs (the store snapshots what it overwrites);
            # more than one asks, and the question carries the count and the names — «are you sure?» over an
            # unnamed number is not a question anybody can answer.
            "confirm": len(rows) > 1,
            "names": [_label(cspec, r) for r in rows[:8]],
            "via": (cspec.get("via") or {}).get(op, ""),
            "id_field": str(cspec.get("id") or "id"),
            "mirror": cspec.get("mirror") or ""}


async def apply(widget_id: str, op: str, payload: dict | None, *, confirmed: bool = False) -> dict:
    """Run the expression. Refusals and the confirm ask come back in the shape every `apply_action` uses."""
    p = plan(widget_id, op, payload)
    if not p.get("ok"):
        return p
    if p.get("confirm") and not confirmed:
        names = "; ".join(p.get("names") or [])
        return _refuse(NEEDS_CONFIRM,
                       f"Son {p['n']} filas de «{p['collection']}»" + (f" ({names})" if names else "")
                       + ". Dímelo y lo hago.",
                       n=p["n"], names=p.get("names") or [], collection=p["collection"],
                       needs_confirm=True)
    if op == "list":
        return {"ok": True, "n": p["n"], "rows": p["rows"]}

    wid = str(widget_id or "").strip().lower()
    pl = payload if isinstance(payload, dict) else {}
    via = str(p.get("via") or "")
    done, failed = 0, []

    if via:
        # THE DECLARED ACTION CARRIES IT. This is the whole design: the generic door resolves WHICH rows and
        # the widget's own action decides WHAT HAPPENS to each — so the Google delete, the canvas refresh and
        # the V2-705 contract all still run, and there is no second doctrine about the same data.
        from .server_api import dispatch_raw
        id_field = p.get("id_field") or "id"
        for row in (p["rows"] if op != "put" else [pl.get("row") or {}]):
            call = dict(pl.get("set") or {}) if op == "patch" else {}
            if op == "put":
                call = dict(row)
            else:
                sel = row.get(id_field) or row.get("id") or row.get("title") or row.get("name")
                call[id_field] = sel
                if id_field != "title" and row.get("title"):
                    call.setdefault("title", row["title"])
            res = await dispatch_raw(wid, via, call)
            if isinstance(res, dict) and res.get("ok") is False:
                failed.append(str(res.get("error") or res.get("message") or "?"))
            else:
                done += 1
    else:
        # No declared action for this collection: write the store, which is still the SINGLE writer and still
        # snapshots. This is the path a generated widget with a plain list takes.
        from . import store
        db = store.load(wid, {})
        rows = [r for r in (db.get(p["collection"]) or []) if isinstance(r, dict)]
        # THE ROWS THE PLAN RESOLVED, never the expression re-read here (V2-720): re-filtering on `where`
        # alone dropped the exclusions and the id list, so the confirm question described one group and this
        # branch deleted a larger one.
        doomed = p["rows"]
        if op == "delete":
            keep = [r for r in rows if r not in doomed]
            done = len(rows) - len(keep)
            db[p["collection"]] = keep
        elif op == "patch":
            sets = pl.get("set") if isinstance(pl.get("set"), dict) else {}
            for r in rows:
                if r in doomed:
                    r.update(sets)
                    done += 1
            db[p["collection"]] = rows
        else:                                   # put
            row = dict(pl.get("row") or {})
            id_field = p.get("id_field") or "id"
            row.setdefault(id_field, f"r_{int(time.time() * 1000)}")
            rows = [r for r in rows if r.get(id_field) != row.get(id_field)] + [row]
            db[p["collection"]] = rows
            done = 1
        store.save(wid, db)

    try:
        from voice.observer import emit as _emit
        _emit("widget", f"🧮 rows.{op} · {done} fila(s)", text="; ".join(p.get("names") or [])[:160],
              extra={"id": wid, "action": f"rows.{op}", "collection": p["collection"],
                     "n": p["n"], "done": done, "via": via, "failed": failed[:3]})
    except Exception:  # noqa: BLE001
        pass

    out = {"ok": not failed or done > 0, "op": op, "collection": p["collection"],
           "n": p["n"], "done": done}
    if failed:
        out["failed"] = failed[:5]
    return out
