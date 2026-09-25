#
# service.py — the provider-AGNOSTIC facade of the calendar connectors (V2-679). The ONLY thing the agenda
# widget imports (lazily, since `widgets/agenda/data.py` must stay stdlib-only at module scope). Fail-safe by
# contract: every entry returns {"ok": False, "error": …} — it never raises, because a widget action or a
# background tick must degrade to words, not to a traceback (the V2-557 rule, copied from video/photos).
#
# This module is MECHANICAL only: it talks to Google and normalizes shapes. Anything that is a POLICY decision
# about what a meeting IS — dedup, the hour-less-twin settlement, reminder scheduling — stays in
# `widgets/agenda/data.py`, which already owns that logic for the local-only path. Splitting it the other way
# (teaching this connector agenda's business rules) would make it impossible to reuse for a future second
# provider without dragging agenda-specific code along.
#
from __future__ import annotations

import time

from connectors.calendar import oauth, providers
from connectors.calendar import google_calendar as _gc

_DEFAULT_PROVIDER = "google"
# How far back/forward a FULL sync (no stored syncToken yet, or one that expired) reaches. Wide enough that
# "revísame que se haya añadido bien esta cosa" for something dictated minutes ago always shows up, without
# pulling a decade of history on every fresh connect.
_PAST_DAYS = 120
_FUTURE_DAYS = 400


def available() -> bool:
    """Is the calendar-account layer usable at all? False until an OAuth client exists — either the one shipped
    with the engine (empty today) or one the operator pasted in ⚙ → Conectores. While False the connector is
    HIDDEN, not shown-and-broken (V2-603's rule, same posture as video/photos)."""
    try:
        return any(oauth.configured(p.id) for p in providers.PROVIDERS.values())
    except Exception:
        return False


def status() -> dict:
    try:
        return {"ok": True, "providers": oauth.status()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200], "providers": []}


def connected(provider_id: str = _DEFAULT_PROVIDER) -> bool:
    try:
        return oauth.configured(provider_id) and oauth.tokens_present(provider_id)
    except Exception:
        return False


def _prepared(provider_id: str = _DEFAULT_PROVIDER):
    p = providers.get(provider_id)
    if not p:
        return None, None, {"ok": False, "error": f"proveedor desconocido: {provider_id or '(vacío)'}"}
    if not oauth.configured(p.id):
        return None, None, {"ok": False, "error": f"sin app OAuth registrada para {p.label} "
                                                  f"(el client_id se pone una vez en Configuración → Conectores)"}
    if not oauth.tokens_present(p.id):
        return None, None, {"ok": False, "error": f"{p.label} no está conectado — conéctalo desde la tarjeta"}
    tok = oauth.access_token(p.id)
    if not tok:
        return None, None, {"ok": False, "error": f"la sesión con {p.label} caducó — reconecta la cuenta"}
    return p, tok, None


def connect_url(provider_id: str = _DEFAULT_PROVIDER, tier_id: str = "", origin: str = "") -> dict:
    try:
        return oauth.authorize_url(provider_id, tier_id, origin=origin)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def disconnect(provider_id: str = _DEFAULT_PROVIDER) -> dict:
    try:
        return oauth.forget(provider_id)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def list_calendars(provider_id: str = _DEFAULT_PROVIDER) -> dict:
    import httpx
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    with httpx.Client() as client:
        return _gc.list_calendars(client, p.api_base, tok)


