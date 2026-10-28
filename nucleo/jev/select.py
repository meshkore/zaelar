"""Jev SELECTION over parsed data (V2-726 F4): which of a list of candidates fits a criterion, in one round trip
(`select_many`, `select_many_status`). Moved out of `nucleo/jev.py` (refactor2710-07); calls the client through the
package, so a patch on `nucleo.jev` governs it."""
from __future__ import annotations

from nucleo import jev as _j

# Measured 2026-09-20 over 100 synthetic listings: ONE trip, 1 041 ms, recall 3/3, false positives all under 0.33.
# ⚠️ Each candidate's identity travels INSIDE its own question: over a shared state alone, ten identical questions all
# answered `strong` at 0.82-0.89 (a 125cc Vespa in a motocross search) — confidently wrong, so no caller builds them.
FIT = {
    "strong": "meets every criterion",
    "partial": "meets some criteria but fails at least one",
    "no": "fails the core criteria",
}


def select_many(candidates, criteria: str, *, key=None, label=None,
                timeout_s: float | None = None, min_confidence: float = _j.MIN_CONFIDENCE) -> list:
    """Score N candidates against `criteria` in ONE trip. Off the voice path by design.

    `candidates` is any sequence; `label(c)` renders one as text (default `str`) and `key(c)` names
    it in the result (default its index). Returns the ones that fit, best first:

        [{"key", "candidate", "fit", "confidence"}]

    Only `strong` verdicts at or above `min_confidence` are returned — «partial» is a shrug and an
    unsure «strong» is the false-positive band the measurement found. Returns [] when disabled, on
    any failure, or when nothing fits: the caller keeps whatever it would have done, as everywhere
    else in this module. Raises `JevBriefTooBig` past `MAX_QUESTIONS` rather than truncating, so a
    caller with a thousand rows pages them instead of silently scoring the first hundred.
    """
    return select_many_status(candidates, criteria, key=key, label=label, timeout_s=timeout_s,
                              min_confidence=min_confidence)[0]


#: What a selection round can END as. `[]` said all five of these at once, and the caller could not
#: tell «nothing fits» (a real answer, act on it) from «the service was not there» (no answer, ask).
#: V2-726 A6a gives them names; A1 generalises them to every bounded decision in the engine.
SELECTED, NO_MATCH, UNAVAILABLE, DISABLED, EMPTY = (
    "selected", "no_match", "unavailable", "disabled", "empty")


def select_many_status(candidates, criteria: str, *, key=None, label=None,
                       timeout_s: float | None = None,
                       min_confidence: float = _j.MIN_CONFIDENCE) -> tuple[list, str]:
    """`select_many` plus the STATUS of the round: `(rows, status)`.

    The audit's finding 8, and it is the difference between two opposite behaviours: with nothing to
    offer, `task_recall` must SAY «nothing like it» when the chooser ran and rejected everything, and
    must ASK when the chooser never ran. Both looked like `[]`.
    """
    items = list(candidates or [])
    if not items or not (criteria or "").strip():
        return [], EMPTY
    if not _j.enabled():
        return [], DISABLED
    _label = label or (lambda c: str(c))
    _key = key or (lambda c: items.index(c))
    questions = {}
    index = {}
    for n, cand in enumerate(items, 1):
        qid = f"cand_{n}"
        index[qid] = cand
        questions[qid] = {
            # The identity goes HERE, in this candidate's own question — see the trap above.
            "instructions": f"CANDIDATE {n}: «{_label(cand)}». Against the criteria in the state, "
                            f"how well does THIS candidate fit?",
            "criteria": dict(FIT),
        }
    verdicts = _j.choose_many_sync(criteria, questions, timeout_s=timeout_s, question_id="select")
    if not verdicts:
        return [], UNAVAILABLE          # network, timeout, open breaker: the chooser never ran
    out = []
    for qid, cand in index.items():
        v = verdicts.get(qid) or {}
        if v.get("choice") == "strong" and v.get("confidence", 0.0) >= min_confidence:
            out.append({"key": _key(cand), "candidate": cand, "fit": "strong",
                        "confidence": v.get("confidence", 0.0)})
    out.sort(key=lambda r: -r["confidence"])
    return out, (SELECTED if out else NO_MATCH)
