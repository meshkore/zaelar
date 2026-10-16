"""search/asked.py — what a request SAYS a candidate must be: its subject, its size, its resolution, its ceiling,
and what a correction ruled out (V2-782 T3.3).

Measured 2026-10-11, the shortlist family:
  · find-concert-tickets ES — «entradas para un concierto de Rosalía en Madrid»: «El Cascanueces» and «DJ
    Symphonic» were named as candidates. The request NAMED its subject; no row said it.
  · cheapest-monitor EN — a 24" non-4K monitor delivered as the pick for a 27" 4K ask: a hard spec a row CONTRADICTS.
  · search-buy-used-car ES — «nada de maquetas de trenes ni recambios»: what a correction excludes.

A grammar of the request's own SHAPE (capitalised names, numerals with a unit, negations), in ES and EN — never a
verb table that decides intent. Each reader returns "" / None / empty when the request does not say it, and a
silent reader filters nothing: a row is rejected only for contradicting what WAS said.
"""
from __future__ import annotations

import re
import unicodedata

from search.category_words import NOT_A_SUBJECT, NOT_A_SUBJECT_SIGLA
from search.soft_zone import is_zone


def norm(text) -> str:
    """Lowercase, accent-free, single-spaced — the form every matcher of this family reads."""
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    return " ".join("".join(c for c in s if not unicodedata.combining(c)).split())


def amount(text) -> float | None:
    """The first monetary-looking number of `text` as a float: «€ 7.999» → 7999, «$13,397» → 13397, «224.51» →
    224.51, «12 mil» → 12000, «14k» → 14000. None when there is no number."""
    m = re.search(r"(\d[\d.,]*)\s*(mil\b|k\b|thousand\b)?", str(text or ""), re.I)
    if not m:
        return None
    raw, mult = m.group(1).rstrip(".,"), 1000.0 if m.group(2) else 1.0
    if "." in raw and "," in raw:
        dec = "." if raw.rfind(".") > raw.rfind(",") else ","
        raw = raw.replace("," if dec == "." else ".", "").replace(dec, ".")
    elif raw.count(".") > 1 or raw.count(",") > 1:
        raw = raw.replace(".", "").replace(",", "")
    elif "." in raw or "," in raw:
        sep = "." if "." in raw else ","
        head, tail = raw.split(sep)
        raw = head + tail if len(tail) == 3 else head + "." + tail
    try:
        return float(raw) * mult
    except ValueError:
        return None


_CUR = r"(?:€|\$|£|euros?|eur|usd|dolares|dollars|bucks|libras|pounds)"
_BOUND = r"(?:hasta|menos de|no pase de|no supere|por debajo de|maximo|max|under|below|less than|up to|no more than)"
_UNIT_AFTER = re.compile(r"^\s*(?:mil\b|k\b)?\s*(?:millas|miles|mi\b|km|kilometros|kms|pulgadas|inch|cc|cv|hp)", re.I)


def ceiling(text) -> float | None:
    """The price ceiling the request states («que no pase de 12 mil euros», «under $14,000»), or None. A number
    followed by a distance/size unit («60k miles») is never a price."""
    t = norm(text)
    for m in re.finditer(rf"{_CUR}\s?(\d[\d.,]*\s*(?:mil\b|k\b)?)|(\d[\d.,]*\s*(?:mil\b|k\b)?)\s?{_CUR}"
                         rf"|{_BOUND}\s+(?:de\s+)?(\d[\d.,]*\s*(?:mil\b|k\b)?)", t):
        num = next(g for g in m.groups() if g)
        if _UNIT_AFTER.match(t[m.end():]) and not re.search(_CUR, m.group(0)):
            continue
        v = amount(num)
        if v and v >= 5:
            return v
    return None


#: A capitalised run of words that is not the sentence's first word: «Rosalía», «Bad Bunny», «Ford Focus».
#: Titlecase only: an all-caps token («SUV», «TDI», «4K») is a spec or a category, never the subject. A word right
#: after an opening «¿»/«¡» starts a sentence: «¿Los tienes?» named the subject «los».
_CAPS = re.compile(r"(?<![.!?¿¡]\s)(?<![¿¡])\b([A-ZÁÉÍÓÚÑ][a-záéíóúñü][\wáéíóúñü&'-]*(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñü][\wáéíóúñü&'-]*)*)")
#: What precedes a PLACE, not a subject: «en Madrid», «in Miami», «cerca de Sevilla».
#: An article may stand between: «in the Mission», «por el Carmen» (search-rent-apartment, 2026-10-14) — never after
#: «to/from», where «tickets to the Weeknd» names an artist.
_PLACE_BEFORE = re.compile(r"(?:\b(?:en|in|at|near|cerca de|around|por)\s+(?:(?:el|la|los|las|the)\s+)?"
                           r"|\b(?:desde|from|to)\s+)$", re.I)


