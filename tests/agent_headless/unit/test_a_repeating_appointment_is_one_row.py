"""V2-769 — a repeating appointment is ONE row with a rule, and every reader sees all of its days.

THE MEASUREMENT (operator's own agenda, 2026-09-25, session a96fdea7). He dictated «piano de Abril, los martes
de 15:15 a 16:00, desde el 22 de septiembre hasta junio de 2027». The model sent exactly that —

    add_meeting {title: "Piano de Abril", date: "2026-09-22", startTime: "15:15", endTime: "16:00",
                 recurrence: "weekly", repeatUntil: "2027-06-30", category: "familia"}

— and the agenda wrote ONE Tuesday, dropped `recurrence` and `repeatUntil` without a word, and answered
success. The reply had already promised «hasta junio de 2027». Week three of the calendar was empty. The
Thursday appointment before it had no field to carry a rule at all, so the model put «recursiva» in the
category. His words: *«no solo poner un ítem un día, sino también hacerlo recursivo entre el período que yo
te digo»*.

Built THROUGH THE PRODUCT (`data.apply_action`), dates relative to today so the file never expires, the store
isolated by the root conftest, the scheduler and Google replaced by recorders.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from pathlib import Path

import pytest

from widgets.agenda import data as agenda, gcal, recur, reminders

ENGINE = Path(__file__).resolve().parents[3]
TODAY = dt.date.today()


def _next(weekday: int, after: dt.date = TODAY) -> dt.date:
    return after + dt.timedelta(days=(weekday - after.weekday()) % 7 or 7)


TUE = _next(1)
UNTIL = TUE + dt.timedelta(weeks=30)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setattr(gcal, "svc", lambda: None)                  # never his real Google Calendar
    notices: list[tuple] = []

    def _sched(title, date, start, at="", before_minutes=120):
        notices.append((title, date, start))
        return f"job{len(notices)}", f"{date} {start}"
    monkeypatch.setattr(agenda, "_schedule_reminder", _sched)
    monkeypatch.setattr(reminders, "_schedule_reminder", _sched)
    monkeypatch.setattr(agenda, "_cancel_reminder", lambda m: None)
    monkeypatch.setattr(reminders, "_cancel_reminder", lambda m: None)
    agenda.apply_action("clear_all", {})
    yield notices
    agenda.apply_action("clear_all", {})


def _piano(**extra):
    p = {"title": "Piano de Abril", "date": TUE.isoformat(), "startTime": "15:15", "endTime": "16:00",
         "recurrence": "weekly", "repeatUntil": UNTIL.isoformat(), "category": "familia"}
    p.update(extra)
    return agenda.apply_action("add_meeting", p)


def _days(title: str) -> list[str]:
    return sorted(m["date"] for m in agenda.view_data()["meetings"] if m.get("title") == title)


# ── the write keeps the rule ──────────────────────────────────────────────────────────────────────────────
def test_the_exact_call_the_model_made_stores_one_row_with_its_rule():
    res = _piano()
    assert res.get("ok") is not False, res
    rows = agenda.load_db()["meetings"]
    assert len(rows) == 1, f"a series is ONE row, never fifty copies: {rows}"
    assert rows[0]["repeat"] == {"freq": "weekly", "interval": 1, "until": UNTIL.isoformat(), "days": [1]}


def test_the_calendar_shows_every_tuesday_until_the_end_and_none_after():
    _piano()
    days = _days("Piano de Abril")
    assert days[0] == TUE.isoformat() and len(days) == 31, days
    assert (TUE + dt.timedelta(weeks=2)).isoformat() in days, "week three was empty — the measured defect"
    assert all(dt.date.fromisoformat(d).weekday() == 1 for d in days)
    assert (UNTIL + dt.timedelta(weeks=1)).isoformat() not in days


def test_his_words_for_it_work_too():
    """«todos los jueves… hasta junio» — a Thursday series dictated on any day starts on a Thursday."""
    until = f"junio de {TODAY.year + 1}"
    agenda.apply_action("add_meeting", {"title": "Flauta", "date": TODAY.isoformat(), "startTime": "15:30",
                                        "endTime": "16:15", "repeat": "todos los jueves", "until": until})
    row = agenda.load_db()["meetings"][0]
    assert row["repeat"]["days"] == [3] and row["repeat"]["until"] == f"{TODAY.year + 1}-06-30", row
    assert dt.date.fromisoformat(row["date"]).weekday() == 3, "the series must start on a Thursday"


def test_an_end_it_cannot_read_is_refused_and_nothing_is_written():
    res = _piano(repeatUntil="cuando acabe el curso")
    assert res.get("ok") is False and "until" in res["error"]
    assert agenda.load_db()["meetings"] == [], "a half-understood series must not be written as a single day"


def test_a_key_the_agenda_does_not_read_is_reported_not_dropped():
    res = _piano(colour="azul")
    assert res.get("ignored") == ["colour"], res.get("ignored")
    assert "recurrence" not in (res.get("ignored") or []) and "repeatUntil" not in (res.get("ignored") or [])


# ── every reader sees the series ──────────────────────────────────────────────────────────────────────────
def test_the_day_plan_three_weeks_out_has_the_appointment():
    _piano()
    day = (TUE + dt.timedelta(weeks=3)).isoformat()
    plan = agenda.planner.plan_day(agenda.load_db(), date=day, lang="es")
    assert any("Piano" in str(b.get("label")) for b in plan["blocks"]), plan["blocks"]


def test_what_the_brain_reads_says_it_repeats_and_until_when():
    _piano()
    digest = agenda.prompt_digest()
    assert "SE REPITE todos los martes hasta el " + UNTIL.isoformat() in digest, digest
    answer = agenda.read_query("¿hasta cuándo es el piano?")
    assert "SE REPITE" in answer and "próxima" in answer, answer


# ── editing a series ──────────────────────────────────────────────────────────────────────────────────────
def test_cancelling_one_day_keeps_the_rest_of_the_series():
    _piano()
    wk2 = (TUE + dt.timedelta(weeks=1)).isoformat()
    res = agenda.apply_action("cancel_meeting", {"title": "piano", "date": wk2})
    assert res.get("ok"), res
    days = _days("Piano de Abril")
    assert wk2 not in days and (TUE + dt.timedelta(weeks=2)).isoformat() in days and len(days) == 30


def test_cancelling_a_series_with_no_day_is_a_question_not_a_deletion():
    """The live use case: «quítamelo solo ese día» arrived with no date, and every Tuesday went."""
    _piano()
    res = agenda.apply_action("cancel_meeting", {"title": "piano"})
    assert res.get("ok") is False and "`date`" in res["error"] and "whole" in res["error"], res
    # …and what HE hears is a question, never the instruction to the model (the third live run read him
    # «vuelve a llamar con `date`» out loud).
    assert res.get("message") and "`" not in res["message"] and "serie" in res["message"], res.get("message")
    assert len(_days("Piano de Abril")) == 31, "nothing may be deleted while the scope is unknown"


def test_the_whole_series_goes_when_he_says_so():
    _piano()
    agenda.apply_action("cancel_meeting", {"title": "piano", "whole": True})
    assert _days("Piano de Abril") == []


def test_the_promise_backstop_sees_a_series_on_its_later_days():
    """The dated-note backstop wrote «piano de abril todos los» beside the series: it compared first days only."""
    from nucleo.flash import reminder_guards
    _piano()
    later = (TUE + dt.timedelta(weeks=3)).isoformat()
    assert reminder_guards.already_in_agenda({"title": "piano de Abril", "date": later}) is True


def test_clearing_one_week_leaves_the_other_weeks():
    _piano()
    wk = TUE + dt.timedelta(weeks=4)
    agenda.apply_action("clear_range", {"from": (wk - dt.timedelta(days=1)).isoformat(),
                                        "to": (wk + dt.timedelta(days=5)).isoformat()})
    days = _days("Piano de Abril")
    assert wk.isoformat() not in days and len(days) == 30, days


def test_the_end_date_alone_can_be_changed():
    _piano()
    new_end = TUE + dt.timedelta(weeks=5)
    agenda.apply_action("update_meeting", {"title": "piano", "until": new_end.isoformat()})
    assert len(_days("Piano de Abril")) == 6


def test_it_can_stop_repeating():
    _piano()
    agenda.apply_action("update_meeting", {"title": "piano", "repeat": "none"})
    assert _days("Piano de Abril") == [TUE.isoformat()]


def test_moving_the_series_moves_every_week():
    _piano()
    wed = TUE + dt.timedelta(days=1)
    agenda.apply_action("move_meeting", {"title": "piano", "newDate": wed.isoformat(), "newTime": "17:00"})
    row = agenda.load_db()["meetings"][0]
    assert row["repeat"]["days"] == [2] and row["startTime"] == "17:00"
    assert all(dt.date.fromisoformat(d).weekday() == 2 for d in _days("Piano de Abril"))


# ── its notice ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_series_that_started_in_the_past_gets_the_notice_of_its_next_day(_isolated):
    last_tue = TUE - dt.timedelta(weeks=2)
    agenda.apply_action("add_meeting", {"title": "Piano", "date": last_tue.isoformat(), "startTime": "15:15",
                                        "endTime": "16:00", "repeat": "weekly", "until": UNTIL.isoformat()})
    assert _isolated[-1][1] == recur.next_occurrence(agenda.load_db()["meetings"][0], TODAY.isoformat())


def test_the_notice_moves_on_when_its_day_has_passed(_isolated):
    _piano()
    db = agenda.load_db()
    db["meetings"][0]["remindFor"] = "2000-01-01"                   # the stored notice's day has gone
    saved = []
    assert reminders.roll_series(lambda: db, saved.append) is True
    assert db["meetings"][0]["remindFor"] == recur.next_occurrence(db["meetings"][0], TODAY.isoformat())
    assert reminders.roll_series(lambda: db, saved.append) is False, "it must not reschedule every tick"


# ── a piece of a sentence, and a write that lost part of itself ──────────────────────────────────────────
def test_the_whole_sentence_takes_back_what_a_piece_of_it_wrote(monkeypatch):
    """The measured afternoon: «recursiva los jueves» became a junk task; the whole sentence the appointment."""
    import widgets
    from nucleo.flash import data_ops, write_outcome
    write_outcome.reset()
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)

    async def _dispatch(tag, body):
        d = body["data"]
        return agenda.apply_action(d["action"], d["payload"])
    monkeypatch.setattr(widgets, "dispatch_tag", _dispatch)
    asyncio.run(data_ops.dispatch_and_report("agenda", "add_task", {"title": "Tarea semanal de los jueves"},
                                             text="recursiva los jueves"))
    assert any(t.get("title") == "Tarea semanal de los jueves" for t in agenda.load_db()["tasks"])
    asyncio.run(data_ops.dispatch_and_report(
        "agenda", "add_meeting",
        {"title": "Llevar a Abril a flauta travesera", "date": _next(3).isoformat(), "startTime": "15:30",
         "endTime": "16:15", "repeat": "weekly", "until": UNTIL.isoformat()},
        text="Vale, Johnny, créame una tarea recursiva los jueves de tres y media a cuatro y cuarto. "
             "Que es llevar a Abril a flauta travesera."))
    assert not any(t.get("title") == "Tarea semanal de los jueves" for t in agenda.load_db()["tasks"]), \
        "the junk task written from a piece of the sentence is still in his list"
    assert _days("Llevar a Abril a flauta travesera"), "and the real appointment landed"


def test_two_separate_orders_both_stay(monkeypatch):
    from nucleo.flash import write_outcome
    write_outcome.reset()
    write_outcome.remember("agenda", "add_task", "apunta comprar pan", {"revert": {"action": "delete_task"}})
    assert write_outcome.superseded("agenda", "add_task", "y apunta también llamar al fontanero") is None


def test_a_write_that_lost_a_field_is_corrected_to_the_model(monkeypatch):
    """Through the dispatcher the turn uses: the widget reports what it ignored, the model is told."""
    import widgets
    from nucleo.flash import data_ops, write_outcome
    from voice import brain_notes
    write_outcome.reset()
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)

    async def _dispatch(tag, body):
        d = body["data"]
        return agenda.apply_action(d["action"], d["payload"])
    monkeypatch.setattr(widgets, "dispatch_tag", _dispatch)
    brain_notes.drain()
    asyncio.run(data_ops.dispatch_and_report("agenda", "add_meeting", {
        "title": "Dentista", "date": TUE.isoformat(), "startTime": "10:00", "colour": "azul"}, text="dentista"))
    notes = " ".join(str(n) for n in brain_notes.drain())
    assert "SIN estos datos" in notes and "colour" in notes, notes


# ── the declared vocabulary, and Google ──────────────────────────────────────────────────────────────────
def test_the_manifest_offers_the_rule_to_the_model():
    m = json.loads((ENGINE / "widgets/agenda/manifest.json").read_text(encoding="utf-8"))
    for key in ("repeat", "days", "until"):
        assert key in m["actions"]["add_meeting"]["payload"], key
        assert key in m["actions"]["update_meeting"]["payload"], key
    assert "whole" in m["actions"]["cancel_meeting"]["payload"]


def test_google_gets_one_recurring_event_and_the_sync_does_not_duplicate_it(monkeypatch):
    from connectors.calendar import google_calendar as gc
    body = gc.meeting_to_event({"title": "Piano", "date": TUE.isoformat(), "startTime": "15:15",
                                "endTime": "16:00", "rrule": recur.to_rrule({"freq": "weekly", "days": [1],
                                                                             "until": UNTIL.isoformat()})})
    assert body["recurrence"][0].startswith("RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL="), body
    assert body["start"].get("timeZone"), "Google refuses a recurring event without its zone"
    inst = gc.event_to_meeting({"id": "abc_20261006", "recurringEventId": "abc", "summary": "Piano",
                                "start": {"dateTime": f"{TUE.isoformat()}T15:15:00+02:00"},
                                "end": {"dateTime": f"{TUE.isoformat()}T16:00:00+02:00"}}, "primary")
    assert inst["googleSeriesId"] == "abc"

    class _Svc:
        def connected(self):
            return True

        def create_event(self, m, cal):
            assert m.get("rrule"), "the series must travel as a rule"
            return {"ok": True, "meeting": {"googleId": "abc", "googleCalendarId": "primary", "source": "google"}}
    monkeypatch.setattr(gcal, "svc", lambda: _Svc())
    _piano()
    row = agenda.load_db()["meetings"][0]
    assert row.get("googleSeriesId") == "abc" and row.get("repeat") and row.get("source") != "google", row


def test_the_sync_does_not_bring_our_own_series_back_as_loose_rows(monkeypatch):
    """Google lists a recurring event instance by instance (`singleEvents`). A series WE pushed must not come
    back as forty loose Tuesdays beside the row that holds its rule; somebody else's series still does."""
    from types import SimpleNamespace
    from connectors.calendar import google_calendar as gc, service
    monkeypatch.setattr(service, "_prepared", lambda pid=None: (SimpleNamespace(api_base="x"), "tok", None))
    monkeypatch.setattr(gc, "list_calendars", lambda *a, **k: {"ok": True, "calendars": [{"id": "primary",
                                                                                            "primary": True}]})

    def _ev(gid, series):
        return {"id": gid, "recurringEventId": series, "summary": "Piano",
                "start": {"dateTime": f"{TUE.isoformat()}T15:15:00+02:00"},
                "end": {"dateTime": f"{TUE.isoformat()}T16:00:00+02:00"}, "updated": "1"}
    monkeypatch.setattr(gc, "list_events", lambda *a, **k: {"ok": True, "events": [
        _ev("abc_1", "abc"), _ev("abc_2", "abc"), _ev("zzz_1", "zzz")]})
    db = {"meetings": [{"title": "Piano", "date": TUE.isoformat(), "startTime": "15:15",
                        "repeat": {"freq": "weekly", "days": [1], "until": ""}, "googleSeriesId": "abc"}]}
    res = service.sync(db)
    assert res["ok"], res
    ids = [m.get("googleId") for m in db["meetings"]]
    assert "abc_1" not in ids and "abc_2" not in ids, f"our series came back as loose rows: {ids}"
    assert "zzz_1" in ids, "a series convened by somebody else must still arrive"


