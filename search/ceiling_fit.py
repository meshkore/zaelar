"""search/ceiling_fit.py — a row priced ABOVE the ceiling he stated is not a candidate (V2-782 T3.3).

search-buy-laptop ES (2026-10-14): «Búscame un MacBook Pro M5 por menos de 1.800 euros». Twice the turn offered
three rows, all above it (2.229 €, 1.999 €, 2.949 €; then 1.899 €, 3.099 €, 2.539 €), as valid options — after he
had already said «esos están por encima de 1.800, no me sirven». `category.py` only used the ceiling as a FLOOR
(a 30 € «car» is not a car); nothing read it as the ceiling it is.

A ceiling is read only where he BOUNDED a price: «menos de / hasta / no más de / máximo / por debajo de / que no
pase de / entre X y Y», «under / up to / no more than / at most / below / max / budget of», with a currency next to
the number or a number of at least 100 that no unit follows («menos de 50.000 km», «hasta 27"» are not prices). A
correction that says rows are ABOVE a number and do not serve («se pasan de 1.800, no me sirven») states it too.
His own words first, the last ceiling he said wins; the sheet's title and criteria only when he said none.

A row is off when its price is parseable, in the same currency (an unmarked price is the sheet's own), and its
LOWEST stated amount is more than `TOLERANCE` above the ceiling. A row without a price stays. A per-unit ceiling
(«a month», «por noche») compares only rows in the same unit; a per-night ceiling never judges an unmarked price,
which on a booking site is usually the stay's total.
"""
from __future__ import annotations

import re

from search import asked as _asked

TOLERANCE = 0.03
_NUM = r"(?P<n>\d(?:[\d.,]*\d)?(?:\s*(?:mil|k)\b)?)"
_CUR = r"(?:€|\$|£|(?:euros?|eur|usd|dolares|dollars|bucks|libras|pounds|gbp)\b)"
_BOUND = (r"(?<![a-z])(?:por menos de|menos de|no mas de|no pase de|no supere|que no pase de|por debajo de|como mucho|"
          r"como maximo|maximo(?: de)?|max\.?|tope de|presupuesto de|hasta|under|below|less than|up to|no more than|"
          r"at most|maximum(?: of)?|budget of|budget is|cap of|<|<=|≤)")
_STATED = re.compile(rf"{_BOUND}\s*(?:de\s+)?(?:(?P<c1>{_CUR})\s?)?{_NUM}(?:\s?(?P<c2>{_CUR}))?")
_BETWEEN = re.compile(rf"\b(?:entre|between)\s+(?:{_CUR}\s?)?\d[\d.,]*\s?(?:{_CUR})?\s+(?:y|and|-)\s+"
                      rf"(?:(?P<c1>{_CUR})\s?)?{_NUM}(?:\s?(?P<c2>{_CUR}))?")
_ABOVE = re.compile(rf"(?<![a-z])(?:por encima de|se pasan? de|pasan? de|superan?|above|over|more than|mas de|exceeds?)\s+"
                    rf"(?:(?P<c1>{_CUR})\s?)?{_NUM}(?:\s?(?P<c2>{_CUR}))?")
_REFUSED = re.compile(r"\bno (?:me )?(?:sirven?|valen?|interesan?)\b|demasiado caros?|\btoo (?:expensive|much)\b|"
                      r"out of (?:my )?budget|fuera de(?:l| mi)? presupuesto|don'?t work|\bno good\b|\bdescarta\w*|\bdiscard\w*")
#: A bare number followed by a noun counts that noun («50.000 km», «27 pulgadas», «100 reviews»): not a price. Only
#: the connectors a price is followed by («hasta 1.200 al mes», «under 1,900 a month», «1.800, no me sirven») pass.
_QTY_AFTER = re.compile(r"^\s*(?:[\"%”'x]|(?!(?:y|e|o|u|and|or|no|ni|al|a|en|el|la|por|per|each|cada|the|que|pero|"
                        r"but|con|with|for|para|de|del|mensuales?|monthly|tops)\b)[a-z])")
_PER = re.compile(r"(?:\b(?:al|a|por|per|each|cada|every)\s+|/\s*)(?P<u>mes|month|mo|noche|night|nt|semana|week|wk|"
                  r"dia|day|persona|person|pax|ano|year|yr)\b|\b(?P<t>total|en total|in total)\b")
