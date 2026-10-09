"""«Can you set a reminder for me on the premiere day?» rings on the day the conversation just named (V2-781 pair 3).

EN round 2026-10-10: zaelar had said «premieres on Friday, October 30, 2026»; he asked for a reminder «on the premiere
day»; the reply was «On it — I'll set a heads-up for that day» and nothing was scheduled. The prose backstop only
read a promise in the reply's own words («I'll remind you», «te aviso»), and every new phrasing slipped past it.
The operator's ASK is the anchor: he asked for a notice, the reply did not refuse it, his turn names no day — so it
rings on the one date the last reply named. Two dates there, or none, schedule nothing.
"""
from __future__ import annotations

import time

import pytest

from nucleo.flash import reminder_guards as R

WINDOW = [{"role": "user", "content": "When does the new Dexter season premiere?"},
          {"role": "assistant", "content": "Dexter: Resurrection Season 2 premieres on Friday, October 30, 2026."}]


@pytest.fixture(autouse=True)
def no_jobs(monkeypatch):
    from nucleo import scheduler as S
    monkeypatch.setattr(S, "list_jobs", lambda active_only=True: [])


@pytest.mark.parametrize("ask, reply", [
    ("Can you set a reminder for me on the premiere day?", "On it — I'll set a heads-up for that day."),
    ("¿Me pones un aviso el día del estreno?", "Hecho, para ese día."),
])
def test_the_ask_rings_on_the_day_just_named(ask, reply):
    got = R.dated_reminder_backstop(reply, ask, window=WINDOW)
    assert got and got["schedule"].startswith("2026-10-30"), got


def test_a_refusal_or_two_dates_schedule_nothing():
    ask = "Can you set a reminder for me on the premiere day?"
    assert R.dated_reminder_backstop("I can't set reminders, sorry.", ask, window=WINDOW) is None
    two = WINDOW[:1] + [{"role": "assistant", "content": "It is October 30 in the US and October 31 in Spain."}]
    assert R.dated_reminder_backstop("Sure.", ask, window=two) is None
