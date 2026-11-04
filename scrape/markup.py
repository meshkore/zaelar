"""scrape/markup.py — the listings a page shows only in its MARKUP, read from the repeated cards (V2-846 F5).

Measured 2026-11-04: idealista and refurbed put their ads in the HTML and nowhere else — no JSON-LD, no script state —
so neither `extract.py` nor `state.py` found a single one. A listings page repeats one card per item; the cards are the
children of ONE container that each carry a link and a price (`cards()`). Inside a card the fields are recognised by
the shape of their values, as in `state.py`: the link on the page's own site, the text with words, the amount with a
currency, the picture. When the values cannot say it, the model names the elements once per site as selectors
(`dom.py`'s syntax), kept as data next to the state maps (`mapping.py`). Pure; no network, no model here.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from scrape import dom as _dom, extract as _extract, state as _state, validate as _validate

_MIN_CARDS = 4
_HEADINGS = ("h1", "h2", "h3", "h4", "h5")


#: An amount is the number written AGAINST its currency (`$4,995`, `1.030 €`, `€ 33.900`). «10 for sale starting at
#: $4,995» holds two numbers; the price is the one the currency touches (AutoTrader, 2026-11-04).
_AMOUNT = re.compile(r"(?:[$€£]\s?\d[\d.,]*|\d[\d.,]*\s?(?:[$€£]|(?:EUR|USD|GBP)\b)|\b(?:EUR|USD|GBP)\s?\d[\d.,]*)")


def _priced(n: _dom.Node) -> str:
    """The amount in the smallest SUBTREE of `n` that holds one against its currency (idealista writes `1.030` and
    `€/mes` in two elements), or ""."""
    best = ""
    for e in n.iter():
        t = e.all_text()
        if not t or len(t) > 60:
            continue
        m = _AMOUNT.search(t)
        if m and all(_extract.parse_price(m.group(0))) and (not best or len(t) < len(best[1])):
            best = (m.group(0), t)
    return best[0] if best else ""


def _links(n: _dom.Node, page_url: str) -> list[_dom.Node]:
    site = _validate.site_of(page_url)
    out = []
    for a in n.select("a"):
        href = urljoin(page_url, a.attrs.get("href", ""))
        if href.startswith("http") and _validate.site_of(href) == site and href.split("#")[0] != page_url:
            out.append(a)
    return out


def cards(root: _dom.Node, page_url: str) -> tuple[_dom.Node | None, list[_dom.Node]]:
    """`(container, cards)` — the container whose children most often each carry a same-site link and a price."""
    best: tuple[int, _dom.Node | None, list] = (0, None, [])
    for node in root.iter():
        if len(node.children) < _MIN_CARDS:
            continue
        kids = [c for c in node.children if _links(c, page_url) and _priced(c)]
        if len(kids) >= _MIN_CARDS and len(kids) > best[0]:
            best = (len(kids), node, kids)
    return best[1], best[2]


def _title_of(card: _dom.Node, links: list[_dom.Node]) -> tuple[str, _dom.Node]:
    """(title, the link that names the item). The link whose text reads as a name is the item's own — a card also
    links its seller or its agency."""
    for a in links:
        t = a.all_text()
        if _state.is_text(t):
            return t, a
    for h in _HEADINGS:
        e = card.first(h)
        if e and _state.is_text(e.all_text()):
            return e.all_text(), (e.first("a") or links[0])
    texts = [" ".join(e.text) for e in card.iter() if _state.is_text(" ".join(e.text))]
    return (max(texts, key=len)[:160] if texts else ""), links[0]


def records(container_cards: list[_dom.Node], page_url: str) -> list[dict]:
    """The cards as records of the shape every extractor returns, fields read by the shape of their values."""
    out = []
    for card in container_cards:
        links = _links(card, page_url)
        if not links:
            continue
        price_text = _priced(card)
        price, currency = _extract.parse_price(price_text)
        img = card.first("img")
        image = (img.attrs.get("src") or img.attrs.get("data-src") or "") if img else ""
        title, link = _title_of(card, links)
        details = []
        for e in card.iter():
            t = " ".join(e.text)
            if t and t not in price_text and t not in title and any(ch.isdigit() for ch in t) and len(t) <= 40:
                details.append(t)
        out.append({"title": " ".join(title.split()), "url": urljoin(page_url, link.attrs.get("href", "")),
                    "price": price, "currency": currency, "original_price": price_text,
                    "original_currency": currency,
                    "image": urljoin(page_url, image) if image and not image.startswith("data:") else "",
                    "location": "", "published_at": "",
                    "attributes": {f"detail{i}": d for i, d in enumerate(dict.fromkeys(details))} if details else {},
                    "extracted_from": "markup"})
    return out


def listings(html: str, page_url: str) -> list[dict]:
    """The page's markup listings, or []. Validation is the caller's (`scrape.records_of`)."""
    _container, found = cards(_dom.parse(html), page_url)
    return records(found, page_url)


def readable(html: str, page_url: str, limit: int = 15000) -> str:
    """The page as text a model can read: its words, each link written after its text as `<url>`, scripts and styles
    gone, cut at `limit`. For the last rung only (`scrape.records_of`)."""
    parts: list[str] = []

    def walk(n: _dom.Node):
        if n.tag == "a" and n.attrs.get("href"):
            t = n.all_text()
            if t:
                parts.append(f"{t} <{urljoin(page_url, n.attrs['href'])}>")
            return
        parts.extend(n.text)
        if n.tag in ("p", "div", "li", "article", "section", "tr", "h1", "h2", "h3", "h4"):
            parts.append("\n")
        for c in n.children:
            walk(c)
    walk(_dom.parse(html))
    text = " ".join(parts)
    text = "\n".join(" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in text.split("\n") if line)[:limit]
