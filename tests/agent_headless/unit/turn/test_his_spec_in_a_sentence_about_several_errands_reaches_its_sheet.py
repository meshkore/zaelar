"""His spec inside a sentence about SEVERAL errands still reaches the right errand's sheet (node 2.646).

three-tasks-at-once (EN, 2026-10-14): the monitor's refinements kept arriving glued to the game's and the report's —
«ok cool, add coins to the game too. and the monitor—any 27 inch ones under $150 yet?», «ping me when the game's
ready… for the monitor… make sure it's got hdmi». `his_spec_to_sheet.carry` left every sentence that named two
errands alone (so «el informe hasta 30.000 y el monitor hasta 150» could not give the monitor a €30,000 ceiling), and
with it the clause that WAS the monitor's. It now reads the same per-errand cut as the routing
(`split_by_errand.parts`): a clause that names one errand carries to that errand's sheet; one naming two is nobody's.
"""
from __future__ import annotations

import time
import types

import pytest

from nucleo import dispatch
from nucleo import dispatch_confirm as dc
from nucleo.flash import escalate
from nucleo.turn import errands_of_a_turn as E, his_spec_to_sheet as S
from nucleo.workers import ended
from widgets.results import data as sheet

SHEET = "t2646"
MONITOR = {"id": "3", "request": E.listing_errand({"query": "used monitor cheap"}), "phase": "", "waiting_on": "",
           "surface": "lista", "sheet": f"results::{SHEET}"}
GAME = {"id": "6", "request": "Build a small platform game widget, Super Mario style: run and jump", "phase": "",
        "waiting_on": "", "surface": "", "sheet": ""}
REPORT = {"id": "1", "request": "Prepare a report on electric cars for city driving", "phase": "", "waiting_on": "",
          "surface": "informe", "sheet": ""}
ROWS = ['MONITOR PC ORDENADOR 19" MARCA', 'Yeyian IPF27 27" FHD 180Hz', 'AOC 24G2 24" IPS']


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [dict(GAME), dict(MONITOR), dict(REPORT)])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: types.SimpleNamespace(label="", title=""))
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(escalate, "_tasks", {})
    monkeypatch.setattr(ended, "_ENDED_SESSIONS", {})
    sheet.store.save(sheet.sheet_key(SHEET), {"title": "Monitors", "items": [{"title": t, "price": "50 €"} for t in ROWS]})
    S.forget()
    yield
    S.forget()


def _titles() -> list[str]:
    return [i["title"] for i in sheet.view_data(SHEET)["items"]]


def test_the_monitors_clause_reaches_its_sheet_beside_the_games(live):
    said = "ok, make the jump higher in the game, and for the monitor at least 27 inches please"
    assert S.carry(said) == [f"results::{SHEET}"]
    assert _titles() == ['Yeyian IPF27 27" FHD 180Hz'], _titles()


def test_a_clause_naming_two_errands_is_nobodys(live):
    said = "the report under 30000 and the monitor under 150 too"
    assert S.carry(said) == [] and _titles() == ROWS
