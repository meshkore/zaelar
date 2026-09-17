"""widgets/agenda/invite.py — «mándame la invitación» (V2-718).

## The ask

The operator, 2026-09-17, reading the Telegram thread where his assistant had just negotiated a meeting,
agreed a time, minted a Meet link and written it into the agenda — and where the other party's last message
was «can you send me a calendar invite to: ivan@charms.dev», unanswered:

> «Lógicamente si tenemos acceso a ese email y al conector de email y a las acciones y todo, deberíamos
> ejecutar esa petición de Ivan. […] Pero no crees un guardarraíl o un workflow solo para eso: intenta
> asegurarte de que el sistema tiene suficiente capacidad o inteligencia como para resolver esto él mismo.»

So this is not a script for one conversation. It is the missing VERB — the agenda could create a meeting,
edit it, answer somebody else's invitation and delete it, and had no way to invite anyone to its own.

## Two rungs of ONE ladder, chosen by the MEETING, never by the recipient

  1. **The meeting lives in a calendar account we hold.** Add the guest there and let the provider send the
     invitation (`connectors/calendar/service.invite`, with `sendUpdates=all`). What the guest receives is a
     real iCalendar REQUEST their own calendar can accept — on Gmail, on iCloud, on Outlook alike — and
     their answer comes back into the event. This is always the better rung when it is available: the
     meeting and the invitation stay the same object.
  2. **There is no calendar behind it.** Build the invitation ourselves (`connectors/calendar/ics.py`) and
     send it by mail as a `text/calendar; method=REQUEST` part plus an `.ics` attachment
     (`mailbox.send_invitation`), which is the interoperable standard and what every client reads.

⚠️ The rung is decided by whether the meeting has a calendar behind it — NEVER by guessing the recipient's
provider from their address. «This one looks like Apple» is a claim about somebody else's mail setup that
nothing here can know, and it would be wrong the first time a company hosts its own domain on Google.

## Who counts as «already in this meeting»

`consent_scope` below answers the question the consent rule (V2-712) cannot answer on its own: whether this
call stays inside a commitment that was already made, or changes it. Both halves come from data — the
meeting's own guest list and the errand's `mandate.parties` — never from the wording of the request.
"""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _directory():
    from .. import directory
    return directory


def _gcal():
    from . import gcal
    return gcal


def emails_in(text) -> list:
    """Every address written in a value, whatever shape it arrives in (a string, a list, a sentence)."""
    out = []
    items = text if isinstance(text, (list, tuple)) else [text]
    for it in items:
        for tok in re.split(r"[\s,;]+", str(it or "")):
            tok = tok.strip().strip("<>()[]\"'.,")
            if _EMAIL_RE.match(tok) and tok.lower() not in [o.lower() for o in out]:
                out.append(tok)
    return out


def resolve_guests(payload: dict) -> dict:
    """WHO to invite: addresses said out loud, plus the addresses of contacts named by name.

    A name that resolves to a contact WITHOUT an email is not a failure to hide — it is the one fact that is
    missing, and the answer says so by name so the caller can ask for that datum (`ASK_FACT`, never «shall I
    proceed»). A name matching several contacts is returned as a question, the same rule every other door in
    this house follows.
    """
    raw = payload.get("who") or payload.get("email") or payload.get("emails") or payload.get("to") or \
        payload.get("contact") or payload.get("guests") or ""
    mails = emails_in(raw)
    names, missing, ambiguous = [], [], []
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    d = _directory()
    for it in items:
        for part in re.split(r"\s*(?:,|;|\by\b|\band\b|&)\s*", str(it or "")):
            part = part.strip()
            if not part or _EMAIL_RE.match(part):
                continue
            hits = d.resolve(part)
            if len(hits) > 1:
                ambiguous.append((part, [c.get("name") or "" for c in hits[:5]]))
                continue
            if not hits:
                continue
            c = hits[0]
            addr = next((e for e in ([c.get("email")] + [x.get("value") for x in (c.get("emails") or [])])
                         if e and _EMAIL_RE.match(str(e).strip())), "")
            if addr:
                if str(addr).lower() not in [m.lower() for m in mails]:
                    mails.append(str(addr).strip())
                names.append(c.get("name") or part)
            else:
                missing.append(c.get("name") or part)
    return {"emails": mails, "names": names, "missing_email": missing, "ambiguous": ambiguous}


def find_meeting(db: dict, payload: dict) -> "dict | None":
    """The meeting this is about. Falls back to the one meeting the card is SHOWING, and — when nothing at
    all is named — to the next one that still has a guest to invite, which is what «mándale la invitación»
    means right after agreeing one."""
    from .details import _strip_accents  # the house matcher, so a title resolves the same way everywhere
    ms = db.get("meetings") or []
    title = _strip_accents(str(payload.get("meeting") or payload.get("title") or "").strip().lower())
    date = str(payload.get("date") or "").strip()
    hits = [m for m in ms
            if (not title or title in _strip_accents(str(m.get("title") or "").strip().lower()))
            and (not date or m.get("date") == date)]
    if title and not hits:
        return None
    if hits:
        return hits[0] if len(hits) == 1 else sorted(hits, key=lambda m: (m.get("date") or "", m.get("startTime") or ""))[-1]
    open_ = sorted([m for m in ms if m.get("date")], key=lambda m: (m.get("date") or "", m.get("startTime") or ""))
    return open_[-1] if open_ else None


