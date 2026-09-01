"""Does the reply ASK THE OPERATOR for something it needs before it can act?

Apart from `router_guards.py` on purpose. That module's header promises "a pure, self-contained text classifier
over normalized (accent-stripped) input", and this one needs the accents: in Spanish the interrogative carries
the accent («¿a qué ciudad?») and the conjunction does not («te aviso cuando lo tenga»). Strip them and every
courtesy question turns into a request for information — so it does not belong in a file whose contract is to
strip them.
"""
from __future__ import annotations

import re as _re

# A reply that ASKS THE OPERATOR for the detail it is missing. The accents are the signal, so this is the one
# guard in this file that does NOT normalize its input: in Spanish the interrogative carries the accent («¿a qué
# ciudad?») and the conjunction does not («te aviso cuando lo tenga»). Stripping accents would collapse the two
# and make every courtesy question look like a request for information.
_ASKS_DETAIL_RE = _re.compile(
    # a question containing an interrogative word: «¿Los precios de qué?» / «¿a qué ciudad quieres ir?»
    r"[^.!?]*\b(qué|cuál|cuáles|dónde|cuándo|cuánto|cuánta|cuántos|cuántas|quién|quiénes|cómo)\b[^.!?]*\?"
    r"|[^.!?]*\b(what|which|where|who|how much|how many)\b[^.!?]*\?"
    # …or saying outright that a detail is missing: «me falta saber», «necesito saber», «no me has dicho»
    r"|\bme falta[n]? (?:saber|que me digas|el |la |los |las )"
    r"|\bnecesito (?:saber|que me digas)\b|\bno me has dicho\b|\bme has dejado la frase a la mitad\b"
    # …or asking for it in the imperative, but ONLY followed by an interrogative («dime de qué», never «dame un
    # momento», which is the most common way of promising to get on with it).
    r"|\b(?:dime|dame|cuéntame|indícame|especifica|concreta)\b[^.!?]{0,40}?"
    r"\b(qué|cuál|cuáles|dónde|cuándo|cuánto|quién|cómo)\b",
    _re.I)


def asks_for_missing_detail(reply: str) -> bool:
    """True when the reply ASKS THE OPERATOR for something it needs before it can act.

    Such a reply is not a broken promise, and the promise backstops must not turn it into an errand. Measured on
    the operator's own sessions (2026-08-17 → 2026-09-01, every firing of the «promesa sin acción» gate): of ten
    firings, THREE were this — «¿Los precios de qué, Ricardo?», «¿a qué ciudad quieres ir desde Zaragoza?», «me
    falta saber los dos puntos exactos». The gate read the «te lo miro» at the end and called it an unkept promise.

    Launching an errand at that moment is wrong twice over: the agent has just said it does not know what to look
    for, and the answer is one turn away — when it arrives, `escalate_goal_from_window` escalates the real request
    (that is what V2-132 built the window lookback for). Firing here buys a worker with half a goal AND a second
    worker a turn later, racing it. Session 651cd038 (2026-09-01) paid exactly that: two browsers, two results
    cards, nine minutes.

    Deliberately narrow. A courtesy question («¿te aviso cuando lo tenga?») is not asking for a detail and must
    keep the backstop armed; so must «dame un momento y te enseño lo que encuentre», which is a promise wearing an
    imperative. When in doubt this returns False — falling back to today's behaviour, not to silence."""
    return bool(_ASKS_DETAIL_RE.search(reply or ""))
