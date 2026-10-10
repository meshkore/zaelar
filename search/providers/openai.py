"""search/providers/openai.py — OpenAI web search (Responses API): a cited answer with REAL deep links (V2-782 F2).

Measured 2026-10-10 with the engine's own `OPENAI_API_KEY`: «¿A qué hora abre el Museo del Prado hoy?» → one
sentence with the right date and hours, and a citation to `museodelprado.madrid/es/visiting-hours` — a page url,
not a redirect. That is what sets it apart from Gemini's grounding: its citations carry `title` + `url` of the
page, so the same call serves a FACT (the answer) and LEADS (the cited pages). It is an `answer` provider that
also counts for `results`.

Model: `OPENAI_SEARCH_MODEL` (default `gpt-4.1-mini`); tool `web_search_preview`. Rate:
`energy_meter._SEARCH_USD_PER_REQUEST["openai"]` per call (the tool call is billed per 1k calls plus a few
hundred tokens; the rate is the per-call ceiling, tokens are not metered twice).
"""
from __future__ import annotations

import os

from . import keys as _keys

_ENDPOINT = "https://api.openai.com/v1/responses"
_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0")) + 10.0
_SYSTEM = ("Answer in the language of the question, in one to three sentences, with today's facts and the specific "
           "datum asked for. Cite the pages you used. Say plainly when you could not find it.")


def _model() -> str:
    return os.getenv("OPENAI_SEARCH_MODEL", "gpt-4.1-mini")


def parse(data: dict, k: int) -> dict:
    """`{answer, results}` from a Responses payload: the message text, and each `url_citation` once. Pure."""
    answer_parts: list[str] = []
    results: list[dict] = []
    seen: set[str] = set()
    for item in (data or {}).get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if not isinstance(c, dict):
                continue
            txt = str(c.get("text") or "").strip()
            if txt:
                answer_parts.append(txt)
            for a in c.get("annotations") or []:
                if not isinstance(a, dict) or a.get("type") != "url_citation":
                    continue
                url = str(a.get("url") or "").strip()
                if not url or url in seen or len(results) >= k:
                    continue
                seen.add(url)
                results.append({"title": str(a.get("title") or "").strip(), "snippet": "", "url": url})
    answer = " ".join(" ".join(p.split()) for p in answer_parts).strip()
    return {"answer": answer, "results": results}


def search(q: str, k: int = 5) -> dict:
    """`{query, answer, results, source:"openai", ai:True}`. BLOCKING. Raises on HTTP failure (the chain degrades)."""
    import datetime as _dt
    import httpx
    key = _keys.key("openai")
    if not key:
        return {"query": q, "answer": "", "results": [], "source": "openai"}
    body = {"model": _model(), "tools": [{"type": "web_search_preview"}],
            "instructions": f"{_SYSTEM} Today is {_dt.date.today().isoformat()}.",
            "input": q, "max_output_tokens": 500}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post(_ENDPOINT, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body)
    if resp.status_code != 200:
        raise RuntimeError(f"openai web_search: HTTP {resp.status_code} {resp.text[:160]}")
    parsed = parse(resp.json(), k)
    if parsed["answer"] or parsed["results"]:
        from nucleo import energy_meter as _energy
        _energy.report_search_usage(provider="openai")
    return {"query": q, "answer": parsed["answer"], "results": parsed["results"], "source": "openai",
            "ai": bool(parsed["answer"])}
