"""The `notice_on` gate never counts a notice that rings on or after the deadline it announces (2026-10-14).

`remember-and-remind-deadline` asked on the Wednesday itself (2026-10-14 ~12:00): the job went in for 2026-10-21
09:00 — next week's Wednesday, six days after Thursday's renewal — and the gate, which accepted next week's day OR
today, would have passed it. With `deadline_on="thursday"` only a day before Thursday counts.
"""
from __future__ import annotations

import datetime as _dt

from tests.use_cases.e2e.agent import gates
from tests.use_cases.e2e.agent import scenarios as SC


def _case(sid):
    return next(s for s in SC.all_scenarios() if s.id == sid)


def _verdict(sid, at, schedule):
    run = {"transcript": [{"at": at.timestamp(), "who": "tester", "text": "x"}],
           "mechanism_report": {"scheduled_jobs": {"created": [{"name": "aviso", "schedule": schedule}]}}}
    return gates.apply(_case(sid), run, {"overall": 5, "scores": {}, "findings": []})


def test_both_twins_name_the_deadline():
    for sid in ("remember-and-remind-deadline", "remember-and-remind-deadline__us"):
        assert _case(sid).deadline_on == "thursday", sid


def test_said_on_the_wednesday_next_weeks_job_fails_and_todays_passes():
    wed = _dt.datetime(2026, 10, 14, 12, 0)
    for sid in ("remember-and-remind-deadline", "remember-and-remind-deadline__us"):
        assert _verdict(sid, wed, "2026-10-21 09:00")["overall"] <= 2, sid
        assert _verdict(sid, wed, "2026-10-14 13:00")["overall"] == 5, sid


def test_said_on_another_day_the_coming_wednesday_still_counts():
    sat = _dt.datetime(2026, 10, 17, 11, 0)
    assert _verdict("remember-and-remind-deadline", sat, "2026-10-21 09:00")["overall"] == 5