def sync(db: dict, provider_id: str = _DEFAULT_PROVIDER) -> dict:
    """Pull every SELECTED Google calendar into `db` in place (`db["meetings"]` gains/loses google-origin rows,
    `db["google"]` keeps the calendar list + per-calendar sync tokens). Returns
    {"ok", "changed", "new_ids": [googleId,...], "removed_ids": [...], "error"}.

    "changed" and "new_ids" are what let the CALLER (agenda's `tick`) decide what to do about it — schedule a
    reminder for a freshly-synced appointment, recompute the plan, persist — without this module knowing
    anything about reminders or plans."""
    import httpx
    p, tok, err = _prepared(provider_id)
    if err:
        return {**err, "changed": False, "new_ids": [], "removed_ids": []}

    g = db.setdefault("google", {"calendars": [], "defaultCalendarId": "", "syncTokens": {}, "lastSync": 0})
    changed = False
    new_ids: list[str] = []
    removed_ids: list[str] = []

    with httpx.Client() as client:
        cals = _gc.list_calendars(client, p.api_base, tok)
        if not cals.get("ok"):
            return {"ok": False, "error": cals.get("error"), "changed": False, "new_ids": [], "removed_ids": []}
        g["calendars"] = cals["calendars"]
        if not g.get("defaultCalendarId"):
            primary = next((c["id"] for c in g["calendars"] if c.get("primary")), "")
            g["defaultCalendarId"] = primary or (g["calendars"][0]["id"] if g["calendars"] else "")

        by_gid = {m.get("googleId"): m for m in db.get("meetings", []) if m.get("source") == "google"}
        # A series WE pushed stays our row (the rule lives there); its instances coming back are not new rows.
        ours = {m.get("googleSeriesId") for m in db.get("meetings", []) if m.get("source") != "google"
                and m.get("googleSeriesId")}
        colors = {c["id"]: c.get("backgroundColor", "") for c in g["calendars"]}
        tokens = g.setdefault("syncTokens", {})

        for cal in g["calendars"]:
            if not cal.get("selected", True):
                continue
            cid = cal["id"]
            tok_stored = tokens.get(cid, "")
            if tok_stored:
                res = _gc.list_events(client, p.api_base, tok, cid, sync_token=tok_stored)
                if not res.get("ok") and res.get("expired"):
                    tok_stored = ""  # fall through to a fresh full sync below
                elif not res.get("ok"):
                    continue          # one calendar's failure must not stop the others (V2-557 isolation rule)
            if not tok_stored:
                res = _gc.list_events(client, p.api_base, tok, cid,
                                      time_min=_dt_offset_rfc3339(-_PAST_DAYS),
                                      time_max=_dt_offset_rfc3339(_FUTURE_DAYS))
                if not res.get("ok"):
                    continue
            for ev in res.get("events") or []:
                m = _gc.event_to_meeting(ev, cid, colors.get(cid, ""))
                if not m or (m.get("googleSeriesId") in ours) or (m.get("googleId") in ours):
                    continue
                gid = m["googleId"]
                prev = by_gid.get(gid)
                if prev is None:
                    new_ids.append(gid)
                    changed = True
                elif prev.get("googleUpdated") != m.get("googleUpdated"):
                    changed = True
                if prev is not None:
                    # keep OUR bookkeeping (a local reminder scheduled against this row) across the refresh.
                    for k in ("reminder_id", "remindAt"):
                        if k in prev:
                            m[k] = prev[k]
                by_gid[gid] = m
            for gid in res.get("deleted") or []:
                if by_gid.pop(gid, None) is not None:
                    removed_ids.append(gid)
                    changed = True
            if res.get("next_sync_token"):
                tokens[cid] = res["next_sync_token"]

    kept = [m for m in db.get("meetings", []) if m.get("source") != "google"]
    kept.extend(by_gid.values())
    db["meetings"] = kept
    g["lastSync"] = time.time()
    return {"ok": True, "changed": changed, "new_ids": new_ids, "removed_ids": removed_ids}


def create_event(meeting: dict, calendar_id: str = "", provider_id: str = _DEFAULT_PROVIDER) -> dict:
    """Insert one meeting as a real Google Calendar event. Returns {"ok": True, "meeting": {...enriched...}} —
    the CALLER replaces its local, plain dict with the enriched one (carries googleId/htmlLink/etc.) so the
    next sync recognizes it as the SAME row instead of a duplicate."""
    import httpx
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    cal = calendar_id or ""
    if not cal:
        cals = list_calendars(provider_id)
        if not cals.get("ok"):
            return cals
        cal = next((c["id"] for c in cals["calendars"] if c.get("primary")), "") \
            or (cals["calendars"][0]["id"] if cals["calendars"] else "")
    if not cal:
        return {"ok": False, "error": "no encontré ningún calendario de Google donde crear la cita"}
    body = _gc.meeting_to_event(meeting)
    with httpx.Client() as client:
        res = _gc.insert_event(client, p.api_base, tok, cal, body)
    if not res.get("ok"):
        return res
    enriched = _gc.event_to_meeting(res["event"], cal)
    if not enriched:
        return {"ok": False, "error": "Google Calendar creó la cita pero no pude leerla de vuelta"}
    return {"ok": True, "meeting": enriched}


