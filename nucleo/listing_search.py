"""nucleo/listing_search.py — LISTING search: products, vehicles, boats, homes — over HTTP (V2-556).

The third search mode `nucleo/websearch.py`'s docstring names («marketplace navigation — no search
engine returns that data») had exactly two implementations: nothing, or a browser worker that costs
minutes. This module is the missing middle: one call in, normalized listings out, and an honest
`needs_browser` when HTTP could not do the job — the operator's «internal MCP»: the ladder is MY
problem, the caller only sees input → output.

THE LADDER (cheap → expensive, each rung optional and fail-open to the next):
  1. **Discovery** — where are the listings? Bright Data SERP API when a token is present (parsed
     Google JSON, geo-targeted per country — quality choice, operator 2026-09-02), else the free
     chain we already own (`websearch.search`: warm Chromium → DDG).
  2. **Fetch** — each candidate page over plain HTTP, through Bright Data Web Unlocker when a token
     is present (bot walls become 200s; billed per SUCCESS) — with per-domain rate limiting either way.
  3. **Extract** — `nucleo/listing_extract.py`: JSON-LD / OpenGraph, normalize, price-filter, dedup.
  4. **Give up honestly** — `needs_browser: True` + reason. This module NEVER spawns a worker and
     never drives a browser: spend authority and operator messaging stay in FlashBrain/dispatch.

MONEY. Every successful Bright Data request is metered (`energy_meter.report_search_usage`), same
contract as websearch's paid backends: rates live in `_SEARCH_USD_PER_REQUEST` with source+date, and
a provider without a rate bills at the catch-all, loudly. No token → the whole module runs free.

BLOCKING, like `websearch`: callers use `asyncio.to_thread`. Results carry a `sources` audit — one
row per rung tried, feeding the Results widget's SOURCES tab («I found nothing» must be auditable).

Keys (env / credentials store): `BRIGHTDATA_API_TOKEN` + zone names `BRIGHTDATA_SERP_ZONE`
(default "serp_api") / `BRIGHTDATA_UNLOCKER_ZONE` (default "web_unlocker1"). Names only, never values.
"""
from __future__ import annotations

import json
import os
import random
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import quote_plus, urlsplit

from loguru import logger

from nucleo import listing_extract
from nucleo.errors import brief as _brief

_BD_ENDPOINT = "https://api.brightdata.com/request"
_TIMEOUT = float(os.getenv("LISTING_SEARCH_TIMEOUT", "12.0"))
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Hosts that a SERP returns constantly and that are never a LISTING page. Aggregating/social/media —
# not a per-marketplace table (that would be the scenario-shaped hole the use-case norm forbids).
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
    limit: int = 20
    min_needed: int = 5                       # fewer normalized items than this → needs_browser
    fetch_cap: int = 8                        # candidate pages fetched per country, max


# ── keys ─────────────────────────────────────────────────────────────────────────────────────────
def _bd_token() -> str:
    return (os.getenv("BRIGHTDATA_API_TOKEN") or "").strip()


def _bd_zone_serp() -> str:
    return (os.getenv("BRIGHTDATA_SERP_ZONE") or "serp_api").strip()


def _bd_zone_unlocker() -> str:
    return (os.getenv("BRIGHTDATA_UNLOCKER_ZONE") or "web_unlocker1").strip()


def _meter(provider: str) -> None:
    """Paid request → Energy, same seam as websearch. Free rungs never call this."""
    try:
        from nucleo import energy_meter as _energy
        _energy.report_search_usage(provider=provider)
    except Exception:  # noqa: BLE001 — the counter's own gates are @_never_raises; belt and braces
        pass


# ── per-domain politeness (the analyst's numbers, kept minimal) ──────────────────────────────────
_MIN_INTERVAL_S = float(os.getenv("LISTING_SEARCH_DOMAIN_INTERVAL", "2.0"))
_PENALTY_S = 120.0                    # repeated 403/429 → the domain rests; retrying into a wall
_MAX_WAIT_S = 6.0                     # is how a polite scraper becomes a banned one
_domain_state: dict[str, dict] = {}   # host → {"next_ok": ts, "strikes": int}
_domain_lock = threading.Lock()


