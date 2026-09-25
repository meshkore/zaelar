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
    prompt = (f"Remind the operator: «{title}» on {date} at {start}."
              if _en else f"Recuérdale al operador: «{title}» el {date} a las {start}.")
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
    return str(r.get("id") or ""), stamp


def _cancel_reminder(meeting: dict) -> None:
    """Cancel the meeting's scheduled notice, if it has one. Best-effort: an orphan alarm fires a ghost."""
    ref = str((meeting or {}).get("reminder_id") or "").strip()
    if not ref:
        return
    try:
        from nucleo import scheduler as _sched
        _sched.cancel(ref)
    except Exception:  # noqa: BLE001
        pass


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
