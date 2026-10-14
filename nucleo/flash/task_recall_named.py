"""nucleo/flash/task_recall_named.py — a past errand he NAMES by a word only it has is that errand.

Measured on `flat-hunt-recall-the-report__es` (2026-10-14): two finished flat hunts were on file (Gràcia and Sant
Antoni) and he said «el de Gràcia». The index handed both to the chooser, which scored the right one `strong` at a
confidence of 0.19 — under the 0.5 floor — so nothing was picked and the turn asked him again, four times, for a
word he had already said. The model was not needed: «gracia» appears in ONE candidate's title and in no
other's, which is the index answering the question on its own.

The rule, lexical and without a model (INI-027 §7 — the index narrows, a model only chooses): a word of his that
appears in exactly one candidate's TITLE is DISTINCTIVE. When every distinctive word he said points at the
same candidate, that is the one. Words both candidates share («piso», «alquiler», «apartment») tell nothing apart
and are ignored; distinctive words pointing at two different candidates are a contradiction, and contradiction is
a question, never a pick.

The TITLE and not the goal, on purpose: the title is what he sees on the board and the name he calls it by, while
a goal carries the incidental words of the request — «apartment … under $3,200/month» would make «the one I told
you about last MONTH» a pick. The goal stands in only for a row that has no title.
"""
from __future__ import annotations

import re
import unicodedata

#: Shorter words are grammar («que», «del», «the», «you»), not names. Four keeps «sant», «soho», «gracia».
MIN_WORD = 4


def words(text: str) -> set[str]:
    """Lower-cased, accent-folded words of at least `MIN_WORD` letters — «Gràcia» and «gracia» are one word."""
    folded = unicodedata.normalize("NFKD", str(text or "").lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", folded) if len(w) >= MIN_WORD}


def named(rows: list[dict], *texts: str) -> dict | None:
    """The one candidate his words name by a word only it has, or None.

    None with fewer than two candidates (nothing to tell apart), when no word of his is distinctive, and when
    his distinctive words point at different candidates."""
    if len(rows) < 2:
        return None
    said: set[str] = set()
    for t in texts:
        said |= words(t)
    bags = [words(r.get("title") or r.get("goal") or "") for r in rows]
    hits = set()
    for w in said:
        owners = [n for n, bag in enumerate(bags) if w in bag]
        if len(owners) == 1:
            hits.add(owners[0])
    return rows[hits.pop()] if len(hits) == 1 else None
