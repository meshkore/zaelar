"""widgets/agenda/meeting_views.py — the agenda's READING and INVITING actions: show a day, find a free slot, open a meeting, invite, answer, propose, connection (split from `actions.py`)."""
from __future__ import annotations

from . import data as _d
from . import title_when as _tw
from . import twins as _twins


def _a_open_meeting(action, payload, db, _extra) -> dict:
    # V2-770 — the appointment's CARD, by voice: a view push like `show_day`, nothing else is written.
    res = _d.edit.open_detail(db, payload) if action == "open_meeting" else _d.edit.close_detail(db)
    if not res.get("ok"):
        return res
    _extra = res
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
        _until = _until or _free.span_end(db.get("meetings") or [], str(_day), payload)
    import time as _tm
    db["view"] = {"sel": _day if not _until else "month", "n": int((db.get("view") or {}).get("n", 0)) + 1,
                  "at": _tm.time()}
    _got = (_free.find_span(db.get("meetings") or [], _day, _d._resolve_date(_until), payload) if _until
            else _free.remember(db, _free.find(db.get("meetings") or [], _day, payload), payload))
    _d.store.save(_d.WIDGET_ID, db)
    return _got


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
