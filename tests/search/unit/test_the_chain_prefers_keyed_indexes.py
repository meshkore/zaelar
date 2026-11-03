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


def test_a_fact_asks_the_cheapest_rung_first_and_openai_last(no_keys, monkeypatch):
    """2026-10-23: OpenAI was first on every fact at ~$0.025 a call while the free Chromium sat seventh. The free
    and quota-free rungs go first; OpenAI is the paid rung that does not fail. Leads keep real pages first."""
    monkeypatch.setattr(web, "_google_on", lambda: True)
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("Z_AI_API_KEY", "placeholder")
    assert web._order("answer") == ["google", "gemini", "zai", "openai", "ddg"]
    assert web.provider() == "google"
    assert web._order("results") == ["zai", "openai", "google", "ddg"]


def test_a_rung_set_aside_hands_the_fact_to_the_next(no_keys, monkeypatch):
    monkeypatch.setattr(web, "_google_on", lambda: True)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    web._aside.clear()
    try:
        web._set_aside_if_lasting("google", "google: bloqueado (captcha/tráfico inusual)")
        assert web._order("answer") == ["gemini", "openai", "ddg"]
    finally:
        web._aside.clear()


def test_perplexity_is_used_before_openai_once_keyed(no_keys, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "placeholder")
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    assert web._order() == ["gemini", "perplexity", "openai", "ddg"]


def test_pages_and_facts_follow_the_one_provider_table(no_keys, monkeypatch):
    """2026-11-03: one table for every web search (here and the MeshKore agents) — free tiers first, then the
    cheapest paid, then the paid rung that does not run dry. Pages: tavily → brave → zai → openai; a fact keeps our
    Chromium and Gemini's free quota ahead of that same order."""
    monkeypatch.setattr(web, "_google_on", lambda: True)
    for k in ("TAVILY_API_KEY", "BRAVE_SEARCH_KEY", "Z_AI_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.setenv(k, "placeholder")
    assert web._order("results") == ["tavily", "brave", "zai", "openai", "google", "ddg"]
    assert web._order("answer") == ["google", "gemini", "tavily", "brave", "zai", "openai", "ddg"]


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
