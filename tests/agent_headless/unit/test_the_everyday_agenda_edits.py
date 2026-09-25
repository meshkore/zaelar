"""V2-770 — the everyday things a person does to an appointment after writing it, each through the product.

His request, 2026-09-25: *«piensa un poco cuál es la operativa básica… abrir un item para que aparezca la
ficha, pedir cerrarla, modificar el título, la descripción o la hora, cancelar una cita recursiva… la gente no
pide las cosas de forma precisa»*. Walking that list against the agenda found four doors missing and one
lying:

  · the detail card could only be opened by a click, and nothing could close it;
  · an END time could not be said — `update_meeting` dropped `endTime` without a word (a key it knew);
  · one day of a series could not move without moving the whole series;
  · «a partir de enero ya no hay piano» had no door short of knowing the `until` field;
  · a date said by its name («el 14 de octubre») resolved to TODAY;
  · move/update found an appointment by exact substring while cancel was tolerant — the same reference found
    a row for one verb and not for the other.

Store isolated by the root conftest; the scheduler and Google replaced by recorders.
"""
from __future__ import annotations

import datetime as dt

import pytest

from widgets.agenda import data as agenda, gcal, reminders

TODAY = dt.date.today()


def _next(weekday: int, after: dt.date = TODAY) -> dt.date:
    return after + dt.timedelta(days=(weekday - after.weekday()) % 7 or 7)


TUE = _next(1)
UNTIL = TUE + dt.timedelta(weeks=20)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    patched: list[dict] = []
    monkeypatch.setattr(gcal, "svc", lambda: None)
    monkeypatch.setattr(gcal, "_patch_series", lambda m: patched.append(dict(m)))
    notices: list[tuple] = []

    def _sched(title, date, start, at="", before_minutes=120):
        notices.append((title, date, start))
        return f"job{len(notices)}", f"{date} {start}"
    monkeypatch.setattr(agenda, "_schedule_reminder", _sched)
    monkeypatch.setattr(reminders, "_schedule_reminder", _sched)
    monkeypatch.setattr(agenda, "_cancel_reminder", lambda m: None)
    monkeypatch.setattr(reminders, "_cancel_reminder", lambda m: None)
    agenda.apply_action("clear_all", {})
    yield {"notices": notices, "patched": patched}
    agenda.apply_action("clear_all", {})


def _piano():
    return agenda.apply_action("add_meeting", {
        "title": "Piano de Abril", "date": TUE.isoformat(), "startTime": "15:15", "endTime": "16:00",
        "repeat": "weekly", "until": UNTIL.isoformat()})


def _dentist(day: dt.date | None = None):
    return agenda.apply_action("add_meeting", {
        "title": "Renovar el seguro del coche", "date": (day or TUE + dt.timedelta(days=1)).isoformat(),
        "startTime": "10:00", "endTime": "10:30"})


def _rows(title: str) -> list[dict]:
    return [m for m in agenda.load_db()["meetings"] if title.lower() in m["title"].lower()]


# ── the card, by voice ─────────────────────────────────────────────────────────────────────────────────────
def test_opening_an_appointment_pushes_its_card_on_its_day():
    _dentist()
    res = agenda.apply_action("open_meeting", {"title": "seguro del coche"})
    assert res.get("ok") is not False, res
    v = res["view"]
    assert v["open"] == {"title": "Renovar el seguro del coche", "date": (TUE + dt.timedelta(days=1)).isoformat()}
    assert v["sel"] == v["open"]["date"]


def test_opening_a_series_lands_on_its_next_day_or_the_one_he_said():
    _piano()
    assert agenda.apply_action("open_meeting", {"title": "piano"})["view"]["open"]["date"] == TUE.isoformat()
    wk3 = (TUE + dt.timedelta(weeks=2)).isoformat()
    assert agenda.apply_action("open_meeting", {"title": "piano", "date": wk3})["view"]["open"]["date"] == wk3


