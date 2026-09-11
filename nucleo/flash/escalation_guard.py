"""nucleo/flash/escalation_guard.py — the two non-reasoner failures that must become an errand.

Extracted from the voice provider on 2026-09-11 paying the architecture ratchet (V2-677 pushed
`nucleo.py` over its ceiling, and the table calls for extracting a concern rather than raising a number).
The extraction also SINGLE-SOURCES a decision the probe was mirroring by hand — V2-252's parallel-
implementation rule, applied instead of maintained.

GUARD MARKETPLACE → NAVEGAR + MODIFICAR-WIDGET → GENERADOR (V2-057, 2026-07-21): two RELIABLE failure
modes of the fast non-reasoning model. (a) a NAMED marketplace plus an intent to search demands entering
and driving the catalogue (a worker), not one datum from `web_search`. (b) changing a widget's CODE or
appearance (colour, column, style) is the generator's work, not a data-op and not an «I can't». In both,
when the turn neither escalated nor touched another tool, it escalates.
"""
from __future__ import annotations


def escalation_text(operator_text: str, turn_text: str) -> str:
    """The errand to escalate, or "" — read from the OPERATOR'S WORDS, never the composed turn.

    V2-677. `turn_text` carries the `[SISTEMA]` notes glued on by `brain_notes.compose_turn`, and MEASURED
    live (session e896f596, 23:16:36) that was enough to spawn a real `claude_code` worker off the KICKOFF
    GREETING: the three words that satisfied `looks_like_modify_widget` were «añade» (from our own «añade
    en una frase lo que sigue»), «fondo» (from «La tarea de fondo…») and «panel» (from «Lo tienes en el
    panel de estado») — not one of them the operator's. That worker ran for fifty seconds and came back
    with a Spanish greeting into an English session.

    A high-precision guard reading the wrong text is a coin flip, and this one spends money. `operator_
    words` exists for exactly this, and its own docstring tells the same story one backstop over: a late
    recall note became the errand, and an appointment with a traumatologist came back as a PLUMBER
    (V2-534). The rule is not about any one note — **a system note is context; it can never be the thing
    to go and do.**
    """
    from . import router as _router
    words = _router.operator_words(operator_text, turn_text)
    if _router.looks_like_marketplace_nav(words) or _router.looks_like_modify_widget(words):
        return words
    return ""
