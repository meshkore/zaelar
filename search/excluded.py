"""search/excluded.py — every form a word he RULED OUT takes on a row (V2-782 T3.3).

hotel-under-15-days ES (2026-10-14): his «no hostales ni albergues» reached the sheet, and «Hostel Ikigai», «Urban Cube
Hostel Sevilla» and «The Nomad Hostel&Pension» stayed as candidates. Two gaps, both in how the excluded word was
matched: the Spanish plural in «-es» kept its «e» («hostale» never matches «hostal»), and the row named the same
kind of thing in English. A word now matches its singular and plural, and every member of its ES/EN family
(`category_words.SAME_THING`). Matched over accent-free lowercase text (`asked.norm`).
"""
from __future__ import annotations

import re

from search.category_words import SAME_THING


def _stems(word: str) -> set[str]:
    w = str(word or "").strip().lower()
    out = {w} if w else set()
    if len(w) > 4 and w.endswith("es"):
        out.add(w[:-2])                      # «hostales» → «hostal», «pensiones» → «pension»
    if len(w) > 3 and w.endswith("s"):
        out.add(w[:-1])                      # «maquetas» → «maqueta», «hostels» → «hostel»
    return out


def forms(word: str) -> set[str]:
    """The stems a row may carry for `word`: its own, and those of every family it belongs to."""
    out = _stems(word)
    for family in SAME_THING:
        if out & set(family):
            out |= set(family)
    return out


def named_in(word: str, text: str) -> bool:
    """Does `text` (accent-free, lowercase) carry `word` in any of its forms, singular or plural?"""
    alts = "|".join(re.escape(f) for f in sorted(forms(word), key=len, reverse=True))
    return bool(alts) and bool(re.search(rf"\b(?:{alts})(?:e?s)?\b", str(text or "")))
