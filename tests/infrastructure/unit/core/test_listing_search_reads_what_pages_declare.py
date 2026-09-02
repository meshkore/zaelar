"""Listing search (V2-556): pages DECLARE their listings and we read the declaration.

The middle tier between `web_search` (facts) and the browser worker (minutes): JSON-LD/OpenGraph out
of real marketplace HTML shapes, normalized to the Results widget vocabulary, price-filtered,
deduplicated — and an HONEST `needs_browser` when HTTP could not do the job, because this module
giving up silently would send every listing errand back to the browser without anyone knowing why.

Everything here is offline: `listing_extract` is pure, and the `search()` ladder is exercised with
its rungs monkeypatched — a unit test never touches the network or a live artifact.
"""
from __future__ import annotations

import pytest

from nucleo import listing_extract, listing_search
from nucleo.listing_search import ListingQuery


# ── extraction: JSON-LD ──────────────────────────────────────────────────────────────────────────
def test_a_product_with_an_offer_becomes_a_normalized_item():
    html = """
    <html><head><script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Product",
     "name": "Lagoon 440", "url": "/boats/lagoon-440-2009",
     "image": "https://cdn.example.com/l440.jpg",
     "brand": {"@type": "Brand", "name": "Lagoon"},
     "offers": {"@type": "Offer", "price": "285000", "priceCurrency": "EUR"}}
    </script></head><body></body></html>"""
    items = listing_extract.extract_items(html, "https://boats.example.com/listing")
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Lagoon 440"
    assert item["price"] == 285000.0 and item["currency"] == "EUR"
    assert item["original_price"] == "285000"          # normalization never destroys the source
    assert item["url"] == "https://boats.example.com/boats/lagoon-440-2009"  # relative → absolute
    assert item["attributes"]["brand"] == "Lagoon"     # nested node flattened to its name
    assert item["extracted_from"] == "jsonld"


def test_an_itemlist_search_page_yields_every_product_in_it():
    products = "".join(
        f'{{"@type": "ListItem", "position": {i}, "item": {{"@type": "Product", '
        f'"name": "BMW X5 {2020 + i}", "url": "/car/{i}", '
        f'"offers": {{"@type": "Offer", "price": {30000 + i * 1000}, "priceCurrency": "EUR"}}}}}},'
        for i in range(1, 4))
    html = ('<script type="application/ld+json">{"@context": "https://schema.org", '
            '"@type": "ItemList", "itemListElement": [' + products.rstrip(",") + "]}</script>")
    items = listing_extract.extract_items(html, "https://cars.example.com/search")
    assert {i["title"] for i in items} == {"BMW X5 2021", "BMW X5 2022", "BMW X5 2023"}
    assert all(i["price"] is not None for i in items)


def test_a_vehicle_carries_its_category_attributes():
    html = """<script type="application/ld+json">
    {"@type": "Vehicle", "name": "BMW X5 xDrive30d",
     "mileageFromOdometer": {"@type": "QuantitativeValue", "value": "89000"},
     "vehicleModelDate": "2022", "fuelType": "Diesel",
     "offers": {"price": "38900", "priceCurrency": "EUR"}}
    </script>"""
    (item,) = listing_extract.extract_items(html, "https://autos.example.com/x5")
    assert item["attributes"]["mileageFromOdometer"] == "89000"
    assert item["attributes"]["vehicleModelDate"] == "2022"
    assert item["attributes"]["fuelType"] == "Diesel"


def test_page_furniture_in_jsonld_is_not_a_listing():
    html = """<script type="application/ld+json">
    {"@type": "BreadcrumbList", "name": "Home > Boats"}</script>
    <script type="application/ld+json">
    {"@type": "Organization", "name": "Boats Inc"}</script>"""
    assert listing_extract.extract_items(html, "https://example.com") == []


# ── extraction: OpenGraph fallback ───────────────────────────────────────────────────────────────
def test_opengraph_product_is_the_fallback_when_no_jsonld():
    html = """<meta property="og:type" content="product">
    <meta property="og:title" content="MacBook Pro M5 14&quot;">
    <meta property="og:url" content="https://store.example.com/mbp-m5">
    <meta property="product:price:amount" content="1795.00">
    <meta property="product:price:currency" content="EUR">"""
    (item,) = listing_extract.extract_items(html, "https://store.example.com/mbp-m5")
    assert item["price"] == 1795.0 and item["currency"] == "EUR"
    assert item["extracted_from"] == "opengraph"


def test_opengraph_does_not_invent_a_listing_out_of_an_article():
    html = """<meta property="og:type" content="article">
    <meta property="og:title" content="The ten best catamarans of 2026">"""
    assert listing_extract.extract_items(html, "https://blog.example.com/post") == []


# ── price parsing: both continental conventions ──────────────────────────────────────────────────
@pytest.mark.parametrize("text,price,currency", [
    ("299.000 €", 299000.0, "EUR"),
    ("1.795,50 €", 1795.5, "EUR"),
    ("$1,795.50", 1795.5, "USD"),
    ("38 900 EUR", 38900.0, "EUR"),
    ("285000", 285000.0, ""),
    ("precio a consultar", None, ""),
])
def test_a_price_reads_the_same_in_madrid_and_in_austin(text, price, currency):
    assert listing_extract.parse_price(text) == (price, currency)


