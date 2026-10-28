"""The browser extraction's reply tells the worker which of its rows the sheet's door turned away, and why — and the
CLI prints it (node 2.663).

search-rent-apartment ES (2026-10-14, sandbox 093858-es): the worker extracted real Fotocasa flats three times; the
door filed every one in Rejected («does not name «ruzafa»») and the sheet held 0 items after 400 s. `intake.push`
returned a bare count and dropped the door's `note_for_worker`, so the worker read its listings back, believed they
were on his sheet, and kept browsing. Through the REAL bridge path (`navegador_act` extract → `_hand_over` →
`intake.push` → the door); only the tab is a double.
"""
from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stdout

import pytest

from nucleo.cli import nav as nav_cli
from widgets.navegador import act_api
from widgets.results import category_gate, data as sheet_data

SHEET = "boat02-ls1"
ASKED = "Búscame un catamarán Lagoon 440 de segunda mano por menos de 300.000 euros."
ON = {"title": "Lagoon 440 (2008) reacondicionado", "price": "269.000 €", "url": "https://www.boat24.com/es/d/717097/"}
OFF = {"title": "Bavaria 46 Cruiser en Alicante", "price": "120.000 €", "url": "https://www.boat24.com/es/d/700001/"}


class _Tab:
    page = None

    def __init__(self, rows):
        self.rows = rows

    async def ensure(self):
        return None

    async def extract_listings(self, limit):
        return list(self.rows)


@pytest.fixture
def sheet(monkeypatch):
    monkeypatch.setattr(act_api, "_emit_nav", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_say_phase", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_sheet_of", lambda task_id: SHEET)
    category_gate.hear(SHEET, ASKED)
    yield


def _extract(rows, monkeypatch, tid="nav7"):
    from widgets.navegador import owner
    monkeypatch.setitem(owner._task_browsers, tid, _Tab(rows))
    return asyncio.run(act_api.navegador_act(task_id=tid, action="extract", args={"limit": 14}))


def test_the_reply_names_the_row_the_door_turned_away(sheet, monkeypatch):
    res = _extract([ON, OFF], monkeypatch)
    titles = [i["title"] for i in sheet_data.view_data(SHEET).get("items") or []]
    assert ON["title"] in titles and OFF["title"] not in titles, titles
    door = res.get("door") or {}
    assert door.get("handed") == 2 and door.get("landed") == 1, door
    assert "Bavaria 46" in door.get("note", "") and "NOT on it" in door.get("note", ""), door
    out = io.StringIO()
    with redirect_stdout(out):
        nav_cli._print_state(res)
    assert "SHEET:" in out.getvalue() and "Bavaria 46" in out.getvalue(), out.getvalue()


def test_a_push_that_all_landed_adds_nothing_to_the_reply(sheet, monkeypatch):
    res = _extract([ON], monkeypatch, tid="nav8")
    assert "door" not in res, res
