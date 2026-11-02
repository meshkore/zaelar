"""widgets/results/pool.py — the candidates a hunt GATHERED, of which the list shows a selection (V2-835 T2).

search-buy-used-car ES (2026-11-02): the sheet held 35 candidate cars, the worker's final `present` carried its 3
picks and replaced the list, and «now give me at least 10» had nothing left. `data["pool"]` keeps every row that
passed the door, in the order it landed; `present` decides which of them the list shows; `append {from_pool: n}`
brings the next n back through the same door; a correction rules rows out of it (`category_gate.recheck`).
"""
from __future__ import annotations

from . import data as _d


def key(it: dict) -> tuple:
    return (it.get("title"), it.get("url"))


def gathered(*lists) -> list[dict]:
    """The candidates this hunt has gathered, in the order they first landed — one per (title, url), a later copy of a
    row (with what was verified on it) taking its place."""
    out: dict[tuple, dict] = {}
    for rows in lists:
        for it in rows or ():
            out[key(it)] = it
    return list(out.values())[-_d._MAX_POOL:]


def note(data: dict) -> dict:
    shown = {key(i) for i in data.get("items") or []}
    left = sum(1 for i in data.get("pool") or [] if key(i) not in shown)
    if not left:
        return {}
    return {"pool": left, "pool_note": (f"{left} more candidate(s) this hunt gathered are kept off the list, not lost: "
                                        f"`append {{\"from_pool\": n}}` brings the next n back.")}


def take(data: dict, n) -> list[dict]:
    """The next `n` gathered candidates not on the list, in the order they landed («more results» starts here)."""
    try:
        n = max(0, int(n))
    except (TypeError, ValueError):
        return []
    shown = {key(i) for i in data.get("items") or []}
    return [dict(i) for i in data.get("pool") or [] if key(i) not in shown][:n]
