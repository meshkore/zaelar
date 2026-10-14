"""«Get rid of the piano completely, the whole series» leaves no day of it behind (agenda-everyday-edits EN, 2026-10-14).

Sandbox 20261014-121305-en: a day was detached from the series (`fromSeries` = the series' first day), then an
undated move shifted the series' first day, the link broke, and the whole-series cancel deleted the series and left
the detached Wednesday standing — answered «Done.». A detached day of the one series the call names is that
series' day whatever its first day became; and if a day of it is still in the calendar after «the whole series»,
the action says so instead of succeeding.

Store isolated by the root conftest; the scheduler and Google replaced by recorders (the same fixture as
`test_the_everyday_agenda_edits.py`).
"""
from __future__ import annotations

import datetime as dt

from tests.agent_headless.unit.test_the_everyday_agenda_edits import _isolated, _next  # noqa: F401
from widgets.agenda import data as agenda, series_days

TUE = _next(1)


def _piano_with_a_moved_day_and_a_moved_series():
    agenda.apply_action("add_meeting", {"title": "Abril's piano lesson", "date": TUE.isoformat(),
                                        "startTime": "17:00", "endTime": "18:00", "repeat": "weekly",
                                        "until": (TUE + dt.timedelta(weeks=12)).isoformat()})
    wed = (TUE + dt.timedelta(days=1)).isoformat()
    agenda.apply_action("move_meeting", {"title": "Abril's piano lesson", "date": TUE.isoformat(), "newDate": wed})
    agenda.apply_action("move_meeting", {"title": "Abril's piano lesson", "newDate": wed})   # the undated re-send
    rows = agenda.load_db()["meetings"]
    ser = next(m for m in rows if isinstance(m.get("repeat"), dict))
    one = next(m for m in rows if m.get("fromSeries"))
    assert one["fromSeries"] != ser["date"], "the scene needs the broken link it reproduces"


def _piano_rows():
    return [m for m in agenda.load_db()["meetings"] if "piano" in m["title"].lower()]


def test_the_whole_series_takes_a_day_whose_first_day_link_went_stale():
    _piano_with_a_moved_day_and_a_moved_series()
    res = agenda.apply_action("cancel_meeting", {"title": "Abril's piano lesson", "whole": True})
    assert res.get("ok") is not False, res
    assert not _piano_rows()


def test_a_day_left_behind_is_a_failure_he_hears(monkeypatch):
    """The claim is checked against the calendar: a link the matcher misses still cannot pass as «done»."""
    _piano_with_a_moved_day_and_a_moved_series()
    monkeypatch.setattr(series_days, "series_of", lambda row, series: None)
    res = agenda.apply_action("cancel_meeting", {"title": "Abril's piano lesson", "whole": True})
    assert res.get("ok") is False and res.get("error") == "series_left_behind", res
    assert "piano" in res["message"].lower() and res["message"] != "series_left_behind"


def test_another_appointment_with_a_different_title_is_never_a_day_of_the_series():
    _piano_with_a_moved_day_and_a_moved_series()
    agenda.apply_action("add_meeting", {"title": "Dentist", "date": TUE.isoformat(), "startTime": "10:00"})
    agenda.apply_action("cancel_meeting", {"title": "Abril's piano lesson", "whole": True})
    assert [m["title"] for m in agenda.load_db()["meetings"]] == ["Dentist"]