def consent_scope(action: str, payload: dict, db: dict) -> dict:
    """Which consent CLASS this call belongs to — the criterion the operator stated, made mechanical.

    > «Esto por ejemplo que no nos hace ningún daño no necesita permiso. Añadir a otra persona, cambiar de
    > hora o hacer otras cosas sí que obviamente necesitan permiso.»

    The distinction is not «invite» versus «reschedule», and it is not a list of verbs: it is whether the
    call stays inside a commitment that was already made with the people already in it. Sending the person
    who just agreed a meeting the invitation for THAT meeting adds nothing and takes nothing back. Putting a
    THIRD person in the room, or moving the hour somebody else has already blocked, changes what was agreed
    with them — and that is the operator's to grant.

    Returns `{"class": <genesis consent class>}`; the rule in `nucleo/consent.py` decides what to do with it,
    and the operator can override any of those classes by saying so.
    """
    if action in ("move_meeting", "reschedule_meeting"):
        # The other half of the same criterion, and the operator named it in the same breath: «cambiar de
        # hora». An hour only he is holding is his to move without asking; an hour somebody ELSE has already
        # blocked was agreed with them, and moving it is a change to that agreement.
        m = find_meeting(db, payload) or {}
        # «Somebody else is holding this hour» is not only the guest list: a meeting negotiated with
        # somebody is agreed with them whether or not they ended up on the event's roster. Same membership
        # test as the invitation half, so the two answers can never disagree about who is in a meeting.
        committed = [a for a in (m.get("attendees") or []) if str(a).strip()] or _parties_of(m)
        return {"class": "calendar.reschedule_committed"} if committed else {}
    if action != "invite":
        return {}
    m = find_meeting(db, payload) or {}
    guests = resolve_guests(payload)
    roster = {str(a).strip().lower() for a in (m.get("attendees") or []) if "@" in str(a)}
    roster |= {str(a).strip().lower() for a in _parties_of(m)}
    if not guests["emails"]:
        return {"class": "calendar.invite_agreed"}      # nothing resolved: the fact question comes first
    outside = [a for a in guests["emails"] if a.lower() not in roster]
    return {"class": "calendar.invite_new_party" if outside else "calendar.invite_agreed"}


def _parties_of(meeting: dict) -> list:
    """The addresses of the people this meeting is ALREADY with, beyond its guest list.

    Two sources, both data, neither of them a reading of the request:

      1. **The directory.** A meeting that was negotiated with somebody carries their NAME — «Meeting with
         Ivan Mikushin», or the thread that produced it quoted in the notes — so a contact whose name is
         written into this meeting is not a stranger to it, and their stored addresses count.
      2. **What that person WROTE TO US.** An address the other party typed into the conversation is, by
         construction, theirs and one they want to be reached at. Sending them the invitation to the meeting
         they just agreed, at the address they just gave, adds nothing to what was already agreed — which is
         precisely the operator's «esto no hace ningún daño y no necesita permiso». Read through the shared
         archive (`connectors/messaging/archive`), inbound only.

    ⚠️ Its limit, stated rather than hidden: a meeting whose title names nobody («café», «reunión») yields
    nothing here, so every guest reads as new and the invitation asks. That is the safe direction — the harm
    this class of call can do is send somebody's meeting to a stranger, and the cost of asking is one turn.
    """
    from .details import _strip_accents
    hay = _strip_accents(" ".join([str(meeting.get("title") or ""), str(meeting.get("notes") or "")]).lower())
    if not hay.strip():
        return []
    out, named = [], []
    try:
        from .. import textmatch
        d = _directory()
        # The HOUSE matcher, and only an UNAMBIGUOUS hit counts. Walking the directory looking for any name
        # that happens to be a substring of the title is how «Meeting with Ivan Mikushin» quietly adopted a
        # different contact called just «Ivan» — and adopting the wrong person here is exactly the harm this
        # whole question exists to prevent. Two contacts matching is doubt, and doubt is not membership.
        for span in textmatch.spans(str(meeting.get("title") or "")):
            hits = d.resolve(span)
            if len(hits) != 1:
                continue
            c = hits[0]
            name = str(c.get("name") or "").strip()
            if not name or name in named:
                continue
            named.append(name)
            for e in [c.get("email")] + [x.get("value") for x in (c.get("emails") or [])]:
                if e and str(e).strip():
                    out.append(str(e).strip().lower())
    except Exception:  # noqa: BLE001
        return out
    try:
        from connectors.messaging import archive as _arch
        for name in named[:4]:
            # By SENDER, not by chat: a one-to-one conversation carries the person's name on every message
            # they sent and, in this archive, often nothing at all on the thread itself.
            for row in _arch.search(sender=name, direction="in", limit=60) or []:
                for addr in emails_in(row.get("body")):
                    if addr.lower() not in out:
                        out.append(addr.lower())
    except Exception:  # noqa: BLE001
        pass
    return out


