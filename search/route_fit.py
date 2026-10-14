"""search/route_fit.py — does a travel row go WHERE he asked, and without the stops he ruled out?

find-direct-flight-budget ES (2026-10-14, sandbox 020034-es): he asked for a direct Madrid–Rome flight; after
eight minutes and sixteen pages the sheet held four rows of other routes — «Buscar vuelos de Logroño (RJL) a Madrid
(MAD) desde 88 €», «de Madrid (MAD) a Lisboa (LIS) desde 49 €», «de Barcelona (BCN) a Palma (PMI)…» — the
navigation links of a fare page, extracted as results. The sheet's own title said «Vuelos Madrid-Roma» and its
hard criteria «Madrid (MAD) a Roma (FCO o CIA)», «Vuelos directos, sin escalas»; no gate read either.

`category.py` answers «is this an instance of the thing asked». This module answers the question a route asks: a
row that STATES a route (A → B, «de A a B», «from A to B») must join the two places of the asked route, in either
order (the return leg is the same trip), and when he asked for a direct trip a row that states stops is not one.
A place matches by name or code, in Spanish or English (`_PLACES`: Roma = Rome = ROM/FCO/CIA). A row that states
no route is never judged here — silence is not a contradiction. A pair whose other end is a place nobody knows
is judged only in its explicit «de A a B» form: «Madrid-Barajas» is an airport, not a route.

Only for a request about TRAVEL (`_TRAVEL`): «Hoteles Madrid - Centro» is a sheet title, not a route.
"""
from __future__ import annotations

import re

from search import asked as _asked
from search.category_words import NOT_A_SUBJECT

#: Each group is ONE place: its names in ES/EN, its metropolitan code and its airports (code and name).
_PLACES = (
    ("madrid", "mad", "barajas", "adolfo suarez"),
    ("roma", "rome", "rom", "fco", "cia", "fiumicino", "ciampino"),
    ("barcelona", "bcn", "el prat"),
    ("nueva york", "new york", "nyc", "jfk", "ewr", "lga", "newark", "laguardia", "john f kennedy"),
    ("londres", "london", "lon", "lhr", "lgw", "stn", "ltn", "heathrow", "gatwick", "stansted", "luton"),
    ("paris", "par", "cdg", "ory", "charles de gaulle", "orly", "beauvais"),
    ("lisboa", "lisbon", "lis"),
    ("milan", "milano", "mil", "mxp", "lin", "bgy", "malpensa", "linate", "bergamo"),
    ("palma", "palma de mallorca", "pmi", "mallorca"),
    ("sevilla", "seville", "svq"),
    ("valencia", "vlc"),
    ("malaga", "agp"),
    ("bilbao", "bio"),
    ("berlin", "ber"),
    ("amsterdam", "ams", "schiphol"),
    ("dublin", "dub"),
    ("bruselas", "brussels", "bru"),
    ("munich", "muc"),
    ("frankfurt", "fra"),
    ("venecia", "venice", "vce"),
    ("napoles", "naples", "nap"),
    ("florencia", "florence", "flr"),
    ("oporto", "porto", "opo"),
    ("atenas", "athens", "ath"),
    ("estambul", "istanbul", "ist"),
    ("los angeles", "lax"),
    ("miami", "mia"),
    ("chicago", "ord"),
    ("boston", "bos"),
    ("san francisco", "sfo"),
    ("washington", "was", "iad", "dca"),
    ("mexico", "ciudad de mexico", "mexico city", "mex"),
    ("buenos aires", "eze"),
)
_ALIAS = {a: frozenset(g) for g in _PLACES for a in g}
#: Capitalised words that open a sentence or a card and never name a place.
_NOT_PLACE = NOT_A_SUBJECT | frozenset((
    "de", "desde", "a", "al", "from", "to", "the", "el", "la", "los", "las", "del", "en", "in", "on", "y", "and",
    "ida", "vuelta", "vuelo", "vuelos", "flight", "flights", "buscar", "search", "opcion", "option", "operado",
    "leaves", "arrives", "sale", "llega", "tren", "train", "bus", "eur", "usd", "gbp", "mxn",
    "ene", "feb", "mar", "abr", "ago", "sep", "sept", "oct", "nov", "dic", "jan", "apr", "jun", "jul", "aug", "dec",
    "lun", "mie", "jue", "vie", "sab", "dom", "mon", "tue", "wed", "thu", "fri", "sat", "sun",
))
_TRAVEL = re.compile(r"\b(vuelos?|vuela|volar|flights?|fly|tren(?:es)?|trains?|autobus(?:es)?|bus(?:es)?|ferry|"
                     r"ferries|aerolineas?|airlines?|nonstop|non-stop|escalas?|layovers?|ave)\b")
_DIRECT = re.compile(r"\b(direct[oa]s?|direct|sin escalas?|nonstop|non-stop|sin transbordos?)\b")
_STOPS = re.compile(r"\b(?:[1-9]|una?|dos|tres|one|two|three)\s+(?:escalas?|paradas?|transbordos?|stops?|layovers?)\b"
                    r"|\bcon escalas?\b|\bescala en\b|\blayover\b|\bconnecting\b|\bconnection in\b")
#: A place as a card writes it: a capitalised run («Nueva York», «New York»), or an airport code («MAD»), each
#: optionally followed by its codes in brackets («Logroño (RJL)», «Roma (FCO o CIA)»).
_PLACE = re.compile(r"(?P<name>[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+){0,2}|\b[A-Z]{3}\b)"
                    r"(?:\s*\((?P<codes>[A-Z]{3}(?:\s*(?:o|or|/|,|y|and)\s*[A-Z]{3})*)\))?")
