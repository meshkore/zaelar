"""A correction of a results sheet is acknowledged with what changed, never a bare «Hecho.» (node 2.634).

find-concert-tickets ES (2026-10-14, sandbox 021207-es). «perdona, esos no son de Rosalía. Quiero entradas para un
concierto de Rosalía en Madrid este mes» — the model's words were dropped for the repaired `results:criteria`, the
sheet's door moved twelve rows to the Rejected tab, and the text channel said «Hecho.». «vale, dale, pero que sea
Rosalía porfa…» got the same. The op's answer carries `off_category`; the line says how many left and that what does
not fit stays out (`nucleo/flash/correction_ack.py`).
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs
from nucleo.flash import correction_ack

HEARD = "perdona, esos no son de Rosalía. Quiero entradas para un concierto de Rosalía en Madrid este mes."
_CRIT = {"executed": "widget_data", "widget": "results", "act": "criteria",
         "ops": [{"widget": "results", "act": "criteria"}],
         "answers": [("results", {"criteria": {"changes": ["solo entradas de Rosalía"]}, "reset": False,
                                  "off_category": 12})]}


@pytest.fixture(params=["es", "en"])
def lang(request, monkeypatch):
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec(request.param))
    return request.param


def test_the_measured_correction_names_how_many_left(lang):
    out = correction_ack.line(_CRIT)
    assert "12" in out and out != langs.spec(lang).data_ack, out


def test_one_row_and_none_are_said_as_such(lang):
    one = {**_CRIT, "answers": [("results", {"criteria": {}, "off_category": 1})]}
    none = {**_CRIT, "answers": [("results", {"criteria": {}})]}
    assert correction_ack.line(one) == langs.spec(lang).correction_dropped_one
    assert correction_ack.line(none) == langs.spec(lang).correction_noted


def test_another_op_or_a_failure_gets_no_correction_line():
    other = {"executed": "widget_data", "widget": "results", "act": "progress",
             "ops": [{"widget": "results", "act": "progress"}], "answers": []}
    assert correction_ack.line(other) == ""
    assert correction_ack.line({**_CRIT, "fallidas": [{"widget": "results", "act": "criteria"}]}) == ""
    assert correction_ack.line(None) == ""


def test_the_real_criteria_op_answers_what_the_line_reads(monkeypatch):
    from nucleo.flash import data_ops
    from widgets.results import data as sheet
    from widgets.server_api import brain_action
    monkeypatch.setattr(langs, "current_language", lambda: langs.spec("es"))
    # rows written before any of his words reached the sheet: nothing was judged at the door
    sheet.store.save(sheet.sheet_key("t2634"), {"title": "Rosalía en Madrid", "items": [
        {"title": "Miguel Lago", "price": "19 €"}, {"title": "Rosalía LUX Tour", "price": "65 €"}]})
    res = asyncio.run(brain_action("results", "criteria", {"q": "t2634", "changes": ["solo entradas de Rosalía"]}))
    parte = {"executed": "widget_data", "ops": [{"widget": "results", "act": "criteria"}],
             "answers": [("results", data_ops.answer_of(res))]}
    assert correction_ack.line(parte) == langs.spec("es").correction_dropped_one, res
    assert [i["title"] for i in sheet.view_data("t2634")["items"]] == ["Rosalía LUX Tour"]
