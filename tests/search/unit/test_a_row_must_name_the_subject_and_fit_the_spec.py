"""A candidate names the SUBJECT he asked about and does not contradict a SPEC he stated (V2-782 T3.3).

find-concert-tickets ES (2026-10-11): a Rosalía ticket hunt offered «El Cascanueces» and «DJ Symphonic». cheapest-monitor
EN: a 24" non-4K monitor was the pick for a 27" 4K ask. Subjects and specs come from HIS words only — a sheet title the
model wrote in Titlecase («Monitor purchase for work») is never a subject.
"""
from __future__ import annotations

import json
from pathlib import Path

from search import asked, category

SHEETS = Path(__file__).resolve().parents[1] / "fixtures" / "sheets"


def test_rows_that_do_not_name_the_artist_leave():
    d = json.loads(next(SHEETS.glob("find-concert-tickets__es*offsubject.json")).read_text(encoding="utf-8"))
    on, off = category.split(d["items"], "Búscame entradas para un concierto de Rosalía en Madrid este mes", [d["title"]])
    gone = {o["title"] for o in off}
    assert {"El Cascanueces - Classic Stage", "DJ Symphonic"} <= gone
    assert all("rosalia" in (o["title"] + o["url"]).lower().replace("í", "i") for o in on)


def test_the_subject_is_his_proper_name_not_a_place_a_month_or_a_title():
    assert asked.subjects("Búscame entradas para un concierto de Rosalía en Madrid este mes") == ["rosalia"]
    assert asked.subjects("tickets for Bad Bunny in Miami in October") == ["bad bunny"]
    assert asked.subjects("Find me a used car, diesel or hybrid, under $14,000") == []
    assert asked.subjects("busco un SUV diésel con 4K de pantalla") == []


def test_a_title_the_model_wrote_is_never_a_subject():
    rows = [{"title": "Dell S2721 27\" monitor", "price": "€199"}]
    assert category.split(rows, "", ["Monitor purchase for work", "Best-Value 27\" Monitors"])[1] == []


def test_another_size_and_a_lower_resolution_contradict_the_spec():
    ask = "the cheapest well-rated 27\" 4K monitor"
    rows = [{"title": "PHILIPS 24E1N1300AM Monitor 24\" FHD", "price": "€119"},
            {"title": "LG 27U631A-B Monitor, 27\", QHD", "price": "€138"},
            {"title": "Philips 27E1N1800A 27\" Ultra HD 4K", "price": "€155"},
            {"title": "Samsung 27\" monitor", "price": "€150"}]
    on, off = category.split(rows, ask, [])
    assert [o["title"] for o in on] == ["Philips 27E1N1800A 27\" Ultra HD 4K", "Samsung 27\" monitor"]
    assert {o["title"]: o["why"] for o in off}["PHILIPS 24E1N1300AM Monitor 24\" FHD"].startswith("24\"")
