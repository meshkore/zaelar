#
# google_calendar.py — the Google Calendar API v3 client (V2-679). Speaks HTTP, returns NORMALIZED shapes that
# already look like an agenda "meeting" dict (see `widgets/agenda/data.py`'s meeting shape, V2-643) — the facade
# (`service.py`) composes and the widget never sees this module or a raw Google event body.
#
# `singleEvents=true` on every list call is the ONE decision that keeps this whole connector simple: Google
# expands recurring events into individual instances for us server-side, so nothing here parses an RRULE or
# tracks a master/instance relationship — each occurrence arrives as its own event with its own id.
#
# Incremental sync via `syncToken` (returned on the LAST page of a `events.list` call) means a steady-state poll
# only pays for what actually changed — a calendar with no new activity between polls costs one cheap request
# that returns zero items, not a full re-list. A `410 Gone` means the token expired (calendars kept for a long
# time, or Google's own retention window) and the caller must fall back to a fresh full sync.
#
from __future__ import annotations

import datetime as _dt
import uuid as _uuid
import logging

logger = logging.getLogger("zaelar.calendar.google")

_TIMEOUT = 15


def _err_of(resp) -> str:
    try:
        body = resp.json()
        reason = ((body.get("error") or {}).get("errors") or [{}])[0].get("reason") or ""
        msg = (body.get("error") or {}).get("message") or ""
    except Exception:
        reason, msg = "", ""
    if resp.status_code == 401:
        return "la sesión con Google Calendar caducó — reconecta la cuenta"
    if resp.status_code == 403 and "quota" in (reason + msg).lower():
        return "cuota diaria de la API de Google Calendar agotada — vuelve a intentarlo mañana"
    if resp.status_code == 403 and "disabled" in msg.lower():
        return "la Google Calendar API no está habilitada en tu proyecto de Google Cloud"
    return f"Google Calendar respondió {resp.status_code}" + (f" ({reason or msg[:80]})" if (reason or msg) else "")


def _local_offset() -> str:
    """This machine's UTC offset as '+02:00'/'-05:00' — sent inline in every dateTime we WRITE so Google never
    needs an IANA zone name from us (`zoneinfo` cannot reliably name the local zone on every platform)."""
    off = _dt.datetime.now().astimezone().strftime("%z")  # '+0200'
    return off[:3] + ":" + off[3:] if off else "+00:00"


def _to_local_hhmm_date(iso: str) -> tuple[str, str]:
    """A Google `dateTime` string (any offset, or 'Z') -> (date, 'HH:MM') in THIS machine's local time, so it
    reads consistently with every other date/time in the widget (all of which are local wall-clock)."""
    try:
        d = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
        return d.strftime("%Y-%m-%d"), d.strftime("%H:%M")
    except Exception:
        return "", ""


#: Google's four answers. Anything outside this set is dropped rather than shown: a value we do not
#: understand is not a claim we get to make about somebody else's answer.
_RSVP = ("accepted", "declined", "tentative", "needsAction")


def _guest_shape(att: dict) -> dict:
    """One row of the Google roster: who, and what they answered (V2-697).

    `attendees` stays a list of plain NAMES because seven callers already read it that way — the voice
    payloads, the errand booker, the digest line, and the write direction that turns it back into Google
    bodies. This richer shape rides ALONGSIDE it under `guests`, written from the same list in the same
    pass, so the two cannot drift; a meeting the operator dictated simply has no `guests`.
    """
    email = str(att.get("email") or "").strip()
    name = str(att.get("displayName") or "").strip() or email
    g: dict = {"name": name[:80]}
    if email:
        g["email"] = email[:120]
    rs = str(att.get("responseStatus") or "").strip()
    if rs in _RSVP:
        g["rsvp"] = rs
    if att.get("organizer"):
        g["organizer"] = True
    return g


