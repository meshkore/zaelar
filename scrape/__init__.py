"""scrape/ — READING A PAGE: one door, the ladders inside (V2-846).

    from scrape import read
    res = read("https://www.autoscout24.es/lst/mercedes-benz/c-220?atype=C", want="listings")
    res.how, res.records, res.extractor, res.tried

`search/` finds pages; `scrape/` gets to a page and reads it. Inside, two ladders, routed by what happens — the
caller never chooses:

  · FETCH (`fetch.py`) — a plain GET from this machine, then Bright Data's unlocker; a wall or a page that held no
    records moves the read one rung up. (The browser rungs, the Machine's own and the residential one, join in F3/F4.)
  · EXTRACT, first that passes the ONE validator (`validate.py`): what the page DECLARES (`extract.py`: JSON-LD /
    OpenGraph) → what its SCRIPT STATE holds (`state.py`, found by the shape of the values, its field map kept per site
    in `mapping.py`).

`walls.py` is the engine's one definition of a page that stopped us. What the module needs from the engine it gets
through `hooks.py`. It never imports the turn, the workers, `memory/` or `widgets/`. BLOCKING: callers on an event loop
use `asyncio.to_thread`. Never raises: a failed read is a `ScrapeResult` with `failure` and every rung tried.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from scrape import extract as _extract, fetch as _fetch, mapping as _mapping, state as _state, validate as _validate

__all__ = ["read", "ScrapeResult"]


@dataclass
class ScrapeResult:
    url: str
    how: str = ""                                # the fetch rung that got the page: http · unlocker
    extractor: str = ""                          # declared · state (+ how its field map was decided)
    records: list = field(default_factory=list)
    html: str = ""
    failure: str = ""
    tried: list = field(default_factory=list)    # one row per rung: {rung, status, n?, note?}
    took_ms: int = 0

    def ok(self) -> bool:
        return not self.failure

    def to_dict(self, with_html: bool = False) -> dict:
        d = {"url": self.url, "how": self.how, "extractor": self.extractor, "records": self.records,
             "n": len(self.records), "failure": self.failure, "tried": self.tried, "took_ms": self.took_ms}
        if with_html:
            d["html"] = self.html
        return d


def records_of(html: str, page_url: str) -> tuple[list[dict], str]:
    """`(records, extractor)` — every free extraction rung is asked and the one with MORE records that pass the
    validator wins (the declared one on a tie). The first that passed used to win: Zillow declares 2 of its 41 rentals
    in JSON-LD and carries all 41 in its state, so the sheet got 2 (measured 2026-11-04)."""
    best: tuple[list[dict], str] = ([], "")
    declared, counts = _validate.keep(_extract.extract_items(html, page_url), page_url)
    if counts:
        best = (declared, "declared")
    path, items = _state.listings(html)
    if items and len(items) > len(best[0]):
        fmap, how = _mapping.field_map(items, path, page_url)
        if fmap:
            recs, counts = _validate.keep(_state.records(items, fmap, page_url), page_url)
            if counts and len(recs) > len(best[0]):
                best = (recs, f"state/{how}")
    return best


def read(url: str, want: str = "listings", *, country: str = "") -> ScrapeResult:
    """Get to `url` and read it. `want="listings"` climbs until a rung yields records that pass; `want="page"` stops at
    the first rung that brings the page. Never raises."""
    t0 = time.monotonic()
    out = ScrapeResult(url=url)
    for name, rung in _fetch.RUNGS:
        try:
            html = rung(url, country)
        except Exception as e:  # noqa: BLE001 — a rung that failed is a row; the next one is asked
            out.tried.append({"rung": name, "status": "wall" if isinstance(e, _fetch.Wall) else "error",
                              "note": str(e)[:160]})
            continue
        out.how, out.html = name, html
        if want != "listings":
            out.tried.append({"rung": name, "status": "ok"})
            break
        records, extractor = records_of(html, url)
        out.tried.append({"rung": name, "status": "ok", "n": len(records), "extractor": extractor})
        if records:
            out.records, out.extractor = records, extractor
            break
    if not out.html:
        out.failure = "no rung reached the page"
    elif want == "listings" and not out.records:
        out.failure = "the page came, no extraction rung found listings that pass"
    out.took_ms = round((time.monotonic() - t0) * 1000)
    return out
