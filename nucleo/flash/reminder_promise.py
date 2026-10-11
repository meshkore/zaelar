"""nucleo/flash/reminder_promise.py — what counts as a SPOKEN promise or claim of a reminder, in ES and EN.

Measured on `find-a-future-release-and-remind-me__us` (2026-10-10 22:08): after the lookup zaelar said «I'm on it —
I'll set that reminder for October 30, 2026.» and later «I've still got that reminder set for 30 October 2026»,
and `scheduled_jobs.created` was EMPTY. The ES run of the same suite scheduled its notice through the prose
backstop. Two holes, both on the English side of one pattern:

  · the EN promise forms only allowed «a|the» between the verb and the noun — «that reminder» (the shape an
    assistant uses for a reminder the operator already asked for) never matched, while the ES side listed
    «ese/este/esa/esta» since V2-151;
  · a CLAIM that a reminder exists («I've got that reminder set», «your reminder is set», «te he puesto el
    aviso») was not read at all, so it could neither be backed nor caught.

A promise or a claim is a VERB plus a reminder NOUN with an explicit determiner in between (never `\\w+`, so a
«ningún recordatorio» cannot match), not preceded by a negation in its own sentence, and not inside a question.
`unbacked_claim_line` is the other half: a claim said while NO active job exists gets an honest correction in the
session language — the claim is checked against `scheduled_jobs`, never trusted.
"""
from __future__ import annotations

import logging
import re as _re

from .text_norm import _norm_txt

logger = logging.getLogger(__name__)

_NOUN_ES = r"(?:recordatorio|aviso|alarma|alerta)"
_DET_ES = r"(?:un|una|el|la|tu|ese|este|esa|esta)\s+"
_NOUN_EN = r"(?:reminder|heads-up|alert|alarm|notification)"
_DET_EN = r"(?:a|the|that|this|your|one|a\s+quick)\s+"
_SET_EN = r"(?:set|put|get|schedule|add|create|pop)"
_DONE_EN = r"(?:got|set|put|scheduled|added|created|saved)"

PROMISE_RE = _re.compile(
    r"\b(te\s+aviso|te\s+avisare|para\s+avisarte|te\s+lo\s+recuerdo|te\s+lo\s+recordare|te\s+recuerdo|te\s+recordare|"
    r"te\s+lo\s+programo|te\s+lo\s+programare|"
    r"dejo\s+puesto\s+" + _DET_ES + _NOUN_ES + r"|"
    r"dejo\s+programad[oa]\s+" + _DET_ES + _NOUN_ES + r"|"
    r"(?:program|pon|cre|configur|activ|dej)\w*\s+" + _DET_ES + _NOUN_ES + r"|"
    r"i'?ll\s+remind\s+you|i\s+will\s+remind\s+you|i'?ll\s+let\s+you\s+know\s+on|"
    r"(?:i'?ll|i\s+will)\s+(?:go\s+ahead\s+and\s+)?" + _SET_EN + r"\s+(?:up\s+|in\s+)?" + _DET_EN + _NOUN_EN + r")\b",
    _re.I)
CLAIM_RE = _re.compile(
    r"\b((?:i'?ve|i\s+have)\s+(?:still\s+|already\s+|now\s+|just\s+)?" + _DONE_EN + r"\s+(?:up\s+|in\s+)?"
    + _DET_EN + _NOUN_EN + r"|"
    r"(?:your|the|that|this)\s+" + _NOUN_EN + r"(?:\s+is|'s)\s+(?:all\s+|already\s+|now\s+|still\s+)?"
    r"(?:set|scheduled|in\s+place|on)|"
    r"te\s+he\s+(?:puest|programad|cread|dejad|activad|configurad)[oa]\s+" + _DET_ES + _NOUN_ES + r"|"
    r"(?:ya\s+)?tienes\s+" + _DET_ES + _NOUN_ES + r"\s+(?:puest|programad)[oa]|"
    r"(?:el|tu|ese)\s+" + _NOUN_ES + r"\s+(?:ya\s+)?(?:esta|queda)\s+(?:puest|programad)[oa])\b", _re.I)
# A negation in the two words just BEFORE the verb, within its clause: «no te pongo un aviso». Only those words:
# «Sure, no problem — I'll set that reminder…» is a promise.
_NEGATION_RE = _re.compile(r"\b(no|not|never|nunca|cannot|unable|can'?t|couldn'?t|won'?t|haven'?t|didn'?t|isn'?t)\b"
                           r"|n't\b", _re.I)
_SENTENCE_END = ".!?…\n"


def norm(text: str) -> str:
    """Accents and case off, and the typographic apostrophe a model writes («I’ll») made plain."""
    return _norm_txt(text or "").replace("’", "'").replace("‘", "'")


def _sentence_bounds(n: str, start: int, end: int) -> tuple[int, int]:
    lo = max(n.rfind(c, 0, start) for c in _SENTENCE_END) + 1
    his = [i for i in (n.find(c, end) for c in _SENTENCE_END) if i >= 0]
    return lo, (min(his) if his else len(n))


def _affirmed(n: str, m) -> bool:
    """The match is said as a fact or a commitment: no negation just before it, not inside a question."""
    lo, hi = _sentence_bounds(n, m.start(), m.end())
    lead = _re.split(r"[,;:—–]", n[lo:m.start()])[-1]
    if _NEGATION_RE.search(" ".join(lead.split()[-2:])):
        return False
    return not (n[hi:hi + 1] == "?" or "¿" in n[lo:m.start()])


def find(reply: str, *, claims: bool = True):
    """The first affirmed promise (or, with `claims`, claim) in `reply` — `(normalised_text, match)` or None."""
    n = norm(reply)
    for rx in ((PROMISE_RE, CLAIM_RE) if claims else (PROMISE_RE,)):
        for m in rx.finditer(n):
            if _affirmed(n, m):
                return n, m
    return None


def claims_a_set_reminder(reply: str) -> bool:
    n = norm(reply)
    return any(_affirmed(n, m) for m in CLAIM_RE.finditer(n))


def unbacked_claim_line(reply: str, lang_code: str = "") -> str:
    """The correction owed when `reply` CLAIMS a reminder exists and no active scheduled job does — else ""."""
    if not claims_a_set_reminder(reply):
        return ""
    try:
        from nucleo import scheduler as _sched
        if list(_sched.list_jobs(active_only=True)):
            return ""
    except Exception as e:  # noqa: BLE001 — the schedule could not be read: no claim can be checked, say nothing
        logger.warning("reminder claim not checked, scheduled_jobs unreadable: %s", e)
        return ""
    try:
        from i18n import langs as _lg
        return _lg.spec(lang_code or None).reminder_not_set_yet
    except Exception as e:  # noqa: BLE001
        logger.warning("reminder claim correction has no language line: %s", e)
        return ""
