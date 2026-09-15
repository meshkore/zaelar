"""V2-705 · `cancel_meeting` cancels ONE appointment — an ambiguous title is a question, never a bulk delete.

Measured 2026-09-15 (session 878b0122): the handler treated «no title and no date» as «every meeting» and
walked the whole store calling Google — 147 DELETEs, 100 accepted. The decision now lives in
`widgets/agenda/sweep.py::cancel_meeting`, beside `clear_range`, and these cases pin its four outcomes:
one match → gone (locally and in Google, reminder cancelled); no match → `not_found`; a title that names
several DIFFERENT appointments and no date → `ambiguous`, nothing touched; identical duplicates of one
appointment → all of them, because «remove the dentist» means that appointment, not «which of the eleven?».
And the `clear_range` lesson holds: a row Google refuses to delete STAYS.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    return ag


def _seed(ag, meetings):
    from widgets import store
    db = ag.load_db()
    db["meetings"] = meetings
    store.save(ag.WIDGET_ID, db)
    return db


def _google_always_ok(monkeypatch):
    from widgets.agenda import gcal
    deleted = []
    monkeypatch.setattr(gcal, "delete_google", lambda m: deleted.append(m.get("id")) or True)
    return deleted


def test_one_match_is_cancelled_locally_in_google_and_its_reminder_goes_with_it(agenda, monkeypatch):
    _seed(agenda, [{"id": "m1", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00",
                    "reminder_id": "r1", "source": "google", "googleId": "g1"},
                   {"id": "m2", "title": "Seguro", "date": "2099-10-01", "startTime": "10:00"}])
    deleted = _google_always_ok(monkeypatch)
    cancelled = []
    monkeypatch.setattr(agenda, "_cancel_reminder", lambda m: cancelled.append(m.get("reminder_id")))
    res = agenda.apply_action("cancel_meeting", {"title": "dentist"})
    assert res.get("ok") is True and res["result"]["removed"] == 1
    assert [m["id"] for m in agenda.load_db()["meetings"]] == ["m2"]
    assert deleted == ["m1"] and cancelled == ["r1"]


def test_an_empty_title_deletes_nothing_even_when_called_as_a_library(agenda, monkeypatch):
    """The funnel refuses it upstream (`widgets/contract.py`); the handler refuses it too — belt and braces,
    because `apply_action` is also a plain function call."""
    _seed(agenda, [{"id": "m1", "title": "A", "date": "2099-01-01", "startTime": "09:00"},
                   {"id": "m2", "title": "B", "date": "2099-01-02", "startTime": "09:00"}])
    deleted = _google_always_ok(monkeypatch)
    res = agenda.apply_action("cancel_meeting", {})
    assert res.get("ok") is False and res.get("error") == "selector_missing"
    assert len(agenda.load_db()["meetings"]) == 2 and deleted == []


def test_a_title_that_matches_two_different_days_is_a_question_not_a_deletion(agenda, monkeypatch):
    _seed(agenda, [{"id": "m1", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00"},
                   {"id": "m2", "title": "Dentist", "date": "2099-11-03", "startTime": "09:30"},
                   {"id": "m3", "title": "Seguro", "date": "2099-10-01", "startTime": "10:00"}])
    deleted = _google_always_ok(monkeypatch)
    res = agenda.apply_action("cancel_meeting", {"title": "Dentist"})
    assert res.get("ok") is False and res.get("error") == "ambiguous"
    assert len(res["options"]) == 2 and any("2099-11-03" in o for o in res["options"])
    assert len(agenda.load_db()["meetings"]) == 3 and deleted == []


def test_the_same_title_with_a_date_picks_that_one(agenda, monkeypatch):
    _seed(agenda, [{"id": "m1", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00"},
                   {"id": "m2", "title": "Dentist", "date": "2099-11-03", "startTime": "09:30"}])
    _google_always_ok(monkeypatch)
    res = agenda.apply_action("cancel_meeting", {"title": "Dentist", "date": "2099-11-03"})
    assert res.get("ok") is True and [m["id"] for m in agenda.load_db()["meetings"]] == ["m1"]


def test_identical_duplicates_are_one_appointment_and_go_together(agenda, monkeypatch):
    """The calendar held 11 copies of «Dentist» on 16/09 at 17:00. «Remove the dentist» means that one."""
    _seed(agenda, [{"id": f"m{i}", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00"}
                   for i in range(11)] + [{"id": "x", "title": "Other", "date": "2099-09-17", "startTime": "08:00"}])
    _google_always_ok(monkeypatch)
    res = agenda.apply_action("cancel_meeting", {"title": "Dentist"})
    assert res.get("ok") is True and res["result"]["removed"] == 11
    assert [m["id"] for m in agenda.load_db()["meetings"]] == ["x"]


def test_no_match_is_said_with_what_is_coming_up(agenda, monkeypatch):
    _seed(agenda, [{"id": "m1", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00"}])
    deleted = _google_always_ok(monkeypatch)
    res = agenda.apply_action("cancel_meeting", {"title": "Kryptonite"})
    assert res.get("ok") is False and res.get("error") == "not_found"
    assert "Dentist" in str(res.get("detail")) and deleted == []
    assert len(agenda.load_db()["meetings"]) == 1


def test_a_row_google_refuses_to_delete_stays_and_the_turn_is_told(agenda, monkeypatch):
    _seed(agenda, [{"id": "m1", "title": "Dentist", "date": "2099-09-16", "startTime": "17:00",
                    "source": "google", "googleId": "g1"}])
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "delete_google", lambda m: False)
    res = agenda.apply_action("cancel_meeting", {"title": "Dentist"})
    assert res.get("ok") is False and "Google" in str(res.get("error"))
    assert len(agenda.load_db()["meetings"]) == 1, "reporting a deletion the cloud never made is the V2-693 lie"


def test_the_handler_no_longer_owns_the_decision():
    """Structural: the branch in `data.py` persists and answers; matching and the one-appointment rule live in
    `sweep.py`, beside `clear_range`, where the erase doctrine is written once."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/agenda/data.py").read_text(encoding="utf-8")
    branch = src[src.index('elif action == "cancel_meeting":'):src.index('elif action == "set_reminder":')]
    assert "sweep.cancel_meeting(" in branch
    assert 'db["meetings"] =' not in branch, "the branch must not filter the list itself again"
