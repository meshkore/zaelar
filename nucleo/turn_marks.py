"""What a turn has ALREADY put in front of the model — and therefore must not be put in front of it again.

The prompt has several faces that say «tell it to them THE FIRST TIME» (a task's death, the offer to stop it)
and the model **cannot know whether it is the first**: that is OUR fact. V2-224 learned this with the death
notice —the same anti-repetition clause failed in BOTH opposite directions in two rounds of the same
commit— and the conclusion was that «did I already tell it?» is not deduced from the window; it is counted.

It lives separately because it is its own concern and `dispatch` is a capped god-file: the ratchet asked to
extract a module instead of making it bigger, and it was right. It is re-exported from `dispatch` so callers
can continue asking for it through the usual facade.

**The rule governing all its tenants, from V2-224, is: silencing repetition is NOT silencing state.**
What stops being given is the NOTICE; the fact —it is still dead, it is still not progressing, and since when— remains.
"""
from __future__ import annotations

_STALL_OFFERED: dict[str, int] = {}


def mark_stall_offered(task_ids) -> None:
    """A turn has already carried the OFFER TO STOP this task in front of the model (V2-454).

    Exact sibling of `mark_death_reported`, and for the same reason: the block says «say it in those words **the
    first time** it comes up and offer to stop it», and the model **cannot know whether it is the first** — that
    is OUR fact, not something deduced from the window. Without counting it, the offer is rendered on every
    turn while the task remains stuck and the turn repeats it: measured across the 334 saved rounds,
    **49 (14 %) repeat the offer to stop two or more times**, including ten of the last fifteen on 2026-08-28.

    The harm is not the redundancy: the operator HAS ALREADY ANSWERED. In `search-buy-used-car` (10:57) they
    said «stop it and try again, or we can look elsewhere; you decide», and the next turn raised the same
    dilemma again — the judge marked it as a blocker [high].

    And the rule governing the wording is the one V2-224 left behind: **silencing repetition is not silencing
    state.** The FACT (it is still not progressing, and since when) remains; what stops being given is the offer.
    """
    for tid in (task_ids or []):
        t = str(tid)
        _STALL_OFFERED[t] = int(_STALL_OFFERED.get(t) or 0) + 1


def stall_offered(task_id) -> int:
    """How many turns have already carried the offer to stop THIS task."""
    return int(_STALL_OFFERED.get(str(task_id)) or 0)

