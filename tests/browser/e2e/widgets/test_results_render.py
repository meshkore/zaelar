"""V2-538 — the results sheet RENDERED, because its defect was a matter of layout.

The operator, with the sheet on screen: "hay una barra arriba con el botón de mover, luego el título sale en el
medio, debajo sale otro título que es el real, después sale una línea que no necesito para nada donde pone el
usuario, la sesión y copiar, y después salen los tabuladores". Four bands of chrome before a single result.

The identity strip (user id · session id · Copy) is real and useful — it is how a session gets handed to a code
agent for auditing — but it belongs where auditing happens, not above every result of every search. It moved to
the bottom of the SUMMARY tab. Nothing here reads source: whether a strip sits between the title and the tabs is
a question about the mounted DOM, the same lesson as node 4.83.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "results", "widget.js")

_SHEET = {
    "title": "Catamaranes de segunda mano de menos de 200.000 euros",
    "subtitle": "8 anuncios reales · ordenados por precio",
    "tab": "results",
    "counts": {"shown": 2, "sources": 2},
    "summary": {"state": "verificando los finalistas", "explored": 47, "discarded": 44,
                "steps": ["barrido en 3 portales", "descartados los de menos de 42 pies"]},
    "items": [
        {"title": "Lagoon 380", "price": "151.008 €", "subtitle": "11,55 m · 2 cascos",
         "score": {"value": 8.2, "max": 10, "why": "la mejor relación eslora/precio"},
         "url": "https://example.com/lagoon", "facts": [{"label": "Año", "value": "2007"}]},
        {"title": "Fountaine Pajot Lipari 41", "price": "189.000 €", "subtitle": "12,48 m · 4 camarotes"},
    ],
    "sources": [{"name": "Yachtworld", "url": "https://www.yachtworld.es", "status": "ok", "found": 128}],
}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202b;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-bubble:#1b2735;--hb-ok:#1f9d55}
body{margin:0;background:#0a1017;padding:0}
#host{width:720px}
</style></head><body><div id="host"></div></body></html>"""

# The identity endpoint is stubbed so the strip actually FILLS: it removes itself when there is no identity,
# and a strip that removed itself would make "it is not in the header" pass for the wrong reason.
_MEASURE = """() => {
  const el = document.querySelector('.hb-results');
  if (!el) return {mounted: false};
  const top = el.querySelector('.hr-top');
  const tabs = el.querySelector('.hr-tabs');
  const panel = el.querySelector('.hr-panel');
  const strip = el.querySelector('.hr-ident');
  const inHeader = !!(top && strip && top.contains(strip));
  const inPanel = !!(panel && strip && panel.contains(strip));
  const firstCard = el.querySelector('.hr-card');
  return {
    mounted: true,
    header_h: top ? Math.round(top.getBoundingClientRect().height) : 0,
    strip_present: !!strip,
    strip_in_header: inHeader,
    strip_in_panel: inPanel,
    strip_ids: strip ? [...strip.querySelectorAll('code')].map(c => c.textContent) : [],
    tabs: [...(tabs ? tabs.querySelectorAll('.hr-tab') : [])].map(b => b.dataset.tab),
    first_result_y: firstCard ? Math.round(firstCard.getBoundingClientRect().top) : -1,
    cards: el.querySelectorAll('.hr-card').length,
  };
}"""


def _paint(data):
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 760, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            async def _identity(route):
                await route.fulfill(status=200, content_type="application/json",
                                    body=json.dumps({"user_id": "4cd1b39d-aaaa-bbbb",
                                                     "session_id": "0ceb114d-cccc"}))
            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_HTML)
            await pg.route("**/api/observability/identity", _identity)
            await pg.route("http://zaelar.test/", _page)
            # A REAL origin, not set_content: the strip fetches "/api/observability/identity" with a relative
            # URL, and from about:blank that request never resolves — the strip then removes itself, which
            # would make "it is not in the header" pass for the wrong reason.
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            await pg.evaluate("d => window.render(document.getElementById('host'), d, {action: () => {}})", data)
            await pg.wait_for_timeout(400)          # the strip fills asynchronously
            m = await pg.evaluate(_MEASURE)
            m["errors"] = errors
            await b.close()
            return m
    return asyncio.run(run())


@pytest.fixture(scope="module")
def results_tab():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return _paint(_SHEET)


@pytest.fixture(scope="module")
def summary_tab():
    return _paint({**_SHEET, "tab": "summary"})


def test_it_mounts_without_a_single_error(results_tab):
    assert results_tab["mounted"], "the sheet did not paint"
    assert results_tab["errors"] == [], results_tab["errors"]


def test_the_audit_ids_are_NOT_in_the_header_of_every_search(results_tab):
    """THE defect this file exists to catch. The strip is not deleted — it is not in the sticky band that sits
    between the sheet's title and its tabs, which is the space results are read in."""
    assert not results_tab["strip_in_header"], "the identity strip is back in the sheet header"


def test_the_header_stays_a_thin_band_and_results_start_high(results_tab):
    """The header is STICKY: every pixel it takes is taken from results for the whole scroll. Measured before
    the fix the strip alone was ~40px of it, on top of title + subtitle + tabs."""
    assert results_tab["header_h"] <= 130, results_tab["header_h"]
    assert 0 < results_tab["first_result_y"] <= 160, results_tab["first_result_y"]


def test_the_five_tabs_are_still_there_and_the_results_still_paint(results_tab):
    assert results_tab["tabs"] == ["process", "results", "summary", "sources", "criteria"]
    assert results_tab["cards"] == 2, "removing chrome must not remove content"


def test_the_ids_live_at_the_bottom_of_the_SUMMARY_tab_and_are_FILLED(summary_tab):
    """The other half: moving it out of the header cannot mean losing it. Auditing a session is summary work,
    so that is where it lives — and it must carry real ids, not the '…' placeholder it paints before the
    identity endpoint answers."""
    assert summary_tab["strip_present"], "the identity strip vanished instead of moving"
    assert summary_tab["strip_in_panel"], "it must sit inside the summary panel, not floating"
    assert all(i and i != "…" for i in summary_tab["strip_ids"]), summary_tab["strip_ids"]
