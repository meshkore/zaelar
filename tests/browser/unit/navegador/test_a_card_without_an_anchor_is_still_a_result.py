"""V2-320 — a listing whose cards have no anchors was entirely INVISIBLE to the extractor.

Measured live (2026-08-25, kayak.es/cars): the page showed «381 resultados» —Fiat 500 a 105 €, Peugeot
408 a 167 €— with 27 leaf nodes containing prices, and `_JS_EXTRACT` returned CERO. By construction, the
candidate loop only traverses `a[href]`, and on Kayak each offer is a `<div>` whose only control is a «Ver
oferta» button. Aggregators love button CTAs (cars, insurance, activities) — which is exactly the shape
of the board’s «empty leaf» family (9/28 rounds).

Tested by RENDERING a local fixture with the measured shape of the real card (examined: no headings,
no img alt, no strong; the name exists ONLY in the button’s aria-label). A source-level test would accept
a collector that compiles; what matters is what comes out of a real DOM.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom

# The MEASURED shape of the Kayak card (examined on 2026-08-25): div, price in a leaf with a
# «Total» label, provider as the first line, and the full name only in the button’s aria-label.
_KAYAK_SHAPED = """
<div id="grid">
  <div class="card"><span>bsp-auto</span><div><span aria-label="22 € en total">22 €</span><span>Total</span></div>
    <button aria-label="Ver oferta para Seat Ibiza de bsp-auto desde 22 €">Ver oferta</button></div>
  <div class="card"><span>Booking.com</span><div><span aria-label="17 € en total">17 €</span><span>Total</span></div>
    <button aria-label="Ver oferta para Renault Clio de Booking.com desde 17 €">Ver oferta</button></div>
  <div class="card"><span>OK Mobility</span><div><span aria-label="31 € en total">31 €</span><span>Total</span></div>
    <button aria-label="Ver oferta para Fiat Panda de OK Mobility desde 31 €">Ver oferta</button></div>
</div>
"""

# And the anchor-per-card shape (Wallapop/Amazon): the established path, which must not move even a hair.
_ANCHORED = """
<div>
  <a href="https://x.example/item/monitor-lg-1"><img alt="Monitor LG Full HD"><span>Monitor LG Full HD</span>
    <span>20 €</span></a>
  <a href="https://x.example/item/monitor-msi-2"><img alt="Monitor MSI Curvo"><span>Monitor MSI Curvo</span>
    <span>100 €</span></a>
</div>
"""


@pytest.fixture(scope="module")
def _page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def _extract(page, html: str, limit: int = 20):
    page.set_content(html)
    return page.evaluate(dom._JS_EXTRACT, limit)


def test_una_tarjeta_sin_ancla_sale_con_nombre_y_precio(_page):
    rows = _extract(_page, _KAYAK_SHAPED)
    assert len(rows) == 3, f"tres tarjetas con precio son tres filas, no {len(rows)}"
    por_precio = {r["price"]: r for r in rows}
    assert set(por_precio) == {"22 €", "17 €", "31 €"}
    # The name is the card’s LONG accessible name, not the price’s short label («22 € en total»)
    assert "Seat Ibiza" in por_precio["22 €"]["title"]
    assert "Renault Clio" in por_precio["17 €"]["title"]
    # Without an anchor there is no URL, and the contract allows it (phone rows also have no amount)
    assert all(not r.get("url") for r in rows)


def test_el_camino_de_anclas_no_se_mueve_ni_un_pelo(_page):
    """The new collector’s guard triggers ONLY when the anchor collector is empty: in a listing with anchors,
    rows come through the established measured path — with URLs — and no phantom row slips in alongside them."""
    rows = _extract(_page, _ANCHORED)
    assert len(rows) == 2
    assert all(r.get("url", "").startswith("https://x.example/item/") for r in rows)
    assert [r["title"] for r in rows] == ["Monitor LG Full HD", "Monitor MSI Curvo"]


def test_una_pagina_sin_ningun_precio_sigue_dando_cero(_page):
    """The rentalcars form (examined: 129 anchors, zero amounts) must still come out
    empty: zero rows from a form is the HONEST answer, not a defect."""
    rows = _extract(_page, "<form><input placeholder='Recogida'><button>Buscar</button></form><a href='https://x.example/ayuda'>Ayuda</a>")
    assert rows == []
