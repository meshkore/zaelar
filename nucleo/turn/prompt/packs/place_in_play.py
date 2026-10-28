"""While an errand he asked FOR A PLACE is running, the introduction does not ask where he lives.

search-restaurant-occasion EN (2026-10-14): «Find me a restaurant for an anniversary in Portland…» was running and
the introduction pack had the reply ask «where are you based these days?». His «San Francisco» then travelled into
the Portland errand (`nucleo/turn/our_question.py` closes that door). The question itself was the first half of the
damage: asked beside an errand that already names a place, «where are you?» reads as part of that errand. The
location stays on the pack's list; it waits for a turn with no such errand running.

A place is read the way a sentence marks one — a capitalised name after «in / en / near / cerca de» — or a known
place of `search.place_fit`. A false hit costs one turn without the question, never a wrong fact.
"""
from __future__ import annotations

import re

_MARKED = re.compile(r"\b(?:in|en|near|cerca de|around|por)\s+([A-ZÁÉÍÓÚÑ][\w'’-]+)")


def names_a_place(text: str) -> bool:
    """Does `text` (an errand's ask) name a place?"""
    t = str(text or "")
    if _MARKED.search(t):
        return True
    try:
        from search import place_fit as _pf
        return bool(_pf.asked_place(t))
    except Exception:  # noqa: BLE001 — the grammatical cue above is the reading; the table is a second one
        return False


def an_errand_names_a_place() -> bool:
    """Is one of his errands (live, starting or parked) about a named place? Never raises."""
    try:
        from nucleo.turn import named_errand as _ne
        from nucleo.turn.errands_of_a_turn import ask_of
        return any(names_a_place(ask_of(str(e.get("request") or ""))) for e in _ne.known())
    except Exception as e:  # noqa: BLE001 — unreadable errands: the pack asks as before
        from loguru import logger
        logger.debug(f"place_in_play: errands unreadable ({e!r})")
        return False
