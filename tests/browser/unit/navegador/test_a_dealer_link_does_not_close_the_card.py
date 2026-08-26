"""V2-347 — PATHS are not LISTINGS: the dealer link inside the card closed the price walk, and every
anchored candidate on autoscout24 died.

Reproduced live and dissected on the SAVED page (2026-08-26): the card is an <article> holding exactly two
path classes — the listing («/anuncios/…», twice: accessibility anchor + naming anchor) and the DEALER
(«/profesionales/…») — with the price node «€ 11.900» right at level 1. `cardPrice` walks with maxPaths=1,
read «2 paths» as «this level spans two cards», broke at the FIRST level, and no listing ever got a price:
zero anchored candidates, so the price-leaf fallback shipped 12 rows titled with the dealer link
(«+ Vehículos del profesional (FLEXICAR…)») and NO url. Measured consequence downstream: the worker could
not open a single detail page and degraded to reading screenshots (~14 s per cycle), the sheet filled with
dealer names, and the delivery backstop went quiet 7 times behind the anti-feed guard.

The boundary the 2026-08-23 measurement actually needed is «a level that spans several LISTINGS», so when
the anchor itself is listing-class (ITEM), only listing-class paths count toward the cap. The grid — 19+
listing paths one level up — still breaks the walk exactly as before, which is the neighbour's-price
protection this cap exists for.

The fixture is a VERBATIM excerpt of the saved real page (three <article> cards, img payloads stripped):
a hand-built lookalike is exactly how this defect stayed invisible — the shape that kills the walk is the
page's, not ours.
"""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom

_FIXTURE = pathlib.Path(__file__).parent / "_data" / "autoscout24_listing_excerpt.html"


@pytest.fixture(scope="module")
def _page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def _rows(page, limit: int = 15):
    page.goto(_FIXTURE.as_uri())
    return page.evaluate(dom._JS_EXTRACT, limit)


def test_every_card_comes_out_as_car_plus_listing_url(_page):
    rows = _rows(_page)
    assert len(rows) == 3, rows
    for r in rows:
        # url = the LISTING, and it is what lets the worker open the detail page instead of reading pixels
        assert "/anuncios/" in (r.get("url") or ""), rows
        assert r.get("price"), rows
    # at least one row keeps a car NAME (the label-repetition blanking may take shared model names, never all)
    named = [r["title"] for r in rows if (r.get("title") or "").strip()]
    assert named, rows
    for t in named:
        assert "profesional" not in t.lower() and "Abrir detalles" not in t, rows


def test_the_dealer_link_is_not_a_row(_page):
    rows = _rows(_page)
    assert not [r for r in rows if "/profesionales/" in (r.get("url") or "")], rows


def test_the_grid_still_breaks_the_walk_for_a_priceless_card(_page):
    # Two listing-class cards side by side, ONE price between them: the priceless card must NOT inherit its
    # neighbour's amount — that is the 2026-08-23 protection the cap exists for, restated with ITEM paths.
    _page.set_content('<base href="https://x.example/">'
                      '<div>'
                      '<div class="card"><a href="/anuncios/con-precio-1">Con precio</a><span>150 €</span></div>'
                      '<div class="card"><a href="/anuncios/sin-precio-2">Sin precio</a></div>'
                      '</div>')
    rows = _page.evaluate(dom._JS_EXTRACT, 10)
    got = {(r["title"], r["price"]) for r in rows}
    assert ("Con precio", "150 €") in got, rows
    assert not [r for r in rows if r["title"] == "Sin precio"], rows
