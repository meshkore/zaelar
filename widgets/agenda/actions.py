"""What each agenda action does, one function per action; `data.ACTIONS` maps the names to them (V2-778 F1-12,
2026-10-01).

Moved out of `widgets/agenda/data.py`'s `apply_action` if-chain with no behaviour change: each body is the branch
it was, and every module-level name of `data` it reads is read through it (`_d.<name>`), so a patch on `data`
still governs every call.
"""
from __future__ import annotations

from . import data as _d
from . import twins as _twins


def _a_drop_project(action, payload, db, _extra) -> dict:
    pid = payload.get("projectId")
    for p in db.get("projects", []):
        if p["id"] == pid:
            p["status"] = "frozen"
    for t in db.get("tasks", []):
        if t.get("projectId") == pid and t.get("status") in (None, "todo", "in_progress"):
            t["status"] = "dropped"
    return _d._Continue(_extra)


def _a_add_meeting(action, payload, db, _extra) -> dict:
    # V2-473 — the write does not INVENT. Measured in `dentist-appointment-into-agenda` round 1
    # (2026-08-29): an empty payload wrote «Cita, today, 17:00» — every field a default wearing the
    # face of success — and the reply said «Hecho.». A write with none of the real fields is an error
    # that names the expected keys (so the model retries with the right shape), never a silent row.
    if not any(str(payload.get(k) or "").strip() for k in ("title", "date", "startTime", "time")):
        # V2-652 — two audiences: `error` coaches the MODEL's retry and must never be spoken;
        # `message` is what the operator may hear (data_ops.report_failure only voices `message`).
        return {"ok": False,
                "error": "no me ha llegado ningún dato de la cita — vuelve a llamar a add_meeting "
                         "con el título, el día (YYYY-MM-DD) y la hora (HH:MM), sin preguntarle nada "
                         "al operador si ya te los dijo",
                "message": _d._spoken("agenda_no_data")}
    # ⚠️ …and a missing TITLE is the same kind of fact as a missing hour (V2-689). This line used to
    # default to «Cita», which is how the operator ended up with two events in his real Google Calendar
    # for one sentence: the STT delivered «Add me one item to my agenda on» as a fragment, the turn ran
    # on it, `date` was present so the guard above let it through, and the agenda wrote an all-day «Cita»
    # on the 17th. The real one («Dentist», 17:00) arrived with the next turn and sat beside it.
    # A word we chose is not a title he said — and once it reaches Google it is a row in HIS calendar
    # that only he can delete. Refused with the same two audiences as the guard above: `error` coaches
    # the model's retry, `message` is the only half that may be spoken.
    title = str(payload.get("title") or "").strip()
    if not title:
        return {"ok": False,
                "error": "la cita no lleva título — vuelve a llamar a add_meeting con `title`, además "
                         "del día (YYYY-MM-DD) y la hora (HH:MM); NO inventes un título genérico",
                "message": _d._spoken("agenda_no_title")}
    # V2-026: normalize spoken date/time into date=+1d and startTime='17:00' when appropriate, so the meeting
    # lands correctly even if the model does not calculate the date itself.
    _rawdate = str(payload.get("date", "") or "")
    # V2-473 round 3: three probe samples in a row sent `time`, not the manifest's `startTime`, and the
    # hour fell to the default AGAIN. The unambiguous natural alias must not cost the fact (V2-341).
    _rawtime = str(payload.get("startTime", "") or payload.get("time", "") or "")
    # V2-473 — the model's natural datetime shape («2026-09-08 15:00», or with a T) is BOTH fields in
    # one: the date resolver kept the date and silently dropped the hour, so «a las tres de la tarde»
    # became the 17:00 default. The glued hour fills startTime only when none was given explicitly.
    _m = _d.re.match(r"^\s*(\d{4}-\d{2}-\d{2})[T ]+(\d{1,2}:\d{2})\s*$", _rawdate)
    if _m:
        _rawdate = _m.group(1)
        if not _rawtime.strip():
            _rawtime = _m.group(2)
    date = _d._resolve_date(_rawdate)
    if not _rawtime.strip():
        # V2-652 — a missing hour is a FACT, never a slot for a default. The old `default="17:00"`
        # dressed absence up as an afternoon appointment: the promise backstop wrote title+date, the
        # agenda invented 17:00, and the operator read it as us copying his «hoy tengo reunión a las
        # cinco» (session 7f77e2cc). No hour given → an all-day entry, which the calendar already
        # renders honestly («todo el día»); the hour arrives later through the timed twin settlement
        # below or through update_meeting.
        _new = {"title": title, "date": date, "allDay": True}
    else:
        start = _d._resolve_time(_rawtime)
        end = payload.get("endTime", "")
        if not _d.re.match(r"^\d{1,2}[:h]\d{2}$|^\d{2}:\d{2}$", str(end)):
            # A DURATION is how he says the end («a 45-minute slot»): the model sent `duration: 45` and
            # the card answered «no sé guardar duration», wrote a one-hour row and told him so (V2-773
            # final pass, C3). The same keys `move_meeting` already reads (`edit._DUR_KEYS`).
            _dur = next((str(payload.get(k) or "") for k in _d.edit._DUR_KEYS if str(payload.get(k) or "").strip()), "")
            _m = _d.re.search(r"\d{1,3}", _dur)
            if _m and 0 < int(_m.group()) <= 24 * 60:
                _t = int(start[:2]) * 60 + int(start[3:5]) + int(_m.group())
                end = f"{(_t // 60) % 24:02d}:{_t % 60:02d}"
            else:
                eh = (int(start[:2]) + 1) % 24         # no explicit end -> +1h
                end = f"{eh:02d}:{start[3:5]}"
        _new = {"title": title, "date": date, "startTime": start, "endTime": end}
    # V2-639 — the operator asks WHAT an appointment is («qué es ese punto del dentista»); a title is
    # a label, the substance travels in `notes` (place, who with, what to bring…), shown in the digest.
    # V2-643 adds the rest of what a calendar entry is: who is coming, where, which category, and
    # whether the other side has confirmed.
    _d._apply_details(_new, payload)
    # V2-769 — the RULE travels with the row (`recur.py`), and a key nothing reads is reported, not dropped.
    if (_why := _d.recur.attach(_new, payload, _d._today())):
        return {"ok": False, "error": _why}
    date = str(_new.get("date") or date)
    _extra = {"ignored": _d.recur.ignored_keys(payload), "stored": dict(_new),
              "revert": {"action": "cancel_meeting", "payload": {"title": title, "date": date, "whole": True}}}
    if "status" not in _new:
        # An appointment WITH other people starts awaiting their answer; one you simply put in your own
        # day is settled the moment you say it. Same default every calendar uses for an invitation.
        _new["status"] = "pending" if _new.get("attendees") else "confirmed"
    # V2-652 — the HOUR-LESS TWIN: the backstop's all-day entry, then «a las once y media» as a TIMED add, stood
    # side by side («dos ítems», session 7f77e2cc). A timed write SETTLES the all-day twin in place; an all-day
    # write over a timed twin adds nothing — either way the timed row is the richer fact.
    _meets = db.get("meetings", [])

    def _twin_of(m: dict) -> bool:
        return (str(m.get("date") or "") == str(_new.get("date") or "")
                and _d._titles_overlap(m.get("title"), _new.get("title")))

    if _new.get("allDay"):
        _twin = next((m for m in _meets if _twin_of(m)), None)   # timed or all-day — either way it exists
        if _twin is None:
            _d.gcal.commit_meeting(db, _new)   # no auto reminder: ~2h before needs an hour
            _d.edit.touch(db, _new)
        elif _d._settle_rule(db, _twin, _new):
            _extra["stored"] = dict(_twin)
    else:
        _ad = next((m for m in _meets if m.get("allDay") and _twin_of(m)), None)
        if _ad is not None:
            # settle in place: the dictated title and hour win; what only the old row knew survives.
            _d._cancel_reminder(_ad)
            for k in ("allDay", "reminder_id", "remindAt"):
                _ad.pop(k, None)
            for k, v in _new.items():
                _ad[k] = v
            _d.gcal.patch_google(_ad)   # the twin may already be a Google event (V2-679) — mirror the settle
            _jid, _at = _d._schedule_reminder(_ad.get("title", title), date, _ad.get("startTime", ""))
            if _jid:
                _ad["reminder_id"], _ad["remindAt"] = _jid, _at
        # V2-208: the SAME meeting twice (see `_is_same_meeting`). A duplicate notice is heard once; a
        # duplicate meeting is SEEN, and remains there until someone deletes it manually.
        elif (_refused := _twins.series_refusal(_new, _meets)) is not None:      # V2-781 T520
            return _refused
        elif (_same := next((m for m in _meets if _d._is_same_meeting(_new, m)), None)) is not None:
            if _d._settle_rule(db, _same, _new):     # V2-773: the twin takes the rule it did not carry
                _extra["stored"] = dict(_same)
        else:
            # V2-473 — the default reminder is the AGENDA's job, not the model's conduct. Measured in
            # `dentist-appointment-into-agenda` round 2: asked for a notice, the model escalated to a
            # WORKER that died on Google's login screen, said «Hecho», and `scheduled_jobs` stayed
            # empty. Telling the agent an appointment schedules its notice (~2h before) with nobody
            # asking (INI-026 A2); moving it is `set_reminder`. Best-effort: a scheduler failure must
            # not lose the WRITE — but it is stored on the meeting, so the state never claims a notice
            # that does not exist.
            _rday = _d.recur.next_occurrence(_new, _d._today()) or date
            _jid, _at = _d._schedule_reminder(title, _rday, _new.get("startTime", ""))
            if _jid:
                _new["reminder_id"], _new["remindAt"] = _jid, _at
            if _new.get("repeat"):
                _new["remindFor"] = _rday
            _d.gcal.commit_meeting(db, _new)
            _d.edit.touch(db, _new)
    return _d._Continue(_extra)


