"""nucleo/flash/row_named.py — did HIS sentence name a row of the sheet? Only by a word that row alone carries.

Two readers asked this with a token test that any category word passed (2026-10-14):
  · `delivery.sheet_delivery_backstop` skipped «a row he named» (V2-781 T521) by SUBSTRING over everything he had said:
    in cheapest-monitor EN «monitor» («my work monitor is dying») and «27» («27-inch») marked «Monitor AGEX 27" 4K —
    179.99» and «LG 27UD68 27" 4K» as already his, so the only rows ever offered were three power adapters, and the
    real monitors sat in the prompt unsaid; in best-plumber-same-day ES «fontanero», «Madrid» and «24» («24h») did the
    same to all three plumbers at his goodbye;
  · `delivery._not_owed` held the delivery on «he named a row» for «I'm after a 27-inch 4K monitor».

A row is NAMED by a word that tells it apart: a word of its title no OTHER row of the sheet shares and that is not his
errand's own vocabulary — compared by a six-letter stem, so «fontanero» meets «fontaneros». Pure numbers never name a
row (a size, a price, a year is a criterion); a model code (letters and digits, four or more) does; a plain word needs
five letters. Matched as a whole word.
"""
from __future__ import annotations

import re
import unicodedata

_STEM = 6


def _words(text) -> list[str]:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.findall(r"[a-z0-9]+", t)


def _title(row) -> str:
    return str(row or "").split(" — ")[0].strip("«» ")


def _significant(w: str) -> bool:
    digits = any(c.isdigit() for c in w)
    if digits:
        return not w.isdigit() and len(w) >= 4 and any(c.isalpha() for c in w)
    return len(w) >= 5


def own_words(row, rows, errand: str = "") -> list[str]:
    """The words of `row`'s title that tell it apart from every other row of `rows` and from `errand`."""
    me = _title(row)
    taken = {w[:_STEM] for w in _words(errand)}
    for other in rows or []:
        if _title(other) != me:
            taken |= {w[:_STEM] for w in _words(_title(other))}
    return [w for w in _words(me) if _significant(w) and w[:_STEM] not in taken]


def by_him(text: str, row, rows, errand: str = "") -> bool:
    """Does `text` name `row` (one of `rows`) by a word only that row carries?"""
    said = set(_words(text))
    return any(w in said for w in own_words(row, rows, errand))
