"""What a turn's admission and its discard say about it, by trace (V2-844 F2) — read by the doors that act on it.

Two marks, written where they are known and read where a door decides:

  · CUT — the turn arrived with a cut, unanswered sentence in front of it (`accumulator.whole_turn` joined them for
    the verdict). Its joined request and the tail he said are kept: an errand this turn names by the tail alone («Okay.»,
    «Sorry.») is about the joined request (`errand.whole_request`).
  · DISCARDED — the turn was dropped unanswered (`NucleoLLMStream._note_death`). It acts on nothing any more: its
    launches belong to the turn that superseded it, which carries the joined request.

Bounded RAM, short-lived on purpose: a turn's side effects land within seconds of it.
"""
from __future__ import annotations

import time

#: How long a turn's marks are read. The measured late write came 2.7 s after the discard; a minute covers a slow pass.
TTL_S = 120.0
_MAX = 256
_CUT: dict[str, tuple] = {}        # trace -> (when, joined request, his tail)
_DISCARDED: dict[str, float] = {}  # trace -> when


def _bound(d: dict) -> None:
    while len(d) > _MAX:
        d.pop(next(iter(d)))


def cut(trace: str, joined: str, tail: str) -> None:
    """The turn `trace` was admitted as `tail` with a cut sentence joined in front of it (`joined`)."""
    if trace and str(joined or "").strip():
        _CUT[trace] = (time.time(), str(joined).strip(), str(tail or "").strip())
        _bound(_CUT)


def cut_of(trace: str) -> tuple[str, str]:
    """(joined request, his tail) of a cut turn, or ("", "") for a turn that was not cut (or too old to say)."""
    v = _CUT.get(str(trace or ""))
    if not v or time.time() - v[0] > TTL_S:
        return "", ""
    return v[1], v[2]


def discarded(trace: str) -> None:
    if trace:
        _DISCARDED[trace] = time.time()
        _bound(_DISCARDED)


def was_discarded(trace: str) -> bool:
    at = _DISCARDED.get(str(trace or ""))
    return bool(at) and time.time() - at <= TTL_S


def reset() -> None:
    _CUT.clear()
    _DISCARDED.clear()