def _others_status(guests: list[dict]) -> str:
    """'confirmed' | 'pending' about the OTHER party — which is what this widget's pill has always claimed
    to mean («sin confirmar por la otra parte») and what a locally dictated meeting sets it from.

    V2-697 fixed a real mix-up here: for a Google row this used to be the OPERATOR's own responseStatus,
    so the same field meant «have they answered me» on one row and «have I answered them» on the next. The
    operator's own answer is a different fact and now lives in `myRsvp`. A guest whose answer Google does
    not report leaves this pending on purpose — not knowing is not the same as being confirmed.
    """
    if not guests:
        return "confirmed"
    return "confirmed" if all(g.get("rsvp") == "accepted" for g in guests) else "pending"


def event_to_meeting(ev: dict, calendar_id: str, calendar_color: str = "") -> dict | None:
    """A Google event body -> our meeting shape. None for a row this widget cannot represent (no title AND no
    time — happens for some provider-synthesized placeholder rows)."""
    if str(ev.get("status") or "") == "cancelled":
        return None
    title = str(ev.get("summary") or "").strip() or "(sin título)"
    start, end = ev.get("start") or {}, ev.get("end") or {}
    m: dict = {"title": title[:200], "source": "google",
               "googleId": ev.get("id"), "googleCalendarId": calendar_id,
               "googleUpdated": ev.get("updated") or "", "calendarColor": calendar_color or ""}
    if "date" in start:                      # all-day
        m["date"], m["allDay"] = start["date"], True
    elif "dateTime" in start:
        d, hh = _to_local_hhmm_date(start["dateTime"])
        if not d:
            return None
        m["date"], m["startTime"] = d, hh
        if "dateTime" in end:
            _, eh = _to_local_hhmm_date(end["dateTime"])
            if eh:
                m["endTime"] = eh
    else:
        return None
    loc = str(ev.get("location") or "").strip()
    if loc:
        m["location"] = loc[:160]
    desc = str(ev.get("description") or "").strip()
    if desc:
        m["notes"] = desc[:500]
    roster = [a for a in (ev.get("attendees") or []) if isinstance(a, dict)]
    guests = [g for g in (_guest_shape(a) for a in roster if not a.get("self")) if g.get("name")][:50]
    if guests:
        m["guests"] = guests
        m["attendees"] = [g["name"] for g in guests]
    mine = next((a for a in roster if a.get("self")), None)
    if mine is not None:
        mail = str(mine.get("email") or "").strip()
        if mail:
            m["selfEmail"] = mail[:120]            # which row of the roster to PATCH when the operator answers
        rs = str(mine.get("responseStatus") or "").strip()
        if rs in _RSVP:
            m["myRsvp"] = rs
    m["status"] = _others_status(guests)
    link = str(ev.get("hangoutLink") or "").strip()
    if not link:
        for ep in (ev.get("conferenceData") or {}).get("entryPoints") or []:
            if ep.get("entryPointType") == "video" and ep.get("uri"):
                link = ep["uri"]
                break
    # ⚠️ Anybody who can send the operator an invitation writes this field, and the card turns it into an
    # anchor's href — so a `javascript:` or `data:` URI would be a stored XSS arriving by calendar invite.
    # Only the two schemes a video call is ever reached by survive (V2-697).
    if link and link.split(":", 1)[0].lower() in ("http", "https"):
        m["meetLink"] = link[:500]
    org = ((ev.get("organizer") or {}).get("displayName")
           or (ev.get("organizer") or {}).get("email") or "").strip()
    if org and not (ev.get("organizer") or {}).get("self"):
        m["organizer"] = org
    if ev.get("htmlLink"):
        m["htmlLink"] = ev["htmlLink"]
    return m