_JOIN = re.compile(r"^\s*(?:→|->|⇄|↔|–|—|-|\ba\b|\bal\b|\bhasta\b|\bto\b)\s*$")
_FROM_BEFORE = re.compile(r"\b(?:de|desde|from)\s+$", re.I)
_CUT_AFTER_TO = re.compile(r"^\s*(?:(?:a|al|hasta|to)\s*)?…", re.I)


def _place(m: re.Match) -> tuple[frozenset, bool, str] | None:
    """(the names this mention can be called by, is it a KNOWN place, as written), or None when it is no place."""
    words = _asked.norm(m.group("name")).split()
    while words and words[0] in _NOT_PLACE and " ".join(words) not in _ALIAS:
        words.pop(0)                             # «Vuelos Madrid»: the card's first word is not the place
    name = " ".join(words)
    if not name:
        return None
    names = set(_ALIAS.get(name, {name}))
    for code in re.findall(r"[A-Z]{3}", m.group("codes") or ""):
        names |= _ALIAS.get(code.lower(), {code.lower()})
    return frozenset(names), name in _ALIAS or bool(names - {name}), " ".join(m.group("name").split()[-len(words):])


def _pairs(text: str) -> list[tuple]:
    """Every route the text states: (origin, destination or None, explicit «de A a B» form)."""
    raw = " ".join(str(text or "").split())
    marks = [(m, _place(m)) for m in _PLACE.finditer(raw)]
    marks = [(m, p) for m, p in marks if p]
    out = []
    for i, (m, p) in enumerate(marks):
        explicit = bool(_FROM_BEFORE.search(raw[:m.start()]))
        nxt = marks[i + 1] if i + 1 < len(marks) else None
        if nxt and _JOIN.match(raw[m.end():nxt[0].start()]):
            if not p[0] & nxt[1][0]:             # «Madrid-Barajas», «FCO–CIA»: one place, not a route
                out.append((p, nxt[1], explicit))
        elif explicit and _CUT_AFTER_TO.match(raw[m.end():]):
            out.append((p, None, True))          # «de Logroño (RJL) a…»: the card cut the destination
    return out


def asked_route(asked: str = "", context=()) -> dict:
    """The route he asked for: {"ends": (names A, names B), "direct": bool}, or {} when no route was asked.
    His own words first (the last route he said wins), then the sheet's title, goal and criteria."""
    texts = [str(asked or "")] + [str(t or "") for t in (context or ()) if t]
    if not _TRAVEL.search(_asked.norm(" ".join(texts))):
        return {}
    for text in texts:
        pairs = [(a, b) for a, b, _x in _pairs(text) if b]
        if pairs:
            a, b = pairs[-1] if text is texts[0] else pairs[0]
            return {"ends": (a[0], b[0]), "names": (a[2], b[2]),
                    "direct": bool(_DIRECT.search(_asked.norm(" ".join(texts))))}
    return {}


def not_places(subjects: list[str]) -> list[str]:
    """`subjects` without the places and the date abbreviations: a route's ends and «Nov 6» are not the subject a
    row must name. find-direct-flight-budget EN (2026-10-14): «(NYC-Rome)… dates Nov 6-8» read as the subjects
    «rome» / «nov», and a correction moved all twelve Google Flights rows — the €653 one he had just been told —
    to the Rejected tab."""
    return [s for s in subjects or [] if s not in _ALIAS and s not in _NOT_PLACE]


def _matches(names: frozenset, end: frozenset) -> bool:
    return bool(names & end)


def why_off(row: dict, route: dict, full_text: str = "") -> str:
    """Why this row is not the asked trip, or "" when nothing it states says so. `full_text` is the row as the
    worker sent it, before the card clipped it (the clip cut «a Madrid (MAD)» off the Logroño row)."""
    if not route:
        return ""
    text = full_text or " ".join(str(row.get(k) or "") for k in ("title", "subtitle"))
    a, b = route["ends"]
    asked = " – ".join(route.get("names") or ("?", "?"))
    for (o, o_known, o_name), dest, explicit in _pairs(text):
        if dest is None:
            if not (_matches(o, a) or _matches(o, b)):
                return f"a trip from {o_name}, not {asked}"
            continue
        d, d_known, d_name = dest
        fits = (_matches(o, a) and _matches(d, b)) or (_matches(o, b) and _matches(d, a))
        if not fits and (explicit or (o_known and d_known)):
            return f"the route {o_name} → {d_name}, not {asked}"
    if route.get("direct") and _STOPS.search(_asked.norm(text)):
        return "states stops, and a direct trip was asked"
    return ""


def _raw_text(item: dict, raw_items) -> str:
    """The unclipped title + subtitle of `item`, found in the payload by the clipped title's head."""
    head = str(item.get("title") or "").rstrip("…").strip()
    for r in raw_items or ():
        if isinstance(r, dict) and head and str(r.get("title") or "").startswith(head):
            return f"{r.get('title') or ''} {r.get('subtitle') or ''}"
    return ""


def split(on: list[dict], off: list[dict], asked: str = "", context=(), raw_items=None):
    """`category.split`'s (on, off) with the rows that are not the asked trip moved to `off` (with `why`)."""
    route = asked_route(asked, context)
    if not route:
        return on, off
    keep, out = [], list(off)
    for it in on:
        why = why_off(it, route, _raw_text(it, raw_items))
        if why:
            out.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            keep.append(it)
    return keep, out