def test_opening_writes_nothing_but_the_view():
    _dentist()
    before = agenda.load_db()["meetings"]
    agenda.apply_action("open_meeting", {"title": "seguro"})
    assert agenda.load_db()["meetings"] == before


def test_opening_an_unknown_appointment_says_so():
    res = agenda.apply_action("open_meeting", {"title": "cena con Marta"})
    assert res.get("ok") is False and "no encuentro" in res["error"]


def test_closing_the_card_is_a_new_push_that_names_no_day():
    _dentist()
    n = agenda.apply_action("open_meeting", {"title": "seguro"})["view"]["n"]
    v = agenda.apply_action("close_meeting", {})["view"]
    assert v["close"] is True and v["n"] == n + 1 and "sel" not in v


def test_both_are_declared_view_actions():
    from widgets import actions, runtime
    spec = next(w for w in runtime.catalog() if w.get("id") == "agenda")["actions"]
    for name in ("open_meeting", "close_meeting"):
        assert actions.is_view(spec[name], name), name


# ── the hour, the end, the day ─────────────────────────────────────────────────────────────────────────────
def test_an_end_time_said_in_an_edit_is_kept_not_dropped():
    _dentist()
    res = agenda.apply_action("update_meeting", {"title": "seguro del coche", "endTime": "11:15"})
    assert res.get("ok") is not False, res
    m = _rows("seguro")[0]
    assert (m["startTime"], m["endTime"]) == ("10:00", "11:15")


def test_a_duration_moves_the_end():
    _dentist()
    agenda.apply_action("move_meeting", {"title": "seguro", "duration": 90})
    assert _rows("seguro")[0]["endTime"] == "11:30"


def test_a_new_start_keeps_the_length():
    _dentist()
    agenda.apply_action("update_meeting", {"title": "seguro", "startTime": "12:00"})
    m = _rows("seguro")[0]
    assert (m["startTime"], m["endTime"]) == ("12:00", "12:30")


def test_an_edit_with_a_time_and_a_detail_does_both():
    _dentist()
    agenda.apply_action("update_meeting", {"title": "seguro", "newTime": "09:00", "location": "Mapfre"})
    m = _rows("seguro")[0]
    assert (m["startTime"], m.get("location")) == ("09:00", "Mapfre")


def test_a_day_said_by_its_name_is_that_day_not_today():
    _dentist()
    agenda.apply_action("move_meeting", {"title": "seguro", "newDate": "el 14 de octubre"})
    d = _rows("seguro")[0]["date"]
    assert d[5:] == "10-14" and d >= TODAY.isoformat()


def test_move_finds_the_row_as_tolerantly_as_cancel_does():
    _dentist()
    res = agenda.apply_action("move_meeting", {"title": "renovar seguro coche", "newTime": "18:00"})
    assert res.get("ok") is not False, res
    assert _rows("seguro")[0]["startTime"] == "18:00"


def test_a_rename_and_a_description():
    _dentist()
    agenda.apply_action("update_meeting", {"title": "seguro", "newTitle": "Seguro coche (Mapfre)",
                                           "notes": "llevar la ficha técnica"})
    m = _rows("Mapfre")[0]
    assert m["title"] == "Seguro coche (Mapfre)" and m["notes"] == "llevar la ficha técnica"


# ── one day of a series ────────────────────────────────────────────────────────────────────────────────────
def test_a_dated_move_of_a_series_moves_that_day_only(_isolated):
    _piano()
    wk2 = (TUE + dt.timedelta(weeks=1)).isoformat()
    res = agenda.apply_action("move_meeting", {"title": "piano", "date": wk2, "newTime": "17:00"})
    assert res.get("ok") is not False, res
    series = next(m for m in _rows("piano") if m.get("repeat"))
    single = [m for m in _rows("piano") if not m.get("repeat")]
    assert wk2 in series["repeat"]["skip"]
    assert [(m["date"], m["startTime"], m["endTime"]) for m in single] == [(wk2, "17:00", "17:45")]
    days = {m["date"]: m["startTime"] for m in agenda.view_data()["meetings"] if m["title"] == "Piano de Abril"}
    assert days[wk2] == "17:00" and days[TUE.isoformat()] == "15:15"
    assert (TUE + dt.timedelta(weeks=2)).isoformat() in days