def _a_dedupe_meetings(action, payload, db, _extra) -> dict:
    # «Simplify to one» (V2-710): keeps one of each identical group. Same persist/answer shape as
    # `cancel_meeting`, and the duplicate KEY is shared with it so the two cannot disagree.
    res, stuck = _d.sweep.dedupe_meetings(db, payload)
    if not res.get("ok"):
        return {**_d.view_data(), **res}
    db["currentPlan"] = _d.compute_plan(db)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data()
    d.update({"ok": True, "result": res})
    if stuck:
        d.update({"ok": False, "error": f"Dejé una de cada, pero Google no me dejó borrar {len(stuck)}."})
    return d


def _a_cancel_meeting(action, payload, db, _extra) -> dict:
    # ONE appointment, never «all of them» (V2-705): the decision lives in `sweep.py` next to
    # `clear_range` — an ambiguous title is a question back to him, not a bulk delete. Persist + answer here.
    res, stuck = _d.sweep.cancel_meeting(db, payload)
    if not res.get("ok"):
        if res.get("code") == "series_needs_scope":        # V2-769: he hears a question, the model its fix
            res = {**res, "message": _d._spoken("agenda_series_scope")}
        elif res.get("error") == "ambiguous" and res.get("options"):   # V2-770: never a bare code aloud
            res = {**res, "message": _d._spoken("ask_which_item").replace("{cands}", ", ".join(res["options"][:4]))}
        elif res.get("error") == "not_found":
            _soon = sorted({str(m.get("title") or "") for m in db.get("meetings", []) if m.get("title")})[:4]
            res = {**res, "message": (_d._spoken("widget_selector_missing").replace("{options}", ", ".join(_soon))
                                      if _soon else _d._spoken("widget_selector_missing_bare"))}
        return {**_d.view_data(), **res}
    db["currentPlan"] = _d.compute_plan(db)
    _d.store.save(_d.WIDGET_ID, db)
    d = _d.view_data()
    if stuck:
        d.update({"ok": False, "result": res,
                  "error": f"Borré {res['removed']}, pero Google no me dejó borrar "
                           f"{len(stuck)}: " + ", ".join(f"«{m.get('title')}»" for m in stuck[:4])})
        return d
    d.update({"ok": True, "result": res})
    return d