# ── dedup: the same listing, once ────────────────────────────────────────────────────────────────
def test_the_same_listing_through_google_and_through_the_site_collides():
    a = {"title": "Lagoon 440", "price": 285000.0,
         "url": "https://boats.example.com/l440?utm_source=google&utm_campaign=x"}
    b = {"title": "Lagoon 440", "price": 285000.0, "url": "https://boats.example.com/l440/"}
    assert len(listing_extract.dedup([a, b])) == 1


def test_a_mirrored_listing_on_another_host_collides_by_title_and_price():
    a = {"title": "BMW X5 xDrive30d 2022", "price": 38900.0, "url": "https://site-a.example/1"}
    b = {"title": "2022 BMW X5 xDrive30d", "price": 38900.0, "url": "https://site-b.example/2"}
    assert len(listing_extract.dedup([a, b])) == 1


# ── price filter: unpriced items are kept, not hidden ────────────────────────────────────────────
def test_an_unpriced_listing_survives_the_price_cap():
    assert listing_extract.matches_price({"price": None}, price_max=1000)
    assert not listing_extract.matches_price({"price": 1500.0}, price_max=1000)
    assert listing_extract.matches_price({"price": 900.0}, price_max=1000, price_min=100)


# ── the ladder: honest needs_browser, no network ─────────────────────────────────────────────────
def _query(**kw) -> ListingQuery:
    base = dict(text="lagoon 440 usado", min_needed=3, fetch_cap=3)
    base.update(kw)
    return ListingQuery(**base)


@pytest.fixture(autouse=True)
def _no_cache_no_domain_state():
    listing_search._cache.clear()
    listing_search._domain_state.clear()
    yield
    listing_search._cache.clear()
    listing_search._domain_state.clear()


def test_blocked_fetches_say_needs_browser_with_the_reason(monkeypatch):
    monkeypatch.setattr(listing_search, "_free_discover", lambda q: [
        {"url": "https://walled.example.com/l1", "title": "t", "snippet": ""}])
    monkeypatch.setattr(listing_search, "_bd_token", lambda: "")

    def _blocked(url, country):
        raise RuntimeError("walled.example.com: HTTP 403 (bot wall)")
    monkeypatch.setattr(listing_search, "_fetch", _blocked)

    result = listing_search.search(_query())
    assert result["needs_browser"] is True
    assert result["items"] == []
    blocked_rows = [s for s in result["sources"] if s["status"] == "blocked"]
    assert blocked_rows and "403" in blocked_rows[0]["note"]
    # The reason is a sentence someone can act on, not a boolean with no story.
    assert "bot wall" in result["reason"] or "unlocker" in result["reason"] or "structured" in result["reason"]


def test_enough_structured_listings_do_not_ask_for_a_browser(monkeypatch):
    monkeypatch.setattr(listing_search, "_bd_token", lambda: "")
    monkeypatch.setattr(listing_search, "_free_discover", lambda q: [
        {"url": "https://boats.example.com/search", "title": "t", "snippet": ""}])
    html = "".join(
        f'<script type="application/ld+json">{{"@type": "Product", "name": "Boat {i}", '
        f'"url": "/b/{i}", "offers": {{"price": {200000 + i}, "priceCurrency": "EUR"}}}}</script>'
        for i in range(4))
    monkeypatch.setattr(listing_search, "_fetch", lambda url, country: (html, "http"))

    result = listing_search.search(_query())
    assert result["needs_browser"] is False
    assert len(result["items"]) == 4
    assert all(i["source"] == "boats.example.com" for i in result["items"])


def test_the_price_cap_is_applied_before_presenting(monkeypatch):
    monkeypatch.setattr(listing_search, "_bd_token", lambda: "")
    monkeypatch.setattr(listing_search, "_free_discover", lambda q: [
        {"url": "https://boats.example.com/search", "title": "t", "snippet": ""}])
    html = ('<script type="application/ld+json">{"@type": "Product", "name": "Cheap", "url": "/a",'
            '"offers": {"price": 250000, "priceCurrency": "EUR"}}</script>'
            '<script type="application/ld+json">{"@type": "Product", "name": "Dear", "url": "/b",'
            '"offers": {"price": 450000, "priceCurrency": "EUR"}}</script>')
    monkeypatch.setattr(listing_search, "_fetch", lambda url, country: (html, "http"))

    result = listing_search.search(_query(price_max=300000))
    assert [i["title"] for i in result["items"]] == ["Cheap"]
    fetch_row = next(s for s in result["sources"] if s["tier"] == "fetch")
    assert fetch_row["n"] == 2 and fetch_row["kept"] == 1   # the audit says what the filter did


def test_a_resting_domain_is_skipped_not_queued_behind_its_penalty():
    import time
    listing_search._domain_state["walled.example.com"] = {
        "next_ok": time.monotonic() + 120.0, "strikes": 2}
    assert listing_search._acquire("walled.example.com") is False
    assert listing_search._acquire("polite.example.com") is True


# ── money: the paid rungs are in the rate table (the 2026-08-13 lesson) ──────────────────────────
def test_every_brightdata_rung_has_its_own_search_rate():
    from nucleo import energy_meter
    for provider in ("brightdata_serp", "brightdata_unlocker"):
        assert provider in energy_meter._SEARCH_USD_PER_REQUEST, (
            f"{provider} would bill at the catch-all — add its real rate with source and date")
