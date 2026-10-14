"""search/row_dedupe.py — the same product is ONE row (V2-782 T3.3).

search-buy-tv ES (2026-10-14): «LG 55QNED70B6C» reached the sheet twice in one batch, and the turn read both out as
two candidates. Two rows are the same product when they share a MODEL CODE under the same brand (the title's
first word), or the same WHOLE title at the same price (a title cut with «…» may be two listings). The one with more facts stays, in the place of the first; the
other leaves with the reason. A row sent again with its own title and link is the same row being UPDATED (the
sheet merges it), never a duplicate.

A model code is a title token of at least six characters that mixes two letters and two digits and is no
quantity with a unit («128GB», «3840x2160», «1400rpm» are specs every model of a range shares).
"""
from __future__ import annotations

import re

from search import asked as _asked

_TOKEN = re.compile(r"[a-z0-9][a-z0-9-]{4,}[a-z0-9]")
_SPEC = re.compile(r"^\d+(?:gb|tb|mb|hz|mm|cm|kg|w|mah|cc|cv|hp|km|mp|rpm|p|k|in|x\d+|th|nd|rd|st)$|^\d+x\d+$")


def _codes(title: str) -> set[str]:
    out = set()
    for tok in _TOKEN.findall(_asked.norm(title)):
        tok = tok.replace("-", "")
        if len(tok) < 6 or _SPEC.match(tok):
            continue
        if sum(c.isdigit() for c in tok) >= 2 and sum(c.isalpha() for c in tok) >= 2:
            out.add(tok)
    return out


def _keys(row: dict) -> set[tuple]:
    title = _asked.norm(row.get("title"))
    brand = title.split()[0] if title else ""
    keys = {("code", brand, c) for c in _codes(row.get("title"))}
    price = _asked.amount(row.get("price")) if row.get("price") else None
    if title and price and not str(row.get("title")).rstrip().endswith(("…", "...")):
        keys.add(("title", title, price))       # a CUT title is not the whole name: two listings may share its start
    return keys


def _weight(row: dict) -> tuple[int, int]:
    facts = [f for f in (row.get("facts") or []) if isinstance(f, dict) and str(f.get("value") or "").strip()]
    return len(facts), sum(1 for k in ("price", "url", "subtitle", "image") if str(row.get(k) or "").strip())


def _same_row(a: dict, b: dict) -> bool:
    return (a.get("title"), a.get("url")) == (b.get("title"), b.get("url"))


def split(on: list[dict], off: list[dict], prior=()):
    """The (on, off) of the gates before, with every second copy of a product moved to `off` (with `why`).
    `prior`: the rows already on the sheet (an `append`): a batch row that repeats one of them is off too."""
    out = list(off)
    seen: dict[tuple, dict] = {}
    for row in prior or ():
        for k in _keys(row):
            seen.setdefault(k, row)
    keep: list[dict] = []
    for row in on:
        twin = next((seen[k] for k in _keys(row) if k in seen), None)
        if twin is None or _same_row(twin, row):
            keep.append(row)
            for k in _keys(row):
                seen.setdefault(k, row)
            continue
        loser, winner = row, twin
        if any(twin is r for r in keep) and _weight(row) > _weight(twin):
            idx = next(i for i, r in enumerate(keep) if r is twin)
            keep[idx], loser, winner = row, twin, row
            for k in _keys(row):
                seen[k] = row
        out.append({"title": loser.get("title", ""), "url": loser.get("url", ""),
                    "why": f"the same product as «{str(winner.get('title'))[:60]}», already a row"[:200]})
    return keep, out