def _a_set_reminder(action, payload, db, _extra) -> dict:
    # V2-473 — moving the notice is VOCABULARY (the clear_all lesson: a frequent intention with no
    # action cannot be gotten right). Finds the meeting like cancel_meeting does, cancels its current
    # reminder and schedules the new instant; errors NAME what is missing so the model can retry.
    title = _d._strip_accents((payload.get("title") or "").strip().lower())
    raw_date = payload.get("date", "")
    date = _d._resolve_date(raw_date) if raw_date else ""
    _hits = [m for m in db.get("meetings", [])
             if (not title or title in _d._strip_accents(m.get("title", "").strip().lower()))
             and (not date or _d.recur.on(m, date))]
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
    res = _a_add_meeting(action, {k: v for k, v in payload.items() if k not in _d.reminders.ASK_KEYS}, db, _extra)
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


def _a_clear_range(action, payload, db, _extra) -> dict:
    # CLEAR A WINDOW, KEEPING WHAT HE NAMES (V2-693). The decision lives in `sweep.py`; what stays here is
    # the part that belongs to this branch — persist, recompute the plan, and answer.
    #
    # IRREVERSIBLE -> `confirm:true`, and the question this widget hands the gate NAMES the count and the
    # keepers, so what he is agreeing to is on screen before he agrees to it.
    res, stuck = _d.sweep.clear_range(db, payload)
    if res.get("ok") is False:
        # A keeper that names nothing (V2-720): nothing was touched and nothing is persisted. The turn
        # reports WHICH one was not there and what the window really holds, so the retry aims at a real
        # title instead of repeating the sweep that would delete everything.
        d = _d.view_data()
        d.update({"ok": False, "result": res, "error": res.get("detail") or res.get("error")})
        return d
    db["currentPlan"] = _d.compute_plan(db)
    _d.store.save(_d.WIDGET_ID, db)
    # `view_data()` with NO argument, like every other branch here: this widget's `apply_action` has no
    # `q` in scope (that is the contacts widget's shape) and the first live call died on a NameError —
    # after the deletion and the Google calls had already gone through, which is the worst place for a
    # crash: the work was done and the caller was told it failed.
    d = _d.view_data()
    if stuck:
        # An ERROR, so the turn reports it instead of answering «hecho» over a job half done.
        d.update({"ok": False, "result": res,
                  "error": f"Borré {res['removed']}, pero Google no me dejó borrar "
                           f"{len(stuck)}: " + ", ".join(f"«{m.get('title')}»" for m in stuck[:4])})
        return d
    d.update({"ok": True, "result": res})
    return d


