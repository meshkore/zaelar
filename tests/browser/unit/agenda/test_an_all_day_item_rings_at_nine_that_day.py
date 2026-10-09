"""An all-day item he writes rings at 09:00 that day, the way a timed one rings 2 h before (operator, 2026-10-10).

V2-781 pair 3, EN: «can you set a reminder for that day? Premiere day works» wrote an all-day «Dexter… premiere» on
30 Oct with NO notice — the agent itself then said «it has no separate alert configured». An all-day item rang only
when the write passed `remind` (T513). The operator's call: it carries a default notice at 09:00 that day. Items
synced from Google keep theirs silent (holidays, birthdays), and an asked notice still wins.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """ISOLATED store and scheduler — never the operator's real agenda or jobs."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as d
    made = []
    from nucleo import scheduler as S
    monkeypatch.setattr(S, "create", lambda prompt, stamp, **k: made.append(stamp) or {"ok": True, "id": str(len(made)),
                                                                                       "display": stamp})
    monkeypatch.setattr(S, "supersede_loose_notices", lambda *a, **k: None)
    return d, made


def _row(title):
    from widgets import store
    return next(m for m in store.load("agenda")["meetings"] if m["title"] == title)


def test_an_all_day_item_gets_a_notice_at_nine(ag):
    d, made = ag
    d.apply_action("add_meeting", {"title": "Dexter premiere", "date": "2027-10-30", "allDay": True})
    assert made == ["2027-10-30 09:00"] and _row("Dexter premiere").get("remindAt") == "2027-10-30 09:00"


def test_an_asked_notice_still_wins(ag):
    d, made = ag
    d.apply_action("add_meeting", {"title": "Dexter premiere", "date": "2027-10-30", "allDay": True,
                                   "remind": "2027-10-29 20:00"})
    assert _row("Dexter premiere").get("remindAt") == "2027-10-29 20:00"


def test_a_timed_item_keeps_two_hours_before(ag):
    d, made = ag
    d.apply_action("add_meeting", {"title": "Dentista", "date": "2027-10-15", "startTime": "10:00"})
    assert _row("Dentista").get("remindAt") == "2027-10-15 08:00"
