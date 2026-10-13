"""nucleo/flash/agenda_said_day.py — the agenda write lands on the day HIS words name (agenda-everyday-edits, 2026-10-14).

Two red steps of the same ES round (Wednesday 2026-10-14, report 20261014-005211), one class: the model's date
was trusted over the operator's sentence.

1. «Apúntame el dentista el jueves que viene a las diez» → `add_meeting {date: 2026-10-22}`. The prompt's own
   lookup said «thursday 2026-10-15»; the model read «que viene» as «of next week» and filed it a week late. The
   widget's resolver (`widgets.agenda.when._resolve_date`) already gives the coming weekday, strictly after
   today — the model simply did not let it resolve, because it sent an ISO date. «el <weekday> que viene»,
   «este <weekday>», «el próximo <weekday>», «next <weekday>» and «this <weekday>» mean the IMMEDIATE coming
   one (the EN twin, `next Thursday` → 15, already passed and is graded the same way). When the model's ISO day
   falls on that weekday exactly ONE week after it, the day is put back. A sentence that names the week ahead
   («el jueves de la semana que viene», «next week», «in two weeks») is left alone.

2. «El piano del martes que viene pásalo al miércoles, solo esa semana» → `move_meeting {newDate}` with NO
   `date`, which the manifest defines as «the whole series» — every Tuesday became a Wednesday, and the later
   «el 27 de octubre no hay clase» then fell on a day the series no longer had (it was applied to the 28th by a
   worker). «Solo esa semana / just that week / only this one» is the operator answering the one-or-all question
   himself: the occurrence gets its `date` — the day his words name, else the series' next one — and the widget's
   existing dated move detaches that day (`edit.detach`).

Deterministic and narrow on purpose: the agenda only, ISO dates only, and only the exact one-week slip or the
missing `date` of a move he scoped to one occurrence. The weekday words are the widget's own table.
"""
from __future__ import annotations

import datetime as _dt
import re

from nucleo.flash.text_norm import _norm_txt

_DAY_FIELDS = ("date", "newDate", "day")

_WEEK_AHEAD_RE = re.compile(
    r"\b(?:(?:la\s+)?semana\s+(?:que\s+viene|proxima|siguiente)|(?:la\s+)?(?:proxima|siguiente|otra)\s+semana|"
    r"dentro\s+de|en\s+(?:dos|tres|\d+)\s+semanas|next\s+week|week\s+after|in\s+(?:two|three|\d+)\s+weeks|"
    r"a\s+week\s+from|the\s+following\s+week)\b")

_ONE_OCCURRENCE_RE = re.compile(
    r"\b(?:solo|solamente|unicamente|nada\s+mas)\s+(?:por\s+)?(?:es[ae]|est[ae])\s+(?:semana|dia|vez|clase|sesion|"
    r"lunes|martes|miercoles|jueves|viernes|sabado|domingo)\b|"
    r"\b(?:just|only)\s+(?:for\s+)?(?:that|this)\s+(?:week|day|once|one|time|session|lesson|class|monday|tuesday|"
    r"wednesday|thursday|friday|saturday|sunday)\b|\b(?:this|that)\s+(?:week|one|day|time)\s+only\b")


def _weekdays() -> dict[str, int]:
    from widgets.agenda.when import _WEEKDAYS, _strip_accents
    return {_strip_accents(k): v for k, v in _WEEKDAYS.items()}


def _qualified(said: str) -> list[int]:
    """The weekdays his words name as the IMMEDIATE coming one, in order."""
    names = "|".join(sorted(_weekdays(), key=len, reverse=True))
    pat = re.compile(rf"\b(?:(?P<a>{names})\s+que\s+viene|(?:este|esta|el\s+proximo|proximo|this|next|this\s+coming|"
                     rf"coming)\s+(?P<b>{names})|(?P<c>{names})\s+proximo)\b")
    wd = _weekdays()
    return [wd[m.group("a") or m.group("b") or m.group("c")] for m in pat.finditer(said)]


