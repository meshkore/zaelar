"""rules/cascade.py — which rows cover a request, and in what order they apply (V2-806).

Selection is a walk over strings (`scope.level_in`), never a model. The covering rows run general → specific and,
per key, the last one wins:

  1. the level the row matched at (global < domain < channel < widget < action < item);
  2. at one level, fewer `*` is more specific;
  3. at one level and specificity, `user` runs after `default`;
  4. then `created_at`.

`note` and `excluded` rows never override one another: every covering note is kept, and every covering exclusion
adds its names (one rule per name he ruled out, V2-838), in that same order.
"""
from __future__ import annotations

import time

from . import scope as _scope

NOTE = "note"
EXCLUDED = "excluded"
#: Keys whose rows ADD to each other instead of one winning: his sentences, and the names he ruled out.
ACCUMULATE = (NOTE, EXCLUDED)
ALLOW = "allow"
ASK = "ask"
NEVER = "never"
GATE_VALUES = (ALLOW, ASK, NEVER)
_SOURCE_RANK = {"default": 0, "user": 1}


def live(row: dict, now: float | None = None) -> bool:
    """Active, and not past its `until` — read by the clock, so nothing has to sweep an expired row."""
    if not row.get("active", True):
        return False
    until = row.get("until")
    if until in (None, ""):
        return True
    try:
        return float(until) > (time.time() if now is None else now)
    except (TypeError, ValueError):
        return True


def covering(rows: list[dict], anchors: list[tuple[int, str]], *, now: float | None = None,
             kind: str | None = None) -> list[dict]:
    """The live rows that cover this path, in the order they apply (the winner of each key is the LAST one)."""
    picked = []
    for r in rows:
        if kind and r.get("kind") != kind:
            continue
        if not live(r, now):
            continue
        lvl = _scope.level_in(r["scope"], anchors)
        if lvl is None or _scope.excluded(r.get("except"), anchors):
            continue
        order = (lvl, -_scope.wildcards(r["scope"]), _SOURCE_RANK.get(r.get("source"), 1),
                 float(r.get("created_at") or 0.0))
        picked.append((order, r))
    picked.sort(key=lambda t: t[0])
    return [r for _o, r in picked]


def resolve(rows: list[dict], anchors: list[tuple[int, str]], *, now: float | None = None) -> dict:
    """`{"values": {key: value}, "rules": {key: winning row}, "notes": [rows], "excluded": [rows]}` for this path."""
    values: dict = {}
    winners: dict = {}
    added: dict = {k: [] for k in ACCUMULATE}
    for r in covering(rows, anchors, now=now):
        if r["key"] in added:
            added[r["key"]].append(r)
            continue
        values[r["key"]] = r["value"]
        winners[r["key"]] = r
    return {"values": values, "rules": winners, "notes": added[NOTE], "excluded": added[EXCLUDED]}
