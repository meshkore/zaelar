"""A Google result behind Google's own redirect is still a result, with its description and its real page.

Measured 2026-10-23 on twelve fact questions through the warm search Chromium: zero rows on every one. Google had
started wrapping each organic link in `https://www.google.com/goto?url=<opaque>`, and the extractor skipped every
link to a google host — its own redirects included. The health probe still said `live` because it only asked
«wikipedia», whose knowledge panel filled the answer field. With the redirects read back: 12/12 in 1.2–2 s.

Same pass: the description is a SIBLING of the anchor's header block, so the snippet was the site name and the
cite path; and the weather card read «65°C» for a Barcelona at 18 °C / 65 °F because the unit was written by hand.
"""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from search import browser


def _result(goto: str, title: str, site: str, cite: str, desc: str) -> str:
    return (f'<div class="g"><div><div><span><a href="{goto}"><h3>{title}</h3><div>{site}</div>'
            f'<cite>{cite}</cite></a></span><span> · <a href="https://translate.google.com/x">Traducir esta página'
            f'</a></span></div><div><span>{desc}</span></div></div></div>')


PAGE = (
    '<div id="search">'
    '<div><span id="wob_loc">Barcelona</span><span id="wob_dc">Nublado</span>'
    '<span id="wob_tm" style="display:inline">18</span><span id="wob_ttm" style="display:none">65</span>'
    '<span aria-disabled="true">°C</span><span>°F</span></div>'
    + _result("https://www.google.com/goto?url=CAESXgHrOzAV7Z0E", "Horarios y tarifas",
              "Museo del Prado", "https://www.museodelprado.es › visita",
              "Lunes a sábado: de 10:00 a 20:00 h · Domingos y festivos: de 10:00 a 19:00 h.")
    + _result("https://www.google.es/url?q=https://en.wikipedia.org/wiki/Tokyo&sa=U", "Tokyo",
              "Wikipedia", "https://en.wikipedia.org › wiki",
              "The population of the city proper was over 14 million as of 2023.")
    + '<a href="https://www.google.com/search?q=more"><h3>More results</h3></a>'
    '</div>')


@pytest.fixture(scope="module")
def extracted():
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        p = b.new_page()
        p.set_content(PAGE)
        out = p.evaluate(browser._EXTRACT_JS)
        b.close()
    return out


def test_every_redirected_result_is_a_row_and_a_google_page_is_not(extracted):
    titles = [r["title"] for r in extracted["results"]]
    assert titles == ["Horarios y tarifas", "Tokyo"], titles


def test_the_snippet_is_the_description_not_the_header(extracted):
    prado, tokyo = extracted["results"]
    assert prado["snippet"].startswith("Lunes a sábado: de 10:00 a 20:00 h"), prado["snippet"]
    assert "14 million" in tokyo["snippet"]
    for r in extracted["results"]:
        assert "cite" not in r["snippet"] and "›" not in r["snippet"] and "Traducir" not in r["snippet"], r["snippet"]


def test_the_weather_reads_the_unit_the_card_shows(extracted):
    assert extracted["answer"] == "Barcelona: 18°C, Nublado", extracted["answer"]


def test_a_redirect_is_rewritten_to_the_page_it_lands_on(monkeypatch):
    class Resp:
        headers = {"location": "https://www.museodelprado.es/visita/horarios-y-tarifas"}

    class Client:
        def __init__(self, *a, **k): self.asked = []
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            assert "/goto?" in url, "only an opaque redirect is asked over the network"
            return Resp()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    rows = [{"url": "https://www.google.com/goto?url=CAESXgHrOzAV7Z0E"},
            {"url": "https://www.google.es/url?q=https://en.wikipedia.org/wiki/Tokyo&sa=U"},
            {"url": "https://www.rtings.com/monitor"}]
    asyncio.run(browser._unwrap_redirects(rows))
    assert [r["url"] for r in rows] == ["https://www.museodelprado.es/visita/horarios-y-tarifas",
                                        "https://en.wikipedia.org/wiki/Tokyo", "https://www.rtings.com/monitor"]


def test_an_opaque_redirect_is_asked_with_the_browsers_cookies(monkeypatch):
    """2026-11-03: asked with no cookies, Google answers a `/goto` with a 200 interstitial and no `Location`; every
    such row stayed a google.com url. The search browser's own context gets the 302 — it is asked first."""
    class Bare:
        headers = {}                                              # the cookie-less 200 interstitial

    class Client:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url): return Bare()

    class Answer:
        headers = {"location": "https://www.serviciositv.es/precios-itv"}

    class Request:
        def __init__(self): self.asked = []
        async def get(self, url, **kw):
            self.asked.append((url, kw.get("max_redirects")))
            return Answer()

    class Ctx:
        request = Request()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    monkeypatch.setattr(browser, "_ctx", Ctx())
    rows = [{"url": "https://www.google.com/goto?url=CAESYgHrOzAVNcoM"}]
    asyncio.run(browser._unwrap_redirects(rows))
    assert rows[0]["url"] == "https://www.serviciositv.es/precios-itv"
    assert Ctx.request.asked == [("https://www.google.com/goto?url=CAESYgHrOzAVNcoM", 0)], "asked once, not followed"


def test_a_google_search_hands_back_the_pages_not_the_redirects(monkeypatch):
    """The wiring: `search_google` itself rewrites what the extractor read, so no caller ever sees a `/goto`."""
    class Page:
        async def goto(self, *a, **k): return None
        async def wait_for_selector(self, *a, **k): return None
        async def evaluate(self, js):
            return {"answer": "", "results": [{"title": "Tokyo", "snippet": "14 million",
                                               "url": "https://www.google.es/url?q=https://en.wikipedia.org/wiki/Tokyo"}]}
        async def close(self): return None

    class Ctx:
        async def new_page(self): return Page()

    async def ready(): return True
    async def nothing(page): return False
    monkeypatch.setattr(browser, "ensure_started", ready)
    monkeypatch.setattr(browser, "_ctx", Ctx())
    monkeypatch.setattr(browser, "_dismiss_consent", nothing)
    monkeypatch.setattr(browser, "_looks_blocked", nothing)
    out = asyncio.run(browser.search_google("Population of Tokyo", 5))
    assert out["results"][0]["url"] == "https://en.wikipedia.org/wiki/Tokyo"
