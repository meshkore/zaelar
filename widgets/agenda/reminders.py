"""widgets/agenda/reminders.py — the appointment's NOTICE: scheduled when it is written, cancelled with it.

Extracted from `data.py` byte for byte (V2-705): that file sat 56 lines over the 900-line architecture
ceiling and the ratchet is paid by extracting, never by raising the number. Nothing here changed —
`data.py` re-exports both names, so every caller and every test seam (`data._schedule_reminder`,
`data._cancel_reminder`) keeps working. The notice is a concern of its own: V2-473 gave every meeting a
~2 h alarm by default, and an orphan alarm «fires a ghost appointment», which is why cancelling one is
part of every erase path (`sweep.py`).
"""
from __future__ import annotations


def _schedule_reminder(title: str, date: str, start: str, at: str = "", before_minutes: int = 120) -> tuple:
    """Schedule the appointment's notice. Returns (job_id, display) — ("", reason) when nothing was scheduled.

    V2-473: by default it falls `before_minutes` before the appointment (the operator's «avisos por
    defecto, en plan, dos horas antes», INI-026 A2); `at` overrides with an absolute «YYYY-MM-DD HH:MM».
    The prompt is RESOLVED content — what to say when it fires — never the user's raw sentence (the
    remember-and-remind lesson: a raw prompt re-asks the agent to schedule instead of reminding). A notice
    whose instant already passed is not scheduled: an alarm for the past is a fabrication with a bell.
    """
    import time as _t
    # An all-day item has no hour, and its notice is only ever an asked one (V2-781 T513): the item lasts the
    # whole day, so the «already over» check measures against its last minute.
    said = start
    at = at or ("" if start else f"{str(date)[:10]} 09:00")    # all-day: 09:00 that day (operator, 2026-10-10)
    start = start or ("23:59" if at else "")
    try:
        target = _t.mktime((int(date[:4]), int(date[5:7]), int(date[8:10]),
                            int(start[:2]), int(start[3:5]), 0, 0, 1, -1))
    except Exception:  # noqa: BLE001 — unreadable date/time → no notice, the write itself still lands
        return "", "fecha/hora ilegibles"
    if at:
        try:
            when = _t.mktime((int(at[:4]), int(at[5:7]), int(at[8:10]),
                              int(at[11:13]), int(at[14:16]), 0, 0, 1, -1))
        except Exception:  # noqa: BLE001
            return "", "instante del aviso ilegible"
    else:
        when = target - before_minutes * 60
        if when <= _t.time() + 60 < target:
            when = _t.time() + 60                      # appointment within the window → notice now-ish
    if when <= _t.time() or target <= _t.time() - 60:
        return "", "el instante ya pasó"
    stamp = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(when))
    try:
        # The LOW layer, not the motor's internals: `i18n.langs` is the facade every widget reads the
        # language through (the direction ratchet, test_dependency_directions_only_improve). The byte-for-
        # byte extraction from data.py carried the old reach along and CI went red on it (2026-09-15).
        from i18n import langs as _langs
        _en = (_langs.current_code() or "es").lower() == "en"
    except Exception:  # noqa: BLE001
        _en = False
    # an all-day item has no hour to say (the 23:59 above is only the «already over» line)
    prompt = (f"Remind the operator: «{title}» on {date}" + (f" at {said}." if said else ".")
              if _en else f"Recuérdale al operador: «{title}» el {date}" + (f" a las {said}." if said else "."))
    try:
        from nucleo import scheduler as _sched
        # `origin="agenda"` keeps this notice OUT of the calendar's system-task band (V2-728): it already
        # has a place on screen — the appointment it belongs to — and painting it again would show the
        # operator two things where he wrote one.
        r = _sched.create(prompt, stamp, name=f"aviso: {title[:80]}", origin="agenda")
    except Exception as e:  # noqa: BLE001 — the scheduler must never lose the agenda WRITE
        return "", str(e)
    if not (r or {}).get("ok"):
        return "", str((r or {}).get("error") or "scheduler")
    try:
        _sched.supersede_loose_notices(r.get("display") or stamp)   # V2-781 T519: one alert, the one with a name
    except Exception:  # noqa: BLE001 — the notice itself stands; a loose twin may ring once more
        __import__("logging").getLogger("zaelar.agenda").warning("supersede_loose_notices failed", exc_info=True)
    return str(r.get("id") or ""), stamp


def notice_fields(title: str, date: str, start: str = "") -> dict:
    """`{reminder_id, remindAt}` of the default notice just scheduled, or {} when none could be."""
    jid, at = _schedule_reminder(title, date, start)
    return {"reminder_id": jid, "remindAt": at} if jid else {}


