"""A page is read from what it CARRIES, not only from what it declares (V2-846).

Measured 2026-11-04: AutoScout24 ships its ads in `__NEXT_DATA__`, coches.net and milanuncios in an escaped
`JSON.parse("…")` state; none declares JSON-LD, so the old extractor found zero ads on every one. These pages are
recorded (four ads each, trimmed) next to the decoys that fooled the first finder: a tag cloud of brand links, a list
of province links, an array of filters. The finder picks the ads by the SHAPE of the values; the field map comes from
the values when they say enough, and from a model answer kept per site when they do not (here a recorded answer).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scrape
from scrape import hooks, mapping, state, validate

FIX = Path(__file__).resolve().parents[1] / "fixtures"
PAGES = {
    "autoscout": ("autoscout24_next_data.html", "https://www.autoscout24.es/lst/mercedes-benz/c-220?atype=C"),
    "cochesnet": ("cochesnet_escaped_state.html", "https://www.coches.net/segunda-mano/?fi=Diesel"),
    "milanuncios": ("milanuncios_escaped_state.html", "https://www.milanuncios.com/anuncios/?s=bicicleta"),
}
#: What the model answered for each site on 2026-11-04 (`mapping.INSTRUCTIONS`), recorded.
MODEL_MAPS = {
    "autoscout24": {"title": "title", "url": "url", "price": "price.priceRaw", "currency": "EUR", "image": "images.0",
                    "details": ["vehicle.mileageInKm", "vehicle.fuel", "tracking.firstRegistration", "location.city"]},
    "coches": {"title": "title", "url": "url", "price": "price", "currency": "EUR", "image": "img",
               "details": ["km", "year", "fuelType", "location.cityLiteral"]},
    "milanuncios": {"title": "title", "url": "url", "price": "price.cashPrice.value", "currency": "EUR",
                    "image": "images.0", "details": ["location.city.name", "location.province.name"]},
}


def _page(name):
    f, url = PAGES[name]
    return (FIX / f).read_text(encoding="utf-8"), url


@pytest.fixture(autouse=True)
def fresh_store():
    """Each test starts with no kept map: a map kept by one test must not answer for the next."""
    mapping._store().unlink(missing_ok=True)
    yield
    mapping._store().unlink(missing_ok=True)


@pytest.fixture
def model(monkeypatch):
    """The recorded model answer for the site whose sample it is shown (told apart by a key only that site has)."""
    asked = []

    def answer(system, sample):
        asked.append(sample)
        site = "autoscout24" if "priceRaw" in sample else "milanuncios" if "cashPrice" in sample else "coches"
        return json.dumps(MODEL_MAPS[site])
    monkeypatch.setattr(hooks, "model", answer)
    return asked


@pytest.mark.parametrize("name, n", [("autoscout", 4), ("cochesnet", 4), ("milanuncios", 4)])
def test_the_ads_are_found_by_the_shape_of_their_values_not_the_decoys(name, n):
    html, _url = _page(name)
    path, items = state.listings(html)
    assert len(items) == n, path
    assert "tag" not in path and "Search" not in path and "filters" not in path, f"a decoy was taken: {path}"


def test_every_json_a_script_carries_is_decoded_including_an_escaped_json_parse():
    html, _ = _page("cochesnet")
    blobs = state.blobs(html)
    assert any(isinstance(b, dict) and "initialResults" in b for b in blobs)


def test_an_id_is_not_a_title_and_a_name_is():
    assert not state.is_text("90f40070-d136-44c4-acd2-684cfdcad078")
    assert not state.is_text("/anuncios/mercedes-benz-c-220")
    assert state.is_text("Mercedes-Benz C 220") and state.is_text("Se vende bicicleta de montaña")


def test_values_alone_read_autoscout_and_the_model_adds_what_compares_them(model):
    html, url = _page("autoscout")
    records, how = scrape.records_of(html, url)
    assert how == "state/model" and len(records) == 3, "four ads, two of them the same car (title and price): three"
    r = records[0]
    assert r["title"].startswith("Mercedes-Benz") and r["price"] and r["url"].startswith("https://www.autoscout24.es/")
    assert r["attributes"], "the figures that compare cars (km, year, fuel) come with every ad"


def test_a_bare_number_price_is_read_through_the_kept_map(model):
    html, url = _page("cochesnet")
    records, how = scrape.records_of(html, url)
    assert how.startswith("state/") and len(records) == 4
    assert all(isinstance(r["price"], float) and r["price"] > 0 for r in records)
    assert all(r["url"].startswith("https://www.coches.net/") for r in records), "a picture host is never the link"


def test_the_map_is_asked_once_per_site_and_kept(model):
    html, url = _page("milanuncios")
    first, how1 = scrape.records_of(html, url)
    second, how2 = scrape.records_of(html, url)
    assert (how1, how2) == ("state/model", "state/kept") and first == second
    assert len(model) == 1, "the model is asked once for a site, then the kept map is read"


def test_without_a_model_the_values_still_pick_each_ads_own_title_and_link(monkeypatch):
    """The category and its link repeat across the ads; the title and the ad's link differ — so the values choose
    them, never the first text met (the first finder took «Bicicletas de montaña» for every title)."""
    monkeypatch.setattr(hooks, "model", None)
    html, url = _page("milanuncios")
    records, how = scrape.records_of(html, url)
    assert how == "state/shape" and len(records) == 4
    assert len({r["title"] for r in records}) == 4 and len({r["url"] for r in records}) == 4
    assert all(r["price"] is None for r in records), "a bare number is not taken for the price without a map"


def test_the_validator_wants_distinct_links_on_the_pages_own_site():
    page = "https://www.coches.net/segunda-mano/"
    good = {"title": "FORD Ka Urban", "url": "https://www.coches.net/ford-ka-1.aspx", "price": 4990.0}
    assert validate.ok(good, page)
    assert not validate.ok({**good, "url": "https://a.ccdn.es/cnet/vehicles/1.jpg/"}, page), "another site"
    assert not validate.ok({**good, "price": -1}, page)
    same = [{**good, "title": f"Ad {i}"} for i in range(5)]
    assert validate.keep(same, page)[1] is False, "five ads with one link is one category page"
    assert validate.site_of("https://www.autoscout24.es/x") == "autoscout24.es"
    assert validate.site_of("https://shop.example.co.uk/x") == "example.co.uk"


def test_a_page_that_declares_its_listings_is_read_from_the_declaration_first():
    html = "".join(f'<script type="application/ld+json">{{"@type":"Product","name":"Boat {i}","url":"/b/{i}",'
                   f'"offers":{{"price":{200000 + i},"priceCurrency":"EUR"}}}}</script>' for i in range(3))
    records, how = scrape.records_of(html, "https://boats.example.com/search")
    assert how == "declared" and len(records) == 3


def test_the_mapping_store_is_data_paths_only(model):
    html, url = _page("milanuncios")
    scrape.records_of(html, url)
    kept = mapping._load()
    assert kept and all(isinstance(v, (str, list)) for m in kept.values() for v in m.values())


def _rentals_page(declared: int, carried: int) -> str:
    """A rentals page that DECLARES a few of its listings and CARRIES all of them in its state (Zillow's shape)."""
    import json as _json
    ld = "".join(f'<script type="application/ld+json">{{"@type":"Product","name":"Flat {i} Main St, Austin",'
                 f'"url":"/homes/{i}","offers":{{"price":{1300 + i},"priceCurrency":"USD"}}}}</script>'
                 for i in range(declared))
    state_ = {"props": {"pageProps": {"results": [
        {"address": f"{i} Main St, Austin, TX", "detailUrl": f"/homes/{i}/", "price": f"${1300 + i:,}/mo",
         "beds": 2, "baths": 1, "area": 900 + i, "photo": f"https://photos.example-cdn.com/{i}.jpg",
         "status": "For rent", "zip": "78701"} for i in range(carried)]}}}
    return ld + f'<script id="__NEXT_DATA__" type="application/json">{_json.dumps(state_)}</script>'


def test_the_rung_with_more_valid_records_wins_not_the_first_that_passes(monkeypatch):
    """Zillow, 2026-11-04: 2 of its 41 rentals declared in JSON-LD, all 41 in its state — the sheet got 2."""
    monkeypatch.setattr(hooks, "model", None)
    records, how = scrape.records_of(_rentals_page(2, 8), "https://www.zillow.com/austin-tx/rentals/")
    assert how.startswith("state/") and len(records) == 8
    records, how = scrape.records_of(_rentals_page(3, 0), "https://www.zillow.com/austin-tx/rentals/")
    assert how == "declared" and len(records) == 3


def test_a_title_no_single_field_holds_is_composed_from_the_kept_paths():
    """A flat has no name: its type, its street, its area (fotocasa, 2026-11-04)."""
    items = [{"type": "Flat", "street": f"Gran Via {i}", "city": "Valencia", "link": f"/piso/{i}"} for i in range(3)]
    recs = state.records(items, {"title": ["type", "street", "city"], "url": "link"}, "https://www.fotocasa.es/x")
    assert [r["title"] for r in recs][0] == "Flat · Gran Via 0 · Valencia"
