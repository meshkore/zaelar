"""A page that LISTS candidates is a SOURCE, never a candidate (V2-782 T3.2) — golden over the recorded sheets.

The fixtures under `tests/search/fixtures/sheets/` are the results sheets the 2026-10-10 rounds actually wrote
(copied from the sandboxes, see the initiative §1). The rule is structural: a row without a datum of its own
whose title counts or ranks a category, or whose url is an article/policy page, is filed as a page with its
reason; a row with a price, a rating, its own phone or a fact stays. Both languages, from real rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from search import candidacy

SHEETS = Path(__file__).resolve().parents[1] / "fixtures" / "sheets"


def _items(name: str) -> list[dict]:
    path = next(SHEETS.glob(name + "*.json"))
    return json.loads(path.read_text(encoding="utf-8")).get("items") or []


def test_the_rental_car_rankings_leave_the_list_es():
    keep, pages = candidacy.split(_items("best-rated-rental-car__es"))
    titles = {p["title"] for p in pages}
    assert any(t.startswith("Las 10 mejores empresas") for t in titles)
    assert any(t.startswith("TOP 35 Compañías") for t in titles)
    assert all(p["why"] for p in pages)
    assert len(keep) == 2, [k["title"] for k in keep]


def test_the_insurer_policy_and_help_pages_leave_the_list_es():
    keep, pages = candidacy.split(_items("compare-insurance-quotes__es"))
    why = {p["title"]: p["why"] for p in pages}
    assert why["Política de Privacidad"].startswith("a policy")
    assert "Preguntas Frecuentes de Seguros…" in why
    assert any(k.get("price") == "156€" for k in keep), "a row with its own price stays"


def test_the_license_page_leaves_the_insurance_list_en():
    keep, pages = candidacy.split(_items("compare-insurance-quotes__en"))
    assert [p["title"] for p in pages] == ["License info"]
    assert len(keep) == 7


@pytest.mark.parametrize("sheet,n", [
    ("cheapest-monitor__es", 7), ("cheapest-monitor__en", 5), ("hotel-under-15-days__en__results--", 7),
    ("search-buy-used-car__es", 10), ("search-buy-used-car__en__results--", 3), ("search-buy-motorcycle__es", 8),
    ("best-plumber-same-day__en", 5), ("knows-who-i-am__en__results--", 3),
])
def test_real_candidates_with_a_datum_all_stay(sheet, n):
    """Every priced listing, rated hotel, phoned plumber and timed recipe the workers finally presented stays."""
    keep, pages = candidacy.split(_items(sheet))
    assert (len(keep), pages) == (n, [])


def test_a_shared_phone_is_the_switchboard_not_a_datum():
    rows = [{"title": "Coches y motos", "facts": [{"label": "Teléfono", "value": "65 111 88 88"}],
             "url": "https://x.es/seguros/coches"},
            {"title": "Hogar", "facts": [{"label": "Teléfono", "value": "65 111 88 88"}], "url": "https://x.es/seguros/hogar"},
            {"title": "Fontanería Rápida", "facts": [{"label": "Phone", "value": "600 000 000"}],
             "url": "https://maps.google.com/?cid=1"}]
    shared = candidacy._shared_phones(rows)
    assert shared and not candidacy._has_datum(rows[0], shared) and candidacy._has_datum(rows[2], shared)


def test_a_web_lead_whose_title_counts_the_category_is_a_ranking_even_with_a_price():
    row = {"title": "The 6 Best Budget Monitors for $279.99 – RTINGS", "price": "$279.99", "url": "https://rtings.com/monitor/reviews/best/budget",
           "facts": [{"label": "Origen", "value": "búsqueda web"}]}
    assert candidacy.why_a_page(row).startswith("a ranking article")
    assert candidacy.why_a_page({**row, "origin": "web", "facts": []}).startswith("a ranking article")


def test_pages_become_sources_and_the_worker_is_told():
    pages = [{"title": "Las 10 mejores empresas de alquiler", "url": "https://a/b", "why": "a ranking article"}]
    src = candidacy.as_sources(pages)
    assert src[0]["name"].startswith("Las 10") and "page, not a candidate" in src[0]["detail"]
    note = candidacy.note_for_worker(pages, kept=0)
    assert "NO candidate" in note and "Las 10 mejores" in note
    assert "Open them" in candidacy.note_for_worker(pages, kept=3)
    assert candidacy.note_for_worker([], 3) == ""


def test_the_sheet_doors_apply_the_rule(tmp_path, monkeypatch):
    """`present` and `append` file pages as sources and say so in their reply (both doors, one rule)."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.results import data as _d
    monkeypatch.setattr(_d, "_DATA_DIR", str(tmp_path / "results"), raising=False)
    sheet = "golden-" + tmp_path.name
    rows = [{"title": "TOP 35 Compañías Alquiler Coches", "url": "https://x/top", "facts": [{"label": "Origen", "value": "búsqueda web"}]},
            {"title": "Alurin CoreVision 27 4K", "price": "149,99 €", "url": "https://shop/a"}]
    out = _d.apply_action("present", {"sheet": sheet, "items": rows})
    assert out["ok"] and out["shown"] == 1
    assert out["not_candidates"][0]["title"].startswith("TOP 35")
    data = _d.view_data(sheet)
    assert [i["title"] for i in data["items"]] == ["Alurin CoreVision 27 4K"]
    assert any("TOP 35" in str(s.get("name")) for s in data.get("sources") or [])
    out2 = _d.apply_action("append", {"sheet": sheet, "items": [{"title": "Las 10 mejores pantallas", "url": "https://x/best/1",
                                                                 "facts": [{"label": "Origin", "value": "web search"}]}]})
    assert out2["ok"] and out2["shown"] == 1 and out2["not_candidates"]
