"""«Solo esa semana» moves ONE lesson, and the later skip finds the real Tuesday (agenda-everyday-edits ES). Node 2.586.

Measured (report 20261014-005211, steps 9-10): «El piano del martes que viene pásalo al miércoles, solo esa semana»
reached the agenda as `move_meeting {title, newDate: 2026-10-21}` with NO `date` — the manifest's «whole series» —
so every Tuesday became a Wednesday, and «el martes 27 de octubre no hay clase» then fell on a day the series no
longer had (a worker applied it to the 28th). He answered the one-or-all question himself; the occurrence gets its
`date` (the day his words name, else the series' next one), and the widget's dated move detaches that day only.
"""
from __future__ import annotations

import datetime as dt

import pytest

from nucleo.flash import agenda_said_day as SD
from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from widgets import store
    from nucleo.pulse import scheduler
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "create", lambda prompt, stamp, name="", origin="cron": {"ok": True, "id": "j"})
    monkeypatch.setattr(scheduler, "cancel", lambda ref: None)


TODAY = dt.date.today()


def _coming(wd: int) -> dt.date:
    return TODAY + dt.timedelta(days=(wd - TODAY.weekday()) % 7 or 7)


def _seed():
    agenda.apply_action("add_meeting", {"title": "Clase de piano de Abril", "date": _coming(1).isoformat(),
                                        "startTime": "17:00", "endTime": "18:00", "repeat": "weekly",
                                        "days": "martes", "until": (TODAY + dt.timedelta(days=90)).isoformat()})


def _series():
    return next(m for m in agenda.load_db()["meetings"] if isinstance(m.get("repeat"), dict))


def test_the_measured_move_gets_its_tuesday():
    tue, wed = _coming(1), _coming(1) + dt.timedelta(days=1)
    got = SD.payload("agenda", "move_meeting", {"title": "Clase de piano de Abril", "newDate": wed.isoformat()},
                     "El piano del martes que viene pásalo al miércoles, solo esa semana", today=TODAY)
    assert got["date"] == tue.isoformat()


def test_one_lesson_moves_and_the_series_keeps_its_tuesdays():
    _seed()
    tue, wed = _coming(1), _coming(1) + dt.timedelta(days=1)
    pl = SD.payload("agenda", "move_meeting", {"title": "Clase de piano de Abril", "newDate": wed.isoformat()},
                    "El piano del martes que viene pásalo al miércoles, solo esa semana", today=TODAY)
    assert agenda.apply_action("move_meeting", pl).get("ok") is not False
    s = _series()
    assert s["repeat"]["days"] == [1] and tue.isoformat() in s["repeat"]["skip"]
    assert any(m.get("date") == wed.isoformat() and not isinstance(m.get("repeat"), dict)
               for m in agenda.load_db()["meetings"])
    # …and «el martes 27 no hay clase» lands on a Tuesday the series still has
    nxt = (tue + dt.timedelta(weeks=1)).isoformat()
    assert agenda.apply_action("cancel_meeting", {"title": "Clase de piano de Abril", "date": nxt}).get("ok") is not False
    assert nxt in _series()["repeat"]["skip"]


def test_with_no_day_named_it_is_the_series_next_lesson():
    _seed()
    got = SD.payload("agenda", "move_meeting", {"title": "Clase de piano de Abril", "newTime": "18:00"},
                     "el piano de esta semana pásalo a las seis, solo esta vez", today=TODAY)
    from widgets.agenda import recur
    assert got["date"] == recur.next_occurrence(_series(), TODAY.isoformat()) != ""


def test_english_just_that_week():
    got = SD.payload("agenda", "move_meeting", {"title": "piano", "newDate": "2026-10-21"},
                     "Move next Tuesday's piano to Wednesday, just that week", today=dt.date(2026, 10, 14))
    assert got["date"] == "2026-10-20"


def test_without_the_scope_the_whole_series_moves_as_declared():
    for said in ("pasa el piano al miércoles", "el piano ahora es los miércoles, todas las semanas"):
        got = SD.payload("agenda", "move_meeting", {"title": "piano", "newDate": "2026-10-21"}, said,
                         today=dt.date(2026, 10, 14))
        assert "date" not in got, said


def test_a_dated_or_whole_move_is_left_as_it_came():
    pl = {"title": "piano", "newDate": "2026-10-21", "date": "2026-10-27"}
    assert SD.payload("agenda", "move_meeting", pl, "solo esa semana", today=dt.date(2026, 10, 14)) == pl
    pl = {"title": "piano", "newDate": "2026-10-21", "whole": True}
    assert SD.payload("agenda", "move_meeting", pl, "solo esa semana", today=dt.date(2026, 10, 14)) == pl
