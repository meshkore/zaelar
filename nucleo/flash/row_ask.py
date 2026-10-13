"""nucleo/flash/row_ask.py — which rows a question NAMES, clause by clause, and what it asks about each one.

cheapest-monitor ES (2026-10-14, sandbox 010117-es): «El curvo de 27 me llama un poco, ¿sabes si es 4K o qué
resolución tiene? Y el Blackview no me suena de nada, ¿tiene buenas reseñas?» was answered with every hard
criterion of three rows («Blackview…: Precio dentro de un presupuesto…, sin verificar; …: Disponible para compra en el
mercado…, sin verificar; AOC…»). `row_check` compared his whole sentence with each criterion by any shared 4-letter
stem, and «para», «otra», «cosa» are in every Spanish sentence; the AOC row was «named» by «para».

Here a question is read one clause at a time: the rows THAT clause names (by a word only that row's title carries,
never a function word), and the stems THAT clause asks about (its content words minus the row's own name). A clause
names a row or it does not: the next clause inherits nothing, so «¿hay algo de 27 pulgadas por debajo de 300?» after
«el Nilox no me vale» asks about no row. Lead rows (a web page still to read, `origen: búsqueda web`) are no
candidates and are not read.
"""
from __future__ import annotations

import re
import unicodedata

_STEM = 6

#: Words of four letters or more that carry no subject in ES/EN: what a clause says ABOUT a row is never these.
_FUNCTION = frozenset((
    "para", "pero", "como", "esto", "esta", "este", "estos", "estas", "otra", "otro", "otras", "otros", "cosa",
    "cosas", "algo", "nada", "todo", "toda", "todos", "todas", "sobre", "entre", "desde", "hasta", "cuando", "donde",
    "porque", "tiene", "tienen", "tengo", "tienes", "hace", "hacer", "puede", "puedes", "sabes", "saber", "quiero",
    "quieres", "bien", "menos", "mucho", "mucha", "poco", "solo", "tambien", "ademas", "aunque", "cual", "cuales",
    "pues", "vale", "mira", "dime", "with", "that", "this", "these", "those", "from", "have", "does", "what",
    "which", "about", "there", "their", "they", "them", "will", "would", "could", "should", "also", "just", "like",
    "some", "more", "than", "then", "when", "where", "into", "your", "know", "tell", "really", "actually", "still",
    "need", "want", "even", "much", "very", "here", "esos", "esas", "aqui", "alli",
))


def norm(text) -> str:
    t = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(t.split())


def content_stems(text) -> set[str]:
    """The comparable stems of what a phrase is ABOUT: words of four letters or more, function words out."""
    return {w[:_STEM] for w in re.findall(r"[a-z]{4,}", norm(text)) if w not in _FUNCTION}


def is_lead(item: dict) -> bool:
    """A web page still to read, not a candidate (the mark `errand_sheet.fila` reads)."""
    return any(norm(f.get("label")) == "origen" and norm(f.get("value")) == "busqueda web"
               for f in (item.get("facts") or []) if isinstance(f, dict))


def _name_words(title) -> set[str]:
    words = re.findall(r"[a-z0-9]+", norm(title))
    return {w for w in words if w not in _FUNCTION and
            (len(w) >= 4 and (w.isalpha() or (any(c.isalpha() for c in w) and any(c.isdigit() for c in w))))}


def named_in(clause: str, items: list[dict]) -> list[dict]:
    """The rows `clause` names, by a word of the title no OTHER row's title has, as a whole word."""
    words = [_name_words(i.get("title")) for i in items]
    said = set(re.findall(r"[a-z0-9]+", norm(clause)))
    out = []
    for k, item in enumerate(items):
        others = set().union(*(w for j, w in enumerate(words) if j != k)) if len(words) > 1 else set()
        if (words[k] - others) & said:
            out.append(item)
    return out


def clauses(heard: str) -> list[str]:
    return [c.strip() for c in re.split(r"(?<=[.?!])\s+", str(heard or "")) if c.strip()]


def asks(heard: str, items: list[dict]) -> list[tuple[dict, set[str]]]:
    """`(row, stems asked about it)` for every QUESTION clause that names rows; [] when none does."""
    out: list[tuple[dict, set[str]]] = []
    for c in clauses(heard):
        if "?" not in c:
            continue
        for item in named_in(c, items):
            if all(item is not seen for seen, _ in out):
                out.append((item, content_stems(c) - content_stems(item.get("title"))))
    return out


def fact_asked(item: dict, stems: set[str]) -> dict | None:
    """The row's fact whose label is what the clause asks about, or None."""
    for f in item.get("facts") or []:
        if isinstance(f, dict) and stems & content_stems(f.get("label")):
            return f
    return None
