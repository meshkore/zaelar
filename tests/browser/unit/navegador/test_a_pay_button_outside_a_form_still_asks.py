"""A pay button that is not a form submit still asks (V2-778 F4-36, 2026-10-02).

`click_gate.decide` read the checkout path only for a SUBMIT-ish control — a `<button>` in a `<form>`. The
shape most single-page shops actually use is neither: a `<div role="button">Pay now</div>` wired by JavaScript,
on `/checkout/`, outside any form. That walked straight through the last rail before a real purchase. And the
path words were English and Spanish only: a German `/kasse/`, a French `/paiement/` passed as ordinary pages.
"""
from __future__ import annotations

import pytest

from widgets.navegador import click_gate as G


def _sig(**kw):
    base = {"name": "Continuar", "role": "div", "isSubmit": False, "inForm": False, "payment": False,
            "signals": "", "targetUrl": "", "pageUrl": "https://shop.example/"}
    base.update(kw)
    return base


@pytest.mark.parametrize("path", ["/checkout/", "/kasse/", "/zahlung", "/warenkorb/", "/panier", "/paiement/",
                                  "/tramitar-pedido/", "/cesta", "/carrito/"])
def test_a_script_button_on_a_checkout_page_asks(path):
    ask, why = G.decide(_sig(role="button", pageUrl=f"https://shop.example{path}"))
    assert ask is True, (path, why)


def test_the_same_words_in_a_submit_form_ask_too():
    assert G.decide(_sig(isSubmit=True, inForm=True, pageUrl="https://shop.example/kasse/"))[0] is True


def test_an_ordinary_page_and_a_non_button_stay_quiet():
    """The V2-776 lesson holds: a button on an ordinary page, and a plain element on a checkout page, do not ask —
    and the query string (a search's `checkout=` date) still never counts."""
    assert G.decide(_sig(role="button", pageUrl="https://shop.example/producto/42"))[0] is False
    assert G.decide(_sig(role="div", pageUrl="https://shop.example/checkout/"))[0] is False
    assert G.decide(_sig(role="button", pageUrl="https://hotels.example/search?checkout=2026-12-25"))[0] is False


@pytest.mark.parametrize("url", ["https://www.idealista.com/comprar-viviendas/madrid/",
                                 "https://www.fotocasa.es/es/comprar/viviendas/madrid/l",
                                 "https://shop.example/caja-fuerte-ignifuga"])
def test_a_spanish_browse_section_is_not_a_checkout(url):
    """«comprar» names where Spanish sites LIST what is for sale; asking on every button of a flat search is the
    V2-776 false alarm again."""
    assert G.decide(_sig(role="button", pageUrl=url))[0] is False, url
