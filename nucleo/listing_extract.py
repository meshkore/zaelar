"""nucleo/listing_extract.py — structured LISTINGS out of a page, without a browser (V2-556).

The missing middle tier of listing search: most marketplaces and stores publish their listings as
schema.org structured data — JSON-LD blocks (`Product`, `Offer`, `Vehicle`, `Boat`,
`RealEstateListing`, `ItemList` of those) and OpenGraph meta tags — precisely so machines do not
have to guess at their DOM. Reading THAT is orders of magnitude cheaper than driving a Chromium,
and stable across redesigns in a way DOM scraping never is.

PURE on purpose: text in, normalized items out. No network, no engine state — the fetching, rate
limiting and metering live in `nucleo/listing_search.py`; this module is the part a unit test can
hold still. Regex-based (no HTML parser in the deps, checked 2026-09-02): JSON-LD lives in
`<script type="application/ld+json">` blocks and OpenGraph in `<meta property=…>` tags, both of
which are regular enough for that to be honest. What is deliberately NOT here is a per-site DOM
scraper — when structured data is absent, the answer is the browser worker, not a fragile guess.

The normalized item is the Results widget's vocabulary (`widgets/results/data.py`) plus the
never-destroy-the-source rule: `original_price`/`original_currency` always survive normalization.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlsplit, urlunsplit

# schema.org types that ARE a listing. Anything else found in JSON-LD (BreadcrumbList, Organization,
# WebSite…) is page furniture, not a result. `ItemList` is unpacked, not listed: its elements are.
_LISTING_TYPES = frozenset({
    "product", "productmodel", "individualproduct", "offer", "aggregateoffer",
    "vehicle", "car", "motorcycle", "motorizedbicycle", "busortrain", "boat",
    "realestatelisting", "apartment", "house", "singlefamilyresidence", "accommodation",
    "residence", "event", "book",
})

# Scalar JSON-LD fields copied into `attributes` when present — the category-specific data the
# operator compares on (year, mileage, length…). Generic vocabulary, never a per-site table.
_ATTRIBUTE_FIELDS = (
    "brand", "model", "sku", "mpn", "color", "itemCondition", "productionDate",
    "vehicleModelDate", "modelDate", "mileageFromOdometer", "vehicleTransmission", "fuelType",
    "vehicleEngine", "numberOfDoors", "vehicleSeatingCapacity", "bodyType",
    "numberOfRooms", "numberOfBathroomsTotal", "floorSize", "yearBuilt",
    "startDate", "endDate", "isbn", "author", "datePublished",
)

_JSONLD_RE = re.compile(
    r"<script[^>]+type\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S)
_META_RE = re.compile(
    r"<meta[^>]+(?:property|name)\s*=\s*[\"']((?:og|product|twitter)[:.][^\"']+)[\"'][^>]*?"
    r"content\s*=\s*[\"']([^\"']*)[\"']", re.I)
# content= can come BEFORE property= — both orders are legal and both are out there.
_META_RE_REV = re.compile(
    r"<meta[^>]+content\s*=\s*[\"']([^\"']*)[\"'][^>]*?"
    r"(?:property|name)\s*=\s*[\"']((?:og|product|twitter)[:.][^\"']+)[\"']", re.I)

_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "¥": "JPY"}
_TRACKING_PARAMS = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|ref_)")


# ── price ────────────────────────────────────────────────────────────────────────────────────────
def parse_price(text) -> tuple[float | None, str]:
    """`"299.000 €"` → `(299000.0, "EUR")` · `"$1,795.50"` → `(1795.5, "USD")`. Handles the
    European (dot-thousands, comma-decimal) and Anglo (comma-thousands, dot-decimal) conventions by
    looking at the LAST separator: 1-2 trailing digits make it a decimal mark, three make it a
    thousands mark. Returns `(None, "")` rather than guessing when there is no number."""
    if isinstance(text, (int, float)):
        return float(text), ""
    s = str(text or "").strip()
    if not s:
        return None, ""
    currency = ""
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in s:
            currency = code
            break
    m = re.search(r"\b(EUR|USD|GBP|JPY|CHF|MXN|ARS|BRL)\b", s, re.I)
    if m:
        currency = m.group(1).upper()
    num = re.search(r"\d[\d.,\s ]*", s)
    if not num:
        return None, currency
    raw = num.group(0).replace(" ", "").replace(" ", "")
    last_dot, last_comma = raw.rfind("."), raw.rfind(",")
    if last_dot == -1 and last_comma == -1:
        cleaned = raw
    else:
        sep = max(last_dot, last_comma)
        decimals = len(raw) - sep - 1
        if 1 <= decimals <= 2:
            cleaned = raw[:sep].replace(".", "").replace(",", "") + "." + raw[sep + 1:]
        else:
            cleaned = raw.replace(".", "").replace(",", "")
    try:
        return float(cleaned), currency
    except ValueError:
        return None, currency


# ── JSON-LD ──────────────────────────────────────────────────────────────────────────────────────
def _iter_jsonld_nodes(html: str):
    for block in _JSONLD_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except Exception:  # noqa: BLE001 — malformed JSON-LD is common; skip, never die
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            node = stack.pop()
            if not isinstance(node, dict):
                continue
            if isinstance(node.get("@graph"), list):
                stack.extend(node["@graph"])
            yield node
            # ItemList pages (search results) carry their products INSIDE the elements.
            for el in node.get("itemListElement") or []:
                if isinstance(el, dict):
                    stack.append(el.get("item") if isinstance(el.get("item"), dict) else el)


def _node_type(node: dict) -> str:
    t = node.get("@type")
    if isinstance(t, list):
        t = t[0] if t else ""
    return str(t or "").rsplit("/", 1)[-1].lower()


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _offer_of(node: dict) -> dict:
    offer = _first(node.get("offers"))
    return offer if isinstance(offer, dict) else {}


def _text_of(value) -> str:
    """A JSON-LD field may be a scalar or a nested node (`brand: {name: "BMW"}`)."""
    v = _first(value)
    if isinstance(v, dict):
        return _text_of(v.get("name") or v.get("value") or v.get("@id") or "")
    return str(v).strip() if v is not None else ""


def _aggregate_offer(offer: dict) -> bool:
    """A node priced by an AGGREGATE is a COLLECTION pricing itself, never one thing for sale.

    Measured 2026-09-02, first round of the new circuit: coches.net's and OcasionPlus's CATEGORY pages
    declare a Product with an AggregateOffer («desde 300 EUR»), and the fast pass delivered them as
    candidates — the agent spoke «un coche por 300 EUR» and the judge rightly called it inventing. The
    V2-510 rule one level down: a page that prices a collection is a SOURCE, never a candidate. The tells
    are structural (its own @type, an offerCount, or a low/high range without a plain price) — never a
    hostname list."""
    if _node_type(offer) == "aggregateoffer" or "offerCount" in offer:
        return True
    return ("lowPrice" in offer or "highPrice" in offer) and offer.get("price") is None


def _jsonld_item(node: dict, base_url: str) -> dict | None:
    ntype = _node_type(node)
    offer = _offer_of(node)
    if ntype == "offer":
        offer, node = node, (node.get("itemOffered") if isinstance(node.get("itemOffered"), dict) else node)
    elif ntype == "aggregateoffer" or ntype not in _LISTING_TYPES:
        return None
    if _aggregate_offer(offer):
        return None
    title = _text_of(node.get("name") or node.get("title"))
    if not title:
        return None
    # `lowPrice` is deliberately NOT a price fallback: it is the bottom of a range, i.e. the aggregate tell.
    price_raw = offer.get("price")
    if price_raw is None and isinstance(offer.get("priceSpecification"), (dict, list)):
        price_raw = (_first(offer["priceSpecification"]) or {}).get("price")
    price, sym_currency = parse_price(price_raw)
    currency = str(offer.get("priceCurrency") or "").upper() or sym_currency
    url = _text_of(node.get("url") or offer.get("url") or node.get("@id"))
    image = _text_of(node.get("image"))
    attributes: dict = {}
    for field in _ATTRIBUTE_FIELDS:
        if field in node:
            val = _text_of(node.get(field))
            if val:
                attributes[field] = val
    location = _text_of((node.get("address") or {}).get("addressLocality")
                        if isinstance(node.get("address"), dict) else node.get("address"))
    if not location and isinstance(offer.get("availableAtOrFrom"), dict):
        location = _text_of(offer["availableAtOrFrom"].get("name"))
    return {
        "title": title,
        "url": urljoin(base_url, url) if url else base_url,
        "price": price, "currency": currency,
        "original_price": str(price_raw) if price_raw is not None else "",
        "original_currency": currency,
        "image": urljoin(base_url, image) if image else "",
        "location": location,
        "published_at": _text_of(node.get("datePosted") or node.get("datePublished")),
        "attributes": attributes,
        "extracted_from": "jsonld",
    }


# ── OpenGraph fallback (one item per page at most) ───────────────────────────────────────────────
def _opengraph_item(html: str, base_url: str) -> dict | None:
    meta: dict[str, str] = {}
    for pattern, flip in ((_META_RE, False), (_META_RE_REV, True)):
        for a, b in pattern.findall(html or ""):
            key, content = (b, a) if flip else (a, b)
            meta.setdefault(key.lower().replace("product.", "product:"), content)
    og_type = meta.get("og:type", "")
    price_raw = (meta.get("product:price:amount") or meta.get("og:price:amount")
                 or meta.get("product:price") or "")
    title = meta.get("og:title", "").strip()
    # A page whose og:type is not product-like and carries no price is an article/site card — the
    # fallback must not invent a listing out of every homepage it reads.
    if not title or (not price_raw and "product" not in og_type):
        return None
    price, sym_currency = parse_price(price_raw)
    currency = (meta.get("product:price:currency") or meta.get("og:price:currency")
                or sym_currency).upper()
    return {
        "title": title,
        "url": urljoin(base_url, meta.get("og:url", "") or base_url),
        "price": price, "currency": currency,
        "original_price": price_raw, "original_currency": currency,
        "image": meta.get("og:image", ""),
        "location": "", "published_at": "",
        "attributes": {},
        "extracted_from": "opengraph",
    }


# ── public surface ───────────────────────────────────────────────────────────────────────────────
def extract_items(html: str, base_url: str) -> list[dict]:
    """Every listing the page DECLARES, JSON-LD first (richer, can carry many per page), OpenGraph
    as the one-item fallback. Empty list means the page declares nothing — which is a fact about the
    page, and the caller's cue to consider the browser tier, never this module's cue to guess."""
    items: list[dict] = []
    seen_urls: set[str] = set()
    for node in _iter_jsonld_nodes(html):
        item = _jsonld_item(node, base_url)
        if item and item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            items.append(item)
    # On a MULTI-item page, an item pointing at the page ITSELF is the page describing itself (a category's
    # own Product node with no url of its own falls back to base_url) — furniture, not a candidate. A page
    # declaring exactly ONE item keeps it: a true detail page's listing legitimately IS its own url.
    if len(items) > 1:
        base_key = canonical_url(base_url)
        real = [i for i in items if canonical_url(i["url"]) != base_key]
        if real:
            items = real
    if not items:
        og = _opengraph_item(html, base_url)
        if og:
            items.append(og)
    return items


def canonical_url(url: str) -> str:
    """Dedup key: scheme/host lowercased, tracking params and fragment dropped, trailing slash
    normalized. The SAME listing reached through Google and through the site must collide here."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return str(url or "")
    query = "&".join(sorted(
        p for p in parts.query.split("&") if p and not _TRACKING_PARAMS.match(p.split("=")[0].lower())
    ))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(),
                       parts.path.rstrip("/") or "/", query, ""))


def _title_key(title: str) -> str:
    return " ".join(sorted(re.findall(r"[a-z0-9áéíóúñü]+", str(title or "").lower())))


def dedup(items: list[dict]) -> list[dict]:
    """Same listing, once: by canonical URL first, then by (normalized title words, rounded price).
    The second key exists because marketplaces mirror each other's listings under different URLs."""
    out: list[dict] = []
    seen: set = set()
    for item in items:
        keys = [("u", canonical_url(item.get("url", "")))]
        if item.get("price") is not None:
            keys.append(("tp", _title_key(item.get("title", "")), round(float(item["price"]))))
        if any(k in seen for k in keys):
            continue
        seen.update(keys)
        out.append(item)
    return out


def matches_price(item: dict, *, price_max: float | None = None,
                  price_min: float | None = None) -> bool:
    """An item with NO price passes: dropping it silently would hide exactly the listings a human
    would click to check. The caller decides how unpriced items rank, not whether they exist."""
    price = item.get("price")
    if price is None:
        return True
    if price_max is not None and price > price_max:
        return False
    if price_min is not None and price < price_min:
        return False
    return True
