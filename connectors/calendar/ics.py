"""connectors/calendar/ics.py — an invitation as a FILE, for everyone who is not on our calendar (V2-718).

## Why this exists

The operator, 2026-09-17, after his assistant negotiated a meeting on Telegram and the other party asked
«can you send me a calendar invite to: ivan@charms.dev»:

> «Entiendo que si vas a usar el conector de Gmail para mandar ese email hay una forma de mandar una
> invitación de Google Calendar que quizás se manda desde Google Calendar para que llegue y él la pueda
> recibir en su propio calendario, no solo un enlace en el email. […] La gente que sea de Apple o de otros
> emails que no usan Gmail o que no tengan calendarios, quizás se hace de otra forma y eso sí que lo tienes
> que parametrizar como una tool o un formato de envío particular.»

He is right about the shape and it is worth stating precisely, because the two halves are often confused:

  · **When the meeting lives in a calendar account we hold** (Google today), the RIGHT answer is not to
    write a mail at all — it is to add the person as a GUEST and let Google send the invitation
    (`service.invite`). That invitation already reaches Apple, Outlook and anyone else: what Google mails is
    a standard iCalendar REQUEST, and the guest's answer comes back into the event. Nothing here is needed.
  · **When there is no calendar account** — a self-hosted install with only mail connected, or a meeting
    that was never synced — nobody will send that invitation for us. This module builds it: the same
    standard object (RFC 5545 VCALENDAR, RFC 5546 METHOD:REQUEST) that every mail client reads as an
    invitation, to be carried by `mailbox.send_invitation` as a `text/calendar` part plus an `.ics`
    attachment.

So this is the SECOND rung of one ladder, not a second way of doing the same thing. Which rung applies is
decided by whether the meeting has a calendar behind it, never by who the recipient is — guessing «this
address looks like Apple» would be a rule about somebody else's mail provider, which is not knowable.

## What it deliberately does not do

No timezone library, no RRULE, no ATTACH, no attendee ROLE/RSVP bookkeeping. An invitation to one meeting
at one time is the whole job; the moment this file starts growing a calendar model of its own it is
re-implementing the connector that already exists.

⚠️ `UID` is the identity of the invitation for the rest of its life. Two mails with the same UID are the
SAME meeting (an update, if SEQUENCE grew); two with different UIDs are two meetings in the guest's
calendar. So it is derived from the meeting whenever the meeting has any identity at all, and random only
when it genuinely has none.
"""
from __future__ import annotations

import datetime as _dt
import re
import uuid as _uuid

#: RFC 5545 §3.1: content lines are folded at 75 OCTETS, continuation lines starting with one space.
_FOLD_AT = 73
_ESCAPE = ((chr(92), chr(92) * 2), (";", r"\;"), (",", r"\,"), ("\n", r"\n"))


def _esc(text: str) -> str:
    out = str(text or "")
    for a, b in _ESCAPE:
        out = out.replace(a, b)
    return out


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= _FOLD_AT:
        return line
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > _FOLD_AT:
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    if cur:
        out.append(cur.decode("utf-8"))
    return ("\r\n ").join(out)


def _utc(date: str, time_: str, offset_minutes: int) -> str:
    """A local wall time as an iCalendar UTC stamp. The offset is passed IN rather than read from the clock:
    the caller (the calendar service) already knows the install's offset, and a second opinion about the
    timezone is how a meeting lands an hour off."""
    d = _dt.date.fromisoformat(str(date))
    hh, mm = (list(int(x) for x in str(time_ or "00:00").split(":")[:2]) + [0, 0])[:2]
    stamp = _dt.datetime(d.year, d.month, d.day, hh, mm) - _dt.timedelta(minutes=offset_minutes)
    return stamp.strftime("%Y%m%dT%H%M%SZ")


def uid_for(meeting: dict) -> str:
    """The invitation's identity. Stable for a meeting we can name, random only when we cannot."""
    seed = str((meeting or {}).get("googleId") or (meeting or {}).get("id") or "").strip()
    if not seed:
        title = re.sub(r"[^a-z0-9]+", "-", str((meeting or {}).get("title") or "").lower()).strip("-")
        date = str((meeting or {}).get("date") or "")
        seed = f"{title}-{date}".strip("-") if title or date else ""
    return f"{seed or _uuid.uuid4().hex}@zaelar"


def build(meeting: dict, *, organizer: str, attendees: list, offset_minutes: int = 0,
          method: str = "REQUEST", sequence: int = 0, uid: str = "") -> str:
    """One VCALENDAR object for `meeting`, ready to be carried by mail.

    `organizer` is the address the invitation comes FROM, and it must be the same mailbox that sends it —
    a REQUEST whose ORGANIZER is somebody else is the shape spam filters are built to reject, and the
    guest's reply would go to an address that is not listening.
    """
    m = meeting or {}
    if not m.get("date"):
        raise ValueError("una invitación necesita una fecha")
    who = [str(a).strip() for a in (attendees or []) if str(a).strip() and "@" in str(a)]
    if not who:
        raise ValueError("una invitación necesita al menos un invitado con correo")
    all_day = bool(m.get("allDay"))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Zaelar//Agenda//ES", "CALSCALE:GREGORIAN",
             f"METHOD:{method}", "BEGIN:VEVENT",
             f"UID:{uid or uid_for(m)}",
             f"DTSTAMP:{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
             f"SEQUENCE:{int(sequence)}"]
    if all_day:
        d = _dt.date.fromisoformat(str(m["date"]))
        lines.append(f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}")
        # An all-day DTEND is EXCLUSIVE — the same rule the Google body already follows one module over.
        lines.append(f"DTEND;VALUE=DATE:{(d + _dt.timedelta(days=1)).strftime('%Y%m%d')}")
    else:
        start = str(m.get("startTime") or "00:00")
        end = str(m.get("endTime") or "") or start
        lines.append(f"DTSTART:{_utc(m['date'], start, offset_minutes)}")
        lines.append(f"DTEND:{_utc(m['date'], end, offset_minutes)}")
    lines.append(f"SUMMARY:{_esc(m.get('title') or 'Reunión')}")
    body = str(m.get("notes") or "").strip()
    link = str(m.get("meetLink") or "").strip()
    if link and link not in body:
        body = (body + "\n\n" + link).strip()
    if body:
        lines.append(f"DESCRIPTION:{_esc(body)}")
    where = str(m.get("location") or "").strip() or link
    if where:
        lines.append(f"LOCATION:{_esc(where)}")
    lines.append(f"ORGANIZER:mailto:{organizer}")
    for a in who:
        lines.append(f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{a}")
    lines += ["STATUS:CONFIRMED", "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(_fold(ln) for ln in lines) + "\r\n"