def _a_clear_all(action, payload, db, _extra) -> dict:
    # EMPTY THE ENTIRE AGENDA in ONE action (2026-08-14, session b70a45d0).
    #
    # The operator asked «vacía la agenda por completo, hoy y siempre» SIX times in four minutes and it was not
    # emptied. It was not a model failure: this API simply **could not express that intention**. There were only
    # single-item actions (`drop` one task, `cancel_meeting` one meeting, `drop_project` one project), so the
    # FlashBrain could only remove one thing per turn — and each turn said «hecho», which was true of the action
    # it had triggered and false of what it had been asked to do. On the 4th attempt it escalated to a worker,
    # which died holding the authorization because of another, separate failure.
    #
    # When a frequent intention does not fit in the declared vocabulary, the model has no way to get it right:
    # the answer is to expand the vocabulary, not fine-tune the prompt. The two slowest turns of the session
    # (25.6 s of TTFT each) were precisely the ones spent on this impossible decision.
    #
    # IRREVERSIBLE → the manifest marks it `confirm:true`, and the gate in `widgets/confirm.py` asks for yes/no first.
    # All THREE lists are emptied: without them, «por completo» would still be false. Projects are FROZEN
    # (`frozen`, the same state as `drop_project`) instead of being deleted: they are the operator's working
    # memory, and they asked for an empty agenda, not to lose what each project was about.
    for t in db.get("tasks", []):
        if t.get("status") in (None, "todo", "in_progress"):
            t["status"] = "dropped"
            t["updatedAt"] = _d._today()
    for p in db.get("projects", []):
        p["status"] = "frozen"
    for m in db.get("meetings", []):
        _d._cancel_reminder(m)                        # V2-473: emptied appointments take their alarms along
    db["meetings"] = []
    db["blocks"] = []
    # The day's FRAME (working hours, lunch time) is NOT touched: it comes from its configuration
    # (`lunchStart`/`lunchEnd`), not from anything the operator scheduled. Deleting it when asking for an empty
    # agenda would leave the schedule broken tomorrow without explaining why. Changing the frame is «cambia mi horario».
    return _d._Continue(_extra)


