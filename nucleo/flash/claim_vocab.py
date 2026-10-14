"""nucleo/flash/claim_vocab.py — the attribute claims a reply makes about a candidate, and whether a source carries them.

Closed vocabulary of the attributes the shortlist rounds of 2026-10-14 measured as asserted without a source, in
the two languages the product speaks: condition (new / unused / «not refurbished», «N months used», «excellent
condition»), availability («still available», «sigue disponible»), capacity («8 kilos»), energy class («clase A»)
and «automatic». Each concept has a CLAIM side (read on the reply, over folded text) and a CARRY side (read on a
source); a keyed concept («6 months», «8 kg», «A») is carried only by a source naming the same key.

A sentence that says it cannot confirm is no claim (`disclaims`), a sentence that says «yes» and «not verified» at
once is the contradiction `row_claims` repairs (`affirms`), and a conditional («if it's new») claims nothing. Pure.
"""
from __future__ import annotations

import re

from .claim_backing import fold

_NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
        "nine": "9", "ten": "10", "eleven": "11", "twelve": "12", "un": "1", "una": "1", "uno": "1", "dos": "2",
        "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8", "nueve": "9",
        "diez": "10", "once": "11", "doce": "12"}
_N = r"(\d+|" + "|".join(_NUM) + r")"
_UNIT = {"month": "m", "months": "m", "mes": "m", "meses": "m", "year": "y", "years": "y", "ano": "y", "anos": "y",
         "week": "w", "weeks": "w", "semana": "w", "semanas": "w"}   # every spelling `_AGE` can capture
_AGE = _N + r"\s+(months?|meses|mes|years?|anos?|weeks?|semanas?)\s+(?:of\s+)?(?:used|old|use|de uso|usad[oa]s?|de antiguedad)"
_COPULA = r"(?:is|it's|its|are|they're|it is|es|son|esta|estan|viene|vienen)\s+(?:(?!not\b|no\b|never\b)\w+\s+)?"

#: concept → (claim regex, carry regex). Keyed concepts capture their key in group 1 on both sides.
_CONCEPTS = {
    "new": (r"\b(?:brand[ -]new|unused|sealed|unopened|sin usar|sin estrenar|a estrenar|precintad[oa]s?|"
            r"not (?:a |an )?(?:refurbished|open[ -]box)|no (?:es |esta )?reacondicionad[oa]|" + _COPULA +
            r"(?:new|nuev[oa]s?))\b",
            r"\b(?:new|nuev[oa]s?|precintad\w*|sealed|unused|sin usar|a estrenar|sin estrenar)\b"),
    "age": (r"\b" + _AGE + r"\b", r"\b" + _AGE + r"\b"),
    "quality": (r"\b" + _COPULA + r"(?:in\s+|en\s+)?(?:(?:excellent|great|good|perfect|mint)\s+(?:condition|shape)|"
                r"like new|(?:buen|perfecto|excelente|impecable)\s+estado|como nuev[oa])\b",
                r"\b(?:condition|shape|like new|mint|estado|como nuev[oa]|impecable)\b"),
    "available": (r"\b(?:(?:still|is|it's|its|are|currently|now)\s+(?:(?!not\b)\w+\s+)?(?:available|in stock)|"
                  r"(?:sigue|siguen|esta|estan)\s+(?:(?!no\b)\w+\s+)?(?:disponibles?|en stock|a la venta))\b",
                  r"\b(?:available|in stock|disponib\w*|en stock|stock)\b"),
    "kg": (r"\b(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?|kilogram\w*)\b", r"\b(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?|kilogram\w*)\b"),
    "energy": (r"\b(?:clase|class)\s+(?:energetica\s+)?([a-g]\+{0,3})(?![\w+])",
               r"\b(?:clase|class|energetica|energy|eficiencia)\b[^.;:(]{0,25}?\b([a-g]\+{0,3})(?![\w+])"),
    "automatic": (r"\b" + _COPULA + r"(?:an? )?(?:automatic|automatico|automatica|automaticos|automaticas)\b",
                  r"\bautomat\w*"),
}
_CLAIM = {k: re.compile(v[0]) for k, v in _CONCEPTS.items()}
_CARRY = {k: re.compile(v[1]) for k, v in _CONCEPTS.items()}
_NOT_NEW = re.compile(r"\b(?:like new|como nuev[oa]s?|seminuev\w*|casi nuev\w*)\b")
_NEGATED = re.compile(r"\b(?:no|not|isn'?t|aren'?t|never|nunca|ni)\s+(?:\w+\s+)?$")
_DISCLAIMS = re.compile(
    r"\b(?:can'?t|cannot|can not|couldn'?t|unable|no (?:te )?(?:lo )?(?:puedo|pude|se)|not (?:sure|verified|"
    r"confirmed)|unverified|sin (?:verificar|confirmar)|no (?:lo )?tengo (?:verificad|confirmad)\w*|"
    r"(?:doesn'?t|does not|don'?t|do not|didn'?t) (?:\w+ )?(?:say|show|list|mention|know|include|state)|"
    r"no (?:lo )?(?:dice|indica|consta|aparece|viene|pone|especifica|trae)|"
    r"(?:isn'?t|is not|aren'?t|are not|wasn'?t) (?:\w+ )?(?:listed|shown|stated|in|on|there|given)|"
    r"shouldn'?t have said|no deberia haber dicho|unclear|no esta claro|still (?:checking|verifying)|"
    r"(?:sigo|estoy) (?:comprobando|verificando|mirando)|pendiente de (?:confirmar|verificar))\b")
