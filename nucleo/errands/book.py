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
