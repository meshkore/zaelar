"""search/place_fit.py — a row that says it is somewhere ELSE than the place he asked is not a candidate (V2-782 T3.3).

search-rent-apartment US (2026-10-14): «Find me an apartment to rent in Austin». The worker's extraction carried
«Azola Avery Centre» (…/Texas/Round-Rock-Apartments/…) and «Lively at Gilbert» (…/Texas/Manor-Apartments/…), and
the turn offered both as Austin apartments. Round Rock and Manor are other cities of the Austin metro.

The asked place is a KNOWN place (`place_words.METROS`) that his words name — capitalised, or after «en / in / near»
— and only then; the sheet's title and criteria are read when his words name none. A row is off when it NAMES at
least one place (a known one in its text, the «City, ST» address shape, or a listing URL's «/Round-Rock-Apartments/»
segment) and none of them is the asked place. A row that names no place stays, and so does one that also names the
asked one («Valdemoro (Madrid)»). A suburb is another place unless he widened the ask («y alrededores», «area»,
«near»). A trip has its own gate (`route_fit`): when he asked a route, nothing is judged here.
"""
from __future__ import annotations

import re
import unicodedata

from search import asked as _asked
from search import place_words as _w
from search import route_fit as _route

_METRO_OF = {n: i for i, (cities, subs) in enumerate(_w.METROS) for n in cities + subs}
_CITY_NAMES = {n: cities for cities, _subs in _w.METROS for n in cities}
_ALL = sorted(_METRO_OF, key=len, reverse=True)
_NAME = re.compile(r"(?<![\w'-])(" + "|".join(re.escape(n) for n in _ALL) + r")(?![\w'-])", re.I)
_PREP = re.compile(r"\b(?:en|in|near|cerca de|around|at|por|de)\s+$", re.I)
_US_ADDR = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+){0,2}),\s*([A-Z]{2})\b")
_WIDENED = re.compile(_w.WIDENED)


def _plain(text) -> str:
    """Accent-free, case KEPT: a place in a row is a capitalised name («Manor», never «manor»)."""
    s = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def _said(text: str) -> list[str]:
    """The known places `text` names as places: capitalised, or after a place preposition."""
    raw = _plain(text)
    return [m.group(1).lower() for m in _NAME.finditer(raw)
            if m.group(1)[0].isupper() or _PREP.search(raw[:m.start()])]


def asked_place(asked: str = "", context=()) -> dict:
    """{"names": the names a row may carry, "said": as he said it}, or {} when no known place was asked."""
    if _route.asked_route(asked, context):
        return {}
    texts = [str(asked or "")] + [str(t or "") for t in (context or ()) if t]
    said = _said(texts[0])
    if not said:
        said = [n for t in texts[1:] for n in _said(t)]
    if not said:
        return {}
    widened = bool(_WIDENED.search(_asked.norm(" ".join(texts))))
    names: set[str] = set()
    for n in said:
        cities, subs = _w.METROS[_METRO_OF[n]]
        names |= set(cities + subs) if widened else set(_CITY_NAMES.get(n, (n,)))
    return {"names": frozenset(names), "said": said[-1].title()}


_QUARTER = frozenset(("east", "west", "north", "south", "downtown", "central", "center", "centre", "midtown", "old",
                      "greater", "centro", "norte", "sur", "este", "oeste", "capital", "ciudad", "city"))


def not_places(subjects: list[str]) -> list[str]:
    """`subjects` without the known places, bare or with a quarter word («east austin», «madrid centro»): a place is
    what a row is judged against here, never the subject it must NAME. search-rent-apartment US (2026-10-14): his
    «East Austin or downtown» made «austin» a subject, and every listing whose card named no city left the sheet."""
    out = []
    for s in subjects or []:
        m = _NAME.search(s)
        rest = (s[:m.start()] + " " + s[m.end():]).split() if m else [s]
        if not (m and all(w in _QUARTER for w in rest)):
            out.append(s)
    return out


def _url_places(url: str) -> set[str]:
    out = set()
    path = re.sub(r"^[a-z]+://[^/]+", "", str(url or "").lower()).split("?")[0]
    for seg in path.split("/"):
        words = [w for w in re.split(r"[-_+.\s]+", seg) if w]
        for n in _ALL:
            k = len(n.split())
            if words[:k] == n.split() and all(w in _w.URL_TAILS for w in words[k:]):
                out.add(n)
    return out


def named(row: dict) -> set[str]:
    """Every place this row names: a known one in its text or URL, or the city of a «City, ST» address."""
    facts = " ".join(f"{f.get('value', '')}" for f in (row.get("facts") or []) if isinstance(f, dict))
    text = _plain(" · ".join(str(row.get(k) or "") for k in ("title", "subtitle")) + " · " + facts)
    out = {m.group(1).lower() for m in _NAME.finditer(text) if m.group(1)[0].isupper()}
    out |= {m.group(1).lower() for m in _US_ADDR.finditer(text) if m.group(2) in _w.US_STATES}
    return out | _url_places(row.get("url"))


def why_off(row: dict, place: dict) -> str:
    """Why this row is somewhere else than the asked place, or "" when nothing it names says so."""
    if not place:
        return ""
    where = named(row)
    if not where or where & place["names"]:
        return ""
    return f"in {sorted(where)[0].title()}, not {place['said']}, which he asked"


def split(on: list[dict], off: list[dict], asked: str = "", context=()):
    """The (on, off) of the gates before, with the rows placed elsewhere moved to `off` (with `why`)."""
    place = asked_place(asked, context)
    if not place:
        return on, off
    keep, out = [], list(off)
    for it in on:
        why = why_off(it, place)
        if why:
            out.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            keep.append(it)
    return keep, out
