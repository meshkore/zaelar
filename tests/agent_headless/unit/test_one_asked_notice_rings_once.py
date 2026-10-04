"""One asked notice rings ONCE, whichever of the two writers got there first (V2-781 T519, 2026-10-03).

Measured on `dentist-appointment-into-agenda` (ES): «Mejor avísame ese día a mediodía» → the agenda's
`set_reminder` moved the appointment's notice to 12:00, and 8 ms EARLIER the prose backstop (the turn had no
`cron.create` tag) scheduled its own loose «aviso» at 12:00 whose text was «…te pidió: Mejor». Two alerts on the
13th at noon, one saying nothing. The backstop already skips an instant a live job covers; this is the other order.
"""
from __future__ import annotations

import time

import pytest

from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from memory import db as memdb
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    memdb.reset_db()
    yield
    memdb.reset_db()


def _day(n: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


def _live():
    from nucleo import scheduler
    return sorted((j["name"], j["schedule"]) for j in scheduler.list_jobs(active_only=True))


def test_the_appointments_notice_retires_the_loose_one_at_the_same_instant():
    from nucleo import scheduler
    d = _day(9)
    agenda.apply_action("add_meeting", {"title": "Dentista de los niños", "date": d, "startTime": "15:00"})
    scheduler.create("AVISA al operador, es el recordatorio que te pidió: Mejor", f"{d} 12:00", name="aviso")
    r = agenda.apply_action("set_reminder", {"title": "Dentista", "at": f"{d} 12:00"})
    assert r.get("ok") is not False, r
    assert _live() == [("aviso: Dentista de los niños", f"{d} 12:00")]


def test_a_loose_notice_at_another_instant_or_from_long_ago_stays():
    from nucleo import scheduler
    d = _day(9)
    scheduler.create("AVISA: otra cosa", f"{d} 12:30", name="aviso")
    old = scheduler.create("AVISA: lo de antes", f"{d} 12:00", name="aviso")
    assert scheduler.supersede_loose_notices(f"{d} 12:00", now=time.time() + 600) == [], "older than the turn"
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": d, "startTime": "15:00"})
    assert ("aviso", f"{d} 12:30") in _live()
    assert old["ok"]


def test_a_named_job_is_never_retired():
    from nucleo import scheduler
    d = _day(9)
    scheduler.create("Recuérdale la reunión", f"{d} 12:00", name="reunión con Ana")
    assert scheduler.supersede_loose_notices(f"{d} 12:00") == []