#: The keys a write uses to say WHEN its notice rings («apúntalo el jueves y avísame el miércoles»). Measured in
#: the pair `remember-and-remind-deadline` (V2-781 T513): EN sent `reminder` (dropped as unknown) and ES, with
#: no field to put it in, wrote a second all-day entry named «Aviso» — a calendar line, never an alert.
ASK_KEYS = ("remind", "reminder", "remindAt", "remind_at", "remindOn", "notice", "aviso")
_DAY_BEFORE = ("day before", "dia antes", "dia anterior", "vispera", "the eve")


def asked_instant(raw, date: str, start: str, resolve_date) -> str:
    """The instant («YYYY-MM-DD HH:MM») of the notice he asked for, "" when the value names none.

    A bare DAY rings at the item's own hour — or 09:00 for an all-day item, which has none; a bare HOUR rings
    on the item's day; «the day before» is counted from the item, not from today."""
    import re
    import time as _t
    s = str(raw if isinstance(raw, str) else "").strip()
    m = re.match(r"^\s*(?:(.+?)[T ,]+(?:a las |at )?)?(\d{1,2})[:h](\d{2})\s*$", s)
    day, hour = (m.group(1) or "", f"{int(m.group(2)):02d}:{m.group(3)}") if m else (s, "")
    if not (day or hour):
        return ""
    folded = day.lower().translate(str.maketrans("áéíóú", "aeiou"))
    if any(w in folded for w in _DAY_BEFORE):
        try:
            noon = _t.mktime((int(date[:4]), int(date[5:7]), int(date[8:10]), 12, 0, 0, 0, 1, -1))
        except Exception:  # noqa: BLE001
            return ""
        day = _t.strftime("%Y-%m-%d", _t.localtime(noon - 86400))
    elif day and not re.match(r"^\d{4}-\d{2}-\d{2}$", day.strip()):
        # A phrase with no day of its own («el mismo día por la mañana», «ese día», «the same day») is the item's
        # day: the resolver falls back to TODAY, and «por la mañana» read as «mañana» rang TOMORROW (V2-781 pair 3).
        from nucleo import scheduler as _sched
        day = (_sched.parse_when(_sched._RE_MORNING_NOUN.sub(" ", folded)) or "")[:10]
    day = day or date
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(day)):
        return ""
    return f"{day} {hour or start or '09:00'}"


def ring_as_asked(m: dict, raw, resolve_date) -> str:
    """Move `m`'s notice to the instant he asked for. Returns "" when it rings there, else why it does not."""
    at = asked_instant(raw, str(m.get("date") or ""), str(m.get("startTime") or ""), resolve_date)
    if not at:
        return "no entiendo cuándo quiere el aviso — `remind` es YYYY-MM-DD, YYYY-MM-DD HH:MM o HH:MM"
    _cancel_reminder(m)
    m.pop("reminder_id", None)
    m.pop("remindAt", None)
    jid, disp = _schedule_reminder(m.get("title", "Cita"), str(m.get("date") or ""), str(m.get("startTime") or ""),
                                   at=at)
    if not jid:
        return disp
    m["reminder_id"], m["remindAt"] = jid, disp
    return ""


def _cancel_reminder(meeting: dict) -> None:
    """Cancel the meeting's scheduled notice, if it has one. Best-effort: an orphan alarm fires a ghost."""
    ref = str((meeting or {}).get("reminder_id") or "").strip()
    if not ref:
        return
    try:
        from nucleo import scheduler as _sched
        _sched.cancel(ref)
    except Exception:  # noqa: BLE001 — an orphan alarm fires a ghost: say so
        __import__("logging").getLogger("zaelar.agenda").warning(f"could not cancel notice {ref}", exc_info=True)


def roll_series(load, save) -> bool:
    """A REPEATING appointment's notice moves on to its next occurrence (V2-769). Called from the agenda's
    background tick: a series stores ONE notice — the next one — and once that day has passed, the one after
    is scheduled. `remindFor` marks which occurrence the stored notice belongs to, so a notice that could
    not be scheduled (its instant already gone) is not retried on every tick. True when something changed."""
    import time as _t
    from . import recur
    db = load()
    today, changed = _t.strftime("%Y-%m-%d"), False
    for m in db.get("meetings", []):
        if not isinstance(m.get("repeat"), dict) or m.get("allDay") or not m.get("startTime"):
            continue
        nxt = recur.next_occurrence(m, today)
        if not nxt or m.get("remindFor") == nxt:
            continue
        _cancel_reminder(m)
        m.pop("reminder_id", None)
        m.pop("remindAt", None)
        jid, at = _schedule_reminder(m.get("title", "Cita"), nxt, m.get("startTime", ""))
        if jid:
            m["reminder_id"], m["remindAt"] = jid, at
        m["remindFor"] = nxt
        changed = True
    if changed:
        save(db)
    return changed
