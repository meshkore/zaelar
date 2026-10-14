"""A reference that names its day keeps the day — «Abril's piano lesson on 2026-10-20» moves ONE day, never the series.

Sandbox 20261014-121305-en, turn 12: the model re-sent «move the 20th to the 21st» as `item: "Abril's piano lesson on
2026-10-20"` with no `date`; `refs.resolve` filled the title and dropped the day, so the move ran undated and every
Tuesday became a Wednesday. The day travels into `date` when the action declares one and nothing else gave a day.
"""
from __future__ import annotations

import datetime as dt

from tests.agent_headless.unit.test_the_everyday_agenda_edits import _isolated, _next  # noqa: F401
from widgets import refs
from widgets.agenda import data as agenda

TUE = _next(1)
WED = TUE + dt.timedelta(days=1)


def _series():
    agenda.apply_action("add_meeting", {"title": "Abril's piano lesson", "date": TUE.isoformat(),
                                        "startTime": "17:00", "endTime": "18:00", "repeat": "weekly",
                                        "until": (TUE + dt.timedelta(weeks=12)).isoformat()})


def test_the_resolved_reference_carries_its_day():
    _series()
    r = refs.resolve("agenda", "move_meeting", f"Abril's piano lesson on {TUE.isoformat()}", {"newDate": WED.isoformat()})
    assert r.ok and r.payload.get("date") == TUE.isoformat() and r.payload.get("title") == "Abril's piano lesson"


def test_a_day_he_or_the_model_already_gave_is_never_overwritten():
    _series()
    other = (TUE + dt.timedelta(weeks=1)).isoformat()
    r = refs.resolve("agenda", "move_meeting", f"Abril's piano lesson on {TUE.isoformat()}", {"date": other})
    assert r.payload["date"] == other


def test_the_re_sent_one_day_move_does_not_move_the_series():
    _series()
    ref = f"Abril's piano lesson on {TUE.isoformat()}"
    for _ in range(2):                                   # the move, then the same move re-sent a turn later
        r = refs.resolve("agenda", "move_meeting", ref, {"newDate": WED.isoformat()})
        agenda.apply_action("move_meeting", r.payload)
    ser = next(m for m in agenda.load_db()["meetings"] if isinstance(m.get("repeat"), dict))
    assert ser["date"] == TUE.isoformat() and ser["repeat"]["days"] == [1], ser


def test_an_action_that_declares_no_day_gets_none():
    from widgets import ref_day
    assert "date" not in ref_day.carried("agenda", "delete_task", "call mum on 2026-10-20", {})
