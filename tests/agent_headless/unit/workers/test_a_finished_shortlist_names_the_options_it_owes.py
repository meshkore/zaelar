"""A finished shortlist names the options it owes, by name (V2-782).

search-buy-used-car EN (2026-10-11): «just send me the top 3» → «Your top three are on screen. Best pick is the 2018 Ford
Fusion Hybrid…» (one of three). cheapest-monitor EN: 44 candidates on the sheet, one monitor named. The notice is
completed from the errand's sheet: the number he asked for, or three when the sheet is a comparison.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.workers import named_top
from widgets.results import data as sheet

CARS = [{"title": "2018 Ford Fusion Hybrid S", "price": "$13,397"}, {"title": "2018 Hyundai IONIQ Plug-In", "price": "$13,495"},
        {"title": "2013 Ford C-Max Hybrid SE", "price": "$10,417"}, {"title": "2014 Volkswagen Golf TDI", "price": "$12,500"}]
LINE = ("Your top three are on screen. Best pick is the 2018 Ford Fusion Hybrid in Orlando, thirteen thousand three "
        "hundred ninety-seven dollars with under twenty-seven thousand miles.")


@pytest.fixture(autouse=True)
def _english(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    sheet.store.save(sheet.sheet_key("t2516"), {"title": "Used cars", "items": CARS})


def _rec(goal: str, injects=()):
    return SimpleNamespace(sheet="t2516", goal=goal, injects=[SimpleNamespace(text=t) for t in injects])


def test_the_top_three_he_asked_for_are_all_named():
    out = named_top.complete(LINE, _rec("Find me a used car, diesel or hybrid, and give me the top 3."))
    assert out.startswith(LINE)
    for car in ("2018 Ford Fusion Hybrid S — $13,397", "2018 Hyundai IONIQ Plug-In — $13,495", "2013 Ford C-Max Hybrid SE"):
        assert car in out
    assert "Golf" not in out


def test_a_number_said_in_a_correction_counts():
    out = named_top.complete(LINE, _rec("find me a used hybrid", ["just send me the top 2 once you have real listings"]))
    assert "The 2 options:" in out and "IONIQ" in out and "C-Max" not in out


def test_a_comparison_with_no_number_still_names_three():
    out = named_top.complete("The best value is the 2018 Ford Fusion Hybrid.", _rec("find me something decent"))
    assert "The 3 options:" in out


def test_a_line_that_already_names_them_is_untouched():
    said = "Top three: the 2018 Ford Fusion Hybrid, the 2018 Hyundai IONIQ and the 2013 Ford C-Max."
    assert named_top.complete(said, _rec("give me the top 3")) == said


def test_a_sheet_with_one_row_owes_nothing():
    sheet.store.save(sheet.sheet_key("t2516"), {"title": "x", "items": CARS[:1]})
    assert named_top.complete(LINE, _rec("give me the top 3")) == LINE


def test_the_delivery_rail_completes_the_spoken_line(monkeypatch):
    from nucleo.workers import session, spoken_delivery
    from voice import proactive
    said = []

    async def _notify(title, text, **kw):
        said.append(text)
        return False

    async def _line(*a, **k):
        return LINE

    monkeypatch.setattr(proactive, "notify", _notify)
    monkeypatch.setattr(spoken_delivery, "line", _line)
    rec = SimpleNamespace(task_id="t2516", result_summary="Top 3 delivered.", ok=False, goal="give me the top 3",
                          kind="research", verdict="", sheet="t2516", injects=[])
    asyncio.run(session._deliver(rec))
    assert said and "IONIQ" in said[0] and "C-Max" in said[0]
