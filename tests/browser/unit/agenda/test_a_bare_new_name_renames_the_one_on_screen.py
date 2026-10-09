"""«Cámbiale el nombre al dentista, ponle revisión dental con el doctor Ruiz» renames the one on screen (V2-781 pair 5).

The model sent `update_meeting {title: "Revisión dental con el doctor Ruiz"}` — the NEW name in `title`, nothing
else. No row has that title, so the edit failed with «no encuentro esa cita»; the model then wrote a duplicate
appointment. An update that carries only a title has nothing to change but the name: when that title names no row
and the conversation is on one appointment (`edit.find`'s focus), it is that appointment's new name.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real agenda."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as d
    monkeypatch.setattr(d, "_today", lambda: "2026-10-09")
    d.apply_action("add_meeting", {"title": "Dentista", "date": "2026-10-15", "startTime": "10:00"})
    d.apply_action("add_meeting", {"title": "Piano de Abril", "date": "2026-10-13", "startTime": "17:00"})
    d.apply_action("open_meeting", {"title": "Dentista"})
    return d


def _titles():
    from widgets import store
    return sorted(m["title"] for m in store.load("agenda").get("meetings", []))


def test_a_bare_new_name_renames_the_appointment_in_focus(ag):
    res = ag.apply_action("update_meeting", {"title": "Revisión dental con el doctor Ruiz"})
    assert res.get("ok") is not False, res
    assert _titles() == ["Piano de Abril", "Revisión dental con el doctor Ruiz"]


def test_a_title_that_names_a_row_still_edits_that_row(ag):
    ag.apply_action("update_meeting", {"title": "Piano de Abril", "notes": "llevar partituras"})
    from widgets import store
    piano = next(m for m in store.load("agenda")["meetings"] if m["title"] == "Piano de Abril")
    assert piano.get("notes") == "llevar partituras" and "Dentista" in _titles()


def test_without_a_focus_an_unknown_title_still_asks(ag):
    from widgets import store
    db = store.load("agenda")
    db.pop("focus", None)
    store.save("agenda", db)
    res = ag.apply_action("update_meeting", {"title": "Revisión dental con el doctor Ruiz"})
    assert res.get("ok") is False and "Dentista" in _titles()
