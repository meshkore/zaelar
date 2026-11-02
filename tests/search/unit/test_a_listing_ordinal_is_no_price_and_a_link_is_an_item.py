"""Real cars were thrown away twice at the sheet's door (node 12.836).

search-buy-used-car ES (V2-835, 2026-11-02):
  · the browser extracted AutoScout24's list — «Mercedes-Benz GLC 220», «€ 24.890», each on its own ad page — and the
    door kept the first and filed the rest as «the same product», because a row's identity was (title, price) and the
    link was never read: `landed 0`, four extractions in a row. A used car is one unit; another ad is another car.
  · a web search snippet numbers the portal's listings, «44. € 32.990 · 02/2019»; «44.» took the «€» of the price
    after it, the row was priced «44. €» and rejected as «below what a whole vehicle costs». The thousands were never
    lost: a list ordinal was read as an amount.
"""
from __future__ import annotations

from search import candidacy, row_dedupe, row_fit
from search import _rows_from_web

AS24 = "https://www.autoscout24.es/anuncios/mercedes-benz-glc-220-d-4matic-amg-line-diesel-gris-cat_ma47mo21086-"
CARS = [{"title": "Mercedes-Benz GLC 220", "price": "€ 24.890",
         "url": AS24 + ad + f"?sort=price&desc=0&position={i}&source=listpage_search-results"}
        for i, ad in enumerate(("62592f1b-96c4", "22497b81-a311", "5b68d80e-f580"), start=3)]


def test_two_ads_with_one_title_and_price_are_two_items():
    on, off = row_dedupe.split(list(CARS), [])
    assert len(on) == 3 and off == []


def test_the_same_ad_walked_again_is_still_one_row():
    again = {**CARS[0], "url": CARS[0]["url"].replace("position=3", "position=11")}
    on, off = row_dedupe.split([CARS[0], again], [])
    assert len(on) == 1 and "the same product" in off[0]["why"]
    on, off = row_dedupe.split([again], [], prior=[CARS[0]])
    assert on == [] and off


def test_a_mass_product_by_its_model_code_is_still_one_row():
    rows = [{"title": "LG 55QNED70B6C 55\" 4K", "price": "499 €", "url": "https://shop-a.example/lg"},
            {"title": "LG 55QNED70B6C QNED", "price": "529 €", "url": "https://shop-b.example/tv/lg"}]
    assert len(row_dedupe.split(rows, [])[0]) == 1


def test_the_whole_door_lands_the_measured_batch():
    on, off = row_fit.split(list(CARS), "Quiero compar un coche. HE visto este: " + CARS[0]["url"], [])
    assert len(on) == 3, [o["why"] for o in off]


def test_a_list_ordinal_is_no_amount():
    assert candidacy.lone_amount("847 ofertas para Mercedes-Benz GLC 220 4matic ; 44. € 32.990 · 02") == "€ 32.990"
    assert candidacy.lone_amount("1,203 cars ; 7. $14,500 · 2017 Toyota Prius") == "$14,500"
    for written in ("€ 7.999", "199,99 €", "$1,299.99", "USD 249", "249 USD", "£99", "€249", "17.690 €"):
        assert candidacy.lone_amount(written) == written


def test_the_measured_snippet_prices_the_row_with_its_real_amount():
    res = {"results": [{"title": "Mercedes-Benz GLC 220 4matic de segunda mano en venta",
                        "snippet": "847 ofertas para Mercedes-Benz GLC 220 4matic ; 44. € 32.990 · 02/2019",
                        "url": "https://www.autoscout24.es/lst/mercedes-benz/glc-220"}]}
    assert _rows_from_web(res)[0]["price"] == "€ 32.990"
