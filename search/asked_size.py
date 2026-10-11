"""search/asked_size.py — a size the request states as a MINIMUM: «de 27 al menos», «27 o más», «at least 27 inches».

three-tasks-at-once (ES/EN, 2026-10-11 11:34). He said «el monitor, que sea de 27 al menos» and «has to be at least 27
inches»; the shortlist then delivered an LG 24", a BenQ 24" and an Asus 23,8" as its top three. `asked.size_inches`
needs a unit, so «27 al menos» read as no size at all, and when a unit was there the gate read it as an EXACT size —
a 32" would have been rejected for a «27 or bigger» ask. A floor is its own reading: a row under it is off, a row
over it is a candidate.

Shape only (a two-digit number beside a minimum marker), ES and EN. A number followed by a currency is a price,
never a size.
"""
from __future__ import annotations

import re

from search.asked import norm

_CUR = r"(?:€|\$|£|eur|euros?|usd|dolares|dollars|bucks)"
_UNIT = r"(?:\s?(?:\"|''|”|pulgadas|inch(?:es)?|in\b|-inch))?"
_BEFORE = re.compile(rf"\b(?:al menos|como minimo|minimo|at least|minimum|min\.?|no menos de|not under|no smaller than)"
                     rf"\s+(?:de\s+|of\s+)?(\d{{2}}){_UNIT}(?!\s?[\d.,]*\s?{_CUR})")
_AFTER = re.compile(rf"\b(\d{{2}}){_UNIT}\s*(?:o mas|al menos|como minimo|para arriba|en adelante|or (?:more|bigger|"
                    rf"larger|above|up)|and (?:up|above|bigger)|\+|plus|minimum|min\b)")


def size_floor(text) -> int | None:
    """The minimum screen-style size the text states, or None. Bounded to 10–99: «al menos 150 €» is a price."""
    t = norm(text)
    for rx in (_BEFORE, _AFTER):
        for m in rx.finditer(t):
            tail = t[m.end(1):m.end(1) + 8]
            if re.match(rf"\s?{_CUR}", tail):
                continue
            v = int(m.group(1))
            if 10 <= v <= 99:
                return v
    return None
