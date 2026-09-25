"""widgets/agenda/edit.py — the everyday edits an appointment gets after it is written (V2-770).

The agenda could create, move, rename and cancel. Walking the list of what a person actually does with a
calendar, four ordinary things had no door, and a missing door is not a refusal the model can make — it is
a promise it narrates (the V2-540 rule):

  · «ábreme la cita del dentista» / «enséñame la ficha del piano» — the DETAIL card only opened on a click;
    «ciérrala» had nothing to close. `open_meeting` / `close_meeting` push it the way `show_day` pushes a
    day: a counter in `view`, honoured once by the card.
  · «que dure hasta las cinco» — an END time could not be said at all: `move_meeting` kept the duration and
    `update_meeting` silently dropped `endTime` (a key it knew and never read, so not even `ignored`).
  · «este martes el piano es a las cinco», «el piano de este martes pásalo al miércoles» — ONE day of a
    series could not move; the whole series moved with it. Now a dated move of a series detaches that day:
    the series skips it and a single appointment holds the new day and hour.
  · «a partir de enero ya no hay piano» — a series could only be cut by knowing the field (`until`).

And one inconsistency: `cancel_meeting` found an appointment tolerantly («renovar seguro coche» →
«Renovar el seguro del coche»), `move_meeting`/`update_meeting` by exact substring. The same reference now
finds the same row whatever the verb (`find`).

`data.py` sits at its line ceiling; every piece lives here and it calls in.
"""
from __future__ import annotations

import re
import time as _t

from . import recur
from .when import _m2, _resolve_date, _resolve_time, _today

#: The keys that say WHEN — present in an `update_meeting`, they are a reschedule and go through the one
#: door that owns the notice (`move_meeting`), instead of being dropped.
TIME_KEYS = ("newDate", "new_date", "newTime", "new_time", "startTime", "time", "endTime", "newEndTime",
             "new_end_time", "duration", "durationMinutes")
_END_KEYS = ("newEndTime", "new_end_time", "endTime", "end")
_DUR_KEYS = ("duration", "durationMinutes", "minutes")
_FROM_KEYS = ("from", "fromDate", "from_date", "since", "desde", "startingFrom", "a_partir_de")


#: How long «the one we are talking about» stays the one. A conversation about one appointment runs over a few
#: turns; after that a bare «ponle una nota» is about nothing in particular and asks.
FOCUS_TTL_S = 600


def find(db: dict, payload: dict) -> list[dict]:
    """The rows a spoken reference names — the SAME tolerant matcher `cancel_meeting` uses.

    With NO title at all, the appointment this conversation is on: the one last written, opened, moved or
    edited, for `FOCUS_TTL_S`. Measured live (V2-770): «y apúntale en la descripción que lleve las
    radiografías», «y que dure hasta la una» — a person says «it» about the appointment he just touched, and
    the model sent exactly that: an edit with no title. Only the NON-destructive edits call this; a deletion
    still needs a named selector (`widgets/contract.py`)."""
    from .sweep import _matches
    if str(payload.get("title") or "").strip():
        return _matches(db, payload)
    f = db.get("focus") or {}
    if not f.get("title") or _t.time() - float(f.get("at") or 0) > FOCUS_TTL_S:
        return []
    return _matches(db, {"title": f["title"], **({"date": payload["date"]} if payload.get("date") else {})})


def touch(db: dict, m: dict | None) -> None:
    """Remember which appointment the conversation is on (see `find`)."""
    if isinstance(m, dict) and m.get("title"):
        db["focus"] = {"title": str(m["title"]), "at": _t.time()}


def missing(db: dict, payload: dict) -> str:
    """Why nothing matched, said so the model can fix its next call: a right title on a wrong DAY names the
    days it does fall on, instead of «I can't find it» about an appointment he can see."""
    if str(payload.get("date") or "").strip():
        undated = find(db, {k: v for k, v in payload.items() if k != "date"})
        if undated:
            m = undated[0]
            when = (recur.describe(m["repeat"]) if isinstance(m.get("repeat"), dict) else str(m.get("date") or ""))
            return (f"«{m.get('title')}» no cae el {_resolve_date(str(payload['date']))} — es {when}. "
                    f"Dime qué día es, o sin `date` si es la cita entera.")
    return "no encuentro esa cita en la agenda — dime el título tal como está apuntada (y la fecha si hay varias)"