def _a_move_meeting(action, payload, db, _extra) -> dict:
    # V2-639 — moving an appointment had NO name: the only path was cancel + re-add, two turns the model
    # never chains. The reminder MOVES with it (an alarm for the old day fires a ghost, the V2-473 rule).
    # V2-770 — found tolerantly like cancel; an END can be said; a DATED move of a series moves that day only.
    _hits = _d.edit.find(db, payload)
    if not _hits:
        return {"ok": False, "error": _d.edit.missing(db, payload)}
    _rawnew = str(payload.get("newDate") or payload.get("new_date") or payload.get("day")
                  or payload.get("to") or "").strip()
    # `newStartTime` because its END twin `newEndTime` was already read (`edit._END_KEYS`) and the start
    # was not: «Move it 30 minutes later» → {newStartTime 16:45, newEndTime 17:30} STRETCHED the meeting to
    # 16:15-17:30 while the reply said «moved it to 4:45» (demo run, 2026-09-26).
    _rawtime = str(payload.get("newTime") or payload.get("new_time") or payload.get("newStartTime")
                   or payload.get("new_start_time") or payload.get("startTime")
                   or payload.get("time") or "").strip()
    _mgl = _d.re.match(r"^\s*(\d{4}-\d{2}-\d{2})[T ]+(\d{1,2}:\d{2})\s*$", _rawnew)
    if _mgl:                                           # glued «YYYY-MM-DD HH:MM» is both fields in one
        _rawnew = _mgl.group(1)
        if not _rawtime:
            _rawtime = _mgl.group(2)
    _rawend = any(str(payload.get(k) or "").strip() for k in _d.edit.TIME_KEYS[6:])
    if not _rawnew and not _rawtime and not _rawend:
        return {"ok": False,
                "error": "me falta el destino — mándame `newDate` (mañana, jueves, YYYY-MM-DD), "
                         "`newTime` (HH:MM) y/o `endTime`"}
    m = _hits[0]
    _day = _d._resolve_date(str(payload["date"])) if str(payload.get("date") or "").strip() else ""
    if _day and isinstance(m.get("repeat"), dict) and not payload.get("whole"):
        _one = _d.edit.detach(db, m, _day)                # this day leaves the series; the rest stays put
        if _one is None:
            return {"ok": False, "error": f"«{m.get('title')}» no cae el {_day} — dime qué día es"}
        _d.gcal.patch_google(m)
        m = _d.gcal.commit_meeting(db, _one)
    new_date = _d._resolve_date(_rawnew) if _rawnew else str(m.get("date") or _d._today())
    new_start = _d._resolve_time(_rawtime) if _rawtime else str(m.get("startTime") or "17:00")
    _end = _d.edit.end_of(m, payload, new_start)
    _d._cancel_reminder(m)
    if _rawnew and (m.get("repeat") or {}).get("freq") == "weekly":   # V2-769: a series moves every week
        m["repeat"]["days"] = [_d.recur.weekday(new_date)]
    m["date"], m["startTime"], m["endTime"] = new_date, new_start, _end
    m.pop("reminder_id", None); m.pop("remindAt", None)
    _d.gcal.patch_google(m)   # V2-679: a moved Google-origin meeting is rescheduled on Google too
    _jid, _at = _d._schedule_reminder(m.get("title", "Cita"), _d.recur.next_occurrence(m, _d._today()) or new_date,
                                   new_start)
    if _jid:
        m["reminder_id"], m["remindAt"] = _jid, _at
    _extra = {"stored": dict(m)}
    _d.edit.touch(db, m)
    return _d._Continue(_extra)


