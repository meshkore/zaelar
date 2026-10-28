"""The sheet's subject is a DATUM the errand's brief declares, never the capitals of a sentence (node 12.13).

Audit V2-783 P0-1 (2026-10-16): the door read every Title-case run of `asked` as a subject every row must name.
Lowercase input — the demo driver types «solo entradas de rosalía», STT writes names lowercase too — gave no subject
and the door filtered nothing; a capital that was not a subject («ow, thanks Drop the touristy…», a hotel named in a
DESCARTAR list) became one and rejected 16 of 20 real rows. The research brief (one model call the slow path already
pays) now declares `subjects`; the seeded criteria carry them to the sheet, and the door reads those — kept only
where his own words name them, so the brief cannot add a subject he never said. No declared list: the old reading.
"""
from __future__ import annotations

from nucleo.workers import brief as research
from search import category
from widgets.results import category_gate
from widgets.results import data as sheet_mod

_LG = {"title": "LG 27UL500-W 27\" monitor", "price": "149 €", "url": "https://x/lg"}
_AOC = {"title": "AOC 27B2H 27\" IPS", "price": "99 €", "url": "https://x/a"}
_ROSALIA = {"title": "Rosalía — Motomami Tour, WiZink Center", "price": "80 €", "url": "https://x/r"}
_OTHER = {"title": "El Cascanueces — Teatro Real", "price": "40 €", "url": "https://x/c"}


def test_a_lowercase_ask_has_its_declared_subject():
    on, off = category.split([_ROSALIA, _OTHER], "solo entradas de rosalía en madrid", (), ["Rosalía"])
    assert on == [_ROSALIA] and off and "does not name" in off[0]["why"]


def test_a_declared_subject_he_never_said_is_dropped():
    on, off = category.split([_ROSALIA, _OTHER], "entradas para un concierto en madrid", (), ["Rosalía"])
    assert len(on) == 2 and not off


def test_a_declared_empty_list_overrides_a_stray_capital():
    asked = "ow, thanks Drop the touristy ones and keep the concerts"
    assert category.asked_from(asked)["subjects"], "the capitals reading still sees «Drop» — the case this closes"
    assert category.asked_from(asked, (), [])["subjects"] == []


def test_no_declared_list_keeps_the_capitals_reading():
    assert category.asked_from("un monitor Samsung o LG de 27 pulgadas")["subjects"] == ["samsung", "lg"]


def test_the_brief_carries_its_subjects_to_the_sheet_door():
    brief = research.parse('{"research": true, "goal": "Find tickets for a Rosalía concert in Madrid", '
                           '"hard": ["Madrid"], "subjects": ["Rosalía"]}', "solo entradas de rosalía")
    crit = research.to_criteria(brief)
    assert crit["subjects"] == ["Rosalía"]
    sheet = "results--t-subj-1"
    sheet_mod.apply_action("criteria", {"sheet": sheet, "criteria": crit})
    category_gate.hear(sheet, "solo entradas de rosalía en madrid")
    sheet_mod.apply_action("present", {"sheet": sheet, "items": [_ROSALIA, _OTHER]})
    view = sheet_mod.view_data(sheet)
    assert [i["title"][:20] for i in view["items"]] == [_ROSALIA["title"][:20]]
    assert any("Cascanueces" in r.get("title", "") for r in view.get("rejected") or [])


def test_a_brief_without_the_field_declares_nothing():
    brief = research.parse('{"research": true, "goal": "Find a monitor"}', "un monitor")
    assert "subjects" not in research.to_criteria(brief)
    assert category_gate._declared({"criteria": {"goal": "x"}}, {}) is None
