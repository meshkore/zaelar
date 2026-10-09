"""A date said by day and month is read, and it wins over a weekday beside it (V2-781 T515, 2026-10-09).

«se estrena el 30 de octubre… queda apuntado para avisarte» scheduled nothing: `parse_when` read tomorrow, a
weekday and «el día N», never «30 de octubre» / «October 30». Worse, «el viernes 30 de octubre» resolved to the NEXT
Friday (the 16th) — a notice set, reported as set, on the wrong day.
"""
from __future__ import annotations

import time

import pytest

from nucleo import scheduler as S
from nucleo.flash import reminder_guards as R

NOW = time.mktime((2026, 10, 9, 23, 0, 0, 0, 1, -1))     # Friday 9 Oct 2026, 23:00


@pytest.mark.parametrize("said, want", [
    ("el 30 de octubre", "2026-10-30 09:00"),
    ("el viernes 30 de octubre a las 10", "2026-10-30 10:00"),
    ("30 de octubre de 2026", "2026-10-30 09:00"),
    ("on October 30", "2026-10-30 09:00"),
    ("Friday, October 30, 2026 at 8", "2026-10-30 08:00"),
    ("30 October", "2026-10-30 09:00"),
    ("el 2 de enero", "2027-01-02 09:00"),                  # already past this year → next year
])
def test_a_day_and_month_is_read(said, want):
    assert S.parse_when(said, now=NOW) == want


def test_a_wrong_or_missing_date_stays_unread():
    assert S.parse_when("el 31 de febrero", now=NOW) == ""
    assert S.parse_when("pronto", now=NOW) == ""


def test_the_promise_to_remind_on_that_day_is_backed():
    assert R._REMIND_VERB_RE.search(R._norm_txt("queda apuntado para avisarte el 30 de octubre"))
    assert R._REMIND_VERB_RE.search(R._norm_txt("I'll get the reminder set up for October 30"))
