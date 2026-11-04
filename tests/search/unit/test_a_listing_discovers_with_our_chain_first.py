"""A listing hunt discovers with our own chain first, and with the Bright Data SERP first only when he named
countries — the one thing our chain cannot do. The SERP asks for Light JSON with the exit country in the body and
drops Google's opaque `/goto` links (measured 2026-11-04: 6-53 s a query, a captcha with `brd_json=1`, 7 of 9 links
opaque; our discovery 1-3 s with real pages)."""
from __future__ import annotations

import json

import pytest

from search import listing


@pytest.fixture
def ladder(monkeypatch):
    calls = []
    monkeypatch.setattr(listing, "_bd_token", lambda: "placeholder")
    monkeypatch.setattr(listing, "_free_discover", lambda q: calls.append("free") or [
        {"url": "https://shop.es/a", "title": "A", "snippet": ""}])
    monkeypatch.setattr(listing, "_serp_discover", lambda q, c: calls.append(f"serp:{c}") or [
        {"url": "https://shop.fr/b", "title": "B", "snippet": ""}])
    monkeypatch.setattr(listing, "_candidate_urls", lambda discovered, cap: [])
    monkeypatch.setattr(listing, "_cached", lambda q: None)
    return calls


def test_without_countries_our_chain_discovers_and_the_serp_is_not_paid(ladder):
    listing.search(listing.ListingQuery(text="bici de montaña talla M"))
    assert ladder == ["free"]


def test_with_countries_the_serp_searches_from_each_one(ladder):
    listing.search(listing.ListingQuery(text="Lagoon 440", countries=("ES", "FR")))
    assert ladder == ["serp:ES", "serp:FR"]


def test_the_serp_asks_light_json_from_the_country_and_keeps_only_pages(monkeypatch):
    sent = {}
    def fake(payload, *, provider):
        sent.update(payload)
        return json.dumps({"organic": [{"link": "https://www.decathlon.es/x", "title": "X", "description": "d"},
                                       {"link": "/goto?url=CAESegHrOzAV", "title": "opaque"}]})
    monkeypatch.setattr(listing, "_bd_request", fake)
    rows = listing._serp_discover(listing.ListingQuery(text="bicicleta"), "ES")
    assert sent["data_format"] == "parsed_light" and sent["country"] == "es"
    assert "brd_json" not in sent["url"] and "gl=" not in sent["url"]
    assert [r["url"] for r in rows] == ["https://www.decathlon.es/x"]
