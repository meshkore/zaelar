"""A reminder keeps the YEAR the conversation said, and a day already gone by schedules nothing (2026-10-11).

`find-a-future-release-and-remind-me__us` (round 2026-10-11 02:31, today 2026-10-11): the search said «premieres on
September 30th, 2026», he asked «Oh nice, September 30th. Could you remind me on premiere day?», zaelar said «I'll
set that reminder for you.» and the job was scheduled for 2027-09-30 09:00. `parse_when` rolled his yearless
«September 30th» to next year because it had gone by; the agenda row said 2026-09-30. The job's prompt was then
the lookup intent (his raw question) because the fact's day (2026) no longer matched the job's (2027).
"""
from __future__ import annotations

import time

import pytest

from nucleo.pulse import scheduler as S
from nucleo.flash import reminder_guards as R
from nucleo.flash import reminder_year as Y

TODAY = time.mktime((2026, 10, 11, 2, 30, 0, 0, 1, -1))     # the run's own clock
BEFORE = time.mktime((2026, 9, 1, 10, 0, 0, 0, 1, -1))      # the same conversation, a month earlier

FACT = ("The new season is called Dexter: Resurrection, and it premieres on September 30th, 2026 on Showtime. "
        "So it's coming this fall, just like you thought.")
WINDOW = [{"role": "user", "content": "Hey, I really like the show Dexter and I think a new season comes out this "
                                      "fall. Can you find out when it premieres and let me know?"},
          {"role": "assistant", "content": FACT}]
ASK = "Oh nice, September 30th. Could you remind me on premiere day? Thanks."
REPLY = "I'll set that reminder for you."
W = WINDOW + [{"role": "user", "content": ASK}]


@pytest.fixture(autouse=True)
def no_jobs(monkeypatch):
    monkeypatch.setattr(S, "list_jobs", lambda active_only=True: [])


def _at(monkeypatch, now):
    monkeypatch.setattr(S.time, "time", lambda: now)


def test_the_model_s_own_tag_is_never_rolled_to_next_year(monkeypatch):
    """Its ISO date in the past, or his yearless words: the year said wins, and `create` then refuses the past."""
    _at(monkeypatch, TODAY)
    for spec in ("2026-09-30 09:00", "September 30", "2027-09-30 09:00"):
        got = R.safe_reminder_schedule(spec, REPLY, ASK, W)
        assert got == "2026-09-30 09:00", (spec, got)
        assert not S.create("x", got, now=TODAY)["ok"]          # no job on a day already gone by


def test_the_mentions_carry_the_year_and_the_words():
    assert S.dated_mentions(FACT) == [("2026-09-30", "September 30th, 2026")]
    assert S.dated_mentions("el 30 de septiembre de 2026 y el 2 de octubre") == [("2026-09-30", "30 de septiembre de 2026")]
    assert S.dated_mentions("September 30th") == []
    assert Y.passed("2026-10-10 09:00", now=TODAY) and not Y.passed("2026-10-11 09:00", now=TODAY)


def test_a_today_tag_is_not_corrected_to_a_rolled_over_day(monkeypatch):
    """The V2-356 correction (a tag firing TODAY while he named another day) must not hand back next year's day."""
    _at(monkeypatch, TODAY)
    today = time.strftime("%Y-%m-%d 23:00", time.localtime(TODAY))
    assert R.safe_reminder_schedule(today, REPLY, ASK, W) == today
