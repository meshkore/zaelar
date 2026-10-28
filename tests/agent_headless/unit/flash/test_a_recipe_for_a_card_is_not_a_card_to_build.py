"""A recipe to show on an existing card is not a card to BUILD (docs-single-recipe-not-a-list EN, 2026-10-14).

Sandbox 20261014-120418-en: «…carbonara recipe (… no cream) and display it in the documento widget» was classified
as widget CODE — «cream» read as the Spanish create verb «crea», and «in the documento widget» (a named card) was
not read as a destination — so the worker asked «you're asking me to BUILD you a new card… Shall I?» and the recipe
never reached the sheet.
"""
from __future__ import annotations

import pytest

from nucleo.request import kind as errand_kind
from nucleo.flash import router_guards

RECIPE = ("Provide a classic, authentic Roman carbonara recipe (guanciale, eggs, pecorino, pasta water — no cream) "
          "and display it in the documento widget as a readable recipe: ingredients with quantities and steps.")


def test_the_measured_request_is_not_a_build():
    assert not router_guards.looks_like_create_widget(RECIPE)
    assert errand_kind.classify_kind(RECIPE) != "code" and errand_kind.code_change(RECIPE) == ""


@pytest.mark.parametrize("text", ["carbonara with no cream for the dinner widget",
                                  "a creamy mushroom soup for the recipes panel"])
def test_cream_is_not_the_spanish_create_verb(text):
    assert not router_guards.looks_like_create_widget(text)


@pytest.mark.parametrize("text", ["make a summary and put it in the documento widget",
                                  "prepare the sales numbers and show them on the markets panel"])
def test_a_named_card_after_in_is_where_it_goes(text):
    assert not router_guards.looks_like_create_widget(text)


@pytest.mark.parametrize("text", ["créame un widget del tiempo", "creamos un panel nuevo para las facturas",
                                  "build me a widget that tracks my steps", "create a weather widget",
                                  "build a widget and put it in a new widget"])
def test_a_real_create_is_still_a_create(text):
    assert router_guards.looks_like_create_widget(text)
