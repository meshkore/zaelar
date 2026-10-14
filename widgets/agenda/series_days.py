"""widgets/agenda/series_days.py — which rows are a series' days, wherever they were moved (2026-10-14).

Measured in `agenda-everyday-edits__us` (sandbox 20261014-121305-en). «Move next Tuesday's piano to Wednesday, just
that week» detached the 20th as its own row on the 21st, stamped `fromSeries: "2026-10-20"` — the series' first
day. Two turns later the model re-sent that move with the day inside the item reference («Abril's piano lesson on
2026-10-20»); the reference resolver kept only the title, so the move ran UNDATED and moved the whole series to
Wednesday the 21st. From then on the detached row pointed at a first day the series no longer had, and «get rid of
the piano completely, the whole series» deleted the series and left the 21st standing — `ok: true`, «Done.».

A day moved out of a series belongs to it by title as well as by the first day it was taken from: when the call
names exactly one series, every detached row of that title is one of its days, whatever its first day became.
"""
from __future__ import annotations


def _fold(text) -> str:
    from .. import textmatch
    return textmatch.fold(str(text or ""))


def series_of(row: dict, series: list[dict]) -> dict | None:
    """The series in `series` that `row` was detached from, or None (`row` is not a detached day)."""
    first = str(row.get("fromSeries") or "")
    if not first or isinstance(row.get("repeat"), dict):
        return None
    for s in series:
        if str(s.get("date") or "") == first:
            return s
    titles = {_fold(s.get("title")) for s in series}
    if len(series) == 1 and titles == {_fold(row.get("title"))}:
        return series[0]
    return None


def left_behind(db: dict, series: list[dict]) -> list[dict]:
    """After the whole series went: its rows still in the calendar (the series itself, or a day moved out of it).
    The claim «the whole series is gone» is checked against the calendar, never against what was meant."""
    titles = {_fold(s.get("title")) for s in series}
    return [m for m in db.get("meetings", [])
            if _fold(m.get("title")) in titles and (isinstance(m.get("repeat"), dict) or m.get("fromSeries"))]