def meeting_to_event(m: dict) -> dict:
    """Our meeting shape -> a Google event body, for insert/patch. Only the fields Google understands travel;
    our bookkeeping fields (googleId, source, reminder_id…) never leave this module."""
    body: dict = {"summary": str(m.get("title") or "Cita")[:1024]}
    if m.get("allDay"):
        body["start"] = {"date": m["date"]}
        # Google's all-day `end.date` is EXCLUSIVE (the day after) — a single-day all-day event's end is
        # start+1, or the all-day band would render zero-length.
        try:
            d = _dt.date.fromisoformat(m["date"]) + _dt.timedelta(days=1)
            body["end"] = {"date": d.isoformat()}
        except Exception:
            body["end"] = {"date": m["date"]}
    else:
        off = _local_offset()
        body["start"] = {"dateTime": f"{m['date']}T{m.get('startTime', '00:00')}:00{off}"}
        body["end"] = {"dateTime": f"{m['date']}T{m.get('endTime') or m.get('startTime', '00:00')}:00{off}"}
    if m.get("location"):
        body["location"] = str(m["location"])[:1024]
    if m.get("notes"):
        body["description"] = str(m["notes"])[:8192]
    who = [w for w in (m.get("attendees") or []) if w and "@" in str(w)]  # Google needs an email per attendee;
    if who:                                                               # a bare name with no email cannot be
        body["attendees"] = [{"email": w} for w in who]                  # invited, so it is simply not sent.
    # V2-685 — GOOGLE MEET. A Meet link is not a product you connect separately: it is `conferenceData` on
    # the event, created by the SAME calendar scope this connector already holds. So «ponme la reunión de
    # mañana con enlace de Meet» costs no extra consent, which is why `connectors/google/services.py`
    # registers Meet with no scopes of its own.
    #
    # `requestId` is the idempotency key: Google mints ONE conference per distinct value, so a retried
    # insert after a timeout must reuse it or the operator ends up with two meetings and two links. It is
    # derived from the meeting when we have an id, and only random when we genuinely have nothing.
    if m.get("meet"):
        rid = str(m.get("googleId") or m.get("id") or "").strip() or _uuid.uuid4().hex
        body["conferenceData"] = {"createRequest": {
            "requestId": f"zaelar-{rid}"[:64],
            "conferenceSolutionKey": {"type": "hangoutsMeet"}}}
    return body


def wants_conference(body: dict) -> bool:
    """Does this body ask Google to MINT a conference? Read by the callers to set `conferenceDataVersion`,
    which is the half of the contract that fails silently when it is missing (see `insert_event`)."""
    return bool((body or {}).get("conferenceData"))


def list_calendars(client, api_base: str, token: str) -> dict:
    """Every calendar the account can see. Returns {"ok": True, "calendars": [{id, summary, backgroundColor,
    primary, selected}]} — `selected` mirrors the operator's own Google Calendar UI ("shown in my list"),
    which is the honest default for what to MERGE (a calendar they hid there they likely don't want here)."""
    try:
        r = client.get(f"{api_base}/users/me/calendarList", params={"maxResults": 250},
                       headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "error": _err_of(r)}
        out = []
        for it in r.json().get("items") or []:
            out.append({"id": it.get("id"), "summary": str(it.get("summary") or it.get("id") or "")[:120],
                       "backgroundColor": it.get("backgroundColor") or "", "primary": bool(it.get("primary")),
                       "selected": it.get("selected", True) is not False})
        return {"ok": True, "calendars": out}
    except Exception as e:
        return {"ok": False, "error": f"no pude hablar con Google Calendar: {e}"[:200]}


