"""nucleo/errands/book.py — the errand WRITES the meeting it just agreed (V2-692).

`party.parse` has always returned an `agreed` block — `{start, end, medium}` — and until today NOBODY READ
IT. The errand reached state `agreed`, said so, and stopped: nothing was written to the agenda, nothing
reached Google, no Meet link was ever minted, and the row then expired hours later announcing «se acordó
con la otra persona y se acabó el plazo sin que quedara confirmado». Measured on the second live run
(2026-09-14): the operator drove every one of those steps by hand and the meeting still did not exist.

**The ENGINE writes it, never the model.** The rule the party turn is built on does not bend here: a
stranger's sentence reaches a model with no tools, the model returns a decision, and this module decides
what of it may happen — inside the mandate the operator granted, and nowhere else. What the model
contributes is a start time it read from the conversation; what it cannot do is choose a calendar, invent
an attendee, or write anything at all.

**The link is ours too.** `party.build_system` forbids the model to write a URL, because it has none and
the one thing worse than no link is a made-up one. The Meet link is minted by Google as `conferenceData`
on the event this module creates (V2-685) and appended to the reply afterwards — so the promise the model
makes («te paso el enlace») is one the engine keeps in the same message.
"""
from __future__ import annotations

import re

from loguru import logger

#: What a `medium` may say and what it means for the write. `meet` is the only one that mints a conference;
#: the others are honest about being a plain appointment.
_VIDEO = ("meet", "video", "videollamada", "hangout", "zoom", "online")

#: «2026-09-15 19:00», «2026-09-15T19:00», «2026-09-15 19:00:00» — the shapes a model writes for the format
#: `party.SHAPE` asks for. Anything else is not repaired: a misread hour is a meeting at the wrong time in
#: somebody's real calendar, and refusing to write costs one more exchange.
_WHEN_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})[T ]+(\d{1,2}):(\d{2})")


def _when(raw) -> tuple[str, str] | None:
    m = _WHEN_RE.match(str(raw or ""))
    if not m:
        return None
    hh = int(m.group(2))
    if not 0 <= hh <= 23:
        return None
    return m.group(1), f"{hh:02d}:{m.group(3)}"


def _title(party: str) -> str:
    """From the language table, never an f-string here (V2-676): this lands in his real calendar."""
    tmpl = "Reunión con {name}"
    try:
        from i18n import langs as _langs
        tmpl = str(getattr(_langs.spec(), "errand_meeting_title", "") or tmpl)
    except Exception:  # noqa: BLE001
        pass
    name = (party or "").strip()
    try:
        return tmpl.format(name=name).strip() if name else tmpl.replace("{name}", "").strip(" .·-")
    except Exception:  # noqa: BLE001
        return tmpl


def can_mint_link() -> bool:
    """Can a Google Meet link actually be created right now? (V2-692d)

    ⚠️ This function exists because of a defect THIS BATCH introduced, caught on its own live run
    (2026-09-14, 19:37). V2-683 forbade the model to promise a link because nothing could make one; V2-692
    built the mechanism and lifted the prohibition — UNCONDITIONALLY, which is the same lie from the other
    side. The operator's Google Calendar was not linked, so the meeting was written locally with no
    conference, and the errand told a real person «the Google Meet link will be sent with the invitation —
    it gets added automatically». Nothing was ever going to arrive.

    A capability the model is told it has is one it PROMISES. So the promise is conditional on the fact,
    and the fact is read here, per use — he can link the calendar between one message and the next.
    Fails CLOSED: unreadable means «do not promise», because a promise nobody keeps is paid by a stranger.
    """
    try:
        from widgets.agenda import gcal
        return bool(gcal.connected())
    except Exception:  # noqa: BLE001
        return False


def may_schedule(errand: dict) -> bool:
    """The mandate is the operator's own grant, and `schedule` is a separate permission from `message`.
    An errand whose mandate cannot be read schedules NOTHING: writing to his calendar is not the direction
    to fail open in."""
    mandate = errand.get("mandate")
    if not isinstance(mandate, dict):
        return False
    may = mandate.get("may")
    return isinstance(may, (list, tuple)) and "schedule" in may


