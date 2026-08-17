"""tests/agent_headless/unit/agentes/test_web_cc_site_catalog.py — the browser worker's trusted-site catalog
(V2-099 follow-up, 2026-08-17): two independent live use-case runs (hotel search, restaurant booking) hit the
identical failure — the worker genuinely fires but never completes, because it improvises a destination site
and flow from scratch every time. `nucleo/flash/site_catalog.py` gives it a short list of known-good defaults
per category, locale-aware (system genetics — see its own docstring for the memory-priority contract: the
operator's own stated preference always overrides this catalog). This test only verifies the catalog itself
and that `web_cc._web_prompt` actually includes it — not that the worker OBEYS it (that needs a live run).
"""
from __future__ import annotations

from nucleo.agentes import web_cc
from nucleo.flash import site_catalog

_CATEGORIES = {
    "restaurant_booking", "hotel_booking", "flight_search", "car_classifieds",
    "general_classifieds", "generic_marketplace",
}


def test_every_locale_covers_the_same_categories():
    # symmetric on purpose (see the module docstring) — a category missing from one locale silently falls
    # back to nothing instead of a sensible per-market default.
    for locale, catalog in site_catalog.SITE_CATALOG.items():
        assert set(catalog) == _CATEGORIES, locale


def test_every_entry_has_a_real_looking_https_url():
    for locale, catalog in site_catalog.SITE_CATALOG.items():
        for key, entry in catalog.items():
            assert entry.url.startswith("https://"), (locale, key)
            assert entry.name
            assert entry.note


def test_resolve_locale_maps_spanish_to_es_and_everything_else_to_us():
    assert site_catalog.resolve_locale("es") == "es"
    assert site_catalog.resolve_locale("en") == "us"
    assert site_catalog.resolve_locale(None) == "us"
    assert site_catalog.resolve_locale("") == "us"


def test_directive_block_mentions_every_site_by_name_and_url_for_its_locale():
    for locale in site_catalog.SITE_CATALOG:
        block = site_catalog.directive_block(locale)
        for entry in site_catalog.SITE_CATALOG[locale].values():
            assert entry.name in block
            assert entry.url in block


def test_es_and_us_catalogs_pick_different_sites_for_the_same_category():
    # a real locale split, not the same content duplicated under two keys
    assert site_catalog.SITE_CATALOG["es"]["restaurant_booking"].name != \
        site_catalog.SITE_CATALOG["us"]["restaurant_booking"].name


def test_directive_block_tells_the_worker_to_check_memory_before_the_catalog():
    block = site_catalog.directive_block("es").lower()
    assert "mem_cli recall" in block
    assert "manda" in block  # the override-priority wording


def test_directive_block_tells_the_worker_to_prefer_the_catalog_even_for_a_named_business():
    block = site_catalog.directive_block("es").lower()
    assert "aunque" in block or "incluso" in block


def test_web_prompt_embeds_the_directive_block():
    prompt = web_cc._web_prompt("resérvame mesa en Casa Lucio esta noche", "es")
    assert site_catalog.directive_block() in prompt
    assert "Casa Lucio" in prompt  # the actual goal must still be present, untouched
