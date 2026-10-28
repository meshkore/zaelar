"""A notice asked for TODAY whose hour has already gone rings soon today — the next full hour — and is noted.

`remember-and-remind-deadline` (ES + __us, Wednesday 2026-10-14 ~12:00): «recuérdamelo el miércoles», said on the
Wednesday itself with the default 09:00 behind us. The agenda refused the notice as past (EN) and the model's tag
was moved to NEXT Wednesday, after the Thursday deadline (ES). `nucleo.pulse.notice_today` is the one rule both doors
use: today and gone → the next full hour at least 15 min ahead; a day already behind us is not moved.
"""
from __future__ import annotations

import time

import pytest

from nucleo.pulse import notice_today as NT


def _ts(d, hh, mm=0):
    return time.mktime((2026, 10, d, hh, mm, 0, 0, 1, -1))


@pytest.fixture(autouse=True)
def _no_stale_moves():
    NT.take_move(_ts(14, 12), within_s=1e12)
    yield
    NT.take_move(_ts(14, 12), within_s=1e12)


def test_the_next_full_hour_at_least_fifteen_minutes_ahead():
    assert NT.stamp(NT.soon(_ts(14, 12))) == "2026-10-14 13:00"
    assert NT.stamp(NT.soon(_ts(14, 12, 50))) == "2026-10-14 14:00"


def test_a_deadline_closer_than_that_hour_or_midnight_gives_five_minutes():
    assert NT.stamp(NT.soon(_ts(14, 12), before=_ts(14, 12, 40))) == "2026-10-14 12:05"
    assert NT.stamp(NT.soon(_ts(14, 23, 50))) == "2026-10-14 23:55"


def test_today_and_gone_is_moved_and_noted_once():
    now = _ts(14, 12)
    at = NT.ring_at(_ts(14, 9), now, before=_ts(15, 9))
    assert NT.stamp(at) == "2026-10-14 13:00"
    assert NT.take_move(now) == {"asked": "2026-10-14 09:00", "at": "2026-10-14 13:00", "t": now}
    assert NT.take_move(now) is None


def test_an_hour_still_ahead_and_a_day_already_gone_are_left_alone():
    now = _ts(14, 12)
    assert NT.ring_at(_ts(14, 15), now) == _ts(14, 15)
    assert NT.ring_at(_ts(13, 9), now) == _ts(13, 9)
    assert NT.ring_at(_ts(14, 9), now, before=_ts(14, 11)) == _ts(14, 9), "the thing it announces is over"
    assert NT.take_move(now) is None


def test_a_move_from_another_turn_is_not_read_back():
    NT.moved(_ts(14, 9), _ts(14, 13), _ts(14, 12))
    assert NT.take_move(_ts(14, 12) + 600) is None
