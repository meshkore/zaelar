"""«Quítalas todas» / «kill all entries like this» cancels EVERY appointment the title matches — the plural is the
whole set, never «which one?» (node 2.916).

Live, 2026-10-28 16:43 (T11-T15): another agent had written 176 one-day «Comedor del niño» rows into his Google
calendar by mistake. Four turns of «hay que quitarlas todas», «kill all series of comedor», «kill all entries like
this» were each answered with «Which one exactly? I have …» — V2-705's ambiguity question, right for ONE
appointment, wrong for an order said in the plural. The model now says `all: true`; the door cancels every match,
one trash entry holds the set (`restore_meeting` brings all back), Google is asked row by row and a row it refuses
STAYS. The two older guards are kept: without `all` the question stands, and an empty title never means «every».

Disarm: with `sweep.every` answering False, the first test goes red.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    return ag


def _rows(n=5):
    return [{"id": f"c{i}", "title": "Comedor del niño", "date": f"2099-02-{i + 1:02d}", "startTime": "14:30",
             "source": "google", "googleId": f"g{i}", "reminder_id": f"r{i}"} for i in range(n)] + \
           [{"id": "x1", "title": "Dentista", "date": "2099-02-03", "startTime": "10:00"}]


def _seed(ag, meetings):
    from widgets import store
    db = ag.load_db()
    db["meetings"] = meetings
    store.save(ag.WIDGET_ID, db)


def test_all_true_cancels_every_match_in_google_and_keeps_the_rest(agenda, monkeypatch):
    from widgets.agenda import gcal
    deleted, cancelled = [], []
    monkeypatch.setattr(gcal, "delete_google", lambda m: deleted.append(m["id"]) or True)
    monkeypatch.setattr(agenda, "_cancel_reminder", lambda m: cancelled.append(m.get("reminder_id")))
    _seed(agenda, _rows())
    res = agenda.apply_action("cancel_meeting", {"title": "comedor del niño", "all": True})
    assert res.get("ok") is True and res["result"]["removed"] == 5 and res["result"]["days"] == 5
    assert [m["id"] for m in agenda.load_db()["meetings"]] == ["x1"]
    assert sorted(deleted) == [f"c{i}" for i in range(5)] and len(cancelled) == 5


def test_restore_brings_the_whole_set_back_as_one(agenda, monkeypatch):
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "delete_google", lambda m: True)
    monkeypatch.setattr(gcal, "commit_meeting", lambda db, m: db.setdefault("meetings", []).append(m))
    monkeypatch.setattr(agenda, "_cancel_reminder", lambda m: None)
    monkeypatch.setattr(agenda, "_schedule_reminder", lambda *a, **k: ("", ""))
    _seed(agenda, _rows(3))
    agenda.apply_action("cancel_meeting", {"title": "Comedor", "all": "true"})
    assert len(agenda.load_db()["meetings"]) == 1
    agenda.apply_action("restore_meeting", {})
    assert len(agenda.load_db()["meetings"]) == 4


def test_a_row_google_refuses_stays_and_is_reported(agenda, monkeypatch):
    from widgets.agenda import gcal
    monkeypatch.setattr(gcal, "delete_google", lambda m: m["id"] != "c2")
    monkeypatch.setattr(agenda, "_cancel_reminder", lambda m: None)
    _seed(agenda, _rows(4))
    res = agenda.apply_action("cancel_meeting", {"title": "comedor", "all": True})
    assert res.get("ok") is False and "c2" in [m["id"] for m in agenda.load_db()["meetings"]]
    assert res["result"]["removed"] == 3


def test_without_all_the_question_stands_and_an_empty_title_is_never_every(agenda, monkeypatch):
    from widgets.agenda import gcal
    deleted = []
    monkeypatch.setattr(gcal, "delete_google", lambda m: deleted.append(m["id"]) or True)
    _seed(agenda, _rows(3))
    res = agenda.apply_action("cancel_meeting", {"title": "comedor"})
    assert res.get("ok") is False and res.get("error") == "ambiguous" and deleted == []
    res = agenda.apply_action("cancel_meeting", {"title": "", "all": True})
    assert res.get("ok") is False and res.get("error") == "selector_missing" and deleted == []
    assert len(agenda.load_db()["meetings"]) == 4
