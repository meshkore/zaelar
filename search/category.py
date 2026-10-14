"""search/category.py — is this row an INSTANCE of the thing asked, or another category of product? (V2-782 T3.3)

Measured 2026-10-11, search-buy-used-car ES and EN: the listing fast pass filled the sheet with what a
marketplace returns for «coche diésel segunda mano» — «Guardabarros delantero derecho — 224.51», «Locomotora
American Flyer Comet — 151.24», «Cursor 1923 1:43 Daimler Benz LKW — 31.26», «Catalog Nissan Laurel Used Car —
46.82», «Lote 1056 Matchcover — 2.71», «View Nationwide Inventory — $14,000». The turn named them as candidates
three times; the operator corrected three times. The same family elsewhere: «El Cascanueces» on a Rosalía ticket
hunt (find-concert-tickets ES), a 24" non-4K pick for a 27" 4K ask (cheapest-monitor EN).

`candidacy.py` already answers «is this a page that lists candidates?». This module answers the next question, at
the SAME door (`present`/`append`, every route ends there): is the row one of the things he asked for? A row is
OFF when it
  · carries a marker of another category (a part, a toy or scale model, a guide/catalogue, a listing index, an
    accessory — `category_words.GENERIC`) that the request itself does not use;
  · is priced below what a whole instance can cost: under 5 % of the ceiling he stated, or — for a vehicle — under
    `VEHICLE_FLOOR`;
  · is a vehicle row that names no make and no model year anywhere (title, subtitle, facts, url);
  · names none of the request's SUBJECTS (a proper name he asked about: «Rosalía»);
  · contradicts a spec he stated (another screen size, a resolution below the 4K he asked);
  · carries a word a correction ruled out («nada de maquetas»).
Nothing here is a judgement of taste: every reason is a fact the row and the request both carry. A row the
request says nothing against stays. Off rows are not dropped — they go to the sheet's REJECTED tab with their
reason (`widgets/results/category_gate.py`), so «why is X not there» is answerable.
"""
from __future__ import annotations

import re

from search import asked as _asked
from search import asked_size as _floor
from search import category_words as _w
from search import route_fit as _route

#: Under this share of the stated ceiling, a price is not the price of the thing asked (a €12,000 ceiling → €600).
_CEILING_SHARE = 0.05
#: «con accesorios», «with parts included»: a marker the row OFFERS on top of the thing is not another category.
_WITH_BEFORE = re.compile(r"\b(con|with|incl\w*|y|and|mas|plus)\s+(?:\w+\s+)?$")
_YEAR = re.compile(r"\b(19[5-9]\d|20[0-3]\d)\b")


def _row_text(row: dict) -> str:
    facts = " ".join(f"{f.get('label', '')} {f.get('value', '')}" for f in (row.get("facts") or [])
                     if isinstance(f, dict))
    return " ".join(str(row.get(k) or "") for k in ("title", "subtitle", "url")) + " " + facts


def _url_words(url: str) -> str:
    return re.sub(r"[/_.\-?=&]+", " ", str(url or ""))


def _marker(pattern: re.Pattern, text: str) -> str:
    """The first hit of `pattern` in `text` that is not «with X» — "" when none."""
    for m in pattern.finditer(text):
        if not _WITH_BEFORE.search(text[:m.start()]):
            return m.group(0)
    return ""


def _price(row: dict) -> float | None:
    v = _asked.amount(row.get("price")) if row.get("price") else None
    return v if v and v > 0 else None             # «0 €» is a row without a price, not a free car


def asked_from(asked: str = "", context=()) -> dict:
    """Everything this module reads from the request side, once per batch.

    `asked` = the operator's OWN words (his ask, his corrections): the only source of subjects and specs — a sheet
    title the model wrote («Monitor purchase for work», «Best-Value 27" Monitors») is Titlecase by style, and read
    as a subject it rejected every real row of four recorded sheets. `context` = the sheet's title, goal and
    criteria changes: enough to know the category, the ceiling and what was ruled out."""
    own = " ".join(str(asked or "").split())
    request = " ".join([own] + [str(t or "") for t in (context or ()) if t])
    n = _asked.norm(request)
    return {
        "norm": n,
        "ceiling": _asked.ceiling(own) or _asked.ceiling(request),
        "vehicle": bool(_w.VEHICLE_ASK.search(n) and _w.BUYING.search(n) and not _w.NOT_BUYING.search(n)),
        "subjects": _route.not_places(_asked.subjects(own)),   # «Madrid–Roma», «Nov 6»: a route, a date
        "size": _asked.size_inches(own),
        "size_min": _floor.size_floor(own),     # «27 al menos»: a floor, not an exact size (three-tasks 2026-10-11)
        "uhd": _asked.wants_4k(own),
        "excluded": [w for w in _asked.exclusions(request) if not re.search(rf"\b{re.escape(w)}\b",
                                                                            _first_clause(n, w))],
    }


