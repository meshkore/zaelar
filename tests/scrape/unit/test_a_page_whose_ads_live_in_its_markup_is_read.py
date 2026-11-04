"""A page whose ads live only in its MARKUP is read from its repeated cards (V2-846 F5).

Measured 2026-11-04: idealista and refurbed carry no JSON-LD and no script state — the cards are the only place the ads
exist — so every rung before this one found zero. The pages here are synthetic but keep the shapes that were met:
idealista's price split across two elements (`1.030` · `€/mes`), a card that also links its agency, AutoTrader's model
tile «10 for sale starting at $4,995» (two numbers; the price is the one the currency touches), a navigation list with
links and no prices. The last rung, the model reading the page's text, is asked once per read and only when no free
rung read anything.
"""
from __future__ import annotations

import json

import pytest

import scrape
from scrape import dom, fetch, hooks, markup, validate

PAGE = "https://www.pisos.example.es/alquiler/valencia/"


def _flats(n: int = 5) -> str:
    cards = "".join(
        f'<article class="item"><a class="agency" href="/pro/agencia-{i}/">Agencia</a>'
        f'<a class="item-link" href="/inmueble/{1000 + i}/">Piso en Calle Mayor {i}, València</a>'
        f'<div class="price-row"><span class="price">{f"{1000 + i * 10:,}".replace(",", ".")}'
        f'</span><span class="unit">€/mes</span></div><span class="detail">{i + 1} hab.</span>'
        f'<span class="detail">{60 + i} m²</span></article>'
        for i in range(n))
    nav = "".join(f'<li><a href="/barrio/{i}/">Barrio {i} de València</a></li>' for i in range(12))
    return f'<html><body><ul class="nav">{nav}</ul><section class="list">{cards}</section></body></html>'


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(hooks, "model", None)


def test_the_cards_are_the_children_of_one_container_that_each_carry_a_link_and_a_price():
    container, cards = markup.cards(dom.parse(_flats()), PAGE)
    assert container is not None and "list" in container.sig() and len(cards) == 5, "never the price-less nav list"


def test_a_price_split_across_two_elements_is_read_and_the_items_own_link_is_kept():
    recs = markup.listings(_flats(), PAGE)
    assert [r["price"] for r in recs] == [1000.0, 1010.0, 1020.0, 1030.0, 1040.0]
    assert all(r["currency"] == "EUR" for r in recs)
    assert all("/inmueble/" in r["url"] for r in recs), "the agency's link is not the flat's"
    assert recs[0]["title"] == "Piso en Calle Mayor 0, València"
    assert "1 hab." in recs[0]["attributes"].values() and "60 m²" in recs[0]["attributes"].values()


def test_the_price_is_the_number_the_currency_touches():
    for text, want in [("10 for sale starting at $4,995", "$4,995"), ("1.030 €/mes", "1.030 €"),
                       ("€ 33.900", "€ 33.900"), ("1,250 USD a month", "1,250 USD")]:
        assert markup._AMOUNT.search(text).group(0) == want, text


def test_the_markup_rung_reads_a_page_the_earlier_rungs_could_not():
    records, how = scrape.records_of(_flats(), PAGE)
    assert how == "markup" and len(records) == 5


def test_the_dom_keeps_what_it_built_on_broken_markup_and_skips_scripts():
    root = dom.parse('<div class="a"><p>uno<script>var x="<p>no</p>";</script><span>dos</div></p><b>tres')
    assert root.all_text().split() == ["uno", "dos", "tres"], "the script's «<p>no</p>» is not page text"
    assert [n.sig() for n in root.select("div.a span")] == ["span"]


def test_the_readable_text_writes_each_link_after_its_words():
    text = markup.readable(_flats(1), PAGE)
    assert "Piso en Calle Mayor 0, València <https://www.pisos.example.es/inmueble/1000/>" in text


def test_the_model_reads_the_text_once_per_read_only_when_no_free_rung_could(monkeypatch):
    asked = []
    found = {"items": []}

    def model(system, text):
        asked.append(text)
        return json.dumps(found)
    monkeypatch.setattr(hooks, "model", model)
    blank = '<html><body><p>Casas rurales con piscina</p></body></html>'
    monkeypatch.setattr(fetch, "RUNGS", (("http", lambda u, c: blank), ("unlocker", lambda u, c: blank)))
    assert not scrape.read("https://www.casas.example.es/teruel").records
    assert len(asked) == 1, "two rungs brought a page, the model was asked once — not once per rung"
    asked.clear()
    found["items"] = [{"title": f"Casa rural {i} en Teruel", "url": f"/casa/{i}", "price": 300 + i,
                       "currency": "EUR", "details": ["6 plazas"]} for i in range(4)]
    res = scrape.read("https://www.casas.example.es/teruel")
    assert res.extractor == "model" and len(res.records) == 4 and res.records[0]["price"] == 300.0
    asked.clear()
    monkeypatch.setattr(fetch, "RUNGS", (("http", lambda u, c: _flats()),))
    assert scrape.read(PAGE).extractor == "markup" and asked == [], "a page a free rung reads never costs a model"


def test_the_models_items_pass_the_same_validator(monkeypatch):
    monkeypatch.setattr(hooks, "model", lambda s, t: json.dumps({"items": [
        {"title": "Elsewhere", "url": "https://other.example.com/x", "price": 10}] * 3}))
    monkeypatch.setattr(fetch, "RUNGS", (("http", lambda u, c: "<p>nada</p>"),))
    res = scrape.read("https://www.casas.example.es/teruel")
    assert res.records == [] and not res.ok(), "links to another site are not this page's items"
    assert validate.site_of("https://www.casas.example.es/x") == "example.es"
