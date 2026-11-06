"""Tavily is the first keyed rung of the one provider table, and a weak answer from it asks the next index (2026-11-03).

Tavily answers HTTP 200 with five rows for any query — a nonsense one included, scored 0.04-0.19 against 0.60-0.91
for a real one. Rows under the provider's own score floor are dropped, so the chain reads a weak rung as an empty
one and the next index answers, through the same degrade every other rung uses.
"""
from __future__ import annotations

import json
from pathlib import Path

from search.providers import USD_PER_REQUEST, tavily

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "tavily_search.json"


def test_recorded_rows_have_title_snippet_and_url():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    out = tavily.parse(data, 10)
    assert out["results"] and all(r["title"] and r["snippet"] and r["url"].startswith("https://")
                                  for r in out["results"])
    assert out["answer"]
    assert tavily.parse(data, 2)["results"] == out["results"][:2]


def test_rows_under_the_score_floor_are_dropped_with_the_answer_built_on_them():
    data = json.loads(FIX.read_text(encoding="utf-8"))
    for r in data["results"]:
        r["score"] = 0.1
    assert tavily.parse(data, 10) == {"answer": "", "results": []}


def test_tavily_has_a_rate_and_asks_basic_depth(monkeypatch):
    assert USD_PER_REQUEST["tavily"] == 0.008
    seen = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"results": []}

    class _Client:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False

        def post(self, url, headers=None, json=None):
            seen.update(url=url, auth=headers.get("Authorization", ""), body=json)
            return _Resp()

    import httpx
    monkeypatch.setattr(httpx, "Client", _Client)
    monkeypatch.setenv("TAVILY_API_KEY", "placeholder")
    monkeypatch.setattr("search.providers.keys.spendable", lambda: True)
    tavily.search("x", 3)
    assert seen["url"] == "https://api.tavily.com/search" and seen["auth"] == "Bearer placeholder"
    assert seen["body"]["search_depth"] == "basic" and "api_key" not in seen["body"]
