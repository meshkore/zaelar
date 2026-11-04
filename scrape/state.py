"""scrape/state.py — the listings a page carries in its own SCRIPT STATE, found by the shape of the values (V2-846).

Measured 2026-11-04: AutoScout24 ships its ads in `__NEXT_DATA__`; coches.net and milanuncios in
`window.__INITIAL_PROPS__ = JSON.parse("…")`, an escaped string; refurbed and idealista in neither. None of them
declares JSON-LD, so `extract.py` found zero on every page that had them all.

HOW A LIST IS FOUND, without a single key name: every JSON the scripts hold is decoded (`<script type=…json>`,
`__NEXT_DATA__`, `= JSON.parse("…")`, `window.X = {…}`); a candidate is an array of at least three objects; its score
is how many of them carry a LINK (a URL or an absolute path that is not a picture) and a TEXT (a string with words).
The best-scoring array is the page's listings. Keys are in the site's language (`price`, `precio`, `prix`), so they
are never read as words: a field is recognised by its value, and what a value cannot say (which number is the price
when there are a price, kilometres and a year) is answered by a MAPPING the model writes ONCE per site, kept as data
(`mapping.py`). Pure: no network, no model.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from scrape import extract as _extract

_MIN_ITEMS = 3
_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|webp|gif|avif)(?:[?#/]|$)", re.I)
_WORDS = re.compile(r"[^\W\d_]{2,}", re.U)
_SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
_JSON_PARSE = re.compile(r"JSON\.parse\(\s*(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*\)", re.S)
#: How many script blobs the last `blobs()` call could not decode (for whoever audits a read).
UNREAD = [0]
_ASSIGN = re.compile(r"(?:window\.|var\s+|let\s+|const\s+)[\w$.]+\s*=\s*(?=[{\[])")


# ── 1 · every JSON the scripts hold ────────────────────────────────────────────────────────────────
def _js_string(lit: str) -> str:
    body = lit[1:-1]
    if lit[0] == "'":
        body = body.replace('\\\'', "'").replace('"', '\\"')
    return json.loads(f'"{body}"')


def blobs(html: str) -> list:
    """Every JSON value the page's scripts carry, decoded. Never raises; a script that is not JSON is counted, not
    read (`UNREAD`), so a page whose state stopped decoding shows up as such."""
    out: list = []
    unread = 0
    dec = json.JSONDecoder()
    for attrs, body in _SCRIPT.findall(html or ""):
        body = body.strip()
        if not body:
            continue
        if "json" in attrs.lower() and "ld+json" not in attrs.lower():
            try:
                out.append(json.loads(body))
            except ValueError:
                unread += 1
            continue
        for m in _JSON_PARSE.finditer(body):
            try:
                out.append(json.loads(_js_string(m.group(1))))
            except ValueError:
                unread += 1
        for m in _ASSIGN.finditer(body):
            try:
                out.append(dec.raw_decode(body, m.end())[0])
            except ValueError:
                unread += 1                         # a JS object literal, not JSON: expected, counted
    UNREAD[0] = unread
    return out


# ── 2 · the page's listings: the array whose items carry a link and a text ─────────────────────────
def is_link(v) -> bool:
    return isinstance(v, str) and (v.startswith(("http://", "https://")) or (v.startswith("/") and len(v) > 3
           and not v.startswith("//") and " " not in v)) and not _IMAGE_EXT.search(v)


def is_image(v) -> bool:
    return isinstance(v, str) and v.startswith(("http://", "https://", "//")) and bool(_IMAGE_EXT.search(v))


def is_text(v) -> bool:
    """A string with words — a name a person reads, not an id: it has a space, two words and more letters than digits."""
    if not isinstance(v, str) or not 3 <= len(v) <= 200 or " " not in v.strip() or is_link(v) or is_image(v):
        return False
    letters = sum(c.isalpha() for c in v)
    return len(_WORDS.findall(v)) >= 2 and letters > sum(c.isdigit() for c in v)


def _scalars(obj, depth: int = 2, prefix: str = ""):
    """(path, value) for the scalar values of an object, nested dicts down to `depth`, first list item of pictures."""
    if not isinstance(obj, dict) or depth < 0:
        return
    for k, v in obj.items():
        path = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _scalars(v, depth - 1, f"{path}.")
        elif isinstance(v, list):
            if v and isinstance(v[0], str):
                yield f"{path}.0", v[0]
            elif v and isinstance(v[0], dict) and depth > 0:
                yield from _scalars(v[0], depth - 1, f"{path}.0.")
        elif v is not None:
            yield path, v


def _arrays(value, path: str = "$", out: list | None = None) -> list:
    out = [] if out is None else out
    if isinstance(value, list):
        dicts = [x for x in value if isinstance(x, dict)]
        if len(dicts) >= _MIN_ITEMS:
            out.append((path, dicts))
        for i, x in enumerate(value[:60]):
            _arrays(x, f"{path}[{i}]", out)
    elif isinstance(value, dict):
        for k, v in value.items():
            _arrays(v, f"{path}.{k}", out)
    return out


def _score(items: list[dict]) -> tuple[int, int]:
    """(items carrying a link and a text, how RICH they are). A listing is an object with many facts — a price, a
    picture, figures; a navigation link (a tag cloud, a list of provinces) has two. Richness is the median count of
    scalar facts, capped, so a long list of thin links never outranks the ads."""
    hits, sizes = 0, []
    for it in items:
        vals = [v for _p, v in _scalars(it)]
        sizes.append(len(vals))
        if any(is_link(v) for v in vals) and any(is_text(v) for v in vals):
            hits += 1
    sizes.sort()
    return hits, min(sizes[len(sizes) // 2] if sizes else 0, 30)


def listings(html: str) -> tuple[str, list[dict]]:
    """`(path, objects)` of the page's listings array, or `("", [])`. At least half of its items must carry a link
    and a text — an array of filters or of breadcrumbs carries labels, not links to items."""
    best: tuple[int, str, list] = (0, "", [])
    for i, blob in enumerate(blobs(html)):
        for path, items in _arrays(blob, f"${i}"):
            hits, rich = _score(items)
            if hits * 2 >= len(items) and rich >= 5 and hits * rich > best[0]:
                best = (hits * rich, path, items)
    return best[1], best[2]


# ── 3 · one object → one record, through a field map ───────────────────────────────────────────────
def get(obj, path: str):
    for part in (path or "").split("."):
        if isinstance(obj, list):
            obj = obj[int(part)] if part.isdigit() and int(part) < len(obj) else None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
    return obj


def shape_map(items: list[dict], page_url: str = "") -> dict:
    """The field map the VALUES alone can give. For each field, of the paths whose values have its shape (a link, a
    picture, a text, a price that carries a currency like `€ 33.900`), the item's OWN value wins: the shallowest path
    first (an ad's title, not its seller's name), then the one whose values differ most across the items (its title,
    not its repeated category), and a link on the page's own site before any other (not its picture host)."""
    from urllib.parse import urlsplit
    site = (urlsplit(page_url).hostname or "").split(".")[-2:] if page_url else []
    shapes = {"url": is_link, "image": is_image, "title": is_text,
              "price": lambda v: isinstance(v, str) and bool(_extract.parse_price(v)[1])}
    seen: dict[str, dict[str, set]] = {f: {} for f in shapes}
    for it in items[:12]:
        for p, v in _scalars(it):
            for f, fits in shapes.items():
                if fits(v):
                    seen[f].setdefault(p, set()).add(v if isinstance(v, str) else repr(v))
                    break

    def own_site(values: set) -> bool:
        return not site or all(v.startswith("/") or (urlsplit(v).hostname or "").split(".")[-2:] == site
                               for v in values)

    def rank(f, p, values):
        return (f != "url" or own_site(values), -p.count("."), len(values))
    return {f: max(paths, key=lambda p: rank(f, p, paths[p])) for f, paths in seen.items() if paths}