def _a_open_meeting(action, payload, db, _extra) -> dict:
    # V2-770 — the appointment's CARD, by voice: a view push like `show_day`, nothing else is written.
    res = _d.edit.open_detail(db, payload) if action == "open_meeting" else _d.edit.close_detail(db)
    if not res.get("ok"):
        return res
    _extra = res
    return _d._Continue(_extra)


def _a_update_meeting(action, payload, db, _extra) -> dict:
    # V2-643 — the DETAILS of an appointment already in the agenda: «el dentista ya me lo ha
    # confirmado», «apunta que vienen cuatro», «es en la clínica Ruiz». Date and time are NOT edited
    # here — moving an appointment reschedules its notice, and that belongs to move_meeting, which
    # owns the reminder. One door per consequence.
    _hits = _d.edit.find(db, payload)
    if not _hits:
        return {"ok": False, "error": _d.edit.missing(db, payload)}
    _fields = ("notes", "details", "location", "place", "category", "attendees", "people", "with",
               "status", "confirmed", "allDay", "all_day", "newTitle") + _d.recur.ALL_KEYS
    if not any(k in payload for k in _fields):
        return {"ok": False,
                "error": "no me has dicho qué cambiar — manda alguno de: status (confirmed/pending), "
                         "attendees, location, category, notes o newTitle"}
    m = _hits[0]
    if (_why := _d.recur.update(m, payload, _d._today())):            # V2-769 — its rule is a detail too
        return {"ok": False, "error": _why}
    _extra = {"ignored": _d.recur.ignored_keys(payload), "stored": dict(m)}
    _d._apply_details(m, payload)
    _nt = str(payload.get("newTitle") or "").strip()
    if _nt:
        m["title"] = _nt[:160]
    _d.edit.touch(db, m)
    _d.gcal.patch_google(m)   # V2-679: an edited Google-origin meeting is patched on Google too
    return _d._Continue(_extra)


def _a_invite(action, payload, db, _extra) -> dict:
    # V2-718 — «¿me puedes mandar el enlace por mail?» / «mándale la invitación». The verb the agenda
    # never had: it could create a meeting, edit it, answer somebody else's and delete it, and had no
    # way to invite anyone to its own. Two rungs (the calendar sends it when the meeting lives there,
    # an .ics by mail when it does not) live in `invite.py`, which also answers the consent question.
    from . import invite as _invite
    _res = _invite.run(db, payload)
    if not _res.get("ok"):
        return {"ok": False, "error": str(_res.get("error") or "no pude mandar la invitación")}
    _d.store.save(_d.WIDGET_ID, db)
    return {**_d.view_data(), "ok": True, "message": _res.get("message", ""),
            "invited": _res.get("invited") or [], "how": _res.get("how", "")}


