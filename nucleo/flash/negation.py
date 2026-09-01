"""A NEGATED clause is not a promise — the shared clause arithmetic of the promise gates (V2-534 follow-up).

Measured over every firing of the promise gate in the operator's sessions (2026-08-17 -> 2026-09-01): four of
ten were «right now I do NOT have any task running» and siblings — the time adverb matched and the
negation sitting right next to it was ignored, so a status REPORT read as a commitment. The rule is
STRUCTURAL (a negator inside the SAME clause as the matched span), never a phrase list (V2-095 measured what
hand-tuning those lists costs). Clause-bounded on purpose, in both directions: «No, I'll look at it right now»
still promises (the «no» answers the PREVIOUS clause), and «I'll get on it, don't worry» is not
un-promised by its neighbour. `nada` is deliberately NOT a negator: «I'll look at it in no time» is a promise, and
losing one is the expensive direction (six measured minutes of silence, V2-049).

Both promise gates read this ONE module — `router_guards.promises_action` and
`promise_backstop.committed` — because two copies of this decision is how the last one drifted (V2-252).
It operates on ALREADY-NORMALIZED text (accents stripped, lowercased): each gate passes its own norm.
"""
from __future__ import annotations

import re as _re

_NEGATOR_RE = _re.compile(r"\b(no|ni|tampoco|nunca|jamas|ningun\w*)\b")
_CLAUSE_BREAKS = ".,;:!?¿¡()\n"


def clause_negated(normalized: str, start: int, end: int) -> bool:
    """True if the clause containing [start:end) of an already-normalized text carries a negator."""
    lo = max([normalized.rfind(c, 0, start) for c in _CLAUSE_BREAKS] + [-1]) + 1
    his = [i for i in (normalized.find(c, end) for c in _CLAUSE_BREAKS) if i != -1]
    hi = min(his) if his else len(normalized)
    return bool(_NEGATOR_RE.search(normalized[lo:hi]))


def unnegated_match(rx, normalized: str) -> bool:
    """Any match of `rx` whose own clause is NOT negated."""
    return any(not clause_negated(normalized, m.start(), m.end()) for m in rx.finditer(normalized))
