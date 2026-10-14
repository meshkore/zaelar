"""nucleo/workers/answer_rows.py — the candidates a search ANSWER names become rows of the errand's sheet.

search-buy-boat-multicountry ES (2026-10-14, sandbox 093838-es). A worker asked our search for «Lagoon 440 … con
enlace del anuncio, precio, año y ubicación»; the provider answered in prose — «1. **Lagoon 440 de 2009** -
**Precio**: 299.000 € - **Ubicación**: Sitges … - **Enlace**: ([yachtworld.es](https://…))» — and only its two
citation rows (two listing INDEX pages) reached the sheet (`findings.hand_search_rows` reads `results` alone). The
candidate lived in the errand's «latest lead» line, labelled «not a candidate», and «me los pasas cuando tengas
los enlaces y años» was answered with a step while the sheet showed two pages.

An enumerated item of the answer is a row when it carries the three things a row needs on its own: a name (its
bold head, or the text before its first field), exactly ONE amount (several is ambiguity, V2-471) and a link the
answer itself wrote. When the answer cites sources, the link's host must be one of them — a link no citation backs
is the model's, not the index's. Pure: no store, no network; the sheet's door (`results.intake`) judges the rows
like any other.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from search.candidacy import lone_amount

#: Where an enumerated item starts: «1. », «2) » at a line start or after a sentence; failing that, an UNindented
#: bullet (an indented one is a field of the item above it — «   - **Precio**: …»).
_NUM_RE = re.compile(r"(?:^|\n|(?<=[.:;)])\s)\s*\d{1,2}[.)]\s+")
_BULLET_RE = re.compile(r"(?:^|\n)[-*•]\s+")
_BOLD_RE = re.compile(r"^\s*\*\*(.+?)\*\*")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^)\s]+)\)")
_BARE_URL_RE = re.compile(r"https?://[^\s)\]»>]+")
_FIELD_SPLIT_RE = re.compile(r"\s+-\s+|\n")
_MAX_ROWS = 6


def _host(url: str) -> str:
    try:
        h = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return h[4:] if h.startswith("www.") else h


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[*_`]+", "", str(text or "")).split())


def _items(answer: str) -> list[str]:
    text = str(answer or "")
    hits = list(_NUM_RE.finditer(text)) or list(_BULLET_RE.finditer(text))
    ends = [m.start() for m in hits[1:]] + [len(text)]
    # an item ends at the next one, or at the blank line that closes the list («También puedes mirar en …»)
    return [text[m.end():b].split("\n\n", 1)[0] for m, b in zip(hits, ends)]


def _row(item: str, hosts: set[str]) -> dict | None:
    links = _MD_LINK_RE.findall(item) or _BARE_URL_RE.findall(item)
    if len(set(links)) != 1:
        return None
    url = links[0].rstrip(".,;")
    if hosts and _host(url) not in hosts:
        return None
    price = lone_amount(_BARE_URL_RE.sub(" ", _MD_LINK_RE.sub(" ", item)))
    if not price:
        return None
    bold = _BOLD_RE.match(item)
    fields = [_plain(f) for f in _FIELD_SPLIT_RE.split(item) if _plain(f)]
    title = _plain(bold.group(1)) if bold else (fields[0] if fields else "")
    if not title or _BARE_URL_RE.search(title) or price in title and len(title) <= len(price) + 2:
        return None
    # the item's other fields (place, year…) as written; the price and the link are the row's own fields
    rest = [f for f in fields[1:] if price not in f and not _BARE_URL_RE.search(f) and not f.endswith(":")]
    return {"title": title[:160], "price": price, "url": url, "subtitle": " · ".join(rest)[:160],
            "facts": [{"label": "Origen", "value": "búsqueda web"}]}


def rows_of(res: dict) -> list[dict]:
    """The answer's enumerated candidates as sheet rows ([] when it names none whole)."""
    if not isinstance(res, dict):
        return []
    hosts = {_host(str(r.get("url") or "")) for r in (res.get("results") or []) if isinstance(r, dict)} - {""}
    out: list[dict] = []
    for item in _items(str(res.get("answer") or "")):
        row = _row(item, hosts)
        if row and all(row["url"] != o["url"] or row["title"] != o["title"] for o in out):
            out.append(row)
    return out[:_MAX_ROWS]