def patch_event(meeting: dict, changes: dict, provider_id: str = _DEFAULT_PROVIDER) -> dict:
    """Apply `changes` (a partial meeting dict, ALREADY merged by the caller) to the Google event this meeting
    mirrors. Requires `meeting["googleId"]`/`["googleCalendarId"]` — a meeting with neither has never been
    synced and this is the wrong door (create_event is)."""
    import httpx
    gid, cid = meeting.get("googleId"), meeting.get("googleCalendarId")
    if not gid or not cid:
        return {"ok": False, "error": "esta cita no viene de Google Calendar"}
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    body = _gc.meeting_to_event(changes)
    with httpx.Client() as client:
        res = _gc.patch_event(client, p.api_base, tok, cid, gid, body)
    if not res.get("ok"):
        return res
    enriched = _gc.event_to_meeting(res["event"], cid, meeting.get("calendarColor", ""))
    if not enriched:
        return {"ok": False, "error": "Google Calendar actualizó la cita pero no pude leerla de vuelta"}
    return {"ok": True, "meeting": enriched}


def rsvp(meeting: dict, answer: str, provider_id: str = _DEFAULT_PROVIDER) -> dict:
    """Answer an invitation: set the OPERATOR's own `responseStatus` on the Google event (V2-697).

    Deliberately NOT routed through `patch_event`. That door rebuilds the whole body from
    `meeting_to_event`, which would re-send title, times and an `attendees` list rebuilt from bare names —
    on somebody ELSE's event, where we are a guest and not the organizer, that is a write we have no
    business making.

    ⚠️ It is a READ-MODIFY-WRITE, and that is not belt-and-braces: in the Google API `attendees` is an
    array, and a PATCH carrying an array REPLACES it. Answering by sending only our own row would delete
    every other guest from the organizer's meeting — a silent, destructive 200. So the live roster is read
    back, OUR row alone is edited, and the whole list goes up again.

    Requires `selfEmail` (which row of the roster is ours). It arrives with every synced Google event that
    has guests; a meeting without it is one nobody invited us to, and there is nothing to answer.
    """
    import httpx
    answer = str(answer or "").strip()
    if answer not in ("accepted", "declined", "tentative"):
        return {"ok": False, "error": f"no sé qué responder a una invitación con «{answer}»"}
    gid, cid = meeting.get("googleId"), meeting.get("googleCalendarId")
    if not gid or not cid:
        return {"ok": False, "error": "esta cita no viene de Google Calendar"}
    mail = str(meeting.get("selfEmail") or "").strip()
    if not mail:
        return {"ok": False, "error": "esta cita no es una invitación: no figuras en la lista de invitados"}
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    with httpx.Client() as client:
        live = _gc.get_event(client, p.api_base, tok, cid, gid)
        if not live.get("ok"):
            return live
        roster = [a for a in (live["event"].get("attendees") or []) if isinstance(a, dict)]
        ours = [a for a in roster if a.get("self") or str(a.get("email") or "").strip().lower() == mail.lower()]
        if not ours:
            return {"ok": False, "error": "ya no figuras en la lista de invitados de esta cita"}
        for a in ours:
            a["responseStatus"] = answer
        res = _gc.patch_event(client, p.api_base, tok, cid, gid, {"attendees": roster})
    if not res.get("ok"):
        return res
    enriched = _gc.event_to_meeting(res["event"], cid, meeting.get("calendarColor", ""))
    if not enriched:
        return {"ok": False, "error": "Google Calendar guardó tu respuesta pero no pude leerla de vuelta"}
    return {"ok": True, "meeting": enriched}


