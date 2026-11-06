"""An appointment's notice is a DERIVATIVE of its row, with one writer (C13, ES/EN).

Move the appointment and the notice moves with it; cancel it and the notice goes; ask to move only the notice
and THAT row's notice moves — never a neighbour's found by title overlap. And the background Google pass never
saves a copy older than a write that landed during its round trip: that stale save erased the dictated row,
brought its Google twin back as «new» with a second default notice, and left the first one ringing over a moved
or cancelled appointment. A notice no row carries is swept by the tick.

Isolated: the store lives in tmp_path, the scheduler is the conftest's in-memory ledger, Google is a fake.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from connectors.calendar import service as cal_service
from widgets.agenda import data as ag
from widgets.agenda import gcal as ag_gcal

DAY = "2099-11-16"

CASES = {
    "es": {"title": "Revisión del coche en el taller", "kid": "Dentista de los niños", "near": "Dentista"},
    "en": {"title": "Car service at the garage", "kid": "Kids' dentist appointment", "near": "Dentist"},
}


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(ag_gcal, "svc", lambda: None)        # local-only unless a test plugs a fake Google
    return ag


def _notices(jobs) -> list[str]:
    return sorted(j["schedule"] for j in jobs.values() if j.get("origin") == "agenda")


def _row(title):
    return next(m for m in ag.load_db()["meetings"] if m["title"] == title)


@pytest.mark.parametrize("lang", sorted(CASES))
def test_moving_then_cancelling_carries_the_notice_along(agenda, _scheduler_never_touches_the_live_journal, lang):
    jobs, t = _scheduler_never_touches_the_live_journal, CASES[lang]["title"]
    agenda.apply_action("add_meeting", {"title": t, "date": DAY, "startTime": "10:00"})
    assert _notices(jobs) == [f"{DAY} 08:00"]
    agenda.apply_action("update_meeting", {"title": t, "date": DAY, "startTime": "17:00"})
    assert _notices(jobs) == [f"{DAY} 15:00"], "the notice moves WITH the appointment, never stays at the old hour"
    assert _row(t)["reminder_id"] in jobs
    agenda.apply_action("cancel_meeting", {"title": t, "date": DAY})
    assert _notices(jobs) == [], "a cancelled appointment leaves no notice behind"


@pytest.mark.parametrize("lang", sorted(CASES))
def test_moving_only_the_notice_moves_that_rows_notice(agenda, _scheduler_never_touches_the_live_journal, lang):
    jobs, kid, near = (_scheduler_never_touches_the_live_journal, CASES[lang]["kid"], CASES[lang]["near"])
    agenda.apply_action("add_meeting", {"title": near, "date": DAY, "startTime": "09:30"})
    agenda.apply_action("add_meeting", {"title": kid, "date": DAY, "startTime": "15:00"})
    assert _notices(jobs) == [f"{DAY} 07:30", f"{DAY} 13:00"]
    agenda.apply_action("add_meeting", {"title": kid, "date": DAY, "startTime": "15:00", "remind": "12:00"})
    assert _notices(jobs) == [f"{DAY} 07:30", f"{DAY} 12:00"], "the asked hour lands on THAT row, the neighbour keeps its own"
    assert jobs[_row(kid)["reminder_id"]]["schedule"] == f"{DAY} 12:00"
    assert jobs[_row(near)["reminder_id"]]["schedule"] == f"{DAY} 07:30"


class _Google:
    """A fake Google whose round trip lasts long enough for the operator to dictate an appointment meanwhile."""
    def __init__(self, during_fetch=None):
        self.events: dict[str, dict] = {}
        self.during_fetch = during_fetch

    def connected(self, *a, **k):
        return True

    def create_event(self, m, calendar_id=""):
        gid = f"g{len(self.events) + 1}"
        off = _dt.datetime.now().astimezone().strftime("%z")
        off = off[:3] + ":" + off[3:]
        self.events[gid] = {"id": gid, "summary": m["title"], "updated": "u1",
                            "start": {"dateTime": f"{m['date']}T{m['startTime']}:00{off}"},
                            "end": {"dateTime": f"{m['date']}T{m.get('endTime') or '23:00'}:00{off}"}}
        return {"ok": True, "meeting": {**m, "source": "google", "googleId": gid, "googleCalendarId": "primary",
                                        "googleUpdated": "u1"}}

    def delete_event(self, m, **k):
        return {"ok": self.events.pop(str(m.get("googleId")), None) is not None}

    def fetch(self, db, *a):
        if self.during_fetch:
            self.during_fetch(), setattr(self, "during_fetch", None)
        return {"ok": True, "calendars": [{"id": "primary", "primary": True}],
                "pulled": [("primary", {"ok": True, "events": list(self.events.values()), "deleted": []})]}

    def merge(self, db, pulled):
        return cal_service.merge(db, pulled)

    def sync(self, db, *a):
        return self.merge(db, self.fetch(db))


class _Ctx:
    def save(self, data):
        from widgets import store
        store.save(ag.WIDGET_ID, data)


@pytest.mark.parametrize("lang", sorted(CASES))
def test_a_google_pass_never_saves_over_a_write_made_during_its_round_trip(
        agenda, _scheduler_never_touches_the_live_journal, monkeypatch, lang):
    jobs, t = _scheduler_never_touches_the_live_journal, CASES[lang]["title"]
    g = _Google(during_fetch=lambda: agenda.apply_action("add_meeting", {"title": t, "date": DAY, "startTime": "10:00"}))
    monkeypatch.setattr(ag_gcal, "svc", lambda: g)
    agenda.tick(_Ctx())
    rows = [m for m in agenda.load_db()["meetings"] if m["title"] == t]
    assert len(rows) == 1 and rows[0].get("created"), "the dictated row survives the pass (its stamp included)"
    assert _notices(jobs) == [f"{DAY} 08:00"], "one appointment, ONE notice — never a second for its Google twin"
    agenda.apply_action("cancel_meeting", {"title": t, "date": DAY})
    assert _notices(jobs) == [], "cancelled: nothing is left to ring"


def test_the_tick_sweeps_a_notice_no_row_carries(agenda, _scheduler_never_touches_the_live_journal, monkeypatch):
    from nucleo.pulse import scheduler
    jobs = _scheduler_never_touches_the_live_journal
    monkeypatch.setattr(scheduler, "pending_carrying", lambda key: [
        {"id": jid, "detail": {"origin": j["origin"]}} for jid, j in jobs.items() if j.get("origin")])
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": DAY, "startTime": "10:00"})
    scheduler.create("Recuérdale: «Taller» a las 10:00", f"{DAY} 08:00", name="aviso: Taller", origin="agenda")
    scheduler.create("Riega las plantas", f"{DAY} 08:00", name="plantas", origin="cron")
    agenda.tick(_Ctx())
    assert sorted(j["name"] for j in jobs.values()) == ["aviso: Dentista", "plantas"], \
        "the orphan notice goes; the carried one and a standing cron stay"
