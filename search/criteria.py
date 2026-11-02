"""search/criteria.py — what the request itself says about HOW MANY and WHICH DATA (V2-782 T4.4 / T3.2).

Two things a search request carries that no module read before 2026-10-10:

  1. **Breadth.** «Pull a couple of recipes» became a research brief with a floor of 25 candidates and 10 final
     picks, ~90 candidates were gathered, and the results arrived after the conversation had ended
     (knows-who-i-am, EN). A number the OPERATOR said is his: this module reads it and the route carries it. A
     request that names none is UNDECLARED (`None`), and a vague quantity («a couple», «some») is his word, not a
     number of ours (V2-840 H1): how many to evaluate and show is decided by the model that composes the errand.

  2. **Fields.** «El mejor valorado que pueda venir hoy» asks for a RATING and an AVAILABILITY; «the cheapest 27"
     4K» asks for a PRICE. The rows came back with names and links and were presented as meeting the criterion
     (best-plumber-same-day, hotel-under-15-days, cheapest-monitor). The field names here become the sheet's
     `criteria.hard`, which is what `candidacy.unshown_criteria` checks the rows against — so a criterion no
     row can show is SAID missing instead of implied met.

This is a grammar of NUMERALS and of DATA-FIELD words, in ES and EN. It is not a router (CRIT-K1: a verb table is
not a router) and it never decides which module runs: `route.py` does that from the brief's verdict. What it
returns is a reading of HIS number; the research brief is composed by a model that reads his words itself.
"""
from __future__ import annotations

import re

#: Numerals as people say them, both languages. Word → count. Digits are read directly.
_NUMBER_WORDS = {
    "one": 1, "uno": 1,
    "two": 2, "dos": 2, "three": 3, "tres": 3, "four": 4, "cuatro": 4, "five": 5, "cinco": 5,
    "six": 6, "seis": 6, "seven": 7, "siete": 7, "eight": 8, "ocho": 8, "nine": 9, "nueve": 9,
    "ten": 10, "diez": 10, "twelve": 12, "doce": 12, "fifteen": 15, "quince": 15, "twenty": 20, "veinte": 20,
}
#: «dame tres opciones», «the 3 best», «ponme veinte», «five hotels», «two recipes».
_COUNTED = re.compile(
    r"\b(?:(?:dame|ponme|busca(?:me)?|quiero|necesito|encuentra(?:me)?|tráeme|traeme|pull|find(?: me)?|give me|"
    r"show me|get me|i need|i want|the|los|las|el|la|unas?|unos?)\s+)?"
    r"(\d{1,2}|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\s+"
    # «three 27 inch 4k monitors»: the measures between the count and the thing are not the count (demo
    # 2026-10-22 — «27 inch» became a top-ten and a 21-minute errand for three monitors).
    r"(?:\d[\w.,\-\"'″]*\s+)*"
    r"(?:mejores|best|top|cheapest|good|buenas?|buenos?|opciones|options|"
    r"[a-záéíóúñü]{3,}(?:es|s)?)\b", re.I)
#: A single pick: «one good one», «the best one», «el mejor», «la más barata», «uno bueno».
_SINGLE = re.compile(r"\b(?:one good one|the best one|just one|only one|the single|el mejor|la mejor|el más|la más|"
                     r"uno bueno|una buena|solo uno|solo una|sólo uno|sólo una)\b", re.I)

#: The data FIELDS a request asks the candidates to carry. Field → the words that ask for it (ES + EN). A row
#: that carries none of the asked field's data is not a row that meets the criterion.
_FIELD_WORDS = {
    "rating": re.compile(r"\b(?:mejor valorad\w*|más valorad\w*|mas valorad\w*|mejores valoraciones|valoraci\w+|"
                         r"opiniones|reseñas|resenas|puntuaci\w+|best[- ]rated|top[- ]rated|highest[- ]rated|"
                         r"well[- ]reviewed|reviews?|ratings?|stars?|estrellas)\b", re.I),
    "availability": re.compile(r"\b(?:hoy|today|same[- ]day|ahora|right now|mañana|manana|tomorrow|"
                               r"este fin de semana|this weekend|disponib\w+|availab\w+|abiert\w+|open now|"
                               r"que pueda venir|who can come|urgente|urgent|asap)\b", re.I),
    "price": re.compile(r"\b(?:barat\w+|cheap\w*|precio|price|cost\w*|cuesta|menos de|under|below|por debajo|"
                        r"presupuesto|budget|máximo|maximo|max|hasta)\b|[€$£]\s?\d|\d\s?(?:€|eur|usd|\$)", re.I),
}


def breadth(request: str) -> dict:
    """`{n_final, said}` — how many he asked to be shown, and the words that said it; `n_final` is None when he named
    no number (undeclared: whoever consumes it names no number either). No floor, no default, and nothing about how
    many to evaluate — those are the composing model's, never ours (V2-840 H1)."""
    text = " ".join(str(request or "").split())
    m = _COUNTED.search(text)
    if m:
        tok = m.group(1).lower()
        n = int(tok) if tok.isdigit() else _NUMBER_WORDS.get(tok)
        if n:
            return {"n_final": n, "said": m.group(0).strip()}
    single = _SINGLE.search(text)
    if single:
        return {"n_final": 1, "said": single.group(0)}
    return {"n_final": None, "said": ""}


def fields(request: str) -> list[str]:
    """The data fields the request asks for, in a stable order: price · rating · availability."""
    text = str(request or "")
    return [name for name in ("price", "rating", "availability") if _FIELD_WORDS[name].search(text)]


def hard_criteria(request: str) -> list[str]:
    """The asked fields as the sheet's `criteria.hard` lines — what `candidacy.unshown_criteria` checks."""
    names = {"price": "price", "rating": "rating / reviews", "availability": "availability (when)"}
    return [names[f] for f in fields(request)]


def for_request(request: str) -> dict:
    """Everything this module reads from a request, in one dict: `{fields, hard, n_final, said}`."""
    out = breadth(request)
    out["fields"] = fields(request)
    out["hard"] = hard_criteria(request)
    return out


#: Public name for readers outside the search package (nucleo/workers/named_top.py).
NUMBER_WORDS = _NUMBER_WORDS
