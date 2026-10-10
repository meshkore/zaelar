"""The provider parsers read what the providers actually send (V2-782 F2), from payloads recorded 2026-10-10.

Z.ai and Gemini payloads are REAL (`tests/search/fixtures/`), recorded with the engine's own keys. The Foursquare
payload is hand-written in the documented shape: the account had no credits that day, so no real payload exists
yet — the test says so, and the day one is recorded it replaces the hand-written one.
"""
from __future__ import annotations

import json
from pathlib import Path

from search.providers import PROVIDERS, foursquare, gemini, zai

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def test_zai_rows_have_title_snippet_and_url():
    data = json.loads((FIX / "zai_web_search.json").read_text(encoding="utf-8"))
    rows = zai.parse(data, 10)
    assert 3 <= len(rows) <= 10
    for r in rows:
        assert r["title"] and r["url"].startswith("http"), r
        assert not r["snippet"].endswith("Read more"), "the trailing «Read more» is the API's, not the page's"
    assert zai.parse(data, 2) == rows[:2]


def test_gemini_answer_and_citations():
    data = json.loads((FIX / "gemini_grounding.json").read_text(encoding="utf-8"))
    out = gemini.parse(data, 5)
    assert out["answer"] and "Prado" in out["answer"]
    assert out["results"] and all(r["url"].startswith("https://") for r in out["results"])
    assert gemini.parse({}, 5) == {"answer": "", "results": []}


def test_foursquare_rows_carry_phone_rating_and_open_now():
    payload = {"results": [
        {"fsq_place_id": "a1", "name": "Fontanería Rápida", "tel": "+34 600 000 000", "website": "https://fr.example",
         "rating": 8.7, "hours": {"open_now": True, "display": "Mon-Sun 0:00-24:00"},
         "location": {"formatted_address": "Calle Mayor 1, Madrid"}, "categories": [{"name": "Plumber"}]},
        {"fsq_place_id": "a2", "name": "Sin datos"},
        {"name": ""},
    ]}
    rows = foursquare.parse(payload, 5)
    assert len(rows) == 2
    r = rows[0]
    assert (r["phone"], r["rating"], r["url"]) == ("+34 600 000 000", "8.7/10", "https://fr.example")
    assert r["availability"].startswith("open now") and "Plumber" in r["subtitle"]
    assert rows[1] == {"title": "Sin datos", "url": "", "phone": "", "rating": "", "availability": "", "subtitle": "",
                       "fsq_id": "a2"}


def test_every_paid_provider_has_an_energy_rate_and_a_host_the_coverage_gate_sees():
    from nucleo import energy_meter
    for p in PROVIDERS.values():
        if p.paid:
            assert p.name in energy_meter._SEARCH_USD_PER_REQUEST, f"{p.name}: no rate — the catch-all would bill it"
            assert p.host, p.name


def test_a_missing_key_returns_an_empty_answer_without_a_network_call(monkeypatch):
    for name in ("Z_AI_API_KEY", "GEMINI_API_KEY", "FOURSQUARE_SERVICE_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert zai.search("x")["results"] == []
    assert gemini.search("x")["answer"] == ""
    assert foursquare.places("x") == []
