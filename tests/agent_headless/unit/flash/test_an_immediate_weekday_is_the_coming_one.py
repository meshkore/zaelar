"""«El jueves que viene» said on a Wednesday is TOMORROW (agenda-everyday-edits ES, 2026-10-14). Node 2.585.

Measured (report 20261014-005211, step 1): on Wednesday 2026-10-14 «Apúntame el dentista el jueves que viene a las
diez» reached the agenda as `add_meeting {date: 2026-10-22}` — the model's own ISO day, one week late, though the
prompt's lookup said «thursday 2026-10-15». Every later edit then worked on the wrong Thursday. The EN twin («next
Thursday» → 15) passed and is graded by the same check. `agenda_said_day.payload` puts back the IMMEDIATE coming
weekday when the model's day is exactly one week after it, on both channels; a sentence that names the week ahead
is left alone.
"""
from __future__ import annotations

import datetime as dt
import pathlib

from nucleo.flash import agenda_said_day as SD

ENGINE = pathlib.Path(__file__).resolve().parents[4]
WED = dt.date(2026, 10, 14)


def _fix(said, payload, action="add_meeting", wid="agenda"):
    return SD.payload(wid, action, payload, said, today=WED)


def test_the_measured_dentist_lands_on_tomorrow():
    got = _fix("Apúntame el dentista el jueves que viene a las diez de la mañana",
               {"title": "Dentista", "date": "2026-10-22", "time": "10:00"})
    assert got["date"] == "2026-10-15"


def test_este_and_proximo_are_the_coming_one_too():
    assert _fix("ponme el gimnasio este viernes", {"title": "Gimnasio", "date": "2026-10-23"})["date"] == "2026-10-16"
    assert _fix("el próximo lunes, la reunión", {"title": "Reunión", "date": "2026-10-26"})["date"] == "2026-10-19"


def test_english_next_thursday_stays_tomorrow():
    """The EN twin already sends the coming day: untouched. And its one-week slip is put back the same way."""
    assert _fix("Put the dentist down for next Thursday at ten", {"date": "2026-10-15"})["date"] == "2026-10-15"
    assert _fix("Put the dentist down for next Thursday at ten", {"date": "2026-10-22"})["date"] == "2026-10-15"


def test_the_week_ahead_he_names_is_kept():
    for said in ("el jueves de la semana que viene", "next week on Thursday", "el jueves que viene no, dentro de dos semanas"):
        assert _fix(said, {"date": "2026-10-22"})["date"] == "2026-10-22", said


def test_a_bare_weekday_and_a_spoken_day_are_left_to_the_widget():
    assert _fix("el jueves a las diez", {"date": "2026-10-22"})["date"] == "2026-10-22"
    assert _fix("el jueves que viene", {"date": "jueves"})["date"] == "jueves"


def test_another_weekday_or_another_card_is_untouched():
    assert _fix("el jueves que viene", {"date": "2026-10-23"})["date"] == "2026-10-23"
    assert _fix("el jueves que viene", {"date": "2026-10-22"}, wid="mensajeria")["date"] == "2026-10-22"


def test_the_move_destination_is_aligned_too():
    got = _fix("pásame el dentista al jueves que viene", {"title": "Dentista", "newDate": "2026-10-22"}, "move_meeting")
    assert got["newDate"] == "2026-10-15"


def test_the_turn_asks_it():
    voice = (ENGINE / "nucleo/flash/tool_executor_widget_calls.py").read_text(encoding="utf-8")
    assert "_txw._said_day.payload(wid, action_name, payload, _txw._bnotes.operator_half(text))" in voice
