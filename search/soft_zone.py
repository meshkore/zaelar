"""search/soft_zone.py — a neighbourhood he would LIKE, or a zone he names, is never a subject every row must name
(V2-782 T3.3).

search-rent-apartment ES (2026-10-14, sandbox 093858-es): «si puedes, mira por Ruzafa o el centro» reached the sheet
as the criteria change «zona: Ruzafa o el centro, bien comunicado». `asked.subjects` read «Ruzafa» as a proper name
the request asks ABOUT, and all three real Valencia flats from Fotocasa went to the Rejected tab «does not name
«ruzafa»». Same family in English: «an apartment in the Mission» made «mission» a subject.

A name is a ZONE, not a subject, when the request's own shape says so:
  · a zone label before it — «zona: Ruzafa», «barrio de Gràcia», «the area of Soho», «neighborhood: Mission»;
  · a zone word right after it — «the Mission district», «Ruzafa neighbourhood»;
  · an either-or with a quarter word — «Ruzafa o el centro», «downtown or the Mission»;
  · a SOFT clause — «si puedes», «preferiblemente», «a ser posible», «if possible», «ideally»: what he would like
    is at most an order on the list, never a filter.
A hard «solo en Ruzafa» is a place («en» already makes it one): an unknown neighbourhood is simply not judged by
the place gate (`place_fit`), so a row silent on it stays.
"""
from __future__ import annotations

import re

_ZONE_LABEL = re.compile(
    r"\b(?:zonas?|barrios?|distritos?|areas?|zones?|neighbou?rhoods?|districts?|quarters?|sectors?)\s*"
    r"(?::|-|de|del|of)?\s*(?:(?:el|la|los|las|the)\s+)?$", re.I)
_ZONE_AFTER = re.compile(r"^\s+(?:district|neighbou?rhood|area|barrio|quarter|distrito)\b", re.I)
_QUARTER = (r"(?:centro|casco antiguo|casco viejo|center|centre|downtown|midtown|uptown|old town|city center|"
            r"city centre|ciudad vieja)")
_OR = r"(?:o|u|or|y|and|,)"
_OR_QUARTER_AFTER = re.compile(rf"^\s*{_OR}\s+(?:(?:el|la|the)\s+)?{_QUARTER}\b", re.I)
_QUARTER_OR_BEFORE = re.compile(rf"\b{_QUARTER}\s*{_OR}\s+(?:(?:el|la|the|en|in|por)\s+)?$", re.I)
_SOFT = re.compile(
    r"\b(?:si puedes|si se puede|si es posible|a ser posible|si hay|preferiblemente|preferentemente|"
    r"idealmente|mejor si|mejor que sea|me gustaria|ojala|if possible|if you can|ideally|preferably|"
    r"would be nice|nice to have|bonus if|i'd prefer|i would prefer|i'd like it|better if)\b", re.I)
_CLAUSE = re.compile(r"[^,;.!?\n]+")


def _soft_spans(raw: str) -> list[tuple[int, int]]:
    """The spans of `raw` a soft marker governs: what follows it in its clause; the next clause when the marker
    stands alone («si puedes, mira por Ruzafa»); what precedes it when it closes a clause that is not the request
    itself («…, Ruzafa si puedes» — but never «Entradas de Rosalía si puedes», whose name IS the ask)."""
    clauses = [(m.start(), m.end()) for m in _CLAUSE.finditer(raw)]
    out: list[tuple[int, int]] = []
    for i, (a, b) in enumerate(clauses):
        hit = _SOFT.search(raw, a, b)
        if not hit:
            continue
        before, after = raw[a:hit.start()].split(), raw[hit.end():b].split()
        out.append((hit.start(), b))
        if len(after) < 2 and before and i > 0:
            out.append((a, hit.start()))
        if len(after) < 2 and len(before) < 2 and i + 1 < len(clauses):
            out.append(clauses[i + 1])
    return out


def is_zone(raw: str, start: int, end: int) -> bool:
    """Is the name at `raw[start:end]` a zone or a soft preference rather than a subject?"""
    before, after = raw[:start], raw[end:]
    if _ZONE_LABEL.search(before) or _ZONE_AFTER.match(after):
        return True
    if _OR_QUARTER_AFTER.match(after) or _QUARTER_OR_BEFORE.search(before):
        return True
    return any(a <= start < b for a, b in _soft_spans(raw))
