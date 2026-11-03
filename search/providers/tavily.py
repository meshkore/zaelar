"""search/providers/tavily.py — Tavily Search API: ranked pages with title, content and url, plus a short answer.

WHY IT IS THE FIRST PAID-API RUNG. Tavily gives 1,000 credits a month with no card, one credit per `basic` search,
and $0.008 per credit beyond that — the cheapest keyed index this engine can ask. Measured 2026-11-03 on six
product-reputation queries, five rows each, with a model judging «real owner/reliability evidence about THIS
product»: Tavily `basic` 14/30 useful rows in 2.2 s, `advanced` the same 14/30 in 3.7 s for two credits, OpenAI
web search 26/30 in 6.7 s. So `basic` is asked, and a weak answer moves on to the next rung instead of being kept.

WEAK EVIDENCE ESCALATES. Every row carries Tavily's own relevance `score` (0-1). Measured the same day: a real
query scores its rows 0.60-0.91, a nonsense query 0.04-0.19 — the index answers HTTP 200 with five rows either way.
Rows under `MIN_SCORE` are dropped; when none is left the answer built on them is dropped too, and the chain
reads an empty rung exactly as it reads «no results» and asks the next index (`web.search`). No parallel
mechanism: the provider's own verdict decides, and the chain's existing degrade does the rest.

Rate: `energy_meter._SEARCH_USD_PER_REQUEST["tavily"]`, metered per successful call like every paid backend.
"""
from __future__ import annotations

import os

from . import keys as _keys

_ENDPOINT = "https://api.tavily.com/search"
_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0"))
#: Below this Tavily score a row is noise (measured 2026-11-03: real rows 0.60+, nonsense 0.19 and under).
MIN_SCORE = 0.3


def _clean(s) -> str:
    return " ".join(str(s or "").split())


def parse(data: dict, k: int) -> dict:
    """`{answer, results}` from a `/search` payload; rows `{title, snippet, url}` at or above `MIN_SCORE`. Pure."""
    rows = []
    for r in (data or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        url, title = str(r.get("url") or "").strip(), _clean(r.get("title"))
        score = r.get("score")
        if not url or not title or (isinstance(score, (int, float)) and score < MIN_SCORE):
            continue
        rows.append({"title": title, "snippet": _clean(r.get("content")), "url": url})
        if len(rows) >= k:
            break
    return {"answer": _clean(data.get("answer")) if rows else "", "results": rows}


def search(q: str, k: int = 5) -> dict:
    """`{query, answer, results, source:"tavily"}`. BLOCKING (network). Raises on HTTP failure so the chain
    degrades with the reason in its string (432/429 → quota, 401 → credential)."""
    import httpx
    key = _keys.key("tavily")
    if not key:
        return {"query": q, "answer": "", "results": [], "source": "tavily"}
    payload = {"query": q, "search_depth": "basic", "include_answer": True, "max_results": max(1, min(int(k), 10))}
    from nucleo.energy import egress as llm_egress
    url, key = llm_egress.route_url(_ENDPOINT, key)
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                      json=payload)
    if resp.status_code != 200:
        raise RuntimeError(f"tavily search: HTTP {resp.status_code} {resp.text[:160]}")
    data = resp.json()
    parsed = parse(data, k)
    if data.get("results"):                    # a credit was spent even when every row was too weak to keep
        from nucleo.energy import meter as _energy
        _energy.report_search_usage(provider="tavily")
    return {"query": q, "answer": parsed["answer"], "results": parsed["results"], "source": "tavily",
            "ai": bool(parsed["answer"])}