#: Both ends of a ROUTE are places: «de Madrid a Londres», «from Boston to Denver». His words now reach every errand's
#: sheet (`nucleo/turn/commission_words.py`), and a flight row says «MAD → LHR», not «Madrid».
_ROUTE = re.compile(r"\b(?:de|desde|from)\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñü-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñü-]*)*"
                    r"\s+(?:a|al|hasta|to)\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñü-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñü-]*)*")


#: An all-caps token of two to four letters offered as an ALTERNATIVE to a name: «Samsung o LG», «Dell or HP».
_SIGLA_OFFERED = re.compile(r"(?:,|\b(?:o|or|y|and|u))\s+([A-Z]{2,4})\b(?![\w-])")


def subjects(text) -> list[str]:
    """The proper names the request asks ABOUT — the subject a candidate must name. Places are left out (a ticket
    row says «Movistar Arena», not «Madrid»; a route's two ends), and so are months, days and greetings. Empty when
    nothing is named."""
    raw = " ".join(str(text or "").split())
    routes = [r.span() for r in _ROUTE.finditer(raw)]
    out: list[str] = []
    for m in _CAPS.finditer(raw):
        if m.start() == 0 or _PLACE_BEFORE.search(raw[:m.start()]) or any(a <= m.start() < b for a, b in routes):
            continue
        if is_zone(raw, m.start(), m.end()):
            continue                       # «zona: Ruzafa», «si puedes, por Ruzafa o el centro»: a zone, at most a hint
        words = [w for w in norm(m.group(1)).split() if w not in NOT_A_SUBJECT and len(w) >= 3]
        if words and words[0] != "i":
            out.append(" ".join(words))
    if out:
        # A sigla he OFFERED beside a name is one of the alternatives, not a spec: «Samsung o LG», «Dell or HP»,
        # «Honda, Yamaha o KTM». Only beside a found name — alone, «un SUV» or «una TV» names a category.
        for m in _SIGLA_OFFERED.finditer(raw):
            tok = norm(m.group(1))
            if tok not in NOT_A_SUBJECT_SIGLA and tok not in out:
                out.append(tok)
    return out


_INCH = r"(?:\"|''|”|pulgadas|inch(?:es)?|in\b|-inch)"


def size_inches(text) -> int | None:
    """A screen-style size the text states («27"», «27 pulgadas», «27-inch»), or None."""
    m = re.search(rf"\b(\d{{2}}(?:[.,]\d)?)\s?{_INCH}", str(text or ""), re.I)
    return int(float(m.group(1).replace(",", "."))) if m else None


_4K = re.compile(r"\b(4k|uhd|ultra hd|2160p|3840\s?x\s?2160)\b", re.I)
_NOT_4K = re.compile(r"\b(1080p|full hd|fhd|1920\s?x\s?1080|1440p|qhd|wqhd|2k|2560\s?x\s?1440|720p|hd ready|"
                     r"1366\s?x\s?768)\b", re.I)


def wants_4k(text) -> bool:
    return bool(_4K.search(str(text or "")))


def states_lower_than_4k(text) -> bool:
    """True when the row SAYS a resolution below 4K (and does not also say 4K)."""
    t = str(text or "")
    return bool(_NOT_4K.search(t)) and not _4K.search(t)


_NEG = re.compile(r"\b(?:no|sin|ni|nada de|not|no more|without|ignore|excluding|except|exclude|nothing)\s+"
                  r"([a-z][a-z/-]{3,})", re.I)
#: Words that follow a negation and are never the thing excluded («no me sirve», «no pase de», «not more than»).
_STOP = frozenset((
    "pase", "supere", "sirve", "quiero", "busques", "pongas", "hace", "falta", "tengo", "tiene", "importa", "sea",
    "seas", "muy", "tan", "demasiado", "solo", "mucho", "mas", "menos", "esta", "este", "esos", "esas", "estos",
    "eso", "the", "that", "more", "than", "much", "many", "only", "just", "need", "want", "those", "these",
    "such", "have", "worry", "bother", "sure", "older", "newer", "over", "less", "really", "quite", "even", "any",
    "puedo", "puedes", "hay", "vale", "gracias", "thanks", "problem", "rush", "prisa", "longer",
))


def without_negated(text) -> str:
    """`text` with every negated noun taken out («busco hotel, no hostales» → «busco hotel, »): what he ASKED for."""
    return _NEG.sub(" ", norm(text))


def exclusions(text) -> list[str]:
    """The nouns a correction rules out: «nada de maquetas de trenes ni recambios» → maquetas, recambios;
    «ignore parts/accessories» → parts, accessories. Accent-free, as written."""
    out: list[str] = []
    for m in _NEG.finditer(norm(text)):
        for w in re.split(r"[/-]", m.group(1)):
            if len(w) >= 4 and w not in _STOP and w not in out:
                out.append(w)
    return out
