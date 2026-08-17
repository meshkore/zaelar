"""tests/agent_headless/unit/agentes/test_web_cc_site_catalog.py — the browser worker's trusted-site catalog
(V2-099 follow-up, 2026-08-17): two independent live use-case runs (hotel search, restaurant booking) hit the
identical failure — the worker genuinely fires but never completes, because it improvises a destination site
and flow from scratch every time. `nucleo/flash/site_catalog.py` gives it a short list of known-good defaults
per category; this test only verifies the catalog itself and that `web_cc._web_prompt` actually includes it —
not that the worker OBEYS it (that needs a live run against the real engine).
"""
from __future__ import annotations

from nucleo.agentes import web_cc
from nucleo.flash import site_catalog


def test_catalog_covers_the_categories_hit_by_promoted_use_cases():
    # restaurant, hotel, flight, car-classifieds, generic-marketplace — one entry per category this suite's
    # promoted scenarios (tests/use_cases/e2e/agent/scenarios.py) actually exercise.
    assert set(site_catalog.SITE_CATALOG) == {
        "restaurant_booking", "hotel_booking", "flight_search", "car_classifieds",
        "general_classifieds", "generic_marketplace",
    }


def test_every_entry_has_a_real_looking_https_url():
    for key, entry in site_catalog.SITE_CATALOG.items():
        assert entry.url.startswith("https://"), key
        assert entry.name
        assert entry.note


def test_directive_block_mentions_every_site_by_name_and_url():
    block = site_catalog.directive_block()
    for entry in site_catalog.SITE_CATALOG.values():
        assert entry.name in block
        assert entry.url in block


def test_directive_block_tells_the_worker_to_prefer_the_catalog_even_for_a_named_business():
    block = site_catalog.directive_block().lower()
    assert "aunque" in block or "incluso" in block  # covers the "even if a specific business is named" clause


def test_web_prompt_embeds_the_directive_block():
    prompt = web_cc._web_prompt("resérvame mesa en Casa Lucio esta noche", "es")
    assert site_catalog.directive_block() in prompt
    assert "Casa Lucio" in prompt  # the actual goal must still be present, untouched