def _first_clause(n: str, word: str) -> str:
    """The request text BEFORE the word's first negation — a word he asked for and later excluded stays
    excluded; one he only ever asked for is never read as an exclusion."""
    m = re.search(rf"\b(?:no|sin|ni|nada de|not|no more|without|ignore|excluding|except|exclude|nothing)\s+"
                  rf"{re.escape(word)}", n)
    return n[:m.start()] if m else n


def why_off(row: dict, ask: dict) -> str:
    """The reason this row is NOT an instance of what was asked, or "" when nothing says it is not."""
    raw_title = str(row.get("title") or "")
    text = _asked.norm(_row_text(row))
    title = _asked.norm(raw_title + " " + str(row.get("subtitle") or ""))
    req = ask.get("norm", "")
    for label, rx in _w.GENERIC.items():
        if rx.search(req):
            continue                                  # he asked for this class: it is his category
        hit = _marker(rx, title)
        if hit:
            return f"{label} («{hit}»), not what was asked"
    for label, rx in _w.CASE_SENSITIVE.items():
        if not _w.GENERIC[label].search(req) and rx.search(raw_title):
            return f"{label} («{rx.search(raw_title).group(0)}»), not what was asked"
    for w in ask.get("excluded") or ():
        if re.search(rf"\b{re.escape(w.rstrip('s'))}(?:e?s)?\b", title):
            return f"he ruled out «{w}»"
    price, ceiling = _price(row), ask.get("ceiling")
    if price is not None and ceiling and price < ceiling * _CEILING_SHARE:
        return f"priced {row.get('price')}, not the price of what was asked under {ceiling:,.0f}"
    if ask.get("vehicle"):
        if not _w.VEHICLE_PARTS.search(req):
            hit = _marker(_w.VEHICLE_PARTS, title)
            if hit:
                return f"a vehicle part («{hit}»), not a vehicle"
        if price is not None and price < _w.VEHICLE_FLOOR:
            return f"priced {row.get('price')}, below what a whole vehicle costs"
        words = set(_asked.norm(_row_text(row) + " " + _url_words(row.get("url"))).split())
        if not (words & _w.MAKES) and not _YEAR.search(text):
            return "names no make, model or year: not one vehicle"
    subj = ask.get("subjects") or []
    if subj:
        hay = _asked.norm(_row_text(row) + " " + _url_words(row.get("url")))
        if not any(all(p in hay for p in s.split()) for s in subj):
            return "does not name " + " / ".join(f"«{s}»" for s in subj[:3])
    size, floor = ask.get("size"), ask.get("size_min")
    if size or floor:
        got = _asked.size_inches(raw_title + " " + str(row.get("subtitle") or ""))
        if got and floor and got < floor:
            return f"{got}\" — under the {floor}\" minimum asked"
        if got and size and not floor and abs(got - size) >= 2:
            return f"{got}\" — not the {size}\" asked"
    if ask.get("uhd") and _asked.states_lower_than_4k(raw_title + " " + str(row.get("subtitle") or "")):
        return "not 4K, which was asked"
    return ""


def split(items: list[dict], asked: str = "", context=()) -> tuple[list[dict], list[dict]]:
    """(on, off) for one batch — see `asked_from` for the two request sides. `off` rows carry `why`, the sheet's
    REJECTED shape. With no request text at all, nothing is off."""
    ask = asked_from(asked, context)
    if not ask["norm"]:
        return list(items or []), []
    on, off = [], []
    for it in items or []:
        why = why_off(it, ask)
        if why:
            off.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            on.append(it)
    return on, off
