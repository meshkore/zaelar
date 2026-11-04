"""search/listing.py — LISTING search: products, vehicles, boats, homes — over HTTP (V2-556; moved from
`nucleo/listing_search.py` by V2-782; the alias went in refactor2710-06).

The third search mode `search/web.py`'s docstring names («marketplace navigation — no search
engine returns that data») had exactly two implementations: nothing, or a browser worker that costs
minutes. This module is the missing middle: one call in, normalized listings out, and an honest
`needs_browser` when HTTP could not do the job — the operator's «internal MCP»: the ladder is MY
problem, the caller only sees input → output.

THE LADDER (cheap → expensive, each rung optional and fail-open to the next):
  1. **Discovery** — where are the listings? Bright Data SERP API when a token is present (parsed
     Google JSON, geo-targeted per country — quality choice, operator 2026-09-02), else the free
     chain we already own (`websearch.search`: warm Chromium → DDG).
  2+3. **Read** — each candidate page through `scrape.read` (V2-846): the fetch ladder (plain GET → Bright Data
     unlocker) and the extraction ladder (declared JSON-LD/OpenGraph → the page's script state), one validator; then
     the price filter and the dedup here.
  4. **Give up honestly** — `needs_browser: True` + reason. This module NEVER spawns a worker and
     never drives a browser: spend authority and operator messaging stay in FlashBrain/dispatch.

METERING. Bright Data's client is `scrape/brightdata.py` (one for both zones), metered on success there.

BLOCKING, like `websearch`: callers use `asyncio.to_thread`. Results carry a `sources` audit — one
row per rung tried, feeding the Results widget's SOURCES tab («I found nothing» must be auditable).

Keys (env / credentials store): `BRIGHTDATA_API_TOKEN` + zone names `BRIGHTDATA_SERP_ZONE`
(default "serp_api") / `BRIGHTDATA_UNLOCKER_ZONE` (default "web_unlocker1"). Names only, never values.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from loguru import logger

import scrape
from scrape import brightdata as _bd, extract as listing_extract, walls as _walls
from nucleo.errors import brief as _brief

#: How many candidate pages are read at once (each one may wait 5-40 s on the unlocker).
_PARALLEL = int(os.getenv("LISTING_SEARCH_PARALLEL", "4"))

_NON_LISTING_HOSTS = re.compile(
    r"(^|\.)(google|youtube|wikipedia|facebook|instagram|x|twitter|tiktok|reddit|pinterest|"
    r"linkedin)\.", re.I)

# country → (hl, gl) for geo-targeted discovery. The engine's own language decides the DEFAULT
# country upstream (browser_search._where — the €271-in-New-Orleans lesson); this map only serves
# EXPLICIT multi-country fan-out ("in Spain, France and Italy").
_COUNTRY_LOCALE = {
    "ES": ("es", "es"), "FR": ("fr", "fr"), "IT": ("it", "it"), "PT": ("pt-PT", "pt"),
    "DE": ("de", "de"), "GB": ("en-GB", "uk"), "UK": ("en-GB", "uk"), "US": ("en", "us"),
    "MX": ("es-MX", "mx"), "AR": ("es-AR", "ar"), "NL": ("nl", "nl"), "BE": ("fr-BE", "be"),
}


@dataclass(frozen=True)
class ListingQuery:
    """What the caller wants, structurally — never a prompt. `text` is the operator's own words for
    the thing («Lagoon 440 usado»); the structured fields are constraints the router already parsed."""
    text: str
    countries: tuple[str, ...] = ()          # ISO-ish, e.g. ("ES", "FR"); empty → engine's own locale
    price_max: float | None = None
    price_min: float | None = None
    currency: str = ""                        # what the price bounds are expressed in
    condition: str = ""                       # "used" | "new" | "" — travels to discovery as words
    # V2-840 H3 — the request's country and category in the words of that market, as the errand's brief declared
    # them («España coches de segunda mano»): discovery without them pulled another country's classifieds.
    market: str = ""
    limit: int = 20
    min_needed: int = 5                       # fewer normalized items than this → needs_browser
    fetch_cap: int = 8                        # candidate pages fetched per country, max
    # A caller answering a LIVE turn cannot wait for eight polite fetches (V2-556 P1: the in-turn fast
    # pass budgets single-digit seconds). 0 = no deadline — the escalated/offline caller's default.
    deadline_s: float = 0.0


# ── result cache (the websearch `_recent_answer` pattern, listing-keyed) ─────────────────────────
_CACHE_TTL_S = float(os.getenv("LISTING_SEARCH_CACHE_TTL", str(30 * 60)))
_cache: dict[tuple, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _cache_key(q: ListingQuery) -> tuple:
    return (" ".join(q.text.lower().split()), q.countries, q.price_max, q.price_min, q.condition)


def _cached(q: ListingQuery) -> dict | None:
    with _cache_lock:
        hit = _cache.get(_cache_key(q))
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_S:
            return dict(hit[1])
        return None


def _remember(q: ListingQuery, result: dict) -> None:
    with _cache_lock:
        if len(_cache) > 64:
            _cache.clear()            # crude and sufficient: a bounded scratchpad, not a store
        _cache[_cache_key(q)] = (time.monotonic(), result)


# ── rung 1: discovery ────────────────────────────────────────────────────────────────────────────
def _discovery_words(q: ListingQuery) -> str:
    """What discovery searches for: his words, the condition, and the market's words he did not already say."""
    words = q.text
    for extra in (q.condition, q.market):
        extra = " ".join(str(extra or "").split())
        if extra and extra.lower() not in words.lower():
            words = f"{words} {extra}"
    return words


