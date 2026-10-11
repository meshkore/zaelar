"""nucleo/flash/delivery_repeat.py — the sheet's rows are delivered ONCE as a tail; after that, only on a wait.

Measured in `rental-car-automatic-airport` (2026-10-11, ES and EN, one errand live). «Bueno, de hecho ya hay
candidatos en la hoja de resultados: … Dime si alguno te encaja o sigo afinando.» was glued to four replies in a row,
with only the prices changing — and three of those replies were ANSWERS to his direct question («¿el Polo es
automático y en el aeropuerto?», «are these automatic?»). The backstop already held a second delivery when several
errands were live (`delivery._not_owed`, three-tasks-at-once), but with ONE errand nothing held it: every turn found
three rows it had not announced yet (twelve on the sheet, three per tail), so every turn got the tail.

What the backstop exists for is a reply that leaves him with NOTHING while the sheet has rows (V2-305: five «te
aviso» in a row with 27 candidates written). A reply that answers his question is not that reply, whatever its
length or vocabulary. So the rule is about the backstop's own history, not about his words: the first delivery of
an errand goes out as before; after it, more rows ride a reply only when that reply is a pure WAIT — the case the
backstop was written for — and a reply that is saying something of its own keeps the turn to itself.
"""
from __future__ import annotations


def held(spoken: str, *, already: bool) -> str:
    """Why a further delivery is NOT owed to this reply ("" = it is). `already` = this errand's rows were
    delivered by the backstop before, in this conversation."""
    if not already or not str(spoken or "").strip():
        return ""                       # a first delivery, or a mute turn: the rows are all there is to say
    from .delivery import _WAITING_REPLY_RE
    from .router_guards import _norm_txt
    if _WAITING_REPLY_RE.search(_norm_txt(str(spoken or ""))):
        return ""
    return "rows already delivered once, and this reply answers something of its own"