def list_events(client, api_base: str, token: str, calendar_id: str, sync_token: str = "",
                time_min: str = "", time_max: str = "") -> dict:
    """One calendar's events, incrementally when `sync_token` is given. Returns {"ok": True, "events": [...],
    "next_sync_token": "...", "deleted": [googleId,...]} or {"ok": False, "error", "expired": bool} — `expired`
    (a 410) tells the caller its stored token is dead and a FULL sync (no token, with a time window) is needed."""
    events, deleted, page = [], [], ""
    params_base: dict = {"singleEvents": "true", "maxResults": 250}
    if sync_token:
        params_base["syncToken"] = sync_token
    else:
        if time_min:
            params_base["timeMin"] = time_min
        if time_max:
            params_base["timeMax"] = time_max
        params_base["orderBy"] = "startTime"
    next_token = ""
    while True:
        params = dict(params_base)
        if page:
            params["pageToken"] = page
        try:
            r = client.get(f"{api_base}/calendars/{_q(calendar_id)}/events", params=params,
                           headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        except Exception as e:
            return {"ok": False, "error": f"no pude hablar con Google Calendar: {e}"[:200]}
        if r.status_code == 410:
            return {"ok": False, "error": "sync token caducado", "expired": True}
        if r.status_code != 200:
            return {"ok": False, "error": _err_of(r)}
        body = r.json()
        for ev in body.get("items") or []:
            if str(ev.get("status") or "") == "cancelled":
                deleted.append(ev.get("id"))
            else:
                events.append(ev)
        page = str(body.get("nextPageToken") or "")
        if body.get("nextSyncToken"):
            next_token = body["nextSyncToken"]
        if not page:
            break
    return {"ok": True, "events": events, "deleted": deleted, "next_sync_token": next_token}


#: What Google does about TELLING the guests (V2-718). It is the same class of trap as
#: `conferenceDataVersion` one function below, and it cost the same kind of silence: the API's default is
#: `sendUpdates=none`, so adding somebody to `attendees` returns 200, puts them on the event, and sends them
#: NOTHING. The invitation the other person receives — the one their own calendar can accept, whether they
#: are on Gmail, iCloud or Outlook, because Google mails a real iCalendar REQUEST — only exists if this
#: parameter says so. Never defaulted here: a caller that has a roster to notify says `all` deliberately.
SEND_UPDATES = ("all", "externalOnly", "none")


def _params(body: dict, send_updates: str = "") -> "dict | None":
    p = {}
    if wants_conference(body):
        p["conferenceDataVersion"] = 1
    su = str(send_updates or "").strip()
    if su in SEND_UPDATES:
        p["sendUpdates"] = su
    return p or None


def insert_event(client, api_base: str, token: str, calendar_id: str, body: dict,
                 send_updates: str = "") -> dict:
    try:
        # ⚠️ `conferenceDataVersion=1` is REQUIRED for `conferenceData` to be honoured. Without it Google
        # returns 200 with the event created and the conference silently DROPPED — no error, no link, and
        # an agent that just told the operator it made them a Meet. Sent only when the body asks for one,
        # so an ordinary appointment keeps the exact request it had before.
        params = _params(body, send_updates)
        r = client.post(f"{api_base}/calendars/{_q(calendar_id)}/events", json=body, params=params,
                        headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code not in (200, 201):
            return {"ok": False, "error": _err_of(r)}
        return {"ok": True, "event": r.json()}
    except Exception as e:
        return {"ok": False, "error": f"no pude crear la cita en Google Calendar: {e}"[:200]}


def get_event(client, api_base: str, token: str, calendar_id: str, event_id: str) -> dict:
    """Read ONE event back from Google. Exists for the RSVP read-modify-write (V2-697): `attendees` is an
    array, and a PATCH carrying an array REPLACES it — answering an invitation by sending just our own row
    would delete every other guest from somebody else's meeting."""
    try:
        r = client.get(f"{api_base}/calendars/{_q(calendar_id)}/events/{_q(event_id)}",
                       headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "error": _err_of(r)}
        return {"ok": True, "event": r.json()}
    except Exception as e:
        return {"ok": False, "error": f"no pude leer la cita en Google Calendar: {e}"[:200]}


def patch_event(client, api_base: str, token: str, calendar_id: str, event_id: str, body: dict,
                send_updates: str = "") -> dict:
    try:
        params = _params(body, send_updates)
        r = client.patch(f"{api_base}/calendars/{_q(calendar_id)}/events/{_q(event_id)}", json=body,
                         params=params, headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code != 200:
            return {"ok": False, "error": _err_of(r)}
        return {"ok": True, "event": r.json()}
    except Exception as e:
        return {"ok": False, "error": f"no pude actualizar la cita en Google Calendar: {e}"[:200]}


def delete_event(client, api_base: str, token: str, calendar_id: str, event_id: str) -> dict:
    try:
        r = client.delete(f"{api_base}/calendars/{_q(calendar_id)}/events/{_q(event_id)}",
                          headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT)
        if r.status_code not in (200, 204, 404, 410):    # already gone counts as done
            return {"ok": False, "error": _err_of(r)}
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"no pude borrar la cita en Google Calendar: {e}"[:200]}


def _q(s: str) -> str:
    import urllib.parse
    return urllib.parse.quote(str(s or ""), safe="")
