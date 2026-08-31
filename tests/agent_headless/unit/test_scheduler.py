"""Core scheduler.py tests (V2-005 · T71/T72) — custom cron backed by memory.journal."""
import time

import pytest

from memory import db as memdb
from nucleo import scheduler


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── parsing ──────────────────────────────────────────────────────────────────────────────────────────────
def test_parse_relative_once():
    now = 1000.0
    s = scheduler.parse_schedule("30m", now=now)
    assert s["type"] == "once" and s["next_run"] == int(now + 1800)
    assert scheduler.parse_schedule("en 2h", now=now)["next_run"] == int(now + 7200)
    assert scheduler.parse_schedule("+45s", now=now)["next_run"] == int(now + 45)


def test_parse_interval():
    now = 1000.0
    s = scheduler.parse_schedule("every 30m", now=now)
    assert s["type"] == "interval" and s["interval_s"] == 1800
    assert scheduler.parse_schedule("cada 2h", now=now)["type"] == "interval"


def test_parse_cron_and_next():
    # 09:00 every day; anchor at a known instant and request the next occurrence.
    base = time.mktime(time.strptime("2026-07-09 08:00", "%Y-%m-%d %H:%M"))
    s = scheduler.parse_schedule("0 9 * * *", now=base)
    assert s["type"] == "cron"
    fired = time.localtime(s["next_run"])
    assert fired.tm_hour == 9 and fired.tm_min == 0


def test_parse_garbage_returns_none():
    assert scheduler.parse_schedule("mañana por la tarde") is None
    assert scheduler.parse_schedule("") is None
    assert scheduler.parse_schedule("99 99 * * *") is None   # cron out of range


def test_next_cron_step_field():
    base = time.mktime(time.strptime("2026-07-09 08:07", "%Y-%m-%d %H:%M"))
    nr = scheduler.next_cron("*/15 * * * *", base)
    assert time.localtime(nr).tm_min == 15


# ── task lifecycle ──────────────────────────────────────────────────────────────────────────────────────
def test_create_list_and_due(fresh_db):
    now = 1000.0
    r = scheduler.create("recuérdame estirar", "30m", name="estirar", now=now)
    assert r["ok"] and r["id"] > 0
    jobs = scheduler.list_jobs()
    assert len(jobs) == 1 and jobs[0]["name"] == "estirar"
    # not due yet
    assert scheduler.due(now=now + 60) == []
    # due after the interval has elapsed
    due = scheduler.due(now=now + 1801)
    assert len(due) == 1 and due[0]["detail"]["prompt"] == "recuérdame estirar"


def test_create_bad_schedule(fresh_db):
    r = scheduler.create("x", "cuando quieras")
    assert r["ok"] is False and r["id"] is None


def test_once_fires_then_done(fresh_db):
    now = 1000.0
    scheduler.create("aviso", "10m", name="aviso", now=now)
    due = scheduler.due(now=now + 601)
    assert len(due) == 1
    nxt = scheduler.mark_fired(due[0], now=now + 601)
    assert nxt is None                                   # one-shot → closes
    assert scheduler.due(now=now + 100000) == []         # no longer due
    assert scheduler.list_jobs(active_only=True) == []   # no longer pending


def test_interval_reschedules(fresh_db):
    now = 1000.0
    scheduler.create("bebe agua", "every 30m", name="agua", now=now)
    due = scheduler.due(now=now + 1801)
    nxt = scheduler.mark_fired(due[0], now=now + 1801)
    assert nxt is not None and nxt["next_run"] == int(now + 1801 + 1800)
    assert scheduler.list_jobs()[0]["fire_count"] == 1   # still active, count increased


def test_cancel_by_name_and_id(fresh_db):
    now = 1000.0
    r = scheduler.create("x", "1h", name="dentista", now=now)
    assert scheduler.cancel("dentista") is True
    assert scheduler.list_jobs() == []
    r2 = scheduler.create("y", "1h", name="médico", now=now)
    assert scheduler.cancel(str(r2["id"])) is True
    assert scheduler.list_jobs() == []


def test_repeat_forces_recurrence(fresh_db):
    now = 1000.0
    r = scheduler.create("ping", "30m", repeat="30m", now=now)
    assert r["ok"]
    assert scheduler.list_jobs()[0]["type"] == "interval"


# ── ABSOLUTE one-shot date (V2-121) ──────────────────────────────────────────────────────────────────────
# Added because the `remember-and-remind-deadline` use case revealed that «remind me on Wednesday» had NO
# way to be expressed: there were only relative deadlines (`2d`, fragile) and five-field cron (RECURRING — it
# would alert every Wednesday). The reminder was never created, while the turn claimed it was.
def _at(y, mo, d, h=12, mi=0):
    return time.mktime((y, mo, d, h, mi, 0, 0, 1, -1))


def test_parse_absolute_date_with_time_is_a_one_shot():
    now = _at(2026, 8, 18, 12, 0)
    s = scheduler.parse_schedule("2026-08-19 09:00", now=now)
    assert s["type"] == "once"                       # one-shot, not a weekly cron
    assert s["next_run"] == int(_at(2026, 8, 19, 9, 0))
    assert s["display"] == "2026-08-19 09:00"        # readable by the operator, not an epoch


def test_parse_absolute_date_accepts_iso_t_separator():
    now = _at(2026, 8, 18, 12, 0)
    assert scheduler.parse_schedule("2026-08-19T07:30", now=now)["next_run"] == int(_at(2026, 8, 19, 7, 30))


def test_parse_absolute_date_without_time_defaults_to_the_morning():
    now = _at(2026, 8, 18, 12, 0)
    s = scheduler.parse_schedule("2026-08-19", now=now)
    assert s["next_run"] == int(_at(2026, 8, 19, scheduler._DEFAULT_HOUR, 0))


def test_absolute_date_already_past_is_rejected():
    # Delivering a reminder for last Thursday «now» is worse than rejecting it: the operator is left believing it
    # was set for the coming Thursday.
    now = _at(2026, 8, 18, 12, 0)
    assert scheduler.parse_schedule("2026-08-17 09:00", now=now) is None
    assert scheduler.parse_schedule("2026-08-18 11:00", now=now) is None


def test_absolute_date_rejects_impossible_and_ambiguous_formats():
    now = _at(2026, 8, 18, 12, 0)
    for spec in ("2026-13-01 09:00", "2026-08-19 25:00", "19/08 09:00", "19-08-2026 09:00"):
        assert scheduler.parse_schedule(spec, now=now) is None, spec


def test_absolute_one_shot_closes_after_firing(fresh_db):
    now = _at(2026, 8, 18, 12, 0)
    r = scheduler.create("renovar el seguro del coche", "2026-08-19 09:00", name="seguro coche", now=now)
    assert r["ok"], r
    job = [j for j in scheduler.list_jobs() if j["name"] == "seguro coche"][0]
    fired = scheduler.due(job["next_run"] + 1)
    assert [j["id"] for j in fired] == [job["id"]]
    scheduler.mark_fired(fired[0], job["next_run"] + 1)
    assert not scheduler.list_jobs(active_only=True)   # `once` is not rescheduled
