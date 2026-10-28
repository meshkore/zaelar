"""«Note it for Thursday, remind me on Wednesday», said ON the Wednesday after 09:00, rings TODAY (2026-10-14).

Measured in `remember-and-remind-deadline__us` (Wednesday 2026-10-14 ~12:00): `add_meeting {date: Thursday,
remind: "2026-10-14 09:00"}` and then `set_reminder {date: "2026-10-14"}` were both refused — «no pude programar el
aviso: el instante ya pasó» — while the reply had promised the notice. The asked notice now rings soon today (the
next full hour), never in the past and never after the item; a day already gone is still refused.
The clock is frozen and the scheduler is the suite's in-memory double (conftest), so no real notice is written.
"""
from __future__ import annotations

import time

import pytest

from widgets.agenda import data as agenda

NOON = time.mktime((2026, 10, 14, 12, 0, 0, 0, 1, -1))     # Wednesday, the run's own clock
DAWN = time.mktime((2026, 10, 14, 7, 30, 0, 0, 1, -1))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from nucleo.pulse import notice_today
    from nucleo.pulse import scheduler
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "supersede_loose_notices", lambda display, **k: [])
    notice_today.take_move(NOON, within_s=1e12)


def _at(monkeypatch, now):
    monkeypatch.setattr(time, "time", lambda: now)


def _live(jobs):
    return sorted(j["schedule"] for j in jobs.values())


def test_the_asked_hour_gone_today_rings_at_the_next_full_hour(monkeypatch, _scheduler_never_touches_the_live_journal):
    _at(monkeypatch, NOON)
    r = agenda.apply_action("add_meeting", {"title": "Renew car insurance", "date": "2026-10-15",
                                            "remind": "2026-10-14 09:00"})
    assert not r.get("notice_error"), r
    (m,) = agenda.load_db()["meetings"]
    assert m["remindAt"] == "2026-10-14 13:00", m
    assert _live(_scheduler_never_touches_the_live_journal) == ["2026-10-14 13:00"]


def test_set_reminder_on_today_rings_today(monkeypatch, _scheduler_never_touches_the_live_journal):
    _at(monkeypatch, NOON)
    agenda.apply_action("add_meeting", {"title": "Renew car insurance", "date": "2026-10-15"})
    r = agenda.apply_action("set_reminder", {"title": "Renew car insurance", "date": "2026-10-14"})
    assert r.get("ok") is not False, r
    assert _live(_scheduler_never_touches_the_live_journal) == ["2026-10-14 13:00"]


def test_before_the_hour_the_asked_hour_stands(monkeypatch, _scheduler_never_touches_the_live_journal):
    _at(monkeypatch, DAWN)
    agenda.apply_action("add_meeting", {"title": "Renew car insurance", "date": "2026-10-15",
                                        "remind": "2026-10-14 09:00"})
    assert _live(_scheduler_never_touches_the_live_journal) == ["2026-10-14 09:00"]


def test_never_after_the_item_and_a_day_gone_is_still_refused(monkeypatch, _scheduler_never_touches_the_live_journal):
    _at(monkeypatch, NOON)
    r = agenda.apply_action("add_meeting", {"title": "Dentist", "date": "2026-10-15", "startTime": "10:00",
                                            "remind": "2026-10-16 09:00"})
    assert "después" in str(r.get("notice_error")), r
    r = agenda.apply_action("add_meeting", {"title": "Insurance", "date": "2026-10-15",
                                            "remind": "2026-10-13 09:00"})
    assert "ya pasó" in str(r.get("notice_error")), r