def _serp_discover(q: ListingQuery, country: str) -> list[dict]:
    """Bright Data SERP: Google results parsed to Light JSON, the exit country in the BODY. Measured 2026-11-04:
    `brd_json=1` in the url or `hl`/`gl` met a captcha and an empty 200; `data_format: parsed_light` with `country`
    answered. Its organic links are often Google's opaque `/goto` redirects — not pages, dropped."""
    hl, _gl = _COUNTRY_LOCALE.get(country.upper(), ("en", country.lower() or "us"))
    url = f"https://www.google.com/search?q={quote_plus(_discovery_words(q))}&hl={hl}"
    raw = _bd.request({"zone": _bd.zone_serp(), "url": url, "format": "raw", "data_format": "parsed_light",
                       "country": (country or "us").lower()}, provider="brightdata_serp")
    data = json.loads(raw)
    out = []
    for entry in (data.get("organic") or []):
        link = entry.get("link") or entry.get("url") or ""
        if link.startswith(("http://", "https://")):
            out.append({"url": link, "title": entry.get("title", ""),
                        "snippet": entry.get("description", "")})
    return out


def _free_discover(q: ListingQuery) -> list[dict]:
    """No token → the discovery we already own: `web.search(mode="results")` (Z.ai when keyed → Brave → warm
    Chromium → DDG), which meters, caches and reports failures itself. Single-locale — the engine's own."""
    from search import web as websearch
    words = _discovery_words(q)
    found = websearch.search(words, k=10, mode="results")
    return [{"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")}
            for r in found.get("results", []) if r.get("url")]


def _candidate_urls(discovered: list[dict], cap: int) -> list[str]:
    out: list[str] = []
    for row in discovered:
        url = row["url"]
        host = _walls.host_of(url)
        if not host or _NON_LISTING_HOSTS.search(host):
            continue
        if url not in out:
            out.append(url)
        if len(out) >= cap:
            break
    return out