def _day_of(m: dict, payload: dict) -> str:
    """The day the operator means: the one he said, else the series' next day, else the row's own."""
    raw = str(payload.get("date") or "").strip()
    if raw:
        return _resolve_date(raw)
    if isinstance(m.get("repeat"), dict):
        return recur.next_occurrence(m, _today()) or str(m.get("date") or "")
    return str(m.get("date") or _today())


def _push(db: dict, **fields) -> None:
    db["view"] = {**fields, "n": int((db.get("view") or {}).get("n", 0)) + 1, "at": _t.time()}


def open_detail(db: dict, payload: dict) -> dict:
    """Show ONE appointment's card on screen, on its day. Writes nothing but the view."""
    hits = find(db, payload)
    if not hits:
        return {"ok": False, "error": missing(db, payload)}
    m = hits[0]
    day = _day_of(m, payload)
    if day and not recur.on(m, day):
        day = _day_of(m, {})
    _push(db, sel=day, open={"title": str(m.get("title") or ""), "date": day})
    touch(db, m)
    return {"ok": True, "opened": str(m.get("title") or ""), "date": day}


def close_detail(db: dict) -> dict:
    """Close the appointment card, leaving the calendar exactly where it was."""
    _push(db, close=True)
    return {"ok": True}


def end_of(m: dict, payload: dict, new_start: str) -> str:
    """The new END: said outright («hasta las cinco»), as a length («que dure hora y media»), or the old
    length kept. Always after the start."""
    raw_end = next((str(payload[k]) for k in _END_KEYS if str(payload.get(k) or "").strip()), "")
    if raw_end:
        end = _resolve_time(raw_end, "")
        if end and _m2(end) > _m2(new_start):
            return end
    raw_dur = next((payload[k] for k in _DUR_KEYS if str(payload.get(k) or "").strip()), None)
    try:
        dur = int(float(str(raw_dur).split()[0])) if raw_dur is not None else 0
    except (ValueError, IndexError):
        dur = 0
    if dur <= 0:
        try:
            dur = (_m2(m.get("endTime")) - _m2(m.get("startTime"))) or 60
        except Exception:  # noqa: BLE001
            dur = 60
    e = (_m2(new_start) + max(15, dur)) % (24 * 60)
    return f"{e // 60:02d}:{e % 60:02d}"


def detach(db: dict, series: dict, day: str) -> dict | None:
    """Take ONE day out of a series as an appointment of its own, and return it (None if that day is not one
    of the series'). The series skips the day; the copy keeps every detail and loses the rule and the
    Google ids that belong to the series — it is a new event there, if it goes anywhere."""
    if not recur.skip(series, day):
        return None
    one = {k: v for k, v in series.items()
           if k not in ("repeat", "googleSeriesId", "googleId", "reminder_id", "remindAt", "remindFor")}
    one["date"], one["fromSeries"] = day, str(series.get("date") or "")
    return one


def cut_from(m: dict, payload: dict) -> bool:
    """«A partir de enero ya no hay piano»: end the series the day BEFORE the one said. True when it did."""
    raw = next((str(payload[k]) for k in _FROM_KEYS if str(payload.get(k) or "").strip()), "")
    if not raw or not isinstance(m.get("repeat"), dict):
        return False
    import datetime as _dt
    day, ok = recur.parse_until(raw, _dt.date.fromisoformat(_today()))
    if ok and not re.search(r"\b\d{1,2}\b", raw):
        day = day[:8] + "01"                           # «a partir de enero» is its FIRST day, not its last
    elif not ok:
        day = _resolve_date(raw)
    try:
        prev = (_dt.date.fromisoformat(day) - _dt.timedelta(days=1)).isoformat()
    except ValueError:
        return False
    cur = str(m["repeat"].get("until") or "")
    m["repeat"]["until"] = min(cur, prev) if cur else prev     # a cut never EXTENDS a series
    return True