def invite(meeting: dict, emails: list, provider_id: str = _DEFAULT_PROVIDER) -> dict:
    """Add guests to an event WE own and have Google send them the invitation (V2-718).

    This is the answer to «can you send me a calendar invite», and it is not an email with a link in it: a
    guest added here receives Google's own iCalendar REQUEST, which their calendar shows with Accept /
    Decline whether they are on Gmail, iCloud or Outlook, and whose answer comes back into this event. The
    link-in-an-email version is the fallback for when there is no calendar account at all
    (`connectors/calendar/ics.py` + the mail connector), not the first choice.

    ⚠️ READ-MODIFY-WRITE, for the same reason `rsvp` above is one and with the same teeth: in the Google API
    `attendees` is an array and a PATCH carrying an array REPLACES it. Sending just the new guest would
    silently delete every other guest from the meeting, with a 200 and no way to notice.

    ⚠️ And `send_updates="all"` is not decoration. Without it the guest is added and told NOTHING — the
    exact shape of the `conferenceDataVersion` trap, one parameter over, and the whole point of the ask.
    """
    import httpx
    gid, cid = meeting.get("googleId"), meeting.get("googleCalendarId")
    if not gid or not cid:
        return {"ok": False, "error": "esta cita no está en Google Calendar"}
    want = []
    for e in emails or []:
        a = str(e or "").strip()
        if a and "@" in a and a.lower() not in [w.lower() for w in want]:
            want.append(a)
    if not want:
        return {"ok": False, "error": "necesito una dirección de correo a la que mandar la invitación"}
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    with httpx.Client() as client:
        live = _gc.get_event(client, p.api_base, tok, cid, gid)
        if not live.get("ok"):
            return live
        roster = [a for a in (live["event"].get("attendees") or []) if isinstance(a, dict)]
        have = {str(a.get("email") or "").strip().lower() for a in roster}
        added = [a for a in want if a.lower() not in have]
        if not added:
            # Already on the list: re-patching would re-notify everybody for nothing.
            return {"ok": True, "added": [], "already": want, "meeting": meeting}
        roster += [{"email": a} for a in added]
        res = _gc.patch_event(client, p.api_base, tok, cid, gid, {"attendees": roster}, send_updates="all")
    if not res.get("ok"):
        return res
    enriched = _gc.event_to_meeting(res["event"], cid, meeting.get("calendarColor", ""))
    if not enriched:
        return {"ok": False, "error": "Google Calendar guardó los invitados pero no pude leerlos de vuelta"}
    return {"ok": True, "added": added, "already": [a for a in want if a not in added], "meeting": enriched}


def delete_event(meeting: dict, provider_id: str = _DEFAULT_PROVIDER) -> dict:
    import httpx
    gid, cid = meeting.get("googleId"), meeting.get("googleCalendarId")
    if not gid or not cid:
        return {"ok": False, "error": "esta cita no viene de Google Calendar"}
    p, tok, err = _prepared(provider_id)
    if err:
        return err
    with httpx.Client() as client:
        return _gc.delete_event(client, p.api_base, tok, cid, gid)


def brain_state() -> str:
    """One compact line for the FlashBrain turn prompt, same rationale as video/service.py::brain_state — a
    verb with no fact gets narrated as done. Only surfaced by `widgets/brief.py` while the agenda card is open
    (cheap: it rides the hot prompt)."""
    if not available():
        return ("AGENDA (Google Calendar): conectar Google Calendar TODAVÍA NO ESTÁ DISPONIBLE en esta versión "
                "— la puerta no existe aún. NO lo ofrezcas ni digas que puedes conectarlo. La agenda local "
                "funciona con normalidad: eso NO depende de ninguna cuenta.")
    try:
        rows = oauth.status()
    except Exception:
        return ""
    if not rows:
        return ""
    r = rows[0]
    if r.get("connected"):
        state = "CONECTADO — esta agenda YA sincroniza con Google Calendar; lo que apuntes por voz aparece allí"
    elif r.get("app_configured"):
        state = "SIN conectar — la app OAuth ya está registrada, falta que el operador autorice su cuenta"
    else:
        state = "SIN conectar y SIN app OAuth registrada"
    return f"AGENDA (Google Calendar): {state}. NUNCA digas que la has conectado tú: el consentimiento lo da " \
           "el operador en la ventana de Google."


def _dt_offset_rfc3339(days: int) -> str:
    import datetime as _d
    return (_d.datetime.now(_d.timezone.utc) + _d.timedelta(days=days)).isoformat().replace("+00:00", "Z")
