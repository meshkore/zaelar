"""A wall moves the read one rung up, and a page that held nothing does too (V2-846).

Measured 2026-11-04: AutoScout24 serves a plain GET from a Fly Machine; coches.net and milanuncios come whole through
the unlocker; Wallapop refuses datacenter IPs, and Bright Data refuses robots-restricted sites with a 200 and an
`x-brd-error` header until the account's KYC. A block is a state, never the answer while a rung is left; each wall is
noted in the engine's one per-source record; the provider's own refusal is never handed on as the site's page.
"""
from __future__ import annotations

import pytest

import scrape
from scrape import brightdata, fetch, hooks

_LISTINGS = "".join(f'<script type="application/ld+json">{{"@type":"Product","name":"Item {i}","url":"/i/{i}",'
                    f'"offers":{{"price":{10 + i},"priceCurrency":"EUR"}}}}</script>' for i in range(3))


@pytest.fixture
def rungs(monkeypatch):
    def install(*pairs):
        monkeypatch.setattr(fetch, "RUNGS", tuple(pairs))
    return install


def test_a_wall_on_the_plain_get_is_climbed_by_the_unlocker(rungs):
    def walled(url, country):
        raise fetch.Wall("shop.example.com: HTTP 403")
    rungs(("http", walled), ("unlocker", lambda url, country: _LISTINGS))
    res = scrape.read("https://shop.example.com/search")
    assert res.how == "unlocker" and len(res.records) == 3 and res.ok()
    assert [t["status"] for t in res.tried] == ["wall", "ok"]


def test_a_page_with_no_listings_climbs_too_and_a_page_read_stops_at_the_first(rungs):
    rungs(("http", lambda u, c: "<html><body>app shell</body></html>"), ("unlocker", lambda u, c: _LISTINGS))
    assert scrape.read("https://shop.example.com/search").how == "unlocker"
    assert scrape.read("https://shop.example.com/search", "page").how == "http"


def test_when_every_rung_failed_the_result_says_so_with_each_reason(rungs):
    def walled(url, country):
        raise fetch.Wall("x: blocked")
    rungs(("http", walled), ("unlocker", walled))
    res = scrape.read("https://shop.example.com/search")
    assert not res.ok() and res.failure and len(res.tried) == 2 and all(t["note"] for t in res.tried)


def test_the_plain_get_classifies_a_blocking_status_as_a_wall_and_notes_it(monkeypatch):
    import httpx
    noted = []
    monkeypatch.setattr(hooks, "note", lambda source, outcome, detail: noted.append((source, outcome)))

    class Resp:
        status_code, url, text, headers = 403, "https://es.wallapop.com/search", "denied", {}

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, url): return Resp()
    monkeypatch.setattr(httpx, "Client", Client)
    fetch._domain_state.clear()
    with pytest.raises(fetch.Wall):
        fetch.http("https://es.wallapop.com/search")
    assert noted == [("es.wallapop.com", "wall")]
    fetch._domain_state.clear()


def test_the_providers_own_refusal_is_raised_never_handed_on_as_the_page(monkeypatch):
    import httpx

    class Resp:
        status_code, text = 200, "Residential Failed (bad_endpoint): requires KYC"
        headers = {"x-brd-error": "Residential Failed (bad_endpoint)"}

    class Client:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, url, headers=None, json=None): return Resp()
    monkeypatch.setattr(httpx, "Client", Client)
    monkeypatch.setattr(brightdata, "token", lambda: "placeholder")
    with pytest.raises(RuntimeError, match="refused"):
        brightdata.request({"zone": "web_unlocker1", "url": "https://es.wallapop.com/"}, provider="brightdata_unlocker")
