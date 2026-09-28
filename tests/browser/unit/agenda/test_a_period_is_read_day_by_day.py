#
# test_a_period_is_read_day_by_day.py — demo pass 34 (2026-09-29), R3.
#
# «find me five days in her vacation where i'm free and tell me the dates» — the model read the agenda for
# «What meetings does Richard have between December 20, 2026 and January 4, 2027?». Neither date was understood
# (only ISO dates and today/tomorrow were), so the read fell back to the next eight appointments, all in
# September, and the answer was «I can't honestly confirm you're free on any of those days». A period is
# answered as a period: every day between its ends, which ones have an hour taken, and the all-day rows once.
#
import pytest

from widgets.agenda import data as agenda_data
from widgets.agenda import query

_MEETINGS = [
    {"id": "1", "title": "ZAELAR weekly review", "date": "2026-09-30", "startTime": "09:00", "endTime": "09:30"},
    {"id": "2", "title": "Dentist", "date": "2026-12-22", "startTime": "10:00", "endTime": "11:00"},
    {"id": "3", "title": "Anna's vacation", "date": "2026-12-20", "allDay": True,
     "repeat": {"freq": "daily", "until": "2027-01-04"}},
]


@pytest.fixture(autouse=True)
def _calendar(monkeypatch):
    monkeypatch.setattr(agenda_data, "load_db", lambda: {"meetings": [dict(m) for m in _MEETINGS]})
    monkeypatch.setattr(query, "_today", lambda: "2026-09-29")


@pytest.mark.parametrize("question", [
    "What meetings does Richard have between December 20, 2026 and January 4, 2027?",
    "¿Qué citas tiene entre el 20 de diciembre de 2026 y el 4 de enero de 2027?",
    "meetings from 2026-12-20 to 2027-01-04",
])
def test_a_period_is_answered_with_every_day_in_it(question):
    out = query.read_query(question)
    assert "2026-12-20" in out and "2027-01-04" in out
    assert "Periodo" in out, out
    free = out.split("Días SIN ninguna cita con hora")[1].split("\n")[0]
    assert "2026-12-21" in free and "2026-12-23" in free
    assert "2026-12-22" not in free, "the dentist's day was listed as free"
    assert "Dentist" in out and "Anna's vacation" in out
    assert "ZAELAR weekly review" not in out, "an appointment outside the period leaked in"


def test_a_month_word_with_no_day_next_to_it_is_not_a_date():
    assert query._dates_in("Richard may have 2 meetings") == []


def test_a_single_day_keeps_its_own_record():
    out = query.read_query("What do I have on 2026-09-30?")
    assert "Periodo" not in out and "ZAELAR weekly review" in out
