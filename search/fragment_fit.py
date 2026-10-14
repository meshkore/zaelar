"""search/fragment_fit.py — a row whose title is a page's facet, filter or navigation label is not a candidate (V2-782 T3.3).

search-buy-washing-machine US (2026-10-14): three browser extractions produced only page chrome — «Washer Capacity
(cu. ft.) 45 to Up» and «Minimum Price» at «$700» with no link, «Contact Us» and «Shop by Brand» with a link and no
price, «ENERGY STAR Certified and 4.0…» with neither — and the sheet ended on that last one as its only candidate.

A row is off when its title has the shape of a page's own chrome (`fragment_words`) AND it lacks a price or a
link: a real offer whose title happens to read «… 55 to 65 inch» still carries both, and stays. Nothing here
judges what the thing is; only that the row is not a thing at all.
"""
from __future__ import annotations

import re

from search import asked as _asked
from search import fragment_words as _w

_WHOLE = re.compile(rf"^\s*(?:{_w.WHOLE})\s*[.:…]*\s*$")
_PREFIX = re.compile(rf"^\s*(?:{_w.PREFIX})")
_INSIDE = [re.compile(p) for p in _w.INSIDE]


def shape(title: str) -> str:
    """Which chrome shape the title has ("" when it reads as a thing): "navigation or filter label", "control", "filter facet"."""
    t = _asked.norm(str(title or "").replace("…", " ").strip())
    if not t:
        return ""
    if _WHOLE.match(t):
        return "navigation or filter label"
    if _PREFIX.match(t):
        return "control"
    if any(rx.search(t) for rx in _INSIDE):
        return "filter facet"
    return ""


def why_off(row: dict) -> str:
    kind = shape(row.get("title"))
    if not kind or (str(row.get("price") or "").strip() and str(row.get("url") or "").strip()):
        return ""
    return f"the page's own {kind} («{str(row.get('title'))[:40]}»), not an offer: no price or no link to one product"


def split(on: list[dict], off: list[dict]):
    """The (on, off) of the gates before, with the page-chrome rows moved to `off` (with `why`)."""
    keep, out = [], list(off)
    for it in on:
        why = why_off(it)
        if why:
            out.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            keep.append(it)
    return keep, out
