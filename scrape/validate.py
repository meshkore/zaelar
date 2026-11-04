"""scrape/validate.py — ONE validator every extraction rung passes through (V2-846).

A record counts when it names something (a title with words), links to an item ON THE PAGE'S OWN SITE (not a picture
host, not another site), and its price — when it has one — is a positive number. Duplicates of an earlier record go.
A rung whose records mostly fail this has read the wrong thing (a picture URL taken for the link, a category for the
title), and its result does not count: the next rung, or a better field map, is asked instead. Pure.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from scrape import extract as _extract

#: A rung's result counts when at least this share of what it extracted passes.
MIN_SHARE = 0.6


def site_of(url: str) -> str:
    """The registrable part of a host, simply: its last two labels (`www.coches.net` → `coches.net`)."""
    host = (urlsplit(url or "").hostname or "").lower()
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 and len(parts[-2]) <= 3 and len(parts[-1]) == 2 else \
        ".".join(parts[-2:])


def ok(record: dict, page_url: str) -> bool:
    title, link = str(record.get("title") or ""), str(record.get("url") or "")
    if len(title.strip()) < 3 or not link.startswith(("http://", "https://")):
        return False
    if site_of(link) != site_of(page_url) or link.split("#")[0].rstrip("/") == page_url.split("#")[0].rstrip("/"):
        return False
    price = record.get("price")
    return price is None or (isinstance(price, (int, float)) and price > 0)


#: Listings are DISTINCT items: when most records share a link, the link field is not the item's (a category page
#: taken for each ad's link — measured on milanuncios, 41 ads → 21 links).
MIN_DISTINCT = 0.7


def keep(records: list[dict], page_url: str) -> tuple[list[dict], bool]:
    """(the records that pass, deduplicated; whether the rung's result counts)."""
    good = [r for r in records if ok(r, page_url)]
    distinct = len({_extract.canonical_url(r["url"]) for r in good})
    counts = bool(records) and len(good) >= MIN_SHARE * len(records) and distinct >= MIN_DISTINCT * len(good)
    return _extract.dedup(good), counts