def test_the_field_names_the_model_invents_are_understood():
    """The live use case, 2026-09-25: the model sees action NAMES, not their fields, and named them itself.
    With `startDate`/`start`/`dayOfWeek` unread, the series landed on the day it was said, all-day."""
    res = agenda.apply_action("add_meeting", {
        "title": "Piano de Abril", "frequency": "weekly", "dayOfWeek": "tuesday",
        "startDate": TUE.isoformat(), "endDate": UNTIL.isoformat(), "start": "15:15", "end": "16:00"})
    assert not res.get("ignored"), res.get("ignored")
    row = agenda.load_db()["meetings"][0]
    assert (row["date"], row.get("startTime"), row.get("endTime")) == (TUE.isoformat(), "15:15", "16:00"), row
    assert row["repeat"]["days"] == [1] and row["repeat"]["until"] == UNTIL.isoformat() and not row.get("allDay")


def test_the_text_channel_applies_the_same_write_rules(monkeypatch):
    """The live use case ran on the TEXT channel, which executes data-ops through `widget_data_turn`, not
    through `data_ops.dispatch_and_report` — a rule installed in one of two branches is half a fix."""
    import widgets
    import widgets.server_api as sapi
    from nucleo.flash import widget_data_turn, write_outcome
    from voice import brain_notes
    write_outcome.reset()
    seen = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label="", **k: seen.append((kind, label, k)))

    async def _brain(wid, act, pl):
        return agenda.apply_action(act, pl)

    async def _dispatch(tag, body):
        d = body["data"]
        return agenda.apply_action(d["action"], d["payload"])
    monkeypatch.setattr(sapi, "brain_action", _brain)
    monkeypatch.setattr(widgets, "dispatch_tag", _dispatch)
    brain_notes.drain()

    def _call(action, payload):
        return [{"name": "widget_data", "args": {"widget_id": "agenda", "action": action, "payload": payload}}]
    asyncio.run(widget_data_turn.execute(_call("add_task", {"title": "Tarea semanal de los jueves"}),
                                         text="recursiva los jueves"))
    asyncio.run(widget_data_turn.execute(
        _call("add_meeting", {"title": "Flauta", "date": _next(3).isoformat(), "startTime": "15:30",
                              "repeat": "weekly", "until": UNTIL.isoformat(), "colour": "azul"}),
        text="créame una tarea recursiva los jueves de tres y media, llevar a Abril a flauta"))
    assert not any(t.get("title") == "Tarea semanal de los jueves" for t in agenda.load_db()["tasks"])
    assert "colour" in " ".join(str(n) for n in brain_notes.drain())
    logged = [k["extra"] for kind, label, k in seen if label == "data:add_meeting"]
    assert logged and logged[0]["payload"].get("repeat") == "weekly", "the order must be logged WITH its payload"


def test_the_harness_does_not_call_the_engines_machinery_a_worker():
    """Every round carries `cat: worker` ticks; a case forbidding `worker` failed on a clean run."""
    from tests.use_cases.e2e.agent import verify
    clean = [{"cat": "worker", "kind": k} for k in ("background", "backed", "navegador")] + [
        {"cat": "widget", "kind": "widget"}]
    assert "worker" not in verify.families_in(clean)
    assert "worker" in verify.families_in(clean + [{"cat": "worker", "kind": "worker_start"}])
