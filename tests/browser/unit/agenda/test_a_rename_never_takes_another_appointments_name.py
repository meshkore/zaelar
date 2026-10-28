"""A rename never gives an appointment ANOTHER appointment's name (agenda-everyday-edits EN, 2026-10-11).

«Move next Tuesday's piano to Wednesday, just that week» was answered «Moving just that day.» with
`update_meeting {item: "Abril's piano lesson…", newTitle: "Dental checkup with Dr Ruiz"}` (the screen verdict read
`move_meeting` 1.00). The series took the dentist's name, and the next three steps — skip a day, end the series from
December, cancel Dr Ruiz — each named two appointments that could no longer be told apart. Node 2.445: the write is
refused with the reason and the right door (the model's in-turn correction reads it), and nothing changes; a rename
to a free name, or to its own name, still lands.
"""
from __future__ import annotations

import datetime as dt

import pytest

from widgets.agenda import data as agenda


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    from widgets import store
    from nucleo.pulse import scheduler
    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    monkeypatch.setattr(scheduler, "create", lambda prompt, stamp, name="", origin="cron": {"ok": True, "id": "j"})
    monkeypatch.setattr(scheduler, "cancel", lambda ref: None)


def _day(n):
    return (dt.date.today() + dt.timedelta(days=n)).isoformat()


def _seed():
    agenda.apply_action("add_meeting", {"title": "Dental checkup with Dr Ruiz", "date": _day(4), "startTime": "11:30"})
    agenda.apply_action("add_meeting", {"title": "Abril's piano lesson", "date": _day(2), "startTime": "17:00",
                                        "endTime": "18:00", "repeat": "weekly", "days": "tuesday",
                                        "until": _day(80)})


def _titles():
    return sorted(str(m.get("title")) for m in agenda.load_db()["meetings"])


def test_the_measured_rename_is_refused_and_nothing_changes():
    _seed()
    before = _titles()
    got = agenda.apply_action("update_meeting", {"title": "Abril's piano lesson",
                                                 "newTitle": "Dental checkup with Dr Ruiz"})
    assert got.get("ok") is False and "move_meeting" in str(got.get("error"))
    assert _titles() == before


def test_the_same_name_in_other_case_is_another_appointments_name_too():
    _seed()
    got = agenda.apply_action("update_meeting", {"title": "piano", "newTitle": "dental checkup with dr ruiz"})
    assert got.get("ok") is False


def test_a_free_name_still_renames():
    _seed()
    agenda.apply_action("update_meeting", {"title": "Dental checkup", "newTitle": "Revisión con el doctor Ruiz"})
    assert "Revisión con el doctor Ruiz" in _titles()


def test_its_own_name_is_not_taken():
    _seed()
    got = agenda.apply_action("update_meeting", {"title": "Abril's piano lesson", "newTitle": "Abril's piano lesson",
                                                 "notes": "bring the score"})
    assert got.get("ok") is not False
