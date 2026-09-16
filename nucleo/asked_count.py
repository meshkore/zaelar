"""nucleo/asked_count.py — how many things the ORDER named, when it named a number at all.

V2-707 F6. Measured in session `080b96a7` (2026-09-16, i=10753→10794):

    he       «Can you clean the three?»                    ← three all-day items he had just described
    gate     «Voy a borrar 5 citas del 2026-09-17. Es permanente. ¿Las borro?»
    he       «Yes.»
    engine   five rows gone

The confirmation SAID the real radius — V2-693 put that number there on purpose — and then offered a
yes/no anyway. A question that states five to an order that said three is not a confirmation: the two
numbers contradict each other, and a «yes» to a contradiction authorises nothing. What was missing is not
a rule about how to phrase it; it is the COMPARISON. This module is one half of it (what he asked) and
`widgets/rows.plan`/`agenda/sweep` are the other (what would happen).

## Why only number WORDS, and why a counted noun for digits

The first version read any numeral and it was wrong within one sentence of the real transcript: «Now on
Thursdays, the seventeenth» and «clean the 17th» carry a numeral that is a DATE, and reading it as a count
would make the door refuse a correct order — the exact failure mode this is meant to prevent, pointed the
other way. So:

  · a number WORD in a counting frame counts («the three», «las tres», «all four», «both»);
  · a DIGIT counts only when a counted noun follows it («3 appointments», «3 citas», «3 of them»);
  · an ORDINAL never counts — «third», «seventeenth», «tercera» are different words, so they simply do
    not match, which is what makes the date case safe rather than special-cased.

Closed in OPERATORS (the frames), open in content: it never decides what the order MEANS, only whether it
put a number on it. Nothing here changes what the model may reason; the engine bounds the outcome.
"""
from __future__ import annotations

import re
import unicodedata

#: Spelled-out counts, both shipped languages. Deliberately stops at twelve: past that, speech says the
#: digits, and a digit needs its counted noun (below) to be distinguishable from a date or a time.
_WORDS: dict[str, int] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12,
    "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
    "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
}
#: «both» is a count with no numeral in it.
_PAIRS = ("both", "ambas", "ambos")

_NUM = "|".join(sorted(_WORDS, key=len, reverse=True))

#: A DETERMINER in front of a number word is what makes it a count of things already on the table — «the
#: three», «all four», «those two», «las tres», «esos dos». A bare «three» is left alone: «at three» is a
#: time, and «September three» is a date.
_DET = (r"the|all|those|these|them|both|"
        r"las|los|la|el|esas|esos|estas|estos|aquellas|aquellos|todas|todos|unas|unos")
_FRAMED_WORD_RE = re.compile(rf"\b(?:{_DET})\s+(?:{_NUM})\b", re.I)
_WORD_AFTER_DET_RE = re.compile(rf"\b(?:{_DET})\s+({_NUM})\b", re.I)

#: The other half of the same frame: the number comes first and the counted thing follows it. This is the
#: only shape in which a DIGIT is read as a count, and it is why «the 17th» cannot be mistaken for one.
_COUNTED = (r"of\s+them|of\s+those|of\s+these|items?|entries|appointments?|meetings?|events?|tasks?|rows?|"
            r"things?|de\s+ell[ao]s|de\s+es[ao]s|citas?|reuniones|eventos?|tareas?|filas?|cosas?|items")
_COUNTED_RE = re.compile(rf"\b(\d{{1,2}}|{_NUM})\s+(?:{_COUNTED})\b", re.I)

#: «los dos» / «las dos» / «the two of them» already come through the frames above; this is the wordless
#: pair, which no numeral covers.
_PAIR_RE = re.compile(rf"\b(?:{'|'.join(_PAIRS)})\b", re.I)


def _fold(text: str) -> str:
    n = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


def named(text: str) -> int | None:
    """The count the order put on what it asked for, or None when it named no number.

    None is the common answer and the safe one: «clean today», «borra la agenda», «empty it» name a radius
    without counting it, and there is nothing to contradict. Only a number the operator actually said can
    disagree with the number the door measured.
    """
    t = _fold(text)
    if not t:
        return None
    m = _WORD_AFTER_DET_RE.search(t)
    if m:
        return _WORDS[m.group(1)]
    m = _COUNTED_RE.search(t)
    if m:
        g = m.group(1)
        return _WORDS[g] if g in _WORDS else int(g)
    if _PAIR_RE.search(t):
        return 2
    return None
