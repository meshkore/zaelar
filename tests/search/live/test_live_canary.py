"""The LIVE canary of the search service (V2-782 T3.4) — opt-in, real providers, loose assertions.

    ZAELAR_TEST_LIVE_SEARCH=1 ./.venv/bin/python -m pytest -q tests/search/live

Skipped without the switch: the deterministic sweep never reaches the network. With it, a handful of fixed
questions go to the real chain once (a few cents) and are compared LOOSELY — a fact came back with an answer, a
lead hunt brought at least N candidates with their urls, a local service said which asked field it could not
show. It measures that the layer is alive and shaped right, not that the world holds a particular answer.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(os.getenv("ZAELAR_TEST_LIVE_SEARCH") != "1",
                                reason="live providers; set ZAELAR_TEST_LIVE_SEARCH=1")


@pytest.fixture(scope="module", autouse=True)
def _credentials():
    from search.health import _load_credentials
    _load_credentials()
    os.environ.setdefault("BROWSER_SEARCH", "0")      # no warm Chromium outside the engine


def test_at_least_one_provider_is_live():
    from search import health
    rows = health.probe_all(["openai", "gemini", "zai", "ddg"])
    s = health.summary(rows)
    assert s["can_answer"], health.render(rows)


def test_a_fact_comes_back_answered():
    import search
    res = search.find("¿a qué hora abre el Museo del Prado?", route="inline_fact")
    assert res.ok() and res.provider, res.to_dict()
    assert res.answer or res.candidates


def test_a_lead_hunt_brings_pages_with_urls():
    import search
    res = search.find("fontanero urgente en Madrid", route="local_service", k=8)
    assert len(res.candidates) + len(res.pages) >= 3, res.to_dict()
    assert all(c.url.startswith("http") for c in res.candidates)


def test_a_criterion_no_lead_shows_is_said_missing():
    import search
    res = search.find("el fontanero mejor valorado de Madrid que pueda venir hoy", route="local_service", k=8)
    if not any(c.rating for c in res.candidates):
        assert "rating / reviews" in res.unshown
