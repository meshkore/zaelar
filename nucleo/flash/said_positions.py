"""Rows his sentence names FROM THE END, and a row he named and then took back.

Use case `la-cola-de-video-con-palabras-imprecisas` (ES, 2026-10-11): «el último… no, el penúltimo, ponlo justo
después del de skills». Two readings were missing, and without them the move had no item to fill:
  · «penúltimo» / «penultimate» / «second to last» is a row counted from the end, like «last» — the one ordinal
    table (`widgets.refs._ORDINALS`) now carries them, and this reads them as rows of the list in front of him;
  · «X… no, Y» is a self-correction: the row he named first is withdrawn, so it is not one of the rows of the
    order. Only a bare correction between two named rows counts («no», «I mean», «sorry»), so a sentence that
    names three rows for real is still three rows — never one order guessed out of them.
Both are closed classes, read off normalized text (`widgets.refs._norm`); nothing here is a verb table.
"""
from __future__ import annotations

#: Words that withdraw the row named just before them.
_RETRACTORS = frozenset("no digo perdon sorry mean rather wait espera".split())
#: Words that may sit around a correction without saying anything else: «el último… no, EL penúltimo».
_AROUND = frozenset("el la lo los las the a an one i mejor quiero decir o sea oh vale ok actually".split())


def from_end_mentions(toks: list[tuple[int, str]], n: int) -> list[tuple[int, int]]:
    """`(offset, row)` (1-based) of every from-the-end word in `toks` («last», «penúltimo») over `n` rows."""
    from widgets import refs as _refs
    out = []
    for off, t in toks:
        idx = _refs.from_end_index(t, n)
        if idx is not None:
            out.append((off, idx + 1))
    return out


def drop_retracted(mentions: list[tuple[int, int]], norm: str) -> list[tuple[int, int]]:
    """`mentions` (sorted by offset) without each row a bare correction withdrew before the next one."""
    keep = []
    for i, (off, row) in enumerate(mentions):
        if i + 1 < len(mentions):
            between = norm[off:mentions[i + 1][0]].split()[1:]    # past the word that named this row
            if between and set(between) & _RETRACTORS and set(between) <= _RETRACTORS | _AROUND:
                continue
        keep.append((off, row))
    return keep
