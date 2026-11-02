"""search/row_fit.py — every gate a row meets at the sheet's door, in order (V2-782 T3.3).

One call for `widgets/results/category_gate.py`: is it an instance of the thing asked (`category`), on the route
asked (`route_fit`), within the ceiling he set (`ceiling_fit`), in the place he asked (`place_fit`), and then
not page chrome, not against a spec he stated, not a second copy (`spec_gates`). Each gate
moves the rows it rules out to `off` with its reason; a gate the request says nothing to leaves every row alone.
"""
from __future__ import annotations

from search import category as _category
from search import ceiling_fit as _ceiling
from search import place_fit as _place
from search import route_fit as _route
from search import spec_gates as _specs


def split(items: list[dict], asked: str = "", context=(), raw_items=None, prior=(),
          declared=None, excluded=None) -> tuple[list[dict], list[dict]]:
    """(on, off) for one batch; `off` rows carry `why`, the sheet's REJECTED shape. `declared`: the subjects the
    errand's brief declared; `excluded`: the names an exclusion declared (see `category.asked_from`)."""
    on, off = _category.split(items, asked, context, declared, excluded)
    _tag(off, 0, "category")             # V2-837 G10: each off row says WHICH gate turned it away (the door event counts)
    n = len(off)
    on, off = _route.split(on, off, asked, context, raw_items=raw_items)
    n = _tag(off, n, "route")
    on, off = _ceiling.split(on, off, asked, context)
    n = _tag(off, n, "ceiling")
    on, off = _place.split(on, off, asked, context)
    n = _tag(off, n, "place")
    on, off = _specs.split(on, off, asked, context, prior)  # chrome, a contradicted spec or capacity, a second copy
    _tag(off, n, "spec")
    return on, off


def _tag(off: list[dict], since: int, gate: str) -> int:
    for r in off[since:]:
        if isinstance(r, dict):
            r.setdefault("gate", gate)
    return len(off)