# ── the module's one door ────────────────────────────────────────────────────────────────────────
def search(q: ListingQuery) -> dict:
    """Input → output: `{items, sources, exhausted, needs_browser, reason}`. BLOCKING (network) —
    call with `asyncio.to_thread`. Never raises: a broken rung is a source row, not an exception."""
    cached = _cached(q)
    if cached is not None:
        cached["cached"] = True
        return cached

    sources: list[dict] = []
    items: list[dict] = []
    countries = tuple(c.upper() for c in q.countries) or ("",)

    # The deadline stops WORK, never honesty: what was already fetched is still extracted, deduped and
    # returned, and `exhausted` flips to False so the caller knows the ladder was cut short, not climbed.
    t0 = time.monotonic()
    timed_out = False

    def _out_of_time() -> bool:
        nonlocal timed_out
        if q.deadline_s > 0 and (time.monotonic() - t0) >= q.deadline_s:
            timed_out = True
        return timed_out

    for country in countries:
        if _out_of_time():
            break
        # 1 · discovery
        # Our own discovery first (1-3 s, real pages); the SERP first only when he named countries — the one
        # thing our chain cannot do is search from another country (Bright Data SERP: 6-53 s, 2026-11-04).
        discovered: list[dict] = []
        tiers = (("serp", "free") if q.countries else ("free", "serp")) if _bd.token() else ("free",)
        for tier in tiers:
            if discovered:
                break
            name, target = ("serp", f"google/{country or 'default'}") if tier == "serp" else ("discovery-free", "websearch")
            try:
                discovered = _serp_discover(q, country or "us") if tier == "serp" else _free_discover(q)
                sources.append({"tier": name, "target": target, "status": "ok", "n": len(discovered)})
            except Exception as e:  # noqa: BLE001
                sources.append({"tier": name, "target": target, "status": "error", "note": _brief(e, 120)})

        # 2+3 · read the candidate pages AT ONCE, a few at a time. In series, a hunt whose pages need the unlocker took
        # ~140 s from a Fly Machine (seven pages × ~20 s). Politeness per host stays in `scrape.fetch` (a second
        # read of the same host waits its turn); the deadline cuts what has not come back, never what has.
        urls = _candidate_urls(discovered, q.fetch_cap)
        if not urls or _out_of_time():
            continue
        pool = ThreadPoolExecutor(max_workers=min(_PARALLEL, len(urls)))
        futures = [(url, pool.submit(scrape.read, url, "listings", country=country)) for url in urls]
        left = (q.deadline_s - (time.monotonic() - t0)) if q.deadline_s > 0 else None
        wait([f for _u, f in futures], timeout=left)
        pool.shutdown(wait=False, cancel_futures=True)
        for url, fut in futures:
            host = _walls.host_of(url)
            if not fut.done():
                timed_out = True
                sources.append({"tier": "fetch", "target": host, "status": "cut", "note": "out of time"})
                continue
            page = fut.result()
            if not page.html:
                sources.append({"tier": "fetch", "target": host, "status": "blocked",
                                "note": _brief(" · ".join(t.get("note", "") for t in page.tried), 120)})
                continue
            via, found = page.how, page.records
            for item in found:
                item["source"] = host
                item["country"] = country
            kept = [i for i in found
                    if listing_extract.matches_price(i, price_max=q.price_max, price_min=q.price_min)]
            sources.append({"tier": "fetch", "target": host, "status": "ok", "via": via,
                            "n": len(found), "kept": len(kept)})
            items.extend(kept)

    items = listing_extract.dedup(items)[: q.limit]
    blocked = sum(1 for s in sources if s.get("status") == "blocked")
    needs_browser = len(items) < q.min_needed
    reason = ""
    if needs_browser:
        if timed_out:
            reason = (f"time budget ({q.deadline_s:.0f}s) ran out with {len(items)} structured "
                      "listings — the ladder was cut short, not exhausted")
        elif blocked and not _bd.token():
            reason = (f"{blocked} candidate pages behind bot walls and no unlocker token — "
                      "a browser session is the remaining way in")
        elif items:
            reason = f"only {len(items)} structured listings found; below min_needed={q.min_needed}"
        else:
            reason = "no page held listings any extraction rung could read"
    result = {"query": q.text, "items": items, "sources": sources,
              "exhausted": not timed_out, "needs_browser": needs_browser, "reason": reason}
    # A cut-short round is NOT what this query returns — it is what fit in this caller's budget. Caching it
    # would serve the truncation to every caller for half an hour, including one with no deadline at all.
    if not timed_out:
        _remember(q, result)
    if needs_browser:
        logger.info(f"listing_search: '{q.text[:60]}' → {len(items)} items, needs_browser ({reason})")
    return result
