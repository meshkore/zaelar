"""A rung that hangs or refuses for a lasting reason does not hold the fact chain.

Measured 2026-10-23 on twelve live fact questions: a grounded Gemini call took 204 s with an 18 s httpx timeout
set (the timeout bounds each read, not the call), and from the 7th call of a minute on Gemini answered 429 —
every search asked it again first and paid the refusal before moving on.
"""
from __future__ import annotations

import time

import pytest

from search import web

ROWS = [{"title": "Horarios — Museo del Prado", "snippet": "Lunes a sábado de 10:00 a 20:00 h.",
         "url": "https://www.museodelprado.es/visita-el-museo"}]


@pytest.fixture
def two_indexes(monkeypatch):
    for k in ("PERPLEXITY_API_KEY", "PPLX_API_KEY", "TAVILY_API_KEY", "BRAVE_SEARCH_KEY", "BRAVE_API_KEY",
              "OPENAI_API_KEY", "WEBSEARCH_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "placeholder")
    monkeypatch.setenv("Z_AI_API_KEY", "placeholder")
    monkeypatch.setenv("BROWSER_SEARCH", "0")
    web._recent.clear()
    web._aside.clear()
    web._strikes.clear()
    calls: list[str] = []
    zai = lambda q, k: (calls.append("zai"), {"query": q, "answer": "", "results": ROWS, "source": "zai"})[1]
    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS, "zai": zai})
    yield calls
    web._aside.clear()
    web._strikes.clear()
    web._recent.clear()


def _gemini(monkeypatch, calls, fail: str):
    def g(q, k):
        calls.append("gemini")
        raise RuntimeError(fail)
    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS, "gemini": g})


def test_a_quota_refusal_sets_the_index_aside_until_it_may_have_reset(two_indexes, monkeypatch):
    calls = two_indexes
    _gemini(monkeypatch, calls, 'gemini grounding: HTTP 429 {"error": {"message": "You exceeded your current quota"')
    assert web.search("¿A qué hora abre hoy el Museo del Prado?")["source"] == "zai"
    assert web.search("What time does the Prado open today?")["source"] == "zai"
    assert calls.count("gemini") == 1, f"the refused index was asked again before its quota could reset: {calls}"
    assert web._aside.get("gemini", 0) > time.time()

    web._aside["gemini"] = time.time() - 1          # the window ran out
    web.search("Prado opening hours on Sunday")
    assert calls.count("gemini") == 2, "an index set aside is asked again once its window is over"


def test_a_network_blip_is_not_lasting(two_indexes, monkeypatch):
    calls = two_indexes
    _gemini(monkeypatch, calls, "gemini grounding: connection reset by peer")
    web.search("¿Cuánto cuesta la entrada al Prado?")
    web.search("How much is a ticket to the Prado?")
    assert calls.count("gemini") == 2 and web._aside.get("gemini", 0) <= time.time()


def test_a_rung_that_hangs_is_left_behind_at_its_wall_clock(two_indexes, monkeypatch):
    monkeypatch.setattr(web, "_RUNG_WALL_S", 0.3)

    def hangs(q, k):
        time.sleep(5)
        return {"query": q, "answer": "late", "results": [], "source": "gemini"}

    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS, "gemini": hangs})
    t = time.time()
    res = web.search("Louvre opening hours today")
    assert res["source"] == "zai" and time.time() - t < 2.0, "the turn waited on a hung index"


# ── how long an index stays aside (operator, 2026-10-23: «if we know it is blocked, the next search goes straight
# to the second; if the second has no balance either, to the third») ─────────────────────────────────────────────

def test_the_wait_the_provider_names_is_the_window():
    assert web._aside_window("gemini", 'HTTP 429 {"error": {"details": [{"retryDelay": "37s"}]}}') == 37.0
    assert web._aside_window("openai", "Rate limit reached. Please try again in 5m.") == 300.0


def test_an_empty_wallet_is_set_aside_for_hours_not_minutes():
    w = web._aside_window("foursquare", 'HTTP 429 {"message":"Your account has no API credits remaining."}')
    assert w == web._NO_FUNDS_S >= 3600


def test_a_per_minute_quota_is_not_mistaken_for_an_empty_wallet():
    w = web._aside_window("gemini", "HTTP 429 You exceeded your current quota, please check your plan and billing details")
    assert w < 3600, "a free tier's per-minute limit set the index aside for hours"


def test_an_index_that_keeps_refusing_stays_aside_longer_and_one_answer_clears_it(two_indexes, monkeypatch):
    calls = two_indexes
    _gemini(monkeypatch, calls, "gemini grounding: HTTP 429 quota")
    windows = []
    for _ in range(3):
        web._aside.pop("gemini", None)                    # its window ran out
        web.search(f"Prado opening hours {_}")
        windows.append(web._aside["gemini"] - time.time())
    assert windows[0] < windows[1] < windows[2] <= web._ASIDE_MAX_S, windows

    web._aside.pop("gemini", None)
    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS, "gemini": lambda q, k: {
        "query": q, "answer": "Abre de 10 a 20 h.", "results": [], "source": "gemini"}})
    assert web.search("Prado hours on Monday")["source"] == "gemini"
    assert "gemini" not in web._strikes, "one answer and the index starts again from the short window"


def test_two_blocked_indexes_hand_the_fact_to_the_third(two_indexes, monkeypatch):
    calls = two_indexes
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    _gemini(monkeypatch, calls, "gemini grounding: HTTP 429 quota")
    monkeypatch.setattr(web, "_BACKENDS", {**web._BACKENDS,
                                           "zai": lambda q, k: (calls.append("zai"), (_ for _ in ()).throw(
                                               RuntimeError("zai web_search: HTTP 402 insufficient balance")))[1],
                                           "openai": lambda q, k: (calls.append("openai"), {
                                               "query": q, "answer": "10:00-20:00", "results": [], "source": "openai"})[1]})
    assert web.search("¿A qué hora abre el Prado?")["source"] == "openai"
    calls.clear()
    assert web.search("What time does the Prado open?")["source"] == "openai"
    assert calls == ["openai"], f"the next search asked the blocked indexes again: {calls}"
