"""nucleo/circuit/baseline.py — what an end state remembers at BIRTH, so a state already true then proves nothing.

Two clauses of `verify.py`'s grammar are judged against the moment the request was born, not against the product
alone:

  · `expect: changed` (a scalar) — the value it WAS («set it as my background» when the phrase names an index, not a
    title): `baseline`;
  · `expect: added` (rows, V2-847) — the rows that ALREADY matched: `baseline_ids`. A send's end state is a NEW
    message in what left, not one like it from last week. Measured in a live session (2026-11-04): «tell her I'm on my
    way» could be «met» by an older identical message, and by a row still sitting in the queue.

A row without an id cannot be told new from old, so an `added` clause over it reads unverifiable (None), never met.
`spec.py` writes the baselines when the end state is rendered or born; `verify.check_clause` reads them.
"""
from __future__ import annotations

from loguru import logger


def snapshot(done_when) -> None:
    """Write each clause's baseline, once (a clause that already carries one keeps it)."""
    from nucleo.circuit import verify as _verify
    _mode, clauses = _verify._clauses(done_when)
    for c in clauses:
        expect = str(c.get("expect") or "").lower()
        if expect == "changed" and "baseline" not in c:
            c["baseline"] = _verify.current_value(c)
        elif expect == "added" and "baseline_ids" not in c:
            ids = row_ids(c)
            if ids is not None:
                c["baseline_ids"] = ids


def hits(clause: dict, wid: str, coll: str) -> list[dict]:
    """The rows of `coll` the clause's `where` and `with` select."""
    from widgets import rows
    matched = rows.select(wid, coll, clause.get("where") if isinstance(clause.get("where"), dict) else {})
    stated = [rows._fold(v) for v in (clause.get("with") or {}).values() if str(v).strip()]
    return [r for r in matched if all(v in rows._fold(r) for v in stated)]   # T-19 R2: a bare row is not it


def _ids(found: list[dict]) -> list[str] | None:
    """The rows' ids, or None when one has none — a row that cannot be named cannot be told new from old."""
    ids = [str(r.get("id") or "").strip() for r in found]
    return None if any(not i for i in ids) else ids


def added(clause: dict, found: list[dict]) -> bool | None:
    """Is one of the rows the clause selects NEW since birth? None with nothing to compare against."""
    base = clause.get("baseline_ids")
    ids = _ids(found)
    if not isinstance(base, list) or ids is None:
        return None
    return any(i not in base for i in ids)


def row_ids(clause: dict) -> list[str] | None:
    """The ids of the rows a row clause selects NOW — the baseline of an `added` clause. None when unreadable."""
    try:
        from nucleo.circuit import verify as _verify
        from widgets import rows
        if _verify.kind_of(clause) != "rows":
            return None
        wid = str(clause.get("widget") or "").strip().lower()      # the instance: its rows live there (a sheet)
        coll = str(clause.get("collection") or "").strip()
        if not wid or coll not in rows.declared(wid):
            return None
        return _ids(hits(clause, wid, coll))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"baseline: unreadable ({e!r})")
        return None
