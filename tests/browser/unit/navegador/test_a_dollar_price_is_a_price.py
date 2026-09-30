"""V2-776 — a listing priced in dollars is a listing.

The extractor's price pattern only knew the euro. On the v2 demo (2026-09-30, an operator in Los Angeles)
the monitors worker ran `extract` on Newegg and got 0 rows, then on eBay US and got one row with no price
and a part number read as a phone. With no listing it could trust, it spent eight minutes trying five other
sites before delivering. The shapes below are the ones those two stores use: the whole-dollar part and the
cents in a <sup>, and eBay's «US $» prefix.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom


@pytest.fixture(scope="module")
def _page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def _rows(page, html: str, limit: int = 10):
    page.set_content('<base href="https://shop.example/">' + html)
    return page.evaluate(dom._JS_EXTRACT, limit)


def test_a_store_card_with_the_cents_in_a_superscript_gives_its_dollar_price(_page):
    rows = _rows(_page,
                 '<div class="grid">'
                 '<div class="item-cell"><a href="/p/N82E1682447" class="item-title">MSI MAG 275UPD 27" 4K</a>'
                 '<ul><li class="price-current">$<strong>249</strong><sup>.99</sup></li></ul></div>'
                 '<div class="item-cell"><a href="/p/N82E1682448" class="item-title">AOC U27B3M 27" 4K</a>'
                 '<ul><li class="price-current">$<strong>279</strong><sup>.99</sup></li></ul></div>'
                 '</div>')
    got = {(r["title"], r["price"]) for r in rows}
    assert ("MSI MAG 275UPD 27\" 4K", "$249") in got, rows
    assert ("AOC U27B3M 27\" 4K", "$279") in got, rows


def test_a_us_prefixed_amount_is_a_price_and_a_part_number_is_not_a_phone(_page):
    rows = _rows(_page,
                 '<ul><li class="s-item"><a href="/itm/36208273">PHILIPS 27E1N1800A/00 27" 4K 36208-273-27</a>'
                 '<span class="s-item__price">US $199.00</span></li>'
                 '<li class="s-item"><a href="/itm/36208274">Dell S2721QS 27" 4K</a>'
                 '<span class="s-item__price">US $259.99</span></li></ul>')
    by_url = {r["url"].rsplit("/", 1)[-1]: r for r in rows}
    assert by_url["36208273"]["price"] == "$199.00", rows
    assert by_url["36208274"]["price"] == "$259.99", rows
    assert not by_url["36208273"]["tel"], rows


def test_the_euro_shapes_still_read(_page):
    rows = _rows(_page,
                 '<div><div class="card"><a href="/producto/1">Monitor A</a><span>169,00 €</span></div>'
                 '<div class="card"><a href="/producto/2">Monitor B</a><span>€ 399</span></div></div>')
    got = {r["price"] for r in rows}
    assert {"169,00 €", "€ 399"} <= got, rows
