"""A criteria change is the turn's paraphrase: its capitalised names are never subjects (search-buy-used-car EN, 2026-10-14).

«ubicación: Bay Area, hasta una hora de coche» sat in the sheet's criteria changes and the gate read «Bay Area» as a
subject every row must name: 55 real cars («2014 Ford Focus SE Hatchback», «2015 Toyota Prius 1»…) were rejected for
«does not name «bay area»». A spec in a change («27 al menos») still counts.
"""
from widgets.results import category_gate


def _sheet(change: str) -> dict:
    return {"asked": "Find me a used car, diesel or hybrid, under 60k miles and under $14,000, and give me the top 3.",
            "criteria": {"changes": [change]}, "items": []}


def test_a_place_in_a_change_rejects_no_car():
    data = _sheet("ubicación: Bay Area, hasta una hora de coche (radio ~1 h desde la zona de la bahía de San Francisco)")
    rows = [{"title": "2014 Ford Focus SE Hatchback", "price": "$11,998", "url": "https://example.com/a"},
            {"title": "2015 Toyota Prius 1", "price": "$12,500", "url": "https://example.com/b"}]
    on, _ = category_gate.gate(data, rows, {})
    assert [r["title"] for r in on] == ["2014 Ford Focus SE Hatchback", "2015 Toyota Prius 1"]


def test_a_spec_in_a_change_still_counts():
    data = {"asked": "Busco un monitor barato y bien valorado", "criteria": {"changes": ["27 al menos"]}, "items": []}
    rows = [{"title": "Monitor LG 24\" FHD", "price": "99 €", "url": "https://example.com/c"},
            {"title": "Monitor AOC 27\" 4K", "price": "199 €", "url": "https://example.com/d"}]
    on, _ = category_gate.gate(data, rows, {})
    assert [r["title"] for r in on] == ["Monitor AOC 27\" 4K"]