def test_a_dated_move_to_another_day_leaves_the_rest_of_the_series():
    _piano()
    wk2 = TUE + dt.timedelta(weeks=1)
    agenda.apply_action("move_meeting", {"title": "piano", "date": wk2.isoformat(),
                                         "newDate": (wk2 + dt.timedelta(days=1)).isoformat()})
    days = sorted(m["date"] for m in agenda.view_data()["meetings"] if m["title"] == "Piano de Abril")
    assert wk2.isoformat() not in days and (wk2 + dt.timedelta(days=1)).isoformat() in days
    assert (TUE + dt.timedelta(weeks=3)).isoformat() in days


def test_an_undated_move_still_moves_the_whole_series():
    _piano()
    agenda.apply_action("move_meeting", {"title": "piano", "newTime": "16:00"})
    assert {m["startTime"] for m in agenda.view_data()["meetings"] if m["title"] == "Piano de Abril"} == {"16:00"}


def test_a_dated_move_on_a_day_the_series_does_not_have_is_refused():
    _piano()
    res = agenda.apply_action("move_meeting", {"title": "piano", "date": (TUE + dt.timedelta(days=2)).isoformat(),
                                               "newTime": "17:00"})
    assert res.get("ok") is False and "no cae" in res["error"]
    assert not next(m for m in _rows("piano") if m.get("repeat"))["repeat"].get("skip")


# ── ending a series from a day on ──────────────────────────────────────────────────────────────────────────
def test_from_a_day_on_ends_the_series_the_day_before(_isolated):
    _piano()
    cut = TUE + dt.timedelta(weeks=5)
    res = agenda.apply_action("cancel_meeting", {"title": "piano", "from": cut.isoformat()})
    assert res.get("ok") is not False, res
    days = sorted(m["date"] for m in agenda.view_data()["meetings"] if m["title"] == "Piano de Abril")
    assert days and days[0] == TUE.isoformat() and days[-1] < cut.isoformat()
    assert len(days) == 5


def test_a_cut_never_extends_a_series():
    _piano()
    agenda.apply_action("cancel_meeting", {"title": "piano", "from": (TUE + dt.timedelta(weeks=3)).isoformat()})
    before = next(m for m in _rows("piano") if m.get("repeat"))["repeat"]["until"]
    agenda.apply_action("cancel_meeting", {"title": "piano", "from": (UNTIL + dt.timedelta(weeks=8)).isoformat()})
    assert next(m for m in _rows("piano") if m.get("repeat"))["repeat"]["until"] == before


def test_a_series_named_with_nothing_still_asks_and_names_the_new_way():
    _piano()
    res = agenda.apply_action("cancel_meeting", {"title": "piano"})
    assert res.get("ok") is False and "`from`" in res["error"]
    assert _rows("piano")


# ── the Google mirror of a series ──────────────────────────────────────────────────────────────────────────
def test_the_google_body_of_a_series_carries_the_days_it_skips():
    from connectors.calendar import google_calendar as gc
    body = gc.meeting_to_event({"title": "Piano", "date": "2026-09-29", "startTime": "15:15", "endTime": "16:00",
                                "rrule": "RRULE:FREQ=WEEKLY;BYDAY=TU", "exdates": ["2026-10-06", "2026-10-13"]})
    ex = [r for r in body["recurrence"] if r.startswith("EXDATE")]
    assert len(ex) == 1 and "20261006T151500" in ex[0] and "20261013T151500" in ex[0]


def _on_google():
    from widgets import store
    db = agenda.load_db()
    db["meetings"][0]["googleSeriesId"] = "gid-1"
    store.save(agenda.WIDGET_ID, db)


