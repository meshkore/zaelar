"""search/row_fit.py — every gate a row meets at the sheet's door, in order (V2-782 T3.3).

One call for `widgets/results/category_gate.py`: is it an instance of the thing asked (`category`), on the route
asked (`route_fit`), within the ceiling he set (`ceiling_fit`), in the place he asked (`place_fit`). Each gate
moves the rows it rules out to `off` with its reason; a gate the request says nothing to leaves every row alone.
"""
from __future__ import annotations

from search import category as _category
from search import ceiling_fit as _ceiling
from search import place_fit as _place
from search import route_fit as _route


def split(items: list[dict], asked: str = "", context=(), raw_items=None) -> tuple[list[dict], list[dict]]:
    """(on, off) for one batch; `off` rows carry `why`, the sheet's REJECTED shape."""
    on, off = _category.split(items, asked, context)
    on, off = _route.split(on, off, asked, context, raw_items=raw_items)
    on, off = _ceiling.split(on, off, asked, context)
    return _place.split(on, off, asked, context)
