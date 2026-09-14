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
        return {"ok": False, "why": "el mandato no incluye agendar"}
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
    # ⚠️ ONE ERRAND, ONE MEETING (V2-692d). Measured on this batch's own live run: the worker wrote
    # «Meeting with Pruebas Zaelar» at 16:00 and the errand wrote «Meeting with Cryptonite» at 16:00, for
    # the same order and the same person — two rows in his real calendar for one appointment. The agenda's
    # own duplicate guard could not see it: `_is_same_meeting` compares TITLES, and the two came from two
    # names for one contact (the directory's, and the one the conversation carries). An errand knows
    # something the agenda cannot — that the slot it is about to write is the one it has been negotiating —
    # so the check that belongs here is the SLOT, not the words. The duplicate cost the operator a row only
    # he can delete, which is the same currency V2-689 paid for the defaulted «Cita».
    already = _meeting_at(date, start)
    if already is not None:
        logger.info(f"errands.book: {errand.get('id')} ya tenía cita el {date} a las {start} — no duplico")
        return {"ok": True, "link": str(already.get("meetLink") or already.get("hangoutLink") or ""),
                "date": date, "time": start, "already": True}
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
    return {"ok": True, "link": link, "date": date, "time": start}


def _meeting_at(date: str, start: str) -> dict | None:
    """A meeting already standing in THIS slot, whatever it is called.

    Deliberately blind to the title: the whole point is that two names for one person produced two rows.
    An appointment the operator already had at that hour is also a reason not to write a second one — he
    would then have two overlapping rows and no way to tell which one the errand meant.
    """
    try:
        from widgets.agenda import data as agenda
        rows = (agenda.load_db() or {}).get("meetings") or []
    except Exception:  # noqa: BLE001
        return None
    for m in rows:
        if isinstance(m, dict) and str(m.get("date") or "") == date \
                and str(m.get("startTime") or "") == start:
            return m
    return None


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
