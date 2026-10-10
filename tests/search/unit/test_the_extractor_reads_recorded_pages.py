"""The extractor against REAL marketplace pages recorded 2026-10-10 (V2-782 T3.3).

Four list pages that answered HTTP 200 with JSON-LD that afternoon (`tests/search/fixtures/pages/`, first 400 KB
each). What the extractor must do with each is a fact about the page, said out loud: a category page that prices
itself with an AggregateOffer is a SOURCE (V2-556's rule), a page whose only node is its own description is
furniture, a search page whose list items are bare urls declares nothing. Zero with a reason is the honest answer
the browser tier then acts on — a guessed listing is not.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from search import extract

PAGES = Path(__file__).resolve().parents[1] / "fixtures" / "pages"


def _page(prefix: str) -> tuple[str, str]:
    path = next(PAGES.glob(prefix + "*.html"))
    host = path.name.split("-", 3)
    return path.read_text(encoding="utf-8", errors="replace"), f"https://{host[0]}.{host[1]}.{host[2]}/"


def test_the_fixtures_exist_and_declare_structured_data():
    files = sorted(PAGES.glob("*.html"))
    assert len(files) >= 4
    for f in files:
        assert "application/ld+json" in f.read_text(encoding="utf-8", errors="replace")[:400_000]


def test_a_category_page_that_prices_itself_with_an_aggregate_offer_is_not_a_listing():
    html, base = _page("www-coches-net")
    nodes = list(extract._iter_jsonld_nodes(html))
    assert any(extract._node_type(n) == "product" for n in nodes), "the page DOES declare a Product"
    assert extract.extract_items(html, base) == [], "…priced as a collection: a source, never a candidate"


def test_a_list_page_whose_only_node_is_its_own_description_is_furniture():
    html, base = _page("www-fotocasa-es")
    nodes = [n for n in extract._iter_jsonld_nodes(html) if extract._node_type(n) == "realestatelisting"]
    assert len(nodes) == 1 and not nodes[0].get("offers"), "one unpriced node naming the whole category"
    assert extract.extract_items(html, "https://www.fotocasa.es/es/alquiler/viviendas/madrid-capital/todas-las-zonas/l") == []


@pytest.mark.parametrize("prefix", ["www-autoscout24-es", "www-motos-net"])
def test_a_page_whose_list_items_are_not_listings_declares_nothing(prefix):
    html, base = _page(prefix)
    assert extract.extract_items(html, base) == []


def test_a_single_priced_detail_page_still_keeps_its_own_listing():
    """The new furniture rule must not eat a true detail page: one node, a price, url = the page."""
    html = ('<script type="application/ld+json">{"@type":"Product","name":"AOC U27B3A","url":"https://shop/a/1",'
            '"offers":{"@type":"Offer","price":"152.99","priceCurrency":"EUR"}}</script>')
    items = extract.extract_items(html, "https://shop/a/1")
    assert len(items) == 1 and items[0]["price"] == 152.99
