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
#: TENS, and the compound that sits on them. Added by V2-710 after the bad half of «past twelve, speech
#: says the digits»: he said «All thirty one appointments», the scan matched the UNITS word and reported
#: **1**, and the door answered a correct order with «You asked me for 1 and there are 31 there: «New»;
#: «New»; … I'm not touching anything until you tell me which ones.» He had said thirty-one.
#: A compound keeps the frame discipline, and the first draft of this did not — caught by its own cases:
#: «the thirty first» came back as 30 (a DATE read as a count, the exact failure this module exists to
#: prevent, pointed the other way), and Spanish says the day of the month the same way («limpia el treinta
#: y uno»). So a tens number counts only with a QUANTIFIER in front that a date never takes («all thirty
#: one», «todas las treinta y una») or with its counted noun behind it («thirty one appointments»).
_TENS: dict[str, int] = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
    "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
    "ochenta": 80, "noventa": 90,
}

#: «both» is a count with no numeral in it.
_PAIRS = ("both", "ambas", "ambos")

_NUM = "|".join(sorted(_WORDS, key=len, reverse=True))
_TEN = "|".join(sorted(_TENS, key=len, reverse=True))
#: The quantifier that a day of the month never takes.
_ALL = r"all|todas|todos|toda|todo"

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

#: A TENS number, alone or compounded, in one of the two frames — see `_TENS`. «treinta y una», «thirty
#: one», «thirty-one», and «veintiuna», which Spanish writes as one word.
_TENS_NUM = rf"(?:{_TEN})(?:\s*-\s*|\s+y\s+|\s+)(?:{_NUM})|veinti(?:un|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)|(?:{_TEN})"
_TENS_ALL_RE = re.compile(rf"\b(?:{_ALL})\s+(?:(?:{_DET})\s+)?({_TENS_NUM})\b", re.I)
_TENS_COUNTED_RE = re.compile(rf"\b({_TENS_NUM})\s+(?:{_COUNTED})\b", re.I)


def _tens_value(g: str) -> int:
    """«thirty one» → 31, «veintiuna» → 21, «treinta» → 30."""
    g = g.strip().lower()
    if g.startswith("veinti"):
        return 20 + _WORDS[g[len("veinti"):]]
    parts = [w for w in re.split(r"[\s-]+|\sy\s", g) if w and w != "y"]
    total = _TENS.get(parts[0], 0)
    if len(parts) > 1 and parts[1] in _WORDS:
        total += _WORDS[parts[1]]
    return total


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
    for _rx in (_TENS_ALL_RE, _TENS_COUNTED_RE):   # a TENS number before «one» is read — see `_TENS`
        m = _rx.search(t)
        if m:
            return _tens_value(m.group(1))
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
