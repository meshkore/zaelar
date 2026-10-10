"""search/providers/foursquare.py — Foursquare Places: a LOCAL SERVICE with phone, rating and open-now (V2-782 F2).

The criterion-never-captured bucket of the diagnosis (§1): «el mejor valorado que pueda venir hoy» came back as
names and phones from Google Maps / OpenStreetMap extractions that have no rating field and no hours, and the
rows were presented as if they met it. A places directory is the one kind of provider that RETURNS the rating
and the open-now flag as fields, so the sheet can show them and `candidacy.unshown_criteria` can stop saying
they are missing.

STATUS (2026-10-10): the engine holds `FOURSQUARE_SERVICE_KEY` and the account has **no API credits** — the probe
answered HTTP 429 «Your account has no API credits remaining». The parser below is written against the Places
API documentation (`X-Places-Api-Version: 2025-06-17`), not against a recorded live payload; the health probe
reports the provider as `exhausted` until the operator adds credits, and `find()` falls back to the web chain
for a local service. Verifying the parser against a real payload is the first thing to do the day it answers.

Rate: `energy_meter._SEARCH_USD_PER_REQUEST["foursquare"]` per successful search.
"""
from __future__ import annotations

import os

from . import keys as _keys

_ENDPOINT = "https://places-api.foursquare.com/places/search"
_VERSION = os.getenv("FOURSQUARE_API_VERSION", "2025-06-17")
_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0"))
_FIELDS = "name,tel,website,rating,hours,location,fsq_place_id,categories,price"


def parse(data: dict, k: int) -> list[dict]:
    """`results[]` → local-service rows: `{title, url, phone, rating, availability, subtitle}`. Pure."""
    out = []
    for r in (data or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        name = str(r.get("name") or "").strip()
        if not name:
            continue
        hours = r.get("hours") if isinstance(r.get("hours"), dict) else {}
        avail = ""
        if hours.get("open_now") is True:
            avail = "open now"
        elif hours.get("open_now") is False:
            avail = "closed now"
        if hours.get("display"):
            avail = (avail + " · " if avail else "") + str(hours["display"])[:80]
        loc = r.get("location") if isinstance(r.get("location"), dict) else {}
        cats = [str(c.get("name") or "") for c in (r.get("categories") or []) if isinstance(c, dict)]
        rating = r.get("rating")
        out.append({
            "title": name,
            "url": str(r.get("website") or "").strip(),
            "phone": str(r.get("tel") or "").strip(),
            "rating": f"{float(rating):.1f}/10" if isinstance(rating, (int, float)) else "",
            "availability": avail,
            "subtitle": " · ".join(b for b in (str(loc.get("formatted_address") or ""), ", ".join(cats[:2])) if b)[:160],
            "fsq_id": str(r.get("fsq_place_id") or ""),
        })
        if len(out) >= k:
            break
    return out


def places(q: str, near: str = "", k: int = 8) -> list[dict]:
    """Businesses matching `q` near `near` (a place name; the engine's locale when empty). BLOCKING. Raises on
    HTTP failure so the caller falls back and the health probe can classify (429 = exhausted)."""
    import httpx
    key = _keys.key("foursquare")
    if not key:
        return []
    params = {"query": q, "limit": max(1, min(int(k), 20)), "fields": _FIELDS}
    if near:
        params["near"] = near
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.get(_ENDPOINT, params=params, headers={"Authorization": f"Bearer {key}",
                                                        "X-Places-Api-Version": _VERSION, "Accept": "application/json"})
    if resp.status_code != 200:
        raise RuntimeError(f"foursquare places: HTTP {resp.status_code} {resp.text[:160]}")
    rows = parse(resp.json(), k)
    if rows:
        from nucleo import energy_meter as _energy
        _energy.report_search_usage(provider="foursquare")
    return rows
