"""V2-639 — the agenda answers to the voice.

Measured live (sessions 0c2af370 18:12 and c4ad8332 19:27, 2026-09-09): the operator asked four times for
the MONTH view and the widget landed on today every time — the model sent `show_day {view: 'month'}` and
`data.py` only read `day`/`date`, so the alias silently resolved to today (the V2-341/V2-473-r3 class: the
model's natural alias must not cost the fact). And three intentions had NO vocabulary at all — moving an
appointment to another day, putting reminders on every appointment of a day, adding a plain task — which is
the clear_all lesson: a frequent intention with no declared action cannot be gotten right. The appointment's
details were also invisible to the brain (coach_context only carries TODAY), and the whole surface spoke
hardcoded Spanish to an English operator.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

from widgets.agenda import data as agenda
from widgets.agenda import planner

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)


@pytest.fixture
def fake_sched(monkeypatch):
    """The scheduler is a real cron store — tests never touch it. Records create/cancel calls."""
    from nucleo import scheduler
    calls = {"created": [], "cancelled": []}

    def _create(prompt, stamp, name=""):
        calls["created"].append((prompt, stamp, name))
        return {"ok": True, "id": f"job{len(calls['created'])}"}

    monkeypatch.setattr(scheduler, "create", _create)
    monkeypatch.setattr(scheduler, "cancel", lambda ref: calls["cancelled"].append(ref))
    return calls


def _tomorrow() -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + 86400))


def _in_days(n: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() + n * 86400))


# ── the measured bug: the view alias the model actually sent ─────────────────────────────────────────────

def test_show_day_reads_the_view_alias_the_model_sent_live():
    """«Muéstrame la agenda con vista mensual» arrived as {view: 'month'} and fell to today, silently."""
    d = agenda.apply_action("show_day", {"view": "month"})
    assert d["view"]["sel"] == "month"


def test_show_day_reads_mode_and_vista_too():
    assert agenda.apply_action("show_day", {"mode": "semana"})["view"]["sel"] == "week"
    assert agenda.apply_action("show_day", {"vista": "mes"})["view"]["sel"] == "month"


def test_show_day_day_key_still_wins_and_resolves_relative_dates():
    d = agenda.apply_action("show_day", {"day": "mañana"})
    assert d["view"]["sel"] == _tomorrow()


# ── move_meeting: an appointment moves WITH its reminder ─────────────────────────────────────────────────

def test_move_meeting_moves_date_and_keeps_duration(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(),
                                        "startTime": "17:00", "endTime": "17:30"})
    agenda.apply_action("move_meeting", {"title": "dentista", "newDate": _in_days(3), "newTime": "10:00"})
    m = agenda.load_db()["meetings"][0]
    assert m["date"] == _in_days(3)
    assert m["startTime"] == "10:00"
    assert m["endTime"] == "10:30", "the end keeps the meeting's duration"


def test_move_meeting_reschedules_the_reminder(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(), "startTime": "17:00"})
    assert len(fake_sched["created"]) == 1
    old_id = agenda.load_db()["meetings"][0]["reminder_id"]
    agenda.apply_action("move_meeting", {"title": "dentista", "newDate": _in_days(4)})
    assert old_id in fake_sched["cancelled"], "an alarm for the old day fires a ghost (V2-473)"
    assert len(fake_sched["created"]) == 2
    m = agenda.load_db()["meetings"][0]
    assert m["reminder_id"] and m["reminder_id"] != old_id
    assert m["startTime"] == "17:00", "no newTime given -> the hour survives the move"


def test_move_meeting_without_target_names_what_is_missing(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(), "startTime": "17:00"})
    r = agenda.apply_action("move_meeting", {"title": "dentista"})
    assert r.get("ok") is False and "newDate" in r["error"]


def test_move_meeting_unknown_title_refuses_instead_of_guessing(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(), "startTime": "17:00"})
    r = agenda.apply_action("move_meeting", {"title": "notario", "newDate": _in_days(2)})
    assert r.get("ok") is False
    assert agenda.load_db()["meetings"][0]["date"] == _tomorrow()


# ── set_reminder in bulk: every appointment of a day ─────────────────────────────────────────────────────

def test_set_reminder_with_date_and_no_title_reaches_every_meeting_of_that_day(fake_sched):
    day = _in_days(2)
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": day, "startTime": "10:00"})
    agenda.apply_action("add_meeting", {"title": "Notario", "date": day, "startTime": "17:00"})
    agenda.apply_action("add_meeting", {"title": "Gimnasio", "date": _in_days(5), "startTime": "09:00"})
    before = len(fake_sched["created"])          # the three default reminders from add_meeting
    agenda.apply_action("set_reminder", {"date": day})
    assert len(fake_sched["created"]) == before + 2, "both meetings of THAT day, not the third"
    for m in agenda.load_db()["meetings"]:
        if m["date"] == day:
            assert m.get("reminder_id")


def test_set_reminder_single_meeting_still_needs_the_hour(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(), "startTime": "17:00"})
    r = agenda.apply_action("set_reminder", {"title": "dentista"})
    assert r.get("ok") is False and "at" in r["error"]


# ── add_task: not everything on an agenda has an hour ────────────────────────────────────────────────────

def test_add_task_creates_a_plain_todo(fake_sched):
    agenda.apply_action("add_task", {"title": "Revisar el contrato", "estimateMinutes": 45})
    tasks = agenda.load_db()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["status"] == "todo" and tasks[0]["estimateMinutes"] == 45
    assert not tasks[0].get("fixed")


def test_add_task_with_a_time_is_fixed_and_empty_title_is_an_error(fake_sched):
    r = agenda.apply_action("add_task", {})
    assert r.get("ok") is False and "title" in r["error"]
    agenda.apply_action("add_task", {"title": "Llamar al banco", "startTime": "10:30"})
    t = agenda.load_db()["tasks"][0]
    assert t["fixed"] and t["startTime"] == "10:30"


# ── details: notes are stored and the brain can SEE the meetings ─────────────────────────────────────────

def test_add_meeting_keeps_notes_and_the_digest_serves_them(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(), "startTime": "17:00",
                                        "notes": "Clínica Ruiz, llevar la radiografía"})
    digest = agenda.prompt_digest()
    assert "Dentista" in digest and _tomorrow() in digest and "17:00" in digest
    assert "radiografía" in digest, "«qué es ese punto» is answerable from the digest"


def test_the_digest_says_empty_plainly():
    assert "sin citas" in agenda.prompt_digest()


def test_ref_index_exposes_future_meetings_never_past_ones(fake_sched):
    agenda.apply_action("add_meeting", {"title": "Dentista", "date": _tomorrow(), "startTime": "17:00"})
    db = agenda.load_db()
    db["meetings"].append({"title": "Vieja", "date": "2020-01-01", "startTime": "10:00", "endTime": "11:00"})
    from widgets import store
    store.save(agenda.WIDGET_ID, db)
    rows = agenda.ref_index()
    titles = [r["label"] for r in rows if r["field"] == "title"]
    assert "Dentista" in titles and "Vieja" not in titles


# ── multilingual: dates, hours and the plan's own words ──────────────────────────────────────────────────

def test_spoken_dates_resolve_in_english_too():
    assert agenda._resolve_date("tomorrow") == _tomorrow()
    assert agenda._resolve_date("today") == time.strftime("%Y-%m-%d")
    assert agenda._resolve_time("5 in the afternoon") == "17:00"
    assert agenda._resolve_time("9 in the morning") == "09:00"


def test_the_plan_speaks_the_active_language():
    db = agenda.load_db()
    es = planner.plan_day(db, date=time.strftime("%Y-%m-%d"), lang="es")
    en = planner.plan_day(db, date=time.strftime("%Y-%m-%d"), lang="en")
    assert any(b["label"] == "Comida" for b in es["blocks"])
    assert any(b["label"] == "Lunch" for b in en["blocks"])


def test_the_horizon_labels_follow_the_language(monkeypatch):
    monkeypatch.setattr(agenda, "_lang", lambda: "en")
    days = agenda.view_data()["days"]
    assert days[0]["label"] == "Today" and days[1]["label"] == "Tomorrow"


# ── the deterministic lane: seeds and declarations ───────────────────────────────────────────────────────

def test_seed_packs_carry_the_operators_view_phrases():
    """The exact live sentence («Muéstrame la agenda con vista mensual») resolves without a model now."""
    for lang, phrase, day in (("es", "muestrame la agenda con vista mensual", "mes"),
                              ("es", "ensename la agenda de manana", "manana"),
                              ("en", "put the agenda in month view", "mes"),
                              ("en", "show me the agenda for today", "hoy")):
        pack = json.loads((ENGINE / "nucleo/actionmap/seeds" / f"{lang}.json").read_text())
        assert pack["version"] >= 7
        hit = [e for e in pack["entries"] if e["phrase"] == phrase]
        assert hit, f"{lang}: {phrase!r} not seeded"
        a = hit[0]["action"]
        assert a == {"do": "widget_data", "widget": "agenda", "action": "show_day", "payload": {"day": day}}


def test_the_new_vocabulary_is_declared_and_fast():
    from widgets import actions as wactions
    manifest = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text())
    acts = manifest["actions"]
    for name in ("add_task", "move_meeting"):
        assert name in acts
        assert wactions.classify(acts[name], name) == wactions.FAST
    assert acts["move_meeting"].get("ref") == "title", "spoken references resolve to the title payload key"
    assert acts["set_reminder"].get("ref") == "title"
