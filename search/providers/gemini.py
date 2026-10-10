"""search/providers/gemini.py — Gemini with Google Search grounding: a cited answer from Google's index (V2-782 F2).

The `websearch` docstring named «Gemini grounding» as an AI-answer provider in July and nobody wired it, while
the engine held a Gemini key the whole time. Measured 2026-10-10: «¿A qué hora abre el Museo del Prado hoy?» →
a one-sentence answer with the day and the hour plus three cited domains (museodelprado.es first), in 2.6 s,
over an API that was never blocked by a captcha. It sits ABOVE the free scrapers in the fact chain because for
a fact the operator speaks the answer is what matters and this one arrives already synthesised and grounded.

What it does NOT do: give deep links. Grounding citations are redirect urls (`vertexaisearch.cloud.google.com/
grounding-api-redirect/…`) whose `title` is the DOMAIN. They are kept as sources so a round is auditable, and
they are never written to the sheet as candidates — this is an `answer` provider, and listing discovery skips
it (`web.search(mode="results")`).

Model: `GEMINI_SEARCH_MODEL` (default `gemini-2.5-flash`; grounding is a tool, any current model takes it).
Rate: `energy_meter._SEARCH_USD_PER_REQUEST["gemini"]` per grounded call (Google bills grounded prompts, not
tokens; the tokens are a few hundred and go unmetered on purpose — a second meter would double-count a request
already paid as one search).
"""
from __future__ import annotations

import os

from . import keys as _keys

_TIMEOUT = float(os.getenv("WEBSEARCH_TIMEOUT", "12.0")) + 6.0   # a grounded call is a model call; a bit longer
_SYSTEM = ("Answer in the language of the question, in one to three sentences, with today's facts. State the "
           "specific datum asked for (time, price, result, date). Say plainly when you could not find it.")


def _model() -> str:
    return os.getenv("GEMINI_SEARCH_MODEL", "gemini-2.5-flash")


def parse(data: dict, k: int) -> dict:
    """`{answer, results}` from a `generateContent` payload. Pure; tested on a recorded fixture."""
    cands = (data or {}).get("candidates") or []
    if not cands:
        return {"answer": "", "results": []}
    c = cands[0] if isinstance(cands[0], dict) else {}
    parts = ((c.get("content") or {}).get("parts") or [])
    answer = " ".join(" ".join(str(p.get("text") or "").split()) for p in parts if isinstance(p, dict)).strip()
    results = []
    for ch in ((c.get("groundingMetadata") or {}).get("groundingChunks") or [])[:k]:
        web = (ch or {}).get("web") or {}
        uri = str(web.get("uri") or "").strip()
        if uri:
            results.append({"title": str(web.get("title") or "").strip(), "snippet": "", "url": uri})
    return {"answer": answer, "results": results}


def search(q: str, k: int = 5) -> dict:
    """`{query, answer, results, source:"gemini", ai:True}`. BLOCKING. Raises on HTTP failure (the chain degrades)."""
    import httpx
    key = _keys.key("gemini")
    if not key:
        return {"query": q, "answer": "", "results": [], "source": "gemini"}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_model()}:generateContent"
    # Today's date travels in the instruction: measured 2026-10-10, without it the grounded answer named the previous
    # day («hoy, viernes 9 de octubre») — the model's clock is not the operator's.
    import datetime as _dt
    today = _dt.date.today().isoformat()
    body = {"systemInstruction": {"parts": [{"text": f"{_SYSTEM} Today is {today}."}]},
            "contents": [{"parts": [{"text": q}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"maxOutputTokens": 300}}
    with httpx.Client(timeout=_TIMEOUT) as c:
        resp = c.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"}, json=body)
    if resp.status_code != 200:
        raise RuntimeError(f"gemini grounding: HTTP {resp.status_code} {resp.text[:160]}")
    parsed = parse(resp.json(), k)
    if parsed["answer"] or parsed["results"]:
        from nucleo import energy_meter as _energy
        _energy.report_search_usage(provider="gemini")
    return {"query": q, "answer": parsed["answer"], "results": parsed["results"], "source": "gemini",
            "ai": bool(parsed["answer"])}