def _a_rsvp_meeting(action, payload, db, _extra) -> dict:
    # V2-697 — ANSWER an invitation somebody else convened. Distinct from `update_meeting`'s `status`,
    # which is a note the operator takes about the OTHER party («el dentista ya me lo ha confirmado»);
    # this one travels to Google and tells the organizer. Two facts, two doors.
    #
    # Deliberately NOT offering «propose another time»: the operator scoped this to yes/no («yo por
    # ahora no haría la funcionalidad de proponer otra hora, pero sí diría si sí o si no»).
    _ans = _d._strip_accents(str(payload.get("answer") or payload.get("rsvp") or "").strip().lower())
    _yes = ("accepted", "accept", "yes", "si", "acepto", "aceptar", "voy", "asisto", "confirmo")
    _no = ("declined", "decline", "no", "rechazo", "rechazar", "no voy", "no asisto")
    if _ans in _yes:
        _ans = "accepted"
    elif _ans in _no:
        _ans = "declined"
    elif _ans in ("tentative", "maybe", "quiza", "quizas", "tal vez"):
        _ans = "tentative"
    else:
        return {"ok": False, "error": "dime si aceptas o rechazas la invitación"}
    title = _d._strip_accents((payload.get("title") or "").strip().lower())
    raw_date = payload.get("date", "")
    date = _d._resolve_date(raw_date) if raw_date else ""
    _hits = [m for m in db.get("meetings", [])
             if (not title or title in _d._strip_accents(m.get("title", "").strip().lower()))
             and (not date or _d.recur.on(m, date))]
    if not title or not _hits:
        return {"ok": False,
                "error": "no encuentro esa invitación — dime el título tal como está apuntada "
                         "(y la fecha si hay varias)"}
    m = _hits[0]
    _ok, _why = _d.gcal.rsvp_google(m, _ans)
    if not _ok:
        # The local row is left UNTOUCHED on purpose. A response status only means anything because the
        # organizer can see it; writing it here while Google never heard it would paint an answer the
        # other side is still waiting for (the `delete_google` lesson, V2-693).
        return {"ok": False, "error": _why}
    # Success falls through to the common tail: `rsvp_google` folded Google's echo back into `m`, which
    # is the same object `db["meetings"]` holds, so the card repaints with the answer Google confirmed.
    return _d._Continue(_extra)


def _a_proposal(action, payload, db, _extra) -> dict:
    # V2-697 — the operator's answer to an appointment somebody else asked for. ALWAYS manual, by his own
    # scoping: a cluster peer's handle is self-declared, so the name attached to a proposal is a label he
    # reads, never an authorization. Accepting is what grants `schedule` and books it.
    from nucleo.errands import proposals as _p
    _eid = str(payload.get("errand_id") or payload.get("id") or "").strip()
    res = _p.accept(_eid) if action == "accept_proposal" else _p.decline(_eid)
    if not res.get("ok"):
        return {"ok": False, "error": str(res.get("error") or "no pude registrar tu respuesta")}
    return {**_d.view_data(), "ok": True, "result": res}


def _a_show_day(action, payload, db, _extra) -> dict:
    # V2-540 — CHANGE THE VIEW is an action, because otherwise it is a PROMISE.
    # Measured in the operator's own session (2026-09-01 15:11, events 873/931/995): he asked three times
    # for tomorrow, the brain replied «Te abro la agenda con la vista de mañana» — and the only thing that
    # ever fired was a bare `show:agenda`, which opens on TODAY. It answered right and did nothing, because
    # the day tabs were pure DOM state (`el._agSel`) with no name in the manifest: there was no wrong tool
    # to pick, there was NO tool. An undeclared capability is not a capability the model can decline; it is
    # one it will narrate.
    #
    # `n` is a monotonic PUSH COUNTER, and it is what makes this work twice. The canvas re-renders on a
    # store write only when the data's JSON signature CHANGES, and the widget re-applies the view only when
    # the token moves — so without `n`, asking for tomorrow, clicking back to today and asking again would
    # write the identical `sel`, change no signature and move nothing, which is the exact failure being
    # fixed here wearing a different mask.
    # V2-639 — the model's natural alias must not cost the fact (the V2-341/V2-473 rule). Measured
    # live 2026-09-09 19:27: «Muéstrame la agenda con vista mensual» arrived as `{view: 'month'}`,
    # only `day`/`date` were read, and the view silently fell to TODAY four requests in a row.
    _raw = str(payload.get("day") or payload.get("date") or payload.get("view")
               or payload.get("mode") or payload.get("vista") or "").strip()
    _n = _d._strip_accents(_raw.lower())
    if "seman" in _n or "week" in _n:
        _sel = "week"
    elif "mes" in _n or "month" in _n:
        _sel = "month"
    elif "lista" in _n or "list" in _n or "agenda" in _n or "schedule" in _n or "proximo" in _n:
        _sel = "list"                              # V2-643: the classic Schedule/Agenda view
    else:
        _sel = _d._resolve_date(_raw)                 # spoken relative date -> YYYY-MM-DD (today if unsaid)
    import time as _tm
    db["view"] = {"sel": _sel, "n": int((db.get("view") or {}).get("n", 0)) + 1, "at": _tm.time()}
    # WHAT the card now shows, as the action's answer (demo pass 31, R2). «when does anna's vacation start?
    # show me in the calendar» → show_day 2026-12-20, where «Anna vacation» sits; the turn then answered from
    # the op's return — the generic view, i.e. THIS week — and said «there's nothing in your calendar about
    # Anna's vacation». A day view answers with that day's rows.
    if _d.re.match(r"^\d{4}-\d{2}-\d{2}$", str(_sel)):
        from . import query as _q_sd
        _extra = {"result": {"day": _sel, "meetings": [
            {k: m.get(k) for k in ("title", "date", "startTime", "endTime", "time", "end", "allDay", "status")
             if m.get(k) not in (None, "")}
            for m in (db.get("meetings") or []) if _q_sd._on_day(m, _sel)]}}
    return _d._Continue(_extra)