def _named_weekdays(said: str) -> list[int]:
    wd = _weekdays()
    names = "|".join(sorted(wd, key=len, reverse=True))
    return [wd[m.group(0)] for m in re.finditer(rf"\b(?:{names})\b", said)]


def coming(weekday: int, today: _dt.date) -> _dt.date:
    """The weekday's next date strictly after today — the widget resolver's own rule."""
    return today + _dt.timedelta(days=(weekday - today.weekday()) % 7 or 7)


def _iso(v) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(str(v or "").strip()[:10])
    except ValueError:
        return None


def _one_week_late(payload: dict, said: str, today: _dt.date) -> dict:
    if _WEEK_AHEAD_RE.search(said):
        return payload
    out = dict(payload)
    for wd in set(_qualified(said)):
        right = coming(wd, today)
        for k in _DAY_FIELDS:
            if _iso(out.get(k)) == right + _dt.timedelta(days=7):
                out[k] = right.isoformat()
    return out


def _occurrence(payload: dict, said: str, today: _dt.date) -> str:
    """The day of the series his words scope the move to: the weekday or date he names that is not the
    destination, else the series' next occurrence."""
    dest = _iso(payload.get("newDate"))
    for wd in _named_weekdays(said):
        if dest is None or wd != dest.weekday():
            day = coming(wd, today)
            if _WEEK_AHEAD_RE.search(said):
                day = today + _dt.timedelta(days=7 - today.weekday() + wd)
            return day.isoformat()
    from widgets.agenda.when import _calendar_date
    if (named := _calendar_date(said)) and named != (dest.isoformat() if dest else ""):
        return named
    from widgets import store as _store
    from widgets.agenda import edit as _edit, recur as _recur
    hits = _edit.find(_store.load("agenda") or {}, payload)
    if hits and isinstance(hits[0].get("repeat"), dict):
        return _recur.next_occurrence(hits[0], today.isoformat())
    return ""


def _scoped_to_one(action: str, payload: dict, said: str, today: _dt.date) -> dict:
    if action != "move_meeting" or str(payload.get("date") or "").strip() or payload.get("whole"):
        return payload
    if not _ONE_OCCURRENCE_RE.search(said):
        return payload
    day = _occurrence(payload, said, today)
    return {**payload, "date": day} if day else payload


def payload(widget_id: str, action: str, payload: dict, said: str, *, today: _dt.date | None = None) -> dict:
    """The agenda payload with the day his words name, or the payload untouched. Never raises."""
    try:
        if str(widget_id or "").split("::", 1)[0].strip().lower() != "agenda" or not isinstance(payload, dict):
            return payload
        n = _norm_txt(said)
        if not n.strip():
            return payload
        today = today or _dt.date.today()
        fixed = _scoped_to_one(action, _one_week_late(payload, n, today), n, today)
        if fixed != payload:
            _trace(action, payload, fixed)
        return fixed
    except Exception:  # noqa: BLE001 — a correction never takes down the write it corrects
        __import__("logging").getLogger("zaelar.flash").debug("said-day alignment skipped", exc_info=True)
        return payload


def align(widget_id: str, action: str, pl: dict, said: str) -> tuple[str, str, dict]:
    """`payload` in the (widget, action, payload) shape the text channel threads through its call."""
    return widget_id, action, payload(widget_id, action, pl, said)


def _trace(action: str, before: dict, after: dict) -> None:
    try:
        from voice.observer import emit as _emit
        changed = {k: after[k] for k in after if before.get(k) != after.get(k)}
        _emit("brain", "🗓️ appointment day aligned with his words", role="system",
              text=f"agenda:{action} {changed}"[:160],
              extra={"cat": "flash", "widget": "agenda", "action": action, "changed": changed})
    except Exception:  # noqa: BLE001 — the trace is best-effort; the correction is not
        __import__("logging").getLogger("zaelar.flash").debug("said-day trace not emitted", exc_info=True)