def book(errand: dict, decision: dict, party: str = "") -> dict:
    """Write the agreed meeting. Returns `{"ok", "link", "date", "time", "why"}`.

    Never raises: a failure here must leave the errand exactly where it was, so the next inbound tries
    again, rather than losing an agreement the other person already gave.
    """
    agreed = decision.get("agreed") if isinstance(decision.get("agreed"), dict) else {}
    when = _when(agreed.get("start"))
    if not when:
        return {"ok": False, "why": "sin hora acordada"}
    if not may_schedule(errand):
        # V2-697 — REFUSING TO WRITE IS RIGHT; REFUSING TO ASK IS NOT. This returned here and the agreement
        # died in silence: the other person had said yes, the slot was in hand, and the operator never heard
        # about it. The slot is parked on the errand and announced instead, and his yes — which IS the grant
        # that was missing — comes back through `proposals.accept`, which calls this same function again.
        from . import proposals
        parked = proposals.park(errand, decision, party)
        return {"ok": False, "parked": bool(parked.get("ok")),
                "why": "pendiente de que el operador acepte la cita" if parked.get("ok")
                       else str(parked.get("why") or "el mandato no incluye agendar")}
    date, start = when
    end = ""
    ended = _when(agreed.get("end"))
    if ended and ended[0] == date:
        end = ended[1]
    medium = str(agreed.get("medium") or "").strip().lower()
    payload = {
        "title": _title(party),
        "date": date,
        "startTime": start,
        "attendees": [party] if party else [],
        "notes": str(errand.get("objective") or "")[:300],
        "category": "trabajo",
        # The other side SAID yes — that is what `agreed` means — so the row is not left waiting on them.
        "status": "confirmed",
    }
    if end:
        payload["endTime"] = end
    if medium in _VIDEO:
        payload["meet"] = True
    # ⚠️ ONE ERRAND, ONE MEETING — and the row it owns is the one IT wrote, never whatever shares the hour.
    #
    # V2-692d put a SLOT check here, blind to the title, because two names for one contact had produced two
    # rows. Its own live run showed why that was the wrong key (2026-09-14, 20:27): the operator answered
    # «make it at 17:00», and his real calendar already held FIVE «Dentista» at 17:00 — so the guard read
    # «already booked», wrote nothing, reported success, and `verify` then closed the errand as «hecha y
    # verificada» against the 16:00 row from the previous round. The person was told 17:00 and the calendar
    # said 16:00, pending. A guard that turns «I did nothing» into «done» is worse than the duplicate it
    # replaced — the V2-660 class exactly, arriving through a check I added.
    #
    # The right key is the errand's OWN record: `done_when.at` is the slot it booked, written by the same
    # turn that booked it. Same slot → nothing to do. A DIFFERENT slot → the hour changed, so the meeting
    # MOVES; that is what «they said 17:00 instead» means, and leaving the old row behind is how he ends up
    # with two. And an appointment that merely shares the hour is somebody else's: people double-book, and
    # refusing his meeting in silence because the dentist is at five is not ours to decide.
    mine = _mine(errand, payload["title"])
    if mine is not None and str((errand.get("done_when") or {}).get("at") or "") == f"{date} {start}":
        logger.info(f"errands.book: {errand.get('id')} ya tenía SU cita el {date} a las {start}")
        return {"ok": True, "link": str(mine.get("meetLink") or mine.get("hangoutLink") or ""),
                "date": date, "time": start, "already": True, "video": medium in _VIDEO}
    if mine is not None:
        moved = _move(mine, payload)
        logger.info(f"errands.book: {errand.get('id')} mueve su cita a {date} {start}")
        return {"ok": True, "link": str(moved.get("meetLink") or moved.get("hangoutLink") or ""),
                "date": date, "time": start, "moved": True, "video": medium in _VIDEO}
    try:
        from widgets.agenda import data as agenda
        res = agenda.apply_action("add_meeting", payload)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"errands.book: no pude escribir la cita de {errand.get('id')}: {e!r}")
        return {"ok": False, "why": "la agenda no aceptó la cita"}
    if isinstance(res, dict) and res.get("ok") is False:
        return {"ok": False, "why": str(res.get("error") or "la agenda rechazó la cita")}
    link = _link_of(date, start, payload["title"])
    logger.info(f"errands.book: {errand.get('id')} → cita el {date} a las {start}"
                + (" con enlace de Meet" if link else ""))
    # `video` is what decides whether a MISSING link is a DEBT. A coffee or a phone call owes nobody a
    # conference URL, and an errand that thinks it does would wait for one for ever and tell the operator
    # about a connector it never needed.
    return {"ok": True, "link": link, "date": date, "time": start, "video": medium in _VIDEO}


def done_spec(errand: dict, date: str, start: str, *, owed: bool) -> dict:
    """What closes this errand, now that it has actually WRITTEN a meeting (V2-692e).

    ⚠️ It also repairs a closing condition the errand may never have had. `playbooks.kind_for` reads the
    objective's WORDS, and the live run produced «Confirm Tuesday 15 September 16:00 and send the Google
    Meet link» — an objective entirely about a meeting that never says the word, so it fell to `generic`,
    whose `done_when` is empty. An errand with no closing condition can only ever end by running out of
    time, however well it goes: the V2-692 `created`-stamp defect again, arriving through the vocabulary
    instead of through the data.

    Booking is a FACT and beats the guess: a row that just wrote a meeting is a meeting errand, whatever
    its sentence happened to say. A spec the playbook already filled in is left exactly as it is.
    """
    spec = dict(errand.get("done_when") or {})
    if not spec.get("widget"):
        spec.update({"widget": "agenda", "has": "meeting", "within": "window"})
    spec["at"] = f"{date} {start}"
    if owed:
        spec["link_owed"] = True
    return spec


