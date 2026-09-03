"""nucleo/flash/answer_guards.py — a FACT about the world, answered with NO source (V2-210).

Extracted from `router_guards.py` on 2026-09-03 paying the architecture ratchet (V2-567's show-vs-close guard
crossed that file's ceiling; the table calls for extracting a concern, not raising a number — this family is
pure regex over (question, answer) pairs and nothing that stayed behind uses it). `router_guards` keeps
ALIASES with the historical names, so `probe.py` and the flash tests import through it unchanged.
"""
from __future__ import annotations

import re as _re

# ── A FACT ABOUT THE WORLD, ANSWERED WITH NO SOURCE (V2-210) ──────────────────────────────────────────────────
# Measured on `quick-fact-opening-hours` (2026-08-20 15:08), the cleanest failure on the board because there is
# nothing else in it — no wall, no worker, no network error:
#
#     TESTER  ¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?
#     ZAELAR  Mañana abre a las 10:00 y la entrada general cuesta 15 €.
#
# Zero tools. Families: flash, memory, system — no `search`. The numbers are roughly right, which is WHY this is
# dangerous: the model is confident, so it never reaches for `web_search`, and a confident wrong price reads
# exactly like a confident right one. V2-022's whole point is that this class of question is answered IN THE
# TURN from a real source; V2-135 already fixed the composing half of this same case. What was missing is the
# trigger for the turn where the model does not ask.
#
# NARROW ON PURPOSE, and both halves are required:
#   · the QUESTION has to be about the opening hours / price / address / phone of something out there, and not
#     about the operator's own things («¿a qué hora es mi cita?» is the agenda, and answering it from memory is
#     correct);
#   · the ANSWER has to state a concrete FIGURE. «Suele abrir por la mañana» claims nothing checkable and
#     forcing a search on it would spend a second on every vague sentence.
# A false «go and search» costs latency on every turn it fires on, so the cost of being wide is paid by turns
# that were fine. A false negative costs one invented fact, which is the failure being fixed — hence a rule that
# fires on the shape actually measured and says so.
_EXTERNAL_FACT_RE = _re.compile(
    r"\b(a\s+qu[eé]\s+hora\s+(abre|abren|cierra|cierran|empieza|empiezan)|"
    r"abre[nu]?\b|abierto\b|cierra[nu]?\b|horario\b|horarios\b|"
    r"cu[aá]nto\s+(cuesta|vale|valen|cuestan)|precio\b|tarifa\b|entrada\s+general\b|"
    r"direcci[oó]n\b|tel[eé]fono\b|"
    r"what\s+time\s+(does|do)\b|opening\s+hours\b|how\s+much\s+(is|are|does)\b)", _re.I)

# The operator's OWN things: their agenda, their car, their subscription. Those are answered from memory or from
# their account, never from a search engine, and «mi» is what marks them.
_OWN_THING_RE = _re.compile(r"\b(mi|mis|m[ií]o|m[ií]a|nuestr[oa]s?)\b", _re.I)

# A checkable figure: a time, an amount, a price. Bare digits are NOT enough — «te lo digo en 2 minutos» is not
# a claim about the world.
_FIGURE_RE = _re.compile(
    r"(\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s*h\b|\b\d{1,4}([.,]\d{1,2})?\s*(€|euros?|dollars?|usd|\$)|"
    r"(€|\$)\s*\d|\b\d{1,2}\s*(de\s+la\s+ma[ñn]ana|de\s+la\s+tarde|am|pm)\b)", _re.I)


def answer_needs_a_source(operator_text: str, reply: str) -> bool:
    """Did this turn state a checkable fact about the world without consulting anything?

    Only the caller knows whether a tool ran, so this answers the OTHER half: whether the pair
    (question, answer) is the shape that must never be improvised.
    """
    q, a = (operator_text or ""), (reply or "")
    if not q or not a:
        return False
    if _OWN_THING_RE.search(q):
        return False
    return bool(_EXTERNAL_FACT_RE.search(q) and _FIGURE_RE.search(a))
