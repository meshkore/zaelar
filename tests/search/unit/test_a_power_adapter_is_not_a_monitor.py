"""A power adapter or charger is an accessory, never a candidate for the thing asked (node 2.605).

cheapest-monitor EN (2026-10-14, sandbox 010127-en): for «27-inch, 4K, new only, up to $250» the sheet's top rows were
«Nuevo Adaptador de CA Monitor… — 170», «Adaptador 19V para LG 27UK650-W… — 17.91», «19.5v3.3a Adapter for LG… —
26.35», and the reply offered all three as candidates; he answered «those are power adapters, not monitors». The
category gate (`search/category.py`) had no adapter, charger or power-supply marker, and 17.91 is above 5 % of the
ceiling, so nothing said they were not monitors.
"""
from __future__ import annotations

import pytest

from search import category

ASK = "Hey, my work monitor is dying… 27-inch, 4K, and new only. Budget is up to $250"


@pytest.mark.parametrize("title", ["Nuevo Adaptador de CA Monitor…", "Adaptador 19V para LG 27UK650-W…",
                                   "19.5v3.3a Adapter for LG…", "Cargador para monitor Samsung 14V",
                                   "Power supply for Dell S2721Q monitor", "Fuente de alimentación monitor LG 19V"])
def test_an_adapter_is_off(title):
    on, off = category.split([{"title": title, "price": "17.91"}], ASK)
    assert not on and "accessory" in off[0]["why"], off


@pytest.mark.parametrize("title", ["Monitor AGEX 27 pulgadas 4K UHD…", 'LG 27UL500 27" 4K monitor with power adapter',
                                   "Dell S2721QS 27 4K UHD Monitor (incluye adaptador)"])
def test_a_monitor_that_ships_with_one_stays(title):
    on, off = category.split([{"title": title, "price": "179.99"}], ASK)
    assert on and not off, off


def test_asking_for_an_adapter_makes_adapters_the_candidates():
    on, off = category.split([{"title": "Adaptador 19V para LG 27UK650-W…", "price": "17.91"}],
                             "necesito un adaptador de corriente para mi monitor LG")
    assert on and not off