@pytest.mark.parametrize("edit", [
    ("update_meeting", lambda: {"title": "piano", "until": (TUE + dt.timedelta(weeks=4)).isoformat()}),
    ("cancel_meeting", lambda: {"title": "piano", "date": (TUE + dt.timedelta(weeks=1)).isoformat()}),
    ("cancel_meeting", lambda: {"title": "piano", "from": (TUE + dt.timedelta(weeks=3)).isoformat()}),
    ("move_meeting", lambda: {"title": "piano", "date": (TUE + dt.timedelta(weeks=1)).isoformat(), "newTime": "17:00"}),
], ids=["new-end", "skip-a-day", "cut-from", "move-one-day"])
def test_every_edit_of_our_series_reaches_its_google_master(_isolated, edit):
    _piano()
    _on_google()
    action, payload = edit
    res = agenda.apply_action(action, payload())
    assert res.get("ok") is not False, res
    assert _isolated["patched"] and _isolated["patched"][-1]["googleSeriesId"] == "gid-1"


# ── «it»: the appointment the conversation is on ───────────────────────────────────────────────────────────
def test_an_edit_with_no_title_lands_on_the_appointment_just_touched():
    _dentist()
    _piano()
    agenda.apply_action("update_meeting", {"title": "seguro", "newTitle": "Revisión con el doctor Ruiz"})
    res = agenda.apply_action("update_meeting", {"notes": "llevar las radiografías"})
    assert res.get("ok") is not False, res
    agenda.apply_action("move_meeting", {"endTime": "11:15"})
    m = _rows("Ruiz")[0]
    assert m["notes"] == "llevar las radiografías" and m["endTime"] == "11:15"
    assert not next(p for p in _rows("piano") if p.get("repeat")).get("notes")


def test_no_title_and_nothing_in_focus_still_says_it_cannot_find_it(monkeypatch):
    from widgets.agenda import edit
    _dentist()
    monkeypatch.setattr(edit, "FOCUS_TTL_S", -1)
    res = agenda.apply_action("update_meeting", {"notes": "x"})
    assert res.get("ok") is False


def test_no_title_never_reaches_a_deletion():
    _dentist()
    agenda.apply_action("open_meeting", {"title": "seguro"})
    res = agenda.apply_action("cancel_meeting", {})
    assert res.get("ok") is False and _rows("seguro")


def test_a_reference_that_carries_the_title_plus_a_gloss_finds_it():
    _piano()
    wk2 = (TUE + dt.timedelta(weeks=1)).isoformat()
    res = agenda.apply_action("cancel_meeting", {"title": f"Piano de Abril del martes {wk2}", "date": wk2})
    assert res.get("ok") is not False, res
    assert wk2 in next(m for m in _rows("piano") if m.get("repeat"))["repeat"]["skip"]


def test_the_whole_series_takes_its_moved_days_with_it():
    _piano()
    wk2 = (TUE + dt.timedelta(weeks=1)).isoformat()
    agenda.apply_action("move_meeting", {"title": "piano", "date": wk2, "newTime": "17:00"})
    res = agenda.apply_action("cancel_meeting", {"title": "piano", "whole": True})
    assert res.get("ok") is not False, res
    assert not _rows("piano")


def test_a_refusal_is_a_sentence_he_can_hear_never_a_code():
    agenda.apply_action("add_meeting", {"title": "Piano", "date": TUE.isoformat(), "startTime": "10:00"})
    agenda.apply_action("add_meeting", {"title": "Piano", "date": (TUE + dt.timedelta(days=1)).isoformat(),
                                        "startTime": "11:00"})
    amb = agenda.apply_action("cancel_meeting", {"title": "piano"})
    miss = agenda.apply_action("cancel_meeting", {"title": "cena con Marta"})
    for r in (amb, miss):
        assert r.get("ok") is False and r.get("message") and r["message"] not in ("ambiguous", "not_found")
