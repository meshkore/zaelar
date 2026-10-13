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


def held(spoken: str, *, already: bool, brief=None) -> str:
    """Why a further delivery is NOT owed to this reply ("" = it is). `already` = this errand's rows were
    delivered by the backstop before, in this conversation; `brief` = the turn's verdicts, when there are any."""
    if not already or not str(spoken or "").strip():
        return ""                       # a first delivery, or a mute turn: the rows are all there is to say
    if waits_for_words(brief):
        return ""
    from .delivery import _WAITING_REPLY_RE
    from .router_guards import _norm_txt
    if _WAITING_REPLY_RE.search(_norm_txt(str(spoken or ""))):
        return ""
    return "rows already delivered once, and this reply answers something of its own"


def waits_for_words(brief) -> bool:
    """HIS turn waits to be told something about the work — «keep me posted», «any news?», a goodbye — and orders
    none: the brief reads `wants_words=tell` and does not send the turn to a worker.

    cheapest-monitor EN (2026-10-14): after a first tail of three power adapters, «ok sounds good, keep me posted»
    got «Will do — I'll ping you the moment I've got real monitors to show», with «Monitor AGEX 27" 4K — 179.99»
    unannounced in the prompt. The reply was a wait in words this file does not list — and listing wait wordings is
    the race V2-364 already lost. What makes the rows owed is his turn, not the reply's vocabulary; only rows never
    announced ride it, and a sentence about a row or another errand is held before this is asked."""
    if brief is None:
        return False
    try:
        from nucleo.flash import turn_brief as _tb
        words, _ = _tb.read(brief, _tb.WORDS_KEY, "")
        route, _ = _tb.read(brief, _tb.ESCALATE_KEY, "", min_confidence=0.0)
        return str(words) == "tell" and str(route) != "escalate"
    except Exception:  # noqa: BLE001 — without verdicts the reply's own wording decides, as before
        return False
