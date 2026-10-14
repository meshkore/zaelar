"""Which turns a phase pack RODE — so a later reader knows a question in the reply was the phase's, not the errand's.

search-restaurant-occasion EN (2026-10-14): the introduction pack rode «ok, let me know» and the reply asked «where
are you based these days?». His «San Francisco. ok, let me know when you have options» was then read as a
refinement of the live Portland errand and injected into it; the worker searched San Francisco. A question the
phase asked is ours (`nucleo/turn/our_question.py`); this module only remembers when the phase was in the prompt.
"""
from __future__ import annotations

from collections import deque

#: (his words, whether a pack rode that turn) — the last few turns, newest last.
_TURNS: deque = deque(maxlen=8)


def _key(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def note(turn_text: str, rode: bool) -> None:
    """Record that a pack did (or did not) ride the turn of `turn_text`. The same words twice keep the last call."""
    k = _key(turn_text)
    if not k:
        return
    if _TURNS and _TURNS[-1][0] == k:
        _TURNS.pop()
    _TURNS.append((k, bool(rode)))


def before(turn_text: str) -> bool:
    """Did a pack ride the turn just BEFORE the one whose words are `turn_text`?"""
    k = _key(turn_text)
    prior = [r for t, r in _TURNS if t != k]
    return bool(prior and prior[-1])


def forget() -> None:
    _TURNS.clear()