#: The words that say «not VERIFIED» — a «yes» beside one of these un-confirms itself (`row_claims` (c)).
_UNVERIFIED = re.compile(r"\b(?:sin (?:verificar|confirmar)|no (?:esta |estan )?(?:verificad|confirmad)\w*|"
                         r"not (?:verified|confirmed)|unverified|unconfirmed|no (?:lo )?tengo (?:verificad|confirmad)\w*|"
                         r"(?:can'?t|cannot|couldn'?t) (?:confirm|verify)|no (?:te )?(?:lo )?(?:puedo|pude) (?:confirmar|verificar)|"
                         r"pendiente de (?:confirmar|verificar))\b")
_AFFIRMS = re.compile(r"^\W*(?:sí|yes|yeah|yep|claro|confirmad[oa]|confirmed|correct|exacto|efectivamente)\b", re.I)
_CONDITIONAL = re.compile(r"(?:^|\W)(?:si|if|whether|en caso de que|as long as|siempre que)\s")
_CLAUSE = re.compile(r"[,;:—–]")
_QUOTES = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”")


def _key(concept: str, m: re.Match) -> str:
    if concept == "age":
        return _NUM.get(m.group(1), m.group(1)) + _UNIT.get(m.group(2), m.group(2))
    if concept in ("kg", "energy"):
        return m.group(1).replace(",", ".")
    return ""


#: A sentence about what it WILL do asserts nothing about a row («I'll look for automatic cars»).
_INTENT = re.compile(r"^\W*(?:i'?ll|i will|i'?m (?:going to|starting|looking|searching|on it)|let me|i'?m gonna|"
                     r"voy a|vamos a|me pongo|empiezo|estoy buscando|busco|buscare|te busco|lo busco)\b")


def intends(sentence: str) -> bool:
    return bool(_INTENT.search(fold(sentence)))


def claims(sentence: str) -> list[tuple[str, str, str]]:
    """`(concept, key, phrase)` for each attribute the sentence ASSERTS (negated mentions are no assertion; a quoted
    title or errand is not ours to assert; a sentence about what it will do asserts nothing)."""
    if intends(sentence):
        return []
    f = fold(re.sub(r"\b[Ss]í\b", "yes", _QUOTES.sub(" ", str(sentence or ""))))   # «sí» is no conditional «si»
    out = []
    for concept, rx in _CLAIM.items():
        for m in rx.finditer(f):
            phrase = m.group(0)
            if _NEGATED.search(f[:m.start()]) and not phrase.startswith(("not ", "no ")):
                continue
            if _CONDITIONAL.search(_CLAUSE.split(f[:m.start()])[-1]):
                continue                                         # «if it's new», «si está disponible»
            if concept == "new" and _NOT_NEW.search(f[max(0, m.start() - 6):m.end() + 6]):
                continue
            out.append((concept, _key(concept, m), _display(concept, _key(concept, m), phrase)))
    return out


_LEAD = re.compile(r"^(?:(?:is|it's|its|are|they're|it|es|son|esta|estan|viene|vienen|still|currently|now|sigue|"
                   r"siguen)\s+)+")


def _display(concept: str, key: str, phrase: str) -> str:
    """The claim as it reads in the honest line: «available», «new», «clase A» — never «is still available»."""
    if concept == "energy":
        return f"{phrase.split()[0]} {key.upper()}"
    return _LEAD.sub("", phrase).strip() or phrase


def carries(text: str, concept: str, key: str = "") -> bool:
    """Does `text` (a source) say this attribute — with the same key for a keyed concept?"""
    f = fold(text)
    if concept == "new":
        f = _NOT_NEW.sub(" ", f)
    for m in _CARRY[concept].finditer(f):
        if not key or _key(concept, m) == key:
            return True
    return False


def disclaims(sentence: str) -> bool:
    """It says it does NOT know — outside any quote («nada de "sin confirmar"» quotes the words, it does not say them)."""
    return bool(_DISCLAIMS.search(fold(_QUOTES.sub(" ", str(sentence or "")))))


def affirms(sentence: str) -> bool:
    return bool(_AFFIRMS.search(str(sentence or "")))


def contradicts(sentence: str) -> bool:
    """«Sí, … sin verificar»: a yes that says, in the same sentence, it is not verified."""
    return affirms(sentence) and bool(_UNVERIFIED.search(fold(_QUOTES.sub(" ", str(sentence or "")))))
