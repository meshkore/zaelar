"""An appointment's title says WHAT, never when — «… a las diez de la [mañana]» outlived the move to 17:00 (2026-10-10).

Use case `agenda-appointment-lifecycle`, ES: the surviving row was titled «una revision del coche en el taller el 20
de octubre a las diez de la» although it had been moved to 17:00. The when lives in `date`/`startTime`; a copy in
the title goes stale the first time the appointment moves. Only complete date/time phrases are cut, a time phrase
only when its hour can be read (that hour is kept), and titles that merely carry a number keep it. Node 2.401.
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("raw, title, hour", [
    ("una revision del coche en el taller el 20 de octubre a las diez de la", "Revision del coche en el taller", "10:00"),
    ("car service at the garage on October 20 at ten in the morning", "Car service at the garage", "10:00"),
    ("Dentista a las 17:00", "Dentista", "17:00"),
    ("Cena a las nueve y media de la noche", "Cena", "21:30"),
    ("Piano a las cinco", "Piano", "17:00"),
    ("Gym at 7am", "Gym", "07:00"),
    ("Lunch at noon", "Lunch", "12:00"),
])
def test_the_date_and_time_phrases_leave_the_title(raw, title, hour):
    from widgets.agenda import title_when as tw
    assert tw.split_when(raw) == (title, hour)


@pytest.mark.parametrize("raw", [
    "Revisión del coche en el taller", "Clase 3 de piano", "Room 101", "Revisión de los 10.000 km",
    "Meeting at 10 Downing Street", "Fiesta del 12 de octubre", "at 5pm", "Dentista a las diez menos cuarto",
])
def test_a_title_that_only_carries_a_number_keeps_it(raw):
    from widgets.agenda import title_when as tw
    assert tw.split_when(raw)[0] == raw


@pytest.fixture
def ag(tmp_path, monkeypatch):
    """ISOLATED store and scheduler — never the operator's real agenda or jobs."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from nucleo import scheduler as S
    monkeypatch.setattr(S, "create", lambda prompt, stamp, **k: {"ok": True, "id": "1", "display": stamp})
    monkeypatch.setattr(S, "supersede_loose_notices", lambda *a, **k: None)
    from widgets.agenda import data as d
    return d


def _rows():
    from widgets import store
    return store.load("agenda")["meetings"]


def test_a_written_title_carries_no_time_and_its_hour_is_the_start(ag):
    ag.apply_action("add_meeting", {"title": "Revisión del coche a las diez de la mañana", "date": "2027-10-20"})
    (m,) = _rows()
    assert m["title"] == "Revisión del coche" and m.get("startTime") == "10:00" and not m.get("allDay")


def test_an_explicit_start_wins_over_the_title(ag):
    ag.apply_action("add_meeting", {"title": "Dentista a las diez", "date": "2027-10-20", "startTime": "17:00"})
    (m,) = _rows()
    assert m["title"] == "Dentista" and m["startTime"] == "17:00"


def test_without_a_date_the_date_phrase_stays_in_the_title(ag):
    """A date phrase is the only copy of the day when no `date` came: it is not cut."""
    from widgets.agenda import title_when as tw
    assert tw.split_when("Fiesta el 20 de octubre", date=False)[0] == "Fiesta el 20 de octubre"
