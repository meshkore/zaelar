"""A notice moved to ring soon today is SAID at the time the live job rings — read back, not recomputed (2026-10-14).

`remember-and-remind-deadline` (Wednesday 2026-10-14 ~12:00): ES said «te aviso el miércoles 14 a las 9» — an
instant already gone — and EN «I'll set that up.»; neither said when the notice really rings. The move is the act's
verdict, `met` at the hour the live job rings: the mouth (`nucleo/turn/reply.py`) reads it back from the schedule
and owes one sentence with that time. Frozen clock; `list_jobs` is a double.
"""
from __future__ import annotations

import time

import pytest

from nucleo.pulse import notice_today as NT
from nucleo.pulse import scheduler as S
from nucleo.flash import notice_readback as NR
from nucleo.turn import reply as R

NOON = time.mktime((2026, 10, 14, 12, 0, 0, 0, 1, -1))
NINE = time.mktime((2026, 10, 14, 9, 0, 0, 0, 1, -1))
ONE = time.mktime((2026, 10, 14, 13, 0, 0, 0, 1, -1))
REPLY = "Vale, el jueves 15 tienes la renovación del seguro del coche y te aviso el miércoles 14 a las 9."


@pytest.fixture
def live(monkeypatch):
    jobs = [{"name": "aviso", "schedule": "2026-10-14 13:00", "type": "once"}]
    monkeypatch.setattr(S, "list_jobs", lambda active_only=True: list(jobs))
    monkeypatch.setattr(S.time, "time", lambda: NOON)
    NT.take_move(NOON, within_s=1e12)
    NT.moved(NINE, ONE, NOON)
    return jobs


def test_the_spanish_reply_owes_the_hour_it_really_rings(live):
    line = NR.moved_line(REPLY, "es")
    assert "13:00" in line and "hoy" in line, line
    assert NR.moved_line(REPLY, "es") == "", "said once"


def test_the_english_reply_owes_it_in_english(live):
    line = NR.moved_line("I'll set that up.", "en")
    assert "13:00" in line and "today" in line, line


def test_the_mouth_says_it_after_the_acts(live):
    import asyncio
    said = []

    class _Speech:
        @staticmethod
        def sanitize(t, drop_metadata=False):
            return t

    got = asyncio.run(R.after_acts((), REPLY, said.append, _Speech))
    assert "13:00" in got and len(said) == 1, got


def test_no_live_job_or_a_reply_that_already_says_it_owes_nothing(live):
    assert NR.moved_line("Te aviso hoy a las 13:00.", "es") == ""
    NT.moved(NINE, ONE, NOON)
    live.clear()
    assert NR.moved_line(REPLY, "es") == ""
