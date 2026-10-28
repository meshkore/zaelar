"""What he RULES OUT about one errand reaches that errand's sheet in HIS words, before the reply names rows (node 2.633).

hotel-under-15-days ES (2026-10-14, sandbox 023118-es). «Oye, que te pedí hoteles de 4 estrellas, no hostales ni
albergues» was relayed to the worker as «DESCARTAR todos los albergues, hostales y pensiones…» — a phrasing whose
negation no reader reads — so the exclusion never reached the door, and two turns later the reply presented «Hostel
Ikigai» and «Urban Cube Hostel Sevilla» from the sheet. `his_spec_to_sheet.carry` now carries his exclusions too —
only to a sheet that already holds his commissioning words, so «nada de CRT ni monitores viejos» cannot rule out the
monitors of a sheet that never heard «busco un monitor».
"""
from __future__ import annotations

import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import escalate
from nucleo.turn import his_spec_to_sheet as S
from nucleo.workers import ended
from widgets.results import data as sheet

SHEET = "t2633"
HOTEL = {"id": "2", "request": "Reservar hotel 4 estrellas en Sevilla para 2 personas del 21 al 25 de octubre",
         "phase": "", "waiting_on": "", "surface": "lista", "sheet": f"results::{SHEET}"}
ASK = "Sevilla, o cerca, lo que encuentres bien. Entramos el miércoles 21 de octubre y salimos el domingo 25."
CORRECTION = ("Oye, que te pedí hoteles de 4 estrellas, no hostales ni albergues. Esos no me sirven, porfa busca "
              "hoteles de 4 estrellas.")
ROWS = ["Hostel Trotamundos", "Arc House Sevilla Only Adults", "Nuevo Suizo", "Hostel Ikigai",
        "Urban Cube Hostel Sevilla", "AC Hotel Sevilla Fórum"]


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(HOTEL)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(escalate, "_tasks", {})
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", {})
    S.forget()


def _seed(asked: str) -> None:
    data = {"title": "Hoteles 4 estrellas en Sevilla", "items": [{"title": t, "price": "€ 231"} for t in ROWS]}
    if asked:
        data["asked"] = asked
    sheet.store.save(sheet.sheet_key(SHEET), data)


def _titles() -> list[str]:
    return [i["title"] for i in sheet.view_data(SHEET)["items"]]


def test_the_measured_correction_takes_every_hostel_off(live):
    _seed(ASK)
    assert S.carry(CORRECTION) == [f"results::{SHEET}"]
    assert _titles() == ["Arc House Sevilla Only Adults", "Nuevo Suizo", "AC Hotel Sevilla Fórum"]


def test_a_sheet_without_his_words_never_hears_an_exclusion(live):
    _seed("")
    S.carry(CORRECTION)
    assert _titles() == ROWS


def test_the_spec_reader_says_it_in_plain_form():
    assert S.spec_of("no hostales ni albergues", exclusions=True) == "no hostales · no albergues"
    assert S.spec_of("no hostales ni albergues") == ""