def records(items: list[dict], fmap: dict, base_url: str) -> list[dict]:
    """The objects as records of the shape every extractor returns (`extract._jsonld_item`'s)."""
    out = []
    for it in items:
        tmap = fmap.get("title", "")
        title = (" · ".join(str(v) for p in tmap if (v := get(it, p)) not in (None, "")) if isinstance(tmap, list)
                 else get(it, tmap))
        link = get(it, fmap.get("url", ""))
        if not is_text(title) or not is_link(link):
            continue
        raw = get(it, fmap.get("price", "")) if fmap.get("price") else None
        price, currency = _extract.parse_price(raw)
        currency = str(fmap.get("currency") or "").upper() or currency
        image = get(it, fmap.get("image", "")) if fmap.get("image") else ""
        details = {p: v for p in fmap.get("details", []) if (v := get(it, p)) not in (None, "", [])}
        out.append({"title": " ".join(str(title).split()), "url": urljoin(base_url, link),
                    "price": price, "currency": currency,
                    "original_price": "" if raw is None else str(raw), "original_currency": currency,
                    "image": urljoin(base_url, image) if isinstance(image, str) and image else "",
                    "location": "", "published_at": "", "attributes": {k: str(v)[:80] for k, v in details.items()},
                    "extracted_from": "state"})
    return out
