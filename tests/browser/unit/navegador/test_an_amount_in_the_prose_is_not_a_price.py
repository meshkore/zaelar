"""V2-335 — an amount inside the link's PROSE made articles and nav links ship as priced candidates.

Measured live 2026-08-26 on three comparator pages, all through the REAL extractor at HEAD:

  · acierto.com/seguros-coche — 8/8 garbage: the footer loan links («Préstamos 2.000 euros») became
    candidates priced «2.000 eur». The amount is the SUBJECT of the headline, not a price — the pattern's
    `(EUR|eur)` was matching the first three letters of the word «euros».
  · kompara.es — article teasers shipped priced from mid-sentence amounts («Vodafone puede cobrar hasta
    314 € de penalización…», a 137-char text node).
  · kelisto.es/internet-movil — «Los mejores préstamos de 1.000 euros» shipped as a candidate, while the
    REAL tariff cards on the same page carry their price split across spans («35,99» + «€») inside a short
    wrapper element — exactly the read `cardPrice` already trusted.

The property: a price is written «€» or «EUR» (the word «euros» is prose), and it lives in an element that
is almost only the amount (`priceIn`, one discipline shared by the anchor's own subtree and the card walk).

Two traps this file inherits from the harness's own measurements (2026-08-26):
  · fixtures carry <base href> — set_content without it leaves URLs origin-less and the test passes with
    and without the fix;
  · survivors are asserted BY THEIR LINK, not their title — an over-aggressive cut gets its rows rescued
    by the anchor-less collector, which produces titles but can never produce a URL.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom

_BASE = '<base href="https://comparador.example/">'

# The measured comparator page, all four shapes at once: a REAL tariff card (anchor wraps the card, price
# split across spans inside a short wrapper, promo amounts in prose), an article headline whose subject is
# an amount, an article card with a mid-sentence amount in its teaser, and the loans footer.
_COMPARATOR = _BASE + """
<div id="listado">
  <a href="/operadores/pepephone/tarifa-fibra-600">
    <span>PATROCINADA</span><span>Fibra 600 Mb + 60 GB de Pepephone</span>
    <span>Líneas adicionales por 5€/mes GB acumulables</span>
    <div class="precio"><span>35,00</span><span>€</span><span>/mes</span></div>
  </a>
  <a href="/prestamos/mejor-compra/los-mejores-prestamos-de-1000-euros">Los mejores préstamos de 1.000 euros</a>
  <a href="/tarifas/baja-vodafone-sin-penalizacion">
    <span>TARIFAS</span><span>Cómo darse de baja de Vodafone sin penalización en 2026</span>
    <p>Vodafone puede cobrar hasta 314 € de penalización según el momento del contrato en que se pida la
    baja, y estas son las condiciones que aplican a cada modalidad.</p>
  </a>
</div>
<footer>
  <a href="/prestamos/300-euros/">Préstamo 300 euros</a>
  <a href="/prestamos/2000-euros/">Préstamos 2.000 euros</a>
  <a href="/prestamos/5000-euros/">Préstamos 5.000 euros</a>
</footer>
"""

# Only the loans footer: with every anchor dead, the anchor-less collector is what runs — and the word
# «euros» must not feed it either.
_LOANS_ONLY = _BASE + """
<footer>
  <a href="/prestamos/300-euros/">Préstamo 300 euros</a>
  <a href="/prestamos/2000-euros/">Préstamos 2.000 euros</a>
</footer>
"""

# A real currency CODE is not the word: this row must survive.
_EUR_CODE = _BASE + """
<div>
  <a href="/anuncio/bici-carretera-9"><img alt="Bici de carretera"><span>Bici de carretera</span>
    <span>25 EUR</span></a>
</div>
"""

# The marketplace shape (price in a sibling node of the card, reached by the card walk) cannot move.
_MARKETPLACE = _BASE + """
<div>
  <div class="card"><a href="/item/monitor-lg-1"><img alt="Monitor LG Full HD"></a><span>150 €</span></div>
  <div class="card"><a href="/item/monitor-msi-2"><img alt="Monitor MSI Curvo"></a><span>100 €</span></div>
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


def test_articles_and_loan_links_are_not_candidates_and_the_tariff_card_is(_page):
    rows = _extract(_page, _COMPARATOR)
    urls = [r.get("url") or "" for r in rows]
    # The survivor is asserted by its LINK: the anchor-less rescue can fabricate a title, never a URL.
    assert [u for u in urls if "/operadores/pepephone/" in u], rows
    tarifa = next(r for r in rows if "/operadores/pepephone/" in (r.get("url") or ""))
    # …and its price is the card's price NODE, not the first amount in the promo prose.
    assert tarifa.get("price") == "35,00 €".replace(" ", "") or tarifa.get("price") == "35,00€", rows
    assert not [u for u in urls if "prestamos" in u], rows
    assert not [u for u in urls if "baja-vodafone" in u], rows


def test_with_every_anchor_dead_the_word_euros_does_not_feed_the_leaf_collector(_page):
    assert _extract(_page, _LOANS_ONLY) == []


def test_a_currency_code_is_a_price_and_the_word_is_not(_page):
    rows = _extract(_page, _EUR_CODE)
    assert len(rows) == 1 and rows[0]["price"] == "25 EUR", rows


def test_the_marketplace_card_walk_cannot_move(_page):
    rows = _extract(_page, _MARKETPLACE)
    got = {(r["title"], r["price"]) for r in rows}
    assert ("Monitor LG Full HD", "150 €") in got and ("Monitor MSI Curvo", "100 €") in got, rows
    assert all(r.get("url") for r in rows), rows
