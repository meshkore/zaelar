"""widgets/agenda/series.py — a series ON a meeting row: its keys, attaching/updating its rule, normalising input."""
from __future__ import annotations

import re
from widgets.agenda import recur as _recur  # read through the module so a patch on recur governs


#: Every key `add_meeting`/`update_meeting` understand. Anything else a write carries is REPORTED back, never
#: dropped in silence — the dropped `recurrence` is how his Tuesdays vanished while the reply promised them.
MEETING_KEYS = frozenset(("title", "date", "startTime", "time", "endTime", "notes", "details", "location",
                          "place", "category", "attendees", "people", "with", "status", "confirmed", "allDay",
                          "all_day", "meet", "newTitle", "id", "item", "widget_id", "action",
                          # a DURATION says the end (V2-773): read by add_meeting and move_meeting alike
                          "duration", "durationMinutes", "duration_minutes", "minutes", "length") + _recur.ALL_KEYS)


def ignored_keys(payload: dict) -> list[str]:
    """The keys of a write that carried a value and that nothing here reads."""
    return [k for k, v in (payload or {}).items()
            if k not in MEETING_KEYS and not str(k).startswith("_") and v not in (None, "", [], {}, False)]


def attach(new: dict, payload: dict, today: str) -> str:
    """Give a NEW meeting its rule, if the write carries one. Returns why it could not ("" when fine).
    The row's `date` becomes the first day the rule lands on, so «los martes» said on a Friday starts on a
    Tuesday."""
    rep, why = _recur.parse(payload, str(new.get("date") or today), _recur._date(today))
    if why:
        return why
    if rep:
        new["date"] = _recur.first_on_or_after(rep, str(new.get("date") or today))
        new["repeat"] = rep
    return ""


def update(m: dict, payload: dict, today: str) -> str:
    """Change the rule of an EXISTING meeting: set it, replace it, move only its end («hasta diciembre»), or
    drop it («ya no se repite»). Returns why it could not ("" when fine or when nothing about it was said)."""
    if not any(k in (payload or {}) for k in _recur.ALL_KEYS):
        return ""
    raw = next((payload[k] for k in _recur.RULE_KEYS if k in payload), None)
    if raw is False or (isinstance(raw, str) and _recur._fold(raw) in _recur._NONE_WORDS):
        m.pop("repeat", None)
        return ""
    cur = m.get("repeat") if isinstance(m.get("repeat"), dict) else None
    if cur and raw is None and not any(payload.get(k) for k in _recur.DAYS_KEYS):
        until, ok = _recur.parse_until(next((payload[k] for k in _recur.UNTIL_KEYS if payload.get(k)), ""), _recur._date(today))
        if not ok:
            return "no entiendo hasta cuándo se repite — manda `until` como YYYY-MM-DD"
        cur["until"] = until
        return ""
    rep, why = _recur.parse(payload, str(m.get("date") or today), _recur._date(today))
    if why:
        return why
    if rep:
        if cur and cur.get("skip"):
            rep["skip"] = cur["skip"]
        m["date"] = _recur.first_on_or_after(rep, str(m.get("date") or today))
        m["repeat"] = rep
    return ""


def weekday(date: str) -> int:
    """Monday = 0, the convention every `days` list here uses."""
    d = _recur._date(date)
    return d.weekday() if d else 0


def on(m: dict, date: str) -> bool:
    """Does this row name `date` — its own day, or one its rule lands on? The selector every edit shares."""
    return str(m.get("date") or "") == date or (isinstance(m.get("repeat"), dict) and _recur.occurs_on(m, date))


# Measured in the live use case (2026-09-25, sandbox 20260925-125624): the model sees action NAMES, never their
# payload shapes (`widgets/brief.py`, on purpose — shapes cost tokens every turn), so it NAMES the fields
# itself. It got the end right (`endDate` → until) and the rest wrong for us: the series landed on the day it
# was said (a Friday), all-day, because `startDate`, `start` and `dayOfWeek` were keys nobody read. A natural
# alias must never cost the fact (the V2-341/V2-473 rule), so they are mapped HERE, once, for every write.
_HHMM = re.compile(r"^\s*\d{1,2}([:h.]\d{2})?\s*(h|am|pm)?\s*$", re.I)


_DATE_ALIASES = ("startDate", "start_date", "fromDate", "from_date", "from", "desde", "firstDate", "first_date",
                 "day", "dia")


_START_ALIASES = ("start", "startHour", "start_hour", "hour", "hora", "startAt", "horaInicio", "hora_inicio",
                  "start_time", "starttime")


_END_ALIASES = ("end", "endHour", "end_hour", "endAt", "horaFin", "hora_fin", "end_time", "endtime")


_DAYS_ALIASES = ("dayOfWeek", "day_of_week", "weekday", "byday", "dia_semana", "diaSemana")


def normalize(payload: dict) -> dict:
    """A copy of `payload` with the model's natural field names mapped onto the agenda's own — only where the
    canonical key is absent, so an explicit field always wins. `start`/`end` go to the HOUR when they look like
    one and to the DAY when they look like a date (`end` as a date is the END of a series)."""
    p = dict(payload or {})

    def _take(keys):
        for k in keys:
            if p.get(k) not in (None, "", []):
                return k, p.pop(k)
        return None, None
    for k in ("start", "end"):
        v = p.get(k)
        if isinstance(v, str) and _recur._date(v) and not _HHMM.match(v):
            p.pop(k)
            p.setdefault("date" if k == "start" else "until", v)
    if not p.get("date"):
        k, v = _take(_DATE_ALIASES)
        if k:
            p["date"] = v
    if not (p.get("startTime") or p.get("time")):
        k, v = _take(_START_ALIASES)
        if k:
            p["startTime"] = v
    if not p.get("endTime"):
        k, v = _take(_END_ALIASES)
        if k:
            p["endTime"] = v
    if not any(p.get(k) for k in _recur.DAYS_KEYS):
        k, v = _take(_DAYS_ALIASES)
        if k:
            p["days"] = v
    return p