def _a_find_free(action, payload, db, _extra) -> dict:
    # A QUESTION about the day, answered without writing (see `free.py`): the day's free stretches, and the
    # card moves to that day so what he is told is what he sees.
    from . import free as _free
    # A DATE under `from`/`to` is the stretch, not a clock window (full21 R3: {from: 2026-12-20, to: 2027-01-04}).
    _is_date = lambda v: bool(_d.re.match(r"^\d{4}-\d{2}-\d{2}", str(v or "").strip()))  # noqa: E731
    if _is_date(payload.get("from")) and not payload.get("date"):
        payload = {**payload, "date": payload["from"], "from": ""}
    if _is_date(payload.get("to")) and not payload.get("until"):
        payload = {**payload, "until": payload["to"], "to": ""}
    _said = str(payload.get("date") or payload.get("day") or payload.get("from_date") or "").strip()
    if not _said:
        # full21 R3: «five days in her vacation where i'm free» arrived as find_free {} — the resolver's «today»
        # default answered about today and «I can't give you five dates». A search with no day is refused and
        # says what is missing, so the same-turn correction can ask the right thing.
        return {"ok": False, "error": "find_free needs `date` (the day, or the first day) — and `until` "
                                      "(the last day) to search a stretch, e.g. a vacation's dates"}
    _day = _d._resolve_date(_said)
    _until = str(payload.get("until") or payload.get("to_date") or payload.get("end_date") or "").strip()
    if not _until and _is_date(_day):
        # The stretch written where the action does not read it (demo pass 88, R3): the repair pass sent
        # {date: 2026-12-20, notes: «… vacaciones de Anna (2026-12-20 a 2027-01-04)»}, searched ONE day, and the
        # answer asked him for dates he had just been told. A later ISO date in the call's own text is the last day.
        _later = sorted(x for v in payload.values() if isinstance(v, str)
                        for x in _d.re.findall(r"\b\d{4}-\d{2}-\d{2}\b", v) if x > str(_day)[:10])
        if _later:
            _until = _later[-1]
    import time as _tm
    db["view"] = {"sel": _day if not _until else "month", "n": int((db.get("view") or {}).get("n", 0)) + 1,
                  "at": _tm.time()}
    _d.store.save(_d.WIDGET_ID, db)
    if _until:
        return _free.find_span(db.get("meetings") or [], _day, _d._resolve_date(_until), payload)
    return _free.find(db.get("meetings") or [], _day, payload)


def _a_connection(action, payload, db, _extra) -> dict:
    # V2-679 — the default-calendar picker; body in `gcal.py`. Connecting and disconnecting Google Calendar
    # left the card on 2026-10-04: they live in the ⚙ Conectores section, the one door for every service.
    res = _d.gcal.ui_action(action, payload, db)
    if action != "set_default_calendar":
        return res
    if not (res or {}).get("ok"):
        return res
    _d.store.save(_d.WIDGET_ID, db)
    return _d.view_data()
