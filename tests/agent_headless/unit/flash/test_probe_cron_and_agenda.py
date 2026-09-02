"""nucleo/flash/probe.py::run_turn — a reminder is only a reminder if something got SCHEDULED.

`remember-and-remind-deadline` asks for two things in one breath: «apúntame que el jueves tengo que renovar el
seguro del coche, y recuérdamelo el miércoles». They are two different subsystems (the agenda entry and the
cron) and the case fails if either is missing — a spoken «te lo recuerdo» with nothing behind it is exactly the
failure it hunts for.

The probe channel is the one the use cases run on, and until V2-121 it only CAPTURED `[[cron.create]]` without
running it: the reminder could not exist in a run no matter how well the model emitted the tag. Nothing pinned
that, so it broke silently. These tests pin the two properties that matter:

  · the tag is EXECUTED (a real job in the scheduler) on the `execute=True` path the harness uses, and
  · it does NOT compete for the turn's single `action`, so booking the appointment cannot kill the reminder.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo import scheduler
from nucleo.flash import probe


class _CronTagClient:
    """Stub: the model speaks a confirmation and emits a cron tag, like the real turn does."""

    async def stream(self, *_a, **_kw):
        yield "Apuntado. Te aviso el miércoles por la mañana."
        yield ('[[cron.create]]{"schedule":"2026-09-02 09:00","prompt":"renovar el seguro del coche mañana",'
               '"name":"seguro-coche"}[[/cron.create]]')


class _CronPlusToolClient:
    """Stub: the SAME turn emits the cron tag AND calls a tool — the shape this use case actually needs."""

    async def stream(self, *_a, on_tool_call=None, **_kw):
        if on_tool_call is not None:
            res = on_tool_call("widget_data", {"widget_id": "agenda", "action": "add_meeting",
                                               "payload": {"title": "renovar el seguro del coche",
                                                           "date": "2026-09-03", "time": "09:00"}})
            if asyncio.iscoroutine(res):
                await res
        yield "Hecho: lo tienes en la agenda del jueves y te aviso el miércoles."
        yield ('[[cron.create]]{"schedule":"2026-09-02 09:00","prompt":"renovar el seguro del coche mañana",'
               '"name":"seguro-coche"}[[/cron.create]]')


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def probe_session():
    sid = "test-cron-agenda"
    yield sid
    probe._SESSIONS.pop(sid, None)
    for job in scheduler.list_jobs(active_only=True):
        if job.get("name") == "seguro-coche":
            scheduler.cancel("seguro-coche")


def _scheduled_names():
    return [j.get("name") for j in scheduler.list_jobs(active_only=True)]


def test_a_cron_tag_is_actually_scheduled_not_just_captured(fresh_db, probe_session, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _CronTagClient)
    res = asyncio.run(probe.run_turn(
        "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles.",
        sid=probe_session, ingest=False, execute=True))
    assert res["ok"] is True
    assert "seguro-coche" in _scheduled_names()


def test_booking_the_appointment_does_not_kill_the_reminder(fresh_db, probe_session, monkeypatch):
    """The turn has ONE `action`; the cron runs outside it on purpose. If they competed, the half the model
    happened to emit last would silently win and the operator would get an agenda entry with no alert."""
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _CronPlusToolClient)
    res = asyncio.run(probe.run_turn(
        "Apúntame que el jueves tengo que renovar el seguro del coche, y recuérdamelo el miércoles.",
        sid=probe_session, ingest=False, execute=True))
    assert res["ok"] is True
    assert res["action"] == "widget_data"          # the tool took the turn's single action…
    assert "seguro-coche" in _scheduled_names()    # …and the reminder still got scheduled


def test_an_absolute_date_is_expressible_in_one_go(fresh_db):
    """The prompt tells the model to use YYYY-MM-DD HH:MM for a one-off on a named day, so the scheduler has
    to accept exactly that — and reject a date already past instead of firing at once.

    The FUTURE date is computed, not written down. It used to be the literal «2026-09-02 09:00», which is a
    future date only until that morning: it went red on its own at 09:00 that day, with nothing changed and no
    defect to find. A test whose meaning depends on the wall clock has to read the wall clock — the PAST case
    can stay a literal, because a date in the past stays in the past."""
    import datetime as _dt
    soon = (_dt.datetime.now() + _dt.timedelta(days=1)).strftime("%Y-%m-%d")
    assert scheduler.parse_schedule(f"{soon} 09:00")["type"] == "once"
    assert scheduler.parse_schedule(soon)["display"].endswith("09:00")           # sane default hour
    assert scheduler.parse_schedule("2020-01-01 09:00") is None                  # in the past → refused
