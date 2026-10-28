"""widgets/agenda/notice_actions.py — the agenda's NOTICE actions: set a reminder, when it rings, a meeting added with its notice (split from `actions.py`)."""
from __future__ import annotations

from . import data as _d
from . import title_when as _tw
from . import twins as _twins
from widgets.agenda import actions as _actions  # read through the module so a patch on actions governs


def _a_set_reminder(action, payload, db, _extra) -> dict:
    # V2-473 — moving the notice is VOCABULARY (the clear_all lesson: a frequent intention with no
    # action cannot be gotten right). Finds the meeting like cancel_meeting does, cancels its current
    # reminder and schedules the new instant; errors NAME what is missing so the model can retry.
    title = _d._strip_accents((payload.get("title") or "").strip().lower())
    raw_date = payload.get("date", "")
    date = _d._resolve_date(raw_date) if raw_date else ""
    _hits = [m for m in db.get("meetings", [])
             if (not title or title in _d._strip_accents(m.get("title", "").strip().lower()))
             and (not date or _d.series.on(m, date))]
    if title and date and not _hits and not payload.get("at"):
        # V2-781 T513 — the `date` was the NOTICE's day («avísame el miércoles» of Thursday's item, measured
        # live): the title alone names the item, so the day goes to `at` instead of filtering the item out.
        _hits = [m for m in db.get("meetings", []) if title in _d._strip_accents(m.get("title", "").strip().lower())]
        payload = {**payload, "at": f"{date} {payload.get('time') or ''}".strip()}
        date = ""
    # V2-639 — «ponme avisos a TODAS las citas del jueves» is one intention, not N turns: a date with
    # no title means every meeting of that day. `at` is optional in bulk (default ~2h before each).
    if not title and date and _hits:
        _done, _fail = 0, []
        for m in _hits:
            _d._cancel_reminder(m)
            m.pop("reminder_id", None); m.pop("remindAt", None)
            _jid, _disp = _d._schedule_reminder(m.get("title", "Cita"), m.get("date", date),
                                             m.get("startTime", ""))
            if _jid:
                m["reminder_id"], m["remindAt"] = _jid, _disp
                m["remindAsked"] = True     # V2-796: he asked for these notices — ours, whatever Google rings
                _done += 1
            else:
                _fail.append(f"«{m.get('title', 'Cita')}»: {_disp}")
        db["currentPlan"] = _d.compute_plan(db)
        _d.store.save(_d.WIDGET_ID, db)
        if not _done:
            return {"ok": False, "error": "no pude programar ningún aviso — " + "; ".join(_fail)}
        return _d.view_data()
    if not title or not _hits:
        return {"ok": False,
                "error": "no encuentro esa cita en la agenda — dime el título tal como está "
                         "apuntada (y la fecha si hay varias)"}
    # V2-781 T519 (EN live): `set_reminder {remind: "…12:00"}` — the key add_meeting reads — was refused four times
    _asked = next((payload[k] for k in _d.reminders.ASK_KEYS if payload.get(k) not in (None, "", False, True)), "")
    _at = str(payload.get("at") or _asked or payload.get("time") or payload.get("startTime") or "").strip()
    if not _at:
        return {"ok": False,
                "error": "me falta cuándo suena el aviso — mándalo en `at` (HH:MM del día de la cita, "
                         "YYYY-MM-DD o YYYY-MM-DD HH:MM)"}
    m = _hits[0]
    _occ = date or _d.recur.next_occurrence(m, _d._today()) or m.get("date")   # V2-769: a series' next day
    # a bare day or hour is read against the occurrence; an all-day item rings too (V2-781 T513)
    if (_why := _ring_on(m, _occ, _at)):
        return {"ok": False, "error": f"no pude programar el aviso: {_why}"}
    return _d._Continue(_extra)


def _ring_on(m: dict, occ, raw) -> str:
    """`ring_as_asked` against the series' occurrence `occ`, keeping the row's own first `date`."""
    first = m.get("date")
    if occ:
        m["date"] = occ
    try:
        return _d.reminders.ring_as_asked(m, raw, _d._resolve_date)
    finally:
        m["date"] = first


def _a_add_meeting_noticed(action, payload, db, _extra):
    # V2-781 T513 — «apúntalo el jueves y avísame el miércoles»: the write lands as before, then the notice he
    # asked for replaces the default one. The ask keys are taken out first so the write does not report them
    # as unknown; a notice that cannot ring is said back in `notice_error`, and the write is kept.
    raw = next((payload[k] for k in _d.reminders.ASK_KEYS if payload.get(k) not in (None, "", False, True)), None)
    from . import free as _free                    # demo pass 109, C3: «ok book it» books the slot just found
    payload = _tw.said_when(_free.with_the_slot_found(db, payload, _d._resolve_date))   # a title says what, not when
    res = _actions._a_add_meeting(action, {k: v for k, v in payload.items() if k not in _d.reminders.ASK_KEYS}, db, _extra)
    if isinstance(res, _d._Continue):
        res.value["clashes"] = _free.clashes(db.get("meetings"), res.value.get("stored"))
    if raw is None or not isinstance(res, _d._Continue):
        return res
    st = res.value.get("stored") or {}
    m = next((x for x in db.get("meetings", []) if str(x.get("date")) == str(st.get("date"))
              and _d._titles_overlap(x.get("title"), st.get("title"))), None)
    why = _d.reminders.ring_as_asked(m, raw, _d._resolve_date) if m is not None else "la cita no quedó escrita"
    if why:
        res.value["notice_error"] = f"no pude poner el aviso donde lo pidió: {why}"
    elif m is not None:
        res.value["stored"] = dict(m)
    return res
