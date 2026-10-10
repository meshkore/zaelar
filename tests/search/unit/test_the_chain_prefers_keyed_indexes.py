"""The fact chain prefers the keyed indexes it holds, and the lead chain skips the answer-only ones (V2-782 F2).

2026-10-10: not one inline search in the sweep reached anything but DuckDuckGo, with a Gemini key and a Z.ai key
sitting in the credential store. The order is now a declared table, read against the keys present.
"""
from __future__ import annotations

import pytest

from search import web

_KEYS = ("PERPLEXITY_API_KEY", "PPLX_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_KEY", "BRAVE_API_KEY",
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
    assert web.is_ai_answer("gemini") and not web.is_ai_answer("zai")


def test_openai_outranks_gemini_for_a_fact_and_serves_leads_too(no_keys, monkeypatch):
    """Its citations are PAGES (title + url), so it answers a fact first and still counts as a lead provider."""
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("Z_AI_API_KEY", "placeholder")
    assert web._order("answer") == ["openai", "gemini", "zai", "ddg"]
    assert web._order("results") == ["zai", "openai", "ddg"]


def test_perplexity_still_outranks_everything(no_keys, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    assert web._order()[:2] == ["perplexity", "gemini"]


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
    assert {"openai", "gemini", "zai"} <= web._PAID_BACKENDS
    assert not {"google", "ddg"} & web._PAID_BACKENDS
