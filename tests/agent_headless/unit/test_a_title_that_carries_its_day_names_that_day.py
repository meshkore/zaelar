"""A reference that carries its DAY («Piano de Abril del martes 2026-10-13») names that occurrence (V2-781).

Measured in `agenda-everyday-edits__es` (2026-10-10): «el piano del martes que viene pásalo al miércoles, solo esa
semana» → move_meeting {title: "Piano - Abril del martes 2026-10-13", newDate: …} with no `date` — the whole SERIES
moved to Wednesdays, and «Hecho.»; «el martes 20 de octubre no hay clase de piano» → cancel_meeting {title: "Piano -
Abril del martes 20 de octubre de 2026"} matched nothing («No he entendido cuál quitar»). The model put the day in
the title; the agenda reads it out of there.
"""
from __future__ import annotations

import datetime as dt

from tests.agent_headless.unit.test_the_everyday_agenda_edits import TUE, _isolated, _piano  # noqa: F401
from widgets.agenda import data as agenda


def _days():
    return sorted(m["date"] for m in agenda.view_data()["meetings"] if m["title"] == "Piano de Abril")


def test_a_move_whose_title_carries_an_iso_day_moves_only_that_day():
    _piano()
    wk2 = TUE + dt.timedelta(weeks=1)
    agenda.apply_action("move_meeting", {"title": f"Piano de Abril del martes {wk2.isoformat()}",
                                         "newDate": (wk2 + dt.timedelta(days=1)).isoformat()})
    days = _days()
    assert wk2.isoformat() not in days and (wk2 + dt.timedelta(days=1)).isoformat() in days
    assert (TUE + dt.timedelta(weeks=3)).isoformat() in days, "the rest of the series stays on Tuesdays"


def test_a_cancel_whose_title_carries_a_named_day_finds_the_appointment():
    _piano()
    wk3 = TUE + dt.timedelta(weeks=2)
    months = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
              "noviembre", "diciembre"]
    said = f"Piano de Abril del martes {wk3.day} de {months[wk3.month - 1]} de {wk3.year}"
    res = agenda.apply_action("cancel_meeting", {"title": said, "date": wk3.isoformat()})
    assert res.get("ok") is not False, res
    assert wk3.isoformat() not in _days() and (TUE + dt.timedelta(weeks=3)).isoformat() in _days()