_UNITS = {"mes": "month", "month": "month", "mo": "month", "noche": "night", "night": "night", "nt": "night",
          "semana": "week", "week": "week", "wk": "week", "dia": "day", "day": "day", "persona": "person",
          "person": "person", "pax": "person", "ano": "year", "year": "year", "yr": "year"}


def _currency(text: str) -> str:
    t = str(text or "").lower()
    if "€" in t or re.search(r"\beur(?:os?)?\b", t):
        return "EUR"
    if "£" in t or re.search(r"\b(?:gbp|libras|pounds)\b", t):
        return "GBP"
    if "$" in t or re.search(r"\b(?:usd|dolares|dollars|bucks)\b", t):
        return "USD"
    return ""


def _unit(text: str) -> str:
    """The unit a price is stated in («a month», «/noche», «total»), "" when none."""
    m = _PER.search(text[:24])
    if not m:
        return ""
    return "total" if m.group("t") else _UNITS.get(m.group("u"), "")


def _read(m: re.Match, text: str) -> dict | None:
    """The ceiling one match states, or None when the number is not a price."""
    cur = m.group("c1") or m.group("c2") or ""
    tail = text[m.end():]
    if not cur and _QTY_AFTER.match(tail):
        return None
    value = _asked.amount(m.group("n"))
    if not value or (not cur and value < 100):
        return None
    return {"value": value, "currency": _currency(cur), "unit": _unit(tail)}


def _stated(text: str) -> dict | None:
    """The LAST ceiling `text` states, or None."""
    t = _asked.norm(text)
    found: list[tuple[int, dict]] = []
    for rx in (_STATED, _BETWEEN):
        found += [(m.start(), c) for m in rx.finditer(t) if (c := _read(m, t))]
    if _REFUSED.search(t):
        found += [(m.start(), c) for m in _ABOVE.finditer(t) if (c := _read(m, t))]
    if not found:
        return None
    ceiling = max(found, key=lambda x: x[0])[1]
    if not ceiling["currency"]:
        ceiling["currency"] = _currency(t)
    return ceiling


def asked_ceiling(asked: str = "", context=()) -> dict | None:
    """{"value", "currency", "unit"} of the price ceiling he stated (his words first), or None."""
    own = _stated(asked)
    if own:
        return own
    for text in context or ():
        got = _stated(str(text or ""))
        if got:
            return got
    return None


def _row_amounts(price: str, ceiling: float) -> list[float]:
    """Every amount a price field states, minus the small ones (instalments, percentages)."""
    out = []
    for m in re.finditer(r"\d[\d.,]*(?:\s*(?:mil|k)\b)?", price):
        if price[m.end():m.end() + 1] == "%":
            continue
        v = _asked.amount(m.group(0))
        if v and v >= ceiling * 0.05:
            out.append(v)
    return out


def why_off(row: dict, ceiling: dict | None) -> str:
    """Why this row's price breaks the ceiling, or "" when it does not (or cannot be compared)."""
    price = str(row.get("price") or "").strip()
    if not ceiling or not price:
        return ""
    cur = _currency(price)
    if cur and ceiling["currency"] and cur != ceiling["currency"]:
        return ""
    unit, want = _unit(_asked.norm(price)), ceiling["unit"]
    if want and (unit != want if unit else want == "night"):
        return ""
    if not want and unit == "total":
        unit = ""
    amounts = _row_amounts(_asked.norm(price), ceiling["value"])
    if not amounts or min(amounts) <= ceiling["value"] * (1 + TOLERANCE):
        return ""
    return f"priced {price[:40]}, above the {ceiling['value']:,.0f} ceiling he set"


def split(on: list[dict], off: list[dict], asked: str = "", context=()):
    """The (on, off) of the gates before, with the rows priced above his ceiling moved to `off` (with `why`)."""
    ceiling = asked_ceiling(asked, context)
    if not ceiling:
        return on, off
    keep, out = [], list(off)
    for it in on:
        why = why_off(it, ceiling)
        if why:
            out.append({"title": it.get("title", ""), "url": it.get("url", ""), "why": why[:200]})
        else:
            keep.append(it)
    return keep, out
