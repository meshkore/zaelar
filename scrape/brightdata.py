"""scrape/brightdata.py — Bright Data's `/request`, ONE client for both zones (V2-846; was `search/listing._bd_*`).

The SERP zone (Google results parsed to Light JSON — discovery, `search/listing.py`) and the Web Unlocker zone (a page
behind a bot wall — scrape's unlocker rung) share one endpoint and one bearer; the zone travels in the body. Each
call goes through mediated egress when the deployment has it, and is metered on SUCCESS only.

A 200 is not always the page. Bright Data answers its OWN refusals with a 200 and an `x-brd-error` header (measured
2026-11-04: «Residential Failed (bad_endpoint)… requires KYC» for a robots-restricted site, «captcha» for a SERP it
could not solve) — that is a refusal of the provider, raised as one, never handed on as the site's page.
"""
from __future__ import annotations

import os

ENDPOINT = "https://api.brightdata.com/request"
#: Bright Data solves the page before answering (captcha, JavaScript, residential exit): 5-40 s measured 2026-11-04.
TIMEOUT_S = float(os.getenv("LISTING_BRIGHTDATA_TIMEOUT", "60.0"))


def token() -> str:
    from search.providers import keys as _keys     # the one door for paid keys (and the energy lease gate)
    return _keys.key("brightdata_serp")


def zone_serp() -> str:
    return (os.getenv("BRIGHTDATA_SERP_ZONE") or "serp_api").strip()


def zone_unlocker() -> str:
    return (os.getenv("BRIGHTDATA_UNLOCKER_ZONE") or "web_unlocker1").strip()


def _meter(provider: str) -> None:
    try:
        from nucleo.energy import meter as _energy
        _energy.report_search_usage(provider=provider)
    except Exception as e:  # noqa: BLE001 — the counter's own gates are @_never_raises; belt and braces
        from loguru import logger
        logger.warning(f"scrape: {provider} served but not metered ({e!r})")


#: The provider's own «retry in a few»: its adaptive rate limit (measured 2026-11-04 on eBay and Amazon). One retry.
_RETRY_AFTER_S = float(os.getenv("BRIGHTDATA_RETRY_AFTER_S", "5.0"))


def request(payload: dict, *, provider: str, _retry: bool = True) -> str:
    """One `/request` call → the body. Raises on a non-200 or on the provider's own refusal (`x-brd-error`); a refusal
    that asks to retry is retried once."""
    import time

    import httpx
    from nucleo.energy import egress as llm_egress
    url, key = llm_egress.route_url(ENDPOINT, token())
    with httpx.Client(timeout=TIMEOUT_S) as client:
        resp = client.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                           json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"brightdata {provider}: HTTP {resp.status_code} {resp.text[:120]}")
    refused = resp.headers.get("x-brd-error") or resp.headers.get("x-luminati-error")
    if refused:
        if _retry and "retry" in refused.lower():
            time.sleep(_RETRY_AFTER_S)
            return request(payload, provider=provider, _retry=False)
        raise RuntimeError(f"brightdata {provider}: refused — {refused[:160]}")
    _meter(provider)
    return resp.text