def run(db: dict, payload: dict) -> dict:
    """Invite somebody to a meeting. Picks the rung, does it, and says what happened in one sentence.

    Never a silent success: an invitation that did not leave is reported as not having left, because the
    operator's next move (telling the other person it is on its way) depends on this answer being true.
    """
    m = find_meeting(db, payload)
    if m is None:
        return {"ok": False, "error": "no encuentro esa reunión en la agenda — dímela por su título "
                                      "(y la fecha si hay varias)"}
    guests = resolve_guests(payload)
    if guests["ambiguous"]:
        who, names = guests["ambiguous"][0]
        return {"ok": False, "error": f"tengo varios contactos que encajan con «{who}»: "
                                      f"{', '.join(n for n in names if n)}. Dime a cuál invito."}
    if not guests["emails"]:
        if guests["missing_email"]:
            who = guests["missing_email"][0]
            return {"ok": False, "error": f"no tengo el correo de {who}. Si te lo han dado en la conversación, "
                                          f"guárdalo con contactos/set_channel y vuelve a invitarle; si no, "
                                          f"pídeselo."}
        return {"ok": False, "error": "díme a qué dirección mando la invitación"}

    note = str(payload.get("message") or payload.get("text") or "").strip()
    # RUNG 1 — the meeting has a calendar behind it: the calendar sends the invitation.
    s = _gcal().svc()
    if m.get("googleId") and m.get("googleCalendarId") and s is not None:
        try:
            res = s.invite(m, guests["emails"])
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "error": str(e)[:160]}
        if res.get("ok"):
            for k, v in (res.get("meeting") or {}).items():
                m[k] = v
            added, already = res.get("added") or [], res.get("already") or []
            if not added:
                return {"ok": True, "invited": [], "already": already, "how": "calendar",
                        "message": f"{', '.join(already)} ya estaba invitado a esta reunión."}
            return {"ok": True, "invited": added, "already": already, "how": "calendar",
                    "message": f"Invitación enviada a {', '.join(added)} desde el calendario."}
        # A calendar that refused is NOT a reason to fall to the second rung: the meeting lives there, and
        # a separate .ics would put a second, unlinked copy in the guest's calendar whose answer nobody
        # would ever see. Report what the calendar said.
        return {"ok": False, "error": str(res.get("error") or "no pude añadir al invitado en el calendario")}

    # RUNG 2 — no calendar behind this meeting: we build the invitation and mail it ourselves.
    return _mail_invitation(m, guests, note)


def _mail_invitation(m: dict, guests: dict, note: str) -> dict:
    """The .ics rung. Queued through the SAME outbound door every other message uses, so it is archived,
    echoed and bound exactly like anything else this house sends."""
    try:
        from connectors.calendar import ics as _ics
        from connectors.email import config as _mailcfg
        from connectors.messaging import ingest as _ingest
    except Exception:
        return {"ok": False, "error": "no tengo el conector de correo disponible para mandar la invitación"}
    me = ""
    try:
        me = str(_mailcfg.address() or "").strip()
    except Exception:
        me = ""
    if not me:
        return {"ok": False, "error": "no hay ninguna cuenta de correo conectada desde la que mandar la "
                                      "invitación — conéctala en Conectores y vuelve a intentarlo"}
    try:
        text = _ics.build(m, organizer=me, attendees=guests["emails"], offset_minutes=_offset_minutes())
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    when = " ".join(x for x in [str(m.get("date") or ""), str(m.get("startTime") or "")] if x)
    body = note or (f"Te paso la invitación para «{m.get('title') or 'la reunión'}» ({when}). "
                    f"La tienes adjunta para añadirla a tu calendario.")
    link = str(m.get("meetLink") or "").strip()
    if link and link not in body:
        body = body + "\n\n" + link
    sent = []
    for addr in guests["emails"]:
        _ingest.publish_send({"ref": f"inv-{_ics.uid_for(m)[:24]}-{addr[:40]}", "platform": "email",
                              "to": addr, "chatId": addr, "name": addr,
                              "subject": str(m.get("title") or "Invitación"), "text": body,
                              "ics": text, "ics_method": "REQUEST"})
        sent.append(addr)
    return {"ok": True, "invited": sent, "already": [], "how": "email",
            "message": f"Invitación enviada por correo a {', '.join(sent)}."}


def _offset_minutes() -> int:
    """The install's own UTC offset, in minutes — the same one the Google body builder derives, asked once
    here so the .ics and the calendar event can never disagree about what hour the meeting is at."""
    import datetime as _dt
    now = _dt.datetime.now().astimezone()
    return int((now.utcoffset() or _dt.timedelta(0)).total_seconds() // 60)
