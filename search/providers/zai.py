"""search/providers/zai.py — Z.ai Web Search API: ranked pages with title, snippet and link (V2-782 F2).

WHY A NEW RUNG. Measured 2026-10-10 over the whole V2-781 sweep: the inline chain had no paid key at all and
fell to DuckDuckGo every time; the listing pass discovered through the same free chain, hit Google's captcha,
and ended `n=0` in 5-13 s on all six hunts; and the workers' own built-in search (`web_search_prime`, the
coding plan's MCP quota) answered «Weekly/Monthly Limit Exhausted» eighteen times across ten cases. The engine
already holds a Z.ai key — the same one the fast model uses — and Z.ai sells web search as a separate, pay-per-
call API on a different wallet from that MCP quota (`zaelar-model-allocation.md`). One POST, 2.7 s measured,
real pages back. It is a `results` provider: good for discovering listing pages and local businesses, where an
`answer` provider's redirect links are useless.

Known shape of what it returns (recorded 2026-10-10 in `tests/search/fixtures/zai_web_search.json`): `link` is
often the site ROOT, not the deep page; `title` may carry a phone number; `content` ends in «Read more». That
is why the service treats a Z.ai row as a LEAD (origin `web`) and `candidacy` decides what it is.

Rate: `energy_meter._SEARCH_USD_PER_REQUEST["zai"]`, metered per successful call like every paid backend.
"""
from __future__ import annotations

import os

from . import keys as _keys

_ENDPOINT = "https://api.z.ai/api/paas/v4/web_search"
_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0"))


def _clean(s) -> str:
    t = " ".join(str(s or "").split())
    return t[:-9].rstrip(" .") if t.endswith("Read more") else t


def parse(data: dict, k: int) -> list[dict]:
    """The API's `search_result` rows → the chain's `{title, snippet, url, date}` rows. Pure; tested on a fixture."""
    out = []
    for r in (data or {}).get("search_result") or []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("link") or "").strip()
        title = _clean(r.get("title"))
        if not url or not title:
            continue
        out.append({"title": title, "snippet": _clean(r.get("content")), "url": url,
                    "date": str(r.get("publish_date") or "").strip()})
        if len(out) >= k:
            break
    return out


def search(q: str, k: int = 8) -> dict:
    """`{query, answer:"", results, source:"zai"}`. BLOCKING (network). Raises on HTTP failure so the chain
    degrades to the next rung with the reason in its string (429 → quota, 401 → credential)."""
    import httpx
    key = _keys.key("zai")
    if not key:
        return {"query": q, "answer": "", "results": [], "source": "zai"}
    payload = {"search_engine": os.getenv("ZAI_SEARCH_ENGINE", "search-prime"), "search_query": q,
               "count": max(1, min(int(k), 20)), "content_size": "medium"}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post(_ENDPOINT, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"zai web_search: HTTP {resp.status_code} {resp.text[:160]}")
    results = parse(resp.json(), k)
    if results:
        from nucleo import energy_meter as _energy
        _energy.report_search_usage(provider="zai")
    return {"query": q, "answer": "", "results": results, "source": "zai"}
