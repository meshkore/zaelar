"""widgets/results/category_gate.py — the sheet's door applies `search.category`: a row that is not one of the things
he asked for never lands as a candidate (V2-782 T3.3).

Every route into the sheet ends at `present`/`append` (`actions.py`), so this is the one place the rule runs: the
listing fast pass, the browser's extraction, a web search's leads and the worker's own report alike. Off rows are
not lost — they go to the REJECTED tab with their reason, and the action's reply tells the worker which and why.

The request side is twofold (see `search.category.asked_from`): `asked`, the operator's own words, stored on the
sheet by whoever opened it for him (`listing_turn`) and grown by every correction that reaches the errand
(`recheck`, wired in `dispatch.inject`); and the sheet's own title, goal and criteria changes.
"""
from __future__ import annotations

from search import category as _category
from search import route_fit as _route

_MAX_ASKED = 900
_MAX_RELAYED = 6
_DEFAULT_TITLES = frozenset(("resultados", "results", "sin resultados", ""))


def _context(data: dict, payload: dict) -> list[str]:
    crit = data.get("criteria") or {}
    pcrit = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    out = [data.get("title"), payload.get("title"), crit.get("goal"), (pcrit or {}).get("goal")]
    out += list(data.get("relayed") or [])          # a correction in OUR words (see `recheck`)
    for src in (crit, pcrit or {}):
        out += list(src.get("changes") or []) + list(src.get("hard") or [])
    # A default title says nothing about what was asked: judging a «Resultados» sheet by category would reject the
    # «funda» of someone who asked for a phone case and whose worker never named the sheet.
    return [str(x) for x in out if x and str(x).strip().lower() not in _DEFAULT_TITLES]


def _own(data: dict, payload: dict) -> str:
    """His words as the sheet knows them: `asked`, plus the corrections a `criteria` op recorded as HIS («correcciones
    del operador» — the turn writes them from his sentence). three-tasks-at-once (ES, 2026-10-11): «27 al menos»
    reached the sheet only as a criteria change, and the gate, reading `asked` alone, never saw it."""
    crit = data.get("criteria") or {}
    pcrit = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else {}
    changes = [str(c) for src in (crit, pcrit or {}) for c in (src.get("changes") or []) if str(c or "").strip()]
    return " ".join([str(data.get("asked") or "")] + changes).strip()


def keep_asked(data: dict, prev: dict, payload: dict) -> None:
    """`asked` survives a `present` (which rebuilds the sheet) and a payload may set it; so do relayed corrections."""
    asked = str(payload.get("asked") or prev.get("asked") or data.get("asked") or "").strip()
    if asked:
        data["asked"] = asked[-_MAX_ASKED:]
    if prev.get("relayed") and not data.get("relayed"):
        data["relayed"] = list(prev["relayed"])


def asked_of(sheet: str) -> str:
    """His words as this sheet holds them ("" when none reached it)."""
    from widgets.results import data as _d
    return str(_d.view_data(sheet).get("asked") or "").strip()


def hear(sheet: str, words: str) -> bool:
    """The sentence that COMMISSIONED the errand becomes the sheet's `asked`, when it has none yet. True when set.

    find-concert-tickets ES (2026-10-14): a worker's sheet never had `asked` — only the listing fast pass wrote it —
    so «Rosalía» was nobody's subject, and «Miguel Lago», «El Club de los Poetas Muertos» and «El Cascanueces» were
    offered as Rosalía tickets. Re-judged too: a sheet inherited from a relay may already hold rows."""
    text = " ".join(str(words or "").split())
    if not text or asked_of(sheet):
        return False
    recheck(sheet, text)
    return True


def _file(data: dict, off: list[dict]) -> None:
    cur = list(data.get("rejected") or [])
    seen = {(x.get("url") or x.get("title") or "").strip().lower() for x in cur}
    for r in off:
        r = {**r, "source": "category gate"}            # the reason is ours (English), not the worker's words
        key = (r.get("url") or r.get("title") or "").strip().lower()
        if key and key not in seen:
            seen.add(key)
            cur.append(r)
    from widgets.results import data as _d
    data["rejected"] = cur[:_d._MAX_REJECTED]


def gate(data: dict, items: list[dict], payload: dict) -> tuple[list[dict], dict]:
    """(rows that are candidates, extra for the action's reply). Off rows are filed in `data["rejected"]`."""
    own, ctx = _own(data, payload), _context(data, payload)
    on, off = _route.split(*_category.split(items, own, ctx), own, ctx, raw_items=payload.get("items"))
    if not off:
        return on, {}
    _file(data, off)
    _emit(len(on), off)
    return on, {"off_category": off[:8],
                "note_for_worker": (f"{len(off)} row(s) are NOT what he asked for — moved to the Rejected tab: "
                                    + "; ".join(f"«{o['title'][:50]}» ({o['why']})" for o in off[:4])
                                    + ". Present only instances of the thing he asked for.")}


def recheck(sheet: str, correction: str, *, relayed: bool = False) -> int:
    """A correction reached the errand: it joins `asked`, and the rows already on the sheet are judged again.
    Returns how many left the list. Measured (search-buy-used-car ES, 2026-10-11): the worker heard «solo coches,
    no maquetas» and said «lo descarto», yet the eBay rows stayed and the reply kept offering them.

    `relayed`: the text is the MODEL's message to the worker, not his sentence. It joins the context side (what
    was ruled out, the ceiling), never `asked`, whose capitalised names are the subjects every row must name.
    hotel-under-15-days ES (2026-10-14): «DESCARTAR … (Hostel Trotamundos, bambu hostel capsules, Arc House…)» was
    read as his ask, and every real four-star hotel left the sheet for «does not name «hostel trotamundos»»;
    search-buy-guitar ES: «(Wallapop, Milanuncios y similares)» rejected eight guitars the same way."""
    from widgets.results import data as _d
    data = _d.view_data(sheet)
    text = " ".join(str(correction or "").split())
    if text and relayed:
        data["relayed"] = (list(data.get("relayed") or []) + [text[:_MAX_ASKED]])[-_MAX_RELAYED:]
    elif text:
        data["asked"] = (str(data.get("asked") or "") + " " + text).strip()[-_MAX_ASKED:]
    own, ctx = _own(data, {}), _context(data, {})
    on, off = _route.split(*_category.split(data.get("items") or [], own, ctx), own, ctx)
    if off:
        data["items"] = on
        _file(data, off)
        _emit(len(on), off, why="correction")
    if text or off:
        _d._save(data, sheet)
    return len(off)


def _emit(kept: int, off: list[dict], why: str = "door") -> None:
    try:
        from voice.observer import emit
        emit("widget", "🚫 off-category rows filed as rejected", role="system",
             extra={"kept": kept, "off": [f"{o['title'][:40]} — {o['why'][:60]}" for o in off[:6]], "why": why})
    except Exception as e:  # noqa: BLE001 — an event that cannot be emitted never blocks the sheet
        __import__("logging").getLogger(__name__).debug("category gate emit failed: %s", e)
