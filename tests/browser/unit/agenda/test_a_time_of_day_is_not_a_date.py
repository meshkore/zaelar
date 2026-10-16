"""«por la mañana» is an HOUR, never the day after (node 2.746).

Measured 2026-10-16 (audit V2-783 P1-1): `when._resolve_date` looked for «manana» before «hoy» and before the
weekdays, so «hoy por la mañana» and «el jueves por la mañana» both resolved to TOMORROW — in Spanish only, since
«morning» is not «tomorrow». The judge's «dates shifted in the agenda» family (25 findings in the window) has this
shape. A time-of-day phrase is stripped before the day is read; «mañana por la mañana» is still tomorrow; «hoy»
beats a weekday said beside it («hoy jueves»); noon is twelve, not the afternoon default.
"""
from __future__ import annotations

import datetime as _dt

import pytest

from widgets.agenda import when


def _iso(days: int) -> str:
    return (_dt.date.today() + _dt.timedelta(days=days)).isoformat()


def _next(wd: int) -> str:
    today = _dt.date.today()
    delta = (wd - today.weekday()) % 7 or 7
    return (today + _dt.timedelta(days=delta)).isoformat()


@pytest.mark.parametrize("said, expect", [
    ("hoy por la mañana", _iso(0)),
    ("hoy a la mañana", _iso(0)),
    ("esta mañana", _iso(0)),
    ("today in the morning", _iso(0)),
    ("mañana por la mañana", _iso(1)),
    ("tomorrow morning", _iso(1)),
    ("pasado mañana por la mañana", _iso(2)),
    ("el jueves por la mañana", _next(3)),
    ("Thursday morning", _next(3)),
    ("hoy jueves", _iso(0)),
])
def test_a_time_of_day_never_moves_the_day(said, expect):
    assert when._resolve_date(said) == expect


@pytest.mark.parametrize("said, expect", [
    ("a mediodía", "12:00"),
    ("at noon", "12:00"),
    ("a las 10 de la mañana", "10:00"),
])
def test_noon_is_twelve(said, expect):
    assert when._resolve_time(said) == expect
