"""The fact chain prefers the keyed indexes it holds, and the lead chain skips the answer-only ones (V2-782 F2).

2026-10-10: not one inline search in the sweep reached anything but DuckDuckGo, with a Gemini key and a Z.ai key
sitting in the credential store. The order is now a declared table, read against the keys present.
"""
from __future__ import annotations

import pytest

from search import web

_KEYS = ("PERPLEXITY_API_KEY", "PPLX_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_KEY", "BRAVE_API_KEY", "GEMINI_SEARCH_API_KEY", "ZAI_SEARCH_API_KEY",
         "GEMINI_API_KEY", "Z_AI_API_KEY", "OPENAI_API_KEY", "WEBSEARCH_PROVIDER")


@pytest.fixture
def no_keys(monkeypatch):
    for k in _KEYS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("BROWSER_SEARCH", "0")


def test_with_no_key_the_chain_is_the_free_scrapers(no_keys):
    assert web._order() == ["ddg"]
    assert web.provider() == "ddg"


def test_gemini_and_zai_are_used_the_moment_their_keys_exist(no_keys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("Z_AI_API_KEY", "placeholder")
    assert web._order("answer") == ["gemini", "zai", "ddg"], "a fact wants the grounded answer first"
    assert web._order("results") == ["zai", "ddg"], "leads want real pages: Gemini's redirects are skipped"


def test_perplexity_is_used_once_keyed(no_keys, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "placeholder")
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    assert web._order() == ["perplexity", "gemini", "openai", "ddg"], "the best measured fact rung (2026-11-03)"
    assert web._order("results") == ["perplexity", "openai", "ddg"], "its pages are real urls"


def test_the_override_still_wins(no_keys, monkeypatch):
    monkeypatch.setenv("WEBSEARCH_PROVIDER", "zai")
    assert web.provider() == "zai"


def test_a_results_search_is_cached_apart_from_an_answer_search(no_keys, monkeypatch):
    calls: list[str] = []

    def fake(q, k):
        calls.append(q)
        return {"query": q, "answer": "", "results": [{"title": "t", "snippet": "", "url": "https://x"}], "source": "ddg"}

    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS, "ddg": fake})
    web._recent.clear()
    web.search("monitor 27", mode="answer")
    web.search("monitor 27", mode="results")
    assert len(calls) == 2, "the two modes ask for different things; one must not serve the other's cache"
    web.search("monitor 27", mode="results")
    assert len(calls) == 2


def test_the_paid_set_names_the_new_backends_and_the_free_ones_stay_out():
    assert {"openai", "gemini", "zai", "tavily"} <= web._PAID_BACKENDS
    assert not {"google", "ddg"} & web._PAID_BACKENDS


def test_perplexity_asks_the_agent_api_with_its_search_tool_and_keeps_the_pages(no_keys, monkeypatch):
    """2026-11-03: `/chat/completions` became a 403 (`agent_api_migration_required`); on `/v1/responses` without the
    `web_search` tool it answers from the model alone. The pages arrive in a `search_results` output item."""
    sent = {}

    class Resp:
        def raise_for_status(self): return None
        def json(self):
            return {"output": [{"type": "search_results", "results": [
                        {"title": "Precios ITV", "snippet": "Diésel desde 41 €", "url": "https://www.serviciositv.es/precios-itv"},
                        {"title": "sin url", "snippet": "x"}]},
                    {"type": "message", "content": [{"type": "output_text", "text": "Unos 47 € de media.[1][6]"}]}]}

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None):
            sent.update(url=url, body=json)
            return Resp()

    import httpx
    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setenv("PERPLEXITY_API_KEY", "placeholder")
    out = web._perplexity("¿Cuánto cuesta la ITV de un diésel en Madrid?", 5)
    assert sent["url"].endswith("/v1/responses") and sent["body"]["preset"] == "fast-search"
    assert out["answer"] == "Unos 47 € de media."
    assert [r["url"] for r in out["results"]] == ["https://www.serviciositv.es/precios-itv"]
    assert out["results"][0]["snippet"] == "Diésel desde 41 €"
    monkeypatch.setenv("PERPLEXITY_MODEL", "perplexity/sonar")
    web._perplexity("x", 5)
    assert sent["body"]["tools"] == [{"type": "web_search"}], "a bare model without the tool does not search"