def _host_of(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except ValueError:
        return ""


def _acquire(host: str) -> bool:
    """Wait for the domain's slot (bounded); False = the domain is resting after strikes — skip it,
    do not queue behind a two-minute penalty."""
    now = time.monotonic()
    with _domain_lock:
        st = _domain_state.setdefault(host, {"next_ok": 0.0, "strikes": 0})
        wait = st["next_ok"] - now
        if wait > _MAX_WAIT_S:
            return False
        start = max(now, st["next_ok"])
        st["next_ok"] = start + _MIN_INTERVAL_S + random.uniform(0.0, 0.5)
    if wait > 0:
        time.sleep(wait)
    return True


def _penalize(host: str, *, retry_after: float | None = None) -> None:
    """429/403: honour `Retry-After` when the site names one; strikes escalate to a rest."""
    with _domain_lock:
        st = _domain_state.setdefault(host, {"next_ok": 0.0, "strikes": 0})
        st["strikes"] += 1
        pause = retry_after if retry_after else (_PENALTY_S if st["strikes"] >= 2 else _MIN_INTERVAL_S * 4)
        st["next_ok"] = max(st["next_ok"], time.monotonic() + pause)


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
def _bd_request(payload: dict, *, provider: str) -> str:
    """One Bright Data `/request` call, metered ON SUCCESS only (their billing counts successes;
    so does ours). Raises on anything but 200 — callers fail open to the next rung."""
    import httpx
    headers = {"Authorization": f"Bearer {_bd_token()}", "Content-Type": "application/json"}
    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(_BD_ENDPOINT, headers=headers, json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"brightdata {provider}: HTTP {resp.status_code} {resp.text[:120]}")
    _meter(provider)
    return resp.text


def _serp_discover(q: ListingQuery, country: str) -> list[dict]:
    """Bright Data SERP: parsed Google results, geo-targeted. `brd_json=1` asks their parser for
    structured JSON instead of HTML — organic entries carry link/title/description."""
    hl, gl = _COUNTRY_LOCALE.get(country.upper(), ("en", country.lower() or "us"))
    words = q.text if not q.condition else f"{q.text} {q.condition}"
    url = (f"https://www.google.com/search?q={quote_plus(words)}"
           f"&hl={hl}&gl={gl}&num=20&brd_json=1")
    raw = _bd_request({"zone": _bd_zone_serp(), "url": url, "format": "raw"},
                      provider="brightdata_serp")
    data = json.loads(raw)
    out = []
    for entry in (data.get("organic") or []):
        link = entry.get("link") or entry.get("url") or ""
        if link:
            out.append({"url": link, "title": entry.get("title", ""),
                        "snippet": entry.get("description", "")})
    return out


def _free_discover(q: ListingQuery) -> list[dict]:
    """No token → the discovery we already own: `websearch.search` (warm Chromium → DDG), which
    meters, caches and reports failures itself. Free, single-locale — the engine's own."""
    from nucleo import websearch
    words = q.text if not q.condition else f"{q.text} {q.condition}"
    found = websearch.search(words, k=10)
    return [{"url": r.get("url", ""), "title": r.get("title", ""), "snippet": r.get("snippet", "")}
            for r in found.get("results", []) if r.get("url")]


def _candidate_urls(discovered: list[dict], cap: int) -> list[str]:
    out: list[str] = []
    for row in discovered:
        url = row["url"]
        host = _host_of(url)
        if not host or _NON_LISTING_HOSTS.search(host):
            continue
        if url not in out:
            out.append(url)
        if len(out) >= cap:
            break
    return out


# ── rung 2: fetch ────────────────────────────────────────────────────────────────────────────────
def _fetch(url: str, country: str) -> tuple[str, str]:
    """`(html, via)` — Web Unlocker when a token exists (bot walls, JS rendering, geo exit through
    `country`), plain GET otherwise. Raises on failure; the caller records the source row."""
    host = _host_of(url)
    if not _acquire(host):
        raise RuntimeError(f"{host}: resting after repeated blocks")
    if _bd_token():
        payload = {"zone": _bd_zone_unlocker(), "url": url, "format": "raw"}
        if country:
            payload["country"] = country.lower()
        return _bd_request(payload, provider="brightdata_unlocker"), "unlocker"
    import httpx
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True,
                      headers={"User-Agent": _UA, "Accept-Language": "es,en;q=0.8"}) as client:
        resp = client.get(url)
    if resp.status_code in (403, 429):
        retry_after = None
        try:
            retry_after = float(resp.headers.get("retry-after", ""))
        except ValueError:
            pass
        _penalize(host, retry_after=retry_after)
        raise RuntimeError(f"{host}: HTTP {resp.status_code} (bot wall)")
    if resp.status_code >= 400:
        raise RuntimeError(f"{host}: HTTP {resp.status_code}")
    return resp.text, "http"


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

    for country in countries:
        # 1 · discovery
        discovered: list[dict] = []
        if _bd_token():
            try:
                discovered = _serp_discover(q, country or "us")
                sources.append({"tier": "serp", "target": f"google/{country or 'default'}",
                                "status": "ok", "n": len(discovered)})
            except Exception as e:  # noqa: BLE001
                sources.append({"tier": "serp", "target": f"google/{country or 'default'}",
                                "status": "error", "note": _brief(e, 120)})
        if not discovered:
            try:
                discovered = _free_discover(q)
                sources.append({"tier": "discovery-free", "target": "websearch",
                                "status": "ok", "n": len(discovered)})
            except Exception as e:  # noqa: BLE001
                sources.append({"tier": "discovery-free", "target": "websearch",
                                "status": "error", "note": _brief(e, 120)})

        # 2+3 · fetch and extract, page by page, politely
        for url in _candidate_urls(discovered, q.fetch_cap):
            host = _host_of(url)
            try:
                html, via = _fetch(url, country)
            except Exception as e:  # noqa: BLE001
                sources.append({"tier": "fetch", "target": host, "status": "blocked",
                                "note": _brief(e, 120)})
                continue
            found = listing_extract.extract_items(html, url)
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
        if blocked and not _bd_token():
            reason = (f"{blocked} candidate pages behind bot walls and no unlocker token — "
                      "a browser session is the remaining way in")
        elif items:
            reason = f"only {len(items)} structured listings found; below min_needed={q.min_needed}"
        else:
            reason = "no page declared structured listings (JSON-LD/OpenGraph)"
    result = {"query": q.text, "items": items, "sources": sources,
              "exhausted": True, "needs_browser": needs_browser, "reason": reason}
    _remember(q, result)
    if needs_browser:
        logger.info(f"listing_search: '{q.text[:60]}' → {len(items)} items, needs_browser ({reason})")
    return result
