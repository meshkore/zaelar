"""Each HARD requirement of his is a column every row carries — yes · no · «?» — through every door of the sheet.

rental-car-automatic-airport (2026-10-11, ES+EN 2/5): «automático, recogida y devolución en el aeropuerto» repeated
three and four times; sixteen navigations, twelve rows of `title + price`, and not one row saying whether it was
automatic. `widgets/results/hard_checks.py` stamps one fact per `criteria.hard` on every row (value «?»), tells the
worker how many are still open, and lets a row sent again carry what was verified.
"""
from __future__ import annotations

import pytest

from widgets.results import data as D
from widgets.results import hard_checks as H

SHEET = "hardcol-1"
HARD = ["cambio automático", "recogida y devolución en el aeropuerto de Málaga"]
ROWS = [{"title": "Volkswagen Polo o similar", "price": "93 €", "url": "https://example.test/polo"},
        {"title": "Fiat Panda o similar", "price": "90 €", "url": "https://example.test/panda"}]


def _facts(title):
    item = next(i for i in D.view_data(SHEET)["items"] if i["title"] == title)
    return {f["label"]: f["value"] for f in item.get("facts") or []}


@pytest.fixture
def sheet():
    D.apply_action("clear", {"sheet": SHEET})
    yield
    D.apply_action("clear", {"sheet": SHEET})


def test_rows_already_on_the_sheet_get_the_column_when_the_requirement_is_declared(sheet):
    D.apply_action("append", {"sheet": SHEET, "items": ROWS})
    res = D.apply_action("criteria", {"sheet": SHEET, "hard": HARD})
    assert res["ok"] and res.get("hard_unverified") == 4
    assert _facts("Volkswagen Polo o similar") == {HARD[0]: "?", HARD[1]: "?"}


def test_a_row_arriving_later_gets_it_and_the_worker_is_told_what_is_open(sheet):
    D.apply_action("criteria", {"sheet": SHEET, "hard": HARD})
    res = D.apply_action("append", {"sheet": SHEET, "items": ROWS})
    assert res.get("hard_unverified") == 4
    assert "«cambio automático»" in res.get("note_for_worker", "")
    assert _facts("Fiat Panda o similar")[HARD[0]] == "?"


def test_a_row_sent_again_carries_what_was_verified_and_a_question_mark_never_undoes_it(sheet):
    D.apply_action("criteria", {"sheet": SHEET, "hard": HARD})
    D.apply_action("append", {"sheet": SHEET, "items": ROWS})
    polo = dict(ROWS[0], facts={HARD[0]: "sí — ficha de rentalcars, «Automático»"})
    res = D.apply_action("append", {"sheet": SHEET, "items": [polo]})
    assert _facts("Volkswagen Polo o similar")[HARD[0]].startswith("sí")
    assert res.get("hard_unverified") == 3
    D.apply_action("append", {"sheet": SHEET, "items": [dict(ROWS[0], facts={HARD[0]: "?"})]})
    assert _facts("Volkswagen Polo o similar")[HARD[0]].startswith("sí")


def test_a_fact_the_worker_already_wrote_under_its_own_label_is_the_column():
    item = {"title": "Jeep Compass", "facts": [{"label": "Transmission", "value": "Automatic (not confirmed)"}]}
    data = {"criteria": {"hard": ["automatic transmission"]}, "items": [item]}
    assert H.stamp(data) == 1, "a value that does not commit is still open"
    assert [f["label"] for f in item["facts"]] == ["Transmission"], "no second column for the same requirement"


@pytest.mark.parametrize("value,verdict", [
    ("yes — Hertz listing, «Automatic»", H.YES), ("sí (ficha de DoYouSpain)", H.YES), ("no — manual on the deal", H.NO),
    ("?", H.UNVERIFIED), ("Automatic (US standard — not confirmed on the deal page)", H.UNVERIFIED), ("", H.UNVERIFIED)])
def test_only_a_value_that_opens_with_yes_or_no_commits(value, verdict):
    assert H.status(value)[0] == verdict


def test_without_hard_requirements_nothing_is_stamped(sheet):
    res = D.apply_action("append", {"sheet": SHEET, "items": ROWS})
    assert "hard_unverified" not in res
    assert not D.view_data(SHEET)["items"][0].get("facts")


def test_a_list_errand_worker_is_told_to_declare_them():
    from nucleo.workers.prompts.surfaces import trusted_blocks
    assert H.worker_block() in trusted_blocks("lista")
    assert H.worker_block() not in trusted_blocks("informe")
