"""widgets/agenda/system_tasks.py — the SYSTEM's own timed work, as the calendar draws it (V2-728).

Operator, 2026-09-20: *«si te digo la semana que viene, haz esto… y además se puede ver perfectamente en la
agenda, aunque es una tarea no para nosotros, sino para el sistema»*.

THE AGENDA READS, IT DOES NOT DUPLICATE. There is one durable record of a timed commission — the `tasks`
table — and this turns it into calendar-shaped rows. Copying them into `meetings` instead is what the
`agenda`/`scheduler` pair used to do in spirit, and it is why the two surfaces could disagree about the same
reminder: two writers of one fact end up with two versions of it.

Extracted from `data.py` for the same reason `reminders.py` was (V2-705): that file is capped by the
architecture ratchet and the rule is to extract a module, never to raise the number. `data.py` re-exports
`_system_tasks`, so every caller and test seam keeps working.
"""
from __future__ import annotations

import time


def _agenda_notice_ids(db) -> set:
    """Job ids that are an APPOINTMENT'S OWN NOTICE, read from the appointments themselves.

    THIS IS THE FILTER THAT MATTERS, and it is a join rather than a flag on purpose. Every meeting schedules
    its own alarm (`reminders._schedule_reminder`) and stores the job id it got back as `reminder_id` — so
    the relationship already EXISTS in the data and does not depend on anybody having remembered to declare
    it. `scheduler.create(origin=…)` does record who asked for a clock, and it is worth recording, but a
    filter built on it alone would be wrong for every job written before that argument existed: measured on
    the operator's own database while writing this, NINE «aviso: Dentist» rows carry no origin at all and
    would each have put a second mark on a day that already shows the appointment.

    A rule each writer has to remember is not a rule. This one reads the relationship instead.
    """
    out = set()
    for m in (db.get("meetings") or []):
        rid = str((m or {}).get("reminder_id") or "").strip()
        if rid:
            out.add(rid)
    return out


def system_tasks(limit: int = 60, db=None) -> list[dict]:
    """Scheduled and recurring TASKS the calendar should mark, newest moment first.

    Only what has a MOMENT is returned: a recurring job's next run is the one instant a calendar can place
    honestly. Best-effort throughout — an unreadable table costs the band, never the calendar.
    """
    try:
        from nucleo import tasks as _tasks
    except Exception:  # noqa: BLE001
        return []
    if db is None:
        try:
            from .data import load_db
            db = load_db()
        except Exception:  # noqa: BLE001
            db = {}
    notices = _agenda_notice_ids(db or {})
    out: list[dict] = []
    for mode in ("scheduled", "recurring"):
        try:
            rows = _tasks.board(mode)
        except Exception:  # noqa: BLE001
            continue
        for r in rows:
            tid = str(r.get("id") or "")
            if str(r.get("origin") or "") == "agenda" or tid.removeprefix("cron:") in notices:
                continue          # it is an appointment's own alarm; the appointment is already on the day
            sch = r.get("schedule") or {}
            nxt = sch.get("next_run") or r.get("due_at")
            if not isinstance(nxt, (int, float)) or nxt <= 0:
                continue
            lt = time.localtime(float(nxt))
            out.append({
                "id": tid,
                "title": str(r.get("title") or r.get("goal") or "").strip(),
                "date": time.strftime("%Y-%m-%d", lt),
                "startTime": time.strftime("%H:%M", lt),
                "every": str(sch.get("display") or ""),
                "recurring": mode == "recurring",
            })
    out.sort(key=lambda x: (x["date"], x["startTime"]))
    return out[:int(limit)]
