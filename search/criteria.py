"""search/criteria.py — what the request itself says about HOW MANY and WHICH DATA (V2-782 T4.4 / T3.2).

Two things a search request carries that no module read before 2026-10-10:

  1. **Breadth.** «Pull a couple of recipes» became a research brief with the breadth floor of 25 candidates
     and 10 final picks (`nucleo/research._MIN_CANDIDATES_FLOOR`), ~90 candidates were gathered, and the
     results arrived after the conversation had ended (knows-who-i-am, EN). The floor exists because the
     model's bias is to pick «10 candidates» for a selection that deserves breadth — but a number the OPERATOR
     said is his, and «a couple» is not 25. This module reads that number; the floor stays for requests that
     name none.

  2. **Fields.** «El mejor valorado que pueda venir hoy» asks for a RATING and an AVAILABILITY; «the cheapest 27"
     4K» asks for a PRICE. The rows came back with names and links and were presented as meeting the criterion
     (best-plumber-same-day, hotel-under-15-days, cheapest-monitor). The field names here become the sheet's
     `criteria.hard`, which is what `candidacy.unshown_criteria` checks the rows against — so a criterion no
     row can show is SAID missing instead of implied met.

This is a grammar of NUMERALS and of DATA-FIELD words, in ES and EN. It is not a router (CRIT-K1: a verb table is
not a router) and it never decides which module runs: `route.py` does that from the brief's verdict. What it
returns is a PROPOSAL the research brief may override when the model read a number this grammar missed.
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
#: Vague quantities. «A couple» is two or three, never twenty-five.
_VAGUE = (
    (re.compile(r"\b(?:a couple(?: of)?|un par de|unas? pocas?|unos pocos|a few|a handful of|un puñado de)\b", re.I), 3),
    (re.compile(r"\b(?:some|several|algunas?|algunos|varias|varios)\b", re.I), 5),
)
#: «dame tres opciones», «the 3 best», «ponme veinte», «five hotels», «two recipes».
_COUNTED = re.compile(
    r"\b(?:(?:dame|ponme|busca(?:me)?|quiero|necesito|encuentra(?:me)?|tráeme|traeme|pull|find(?: me)?|give me|"
    r"show me|get me|i need|i want|the|los|las|el|la|unas?|unos?)\s+)?"
    r"(\d{1,2}|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True)) + r")\s+"
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


def breadth(request: str, *, floor: int = 25, cap: int = 200, n_final_default: int = 10) -> dict:
    """`{n_final, min_candidates, said}` — how many to deliver, how many to look at, and the words that said it.

    When the request names a size («a couple», «tres», «twenty»), the number is his: `n_final` = that number and
    `min_candidates` = enough to choose from (×4, at least 6) but never ABOVE the floor a wide selection
    gets. When it names none, both defaults apply — the floor is kept for the requests that deserve breadth."""
    text = " ".join(str(request or "").split())
    said = ""
    n: int | None = None
    m = _COUNTED.search(text)
    if m:
        tok = m.group(1).lower()
        n = int(tok) if tok.isdigit() else _NUMBER_WORDS.get(tok)
        said = m.group(0).strip()
        # «un par de recetas» reads «un» as 1 through the numeral table — the vague forms win when they match.
    for rx, vague_n in _VAGUE:
        vm = rx.search(text)
        if vm:
            n, said = vague_n, vm.group(0)
            break
    if n is None and _SINGLE.search(text):
        n, said = 1, _SINGLE.search(text).group(0)
    if n is None or n <= 0:
        return {"n_final": n_final_default, "min_candidates": floor, "said": ""}
    n = min(n, cap)
    return {"n_final": n, "min_candidates": max(6, min(floor, n * 4)), "said": said}


def fields(request: str) -> list[str]:
    """The data fields the request asks for, in a stable order: price · rating · availability."""
    text = str(request or "")
    return [name for name in ("price", "rating", "availability") if _FIELD_WORDS[name].search(text)]


def hard_criteria(request: str) -> list[str]:
    """The asked fields as the sheet's `criteria.hard` lines — what `candidacy.unshown_criteria` checks."""
    names = {"price": "price", "rating": "rating / reviews", "availability": "availability (when)"}
    return [names[f] for f in fields(request)]


def for_request(request: str, **kw) -> dict:
    """Everything this module reads from a request, in one dict: `{fields, hard, n_final, min_candidates, said}`."""
    out = breadth(request, **kw)
    out["fields"] = fields(request)
    out["hard"] = hard_criteria(request)
    return out