def note_owed(errand: dict, date: str, start: str) -> dict:
    """Remember that this errand agreed a VIDEO call and could not send the link yet (V2-692e).

    It rides `done_when`, which is already a round-tripped JSON column and is already the answer to «what
    closes this errand» — and a link that was promised IS part of being done. `verify._VERIFIERS` keys on
    (widget, has) and ignores everything else, so the extra fields cost that verifier nothing.

    Without this the errand has no way back: it agreed, wrote the meeting with no conference because the
    calendar was not linked, and then sat in `agreed` until the deadline and announced it was never
    confirmed — AFTER the operator had connected and Google had minted the link. Measured on the live run
    (2026-09-14): «no he recibido el enlace», and he was right that an explanation is not a finish.
    """
    return done_spec(errand, date, start, owed=True)


def link_owed(errand: dict) -> str:
    """The conference link this errand promised and has not sent, once it exists. "" while it does not."""
    spec = errand.get("done_when") or {}
    if not isinstance(spec, dict) or not spec.get("link_owed"):
        return ""
    when = str(spec.get("at") or "")
    got = _when(when)
    if not got:
        return ""
    m = _meeting_at(*got)
    return str((m or {}).get("meetLink") or (m or {}).get("hangoutLink") or "")


def clear_owed(errand: dict) -> dict:
    spec = dict(errand.get("done_when") or {})
    spec.pop("link_owed", None)
    return spec


def _rows() -> list:
    try:
        from widgets.agenda import data as agenda
        return list((agenda.load_db() or {}).get("meetings") or [])
    except Exception:  # noqa: BLE001
        return []


def _meeting_at(date: str, start: str, title: str = "") -> dict | None:
    """The meeting standing in this slot — narrowed by TITLE when one is given, because an appointment that
    merely shares the hour belongs to somebody else's day."""
    for m in _rows():
        if not isinstance(m, dict):
            continue
        if str(m.get("date") or "") != date or str(m.get("startTime") or "") != start:
            continue
        if title and str(m.get("title") or "") != title:
            continue
        return m
    return None


def _mine(errand: dict, title: str) -> dict | None:
    """The row THIS errand wrote, found by the slot it recorded and the title it uses. None before it has
    written anything — which is the ordinary first booking."""
    prev = str((errand.get("done_when") or {}).get("at") or "")
    got = _when(prev)
    return _meeting_at(got[0], got[1], title) if got else None


def _move(m: dict, payload: dict) -> dict:
    """The hour changed. The row MOVES, with its reminder, and Google is told — never a second row."""
    from widgets.agenda import data as agenda, gcal
    from widgets import store
    db = agenda.load_db()
    row = next((r for r in db.get("meetings") or []
                if r.get("date") == m.get("date") and r.get("startTime") == m.get("startTime")
                and r.get("title") == m.get("title")), None)
    if row is None:
        return m
    agenda._cancel_reminder(row)
    for k in ("date", "startTime", "endTime", "notes", "meet", "attendees", "status"):
        if k in payload:
            row[k] = payload[k]
    jid, at = agenda._schedule_reminder(row.get("title", ""), row.get("date", ""), row.get("startTime", ""))
    if jid:
        row["reminder_id"], row["remindAt"] = jid, at
    gcal.patch_google(row)
    db["currentPlan"] = agenda.compute_plan(db)
    store.save(agenda.WIDGET_ID, db)
    return row


def _link_of(date: str, start: str, title: str) -> str:
    """The conference link Google minted, read back from the row that was just written.

    `apply_action` does not return the stored meeting — it persists and answers the whole view — so the row
    is located by the three fields that identify it. Read back rather than assumed: `commit_meeting` only
    reaches Google when the calendar is CONNECTED, and an operator who has not linked one still gets his
    appointment, just without a link. Saying so honestly is the whole point of reading instead of composing
    a URL we hope exists.
    """
    try:
        from widgets.agenda import data as agenda
        rows = (agenda.load_db() or {}).get("meetings") or []
    except Exception:  # noqa: BLE001
        return ""
    for m in reversed(rows):
        if not isinstance(m, dict):
            continue
        if str(m.get("date") or "") == date and str(m.get("startTime") or "") == start \
                and str(m.get("title") or "") == title:
            return str(m.get("meetLink") or m.get("hangoutLink") or "")
    return ""
