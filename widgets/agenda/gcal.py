#
# gcal.py — the Google Calendar GLUE between `widgets/agenda/data.py` and `connectors/calendar/service.py`
# (V2-679). Extracted out of data.py to pay the architecture ratchet by EXTRACTION rather than raising the
# ceiling (data.py sat exactly at the 900-line ceiling before this feature — the same newborn-file rule that
# already governs `widgets/youtube/account.py`, this module's closest sibling in shape).
#
# `data.py` imports this module at the top (safe: nothing here imports `data` at module scope, only lazily
# inside functions that need `load_db`/`compute_plan`/`WIDGET_ID` — the usual way this codebase avoids a
# circular import between a widget's data.py and its own delegate module).
#
from __future__ import annotations

# CALENDAR CONNECTORS shown in the agenda's header (V2-540). Deliberately a READ of the real inventory, never
# a hardcoded «off»: the day a calendar connector is registered under this family it lights up here with
# nothing else to change. V2-679 built exactly one of the three (Google) — the honest answer for the other
# two stays «not built yet», and per INI-027 showing what we do NOT have is the point, not an embarrassment.
#
# WHY THESE THREE and not the famous ones: Google Calendar is the one everybody has; iCloud's CALENDAR is
# reachable over CalDAV with an app-specific password (unlike iCloud Drive, which CloudKit makes impossible);
# and a generic CalDAV covers Outlook/Fastmail/Nextcloud with one connector instead of three brands.
_CALENDARS = (("google", "Google Calendar"), ("icloud", "iCloud (Apple)"), ("caldav", "CalDAV (Outlook, Fastmail…)"))


def calendars() -> list[dict]:
    """Connection state of each calendar provider, for the header strip.

    `status`: "connected" | "off" (built, not linked) | "unconfigured" (built, no OAuth client registered yet)
    | "unavailable" (no connector exists at all). The widget must be able to tell these apart — «you have not
    linked it» and «we have not built it» are different sentences, and showing the first when the second is
    true is the same class of lie as promising a view."""
    live: dict[str, dict] = {}
    try:
        from connectors import registry
        for d in registry.descriptors():
            if str(d.get("family") or "") in ("agenda", "calendar"):
                live[str(d.get("id") or "")] = d
    except Exception:
        pass                                          # a registry that cannot be read is not a linked calendar
    known = dict(_CALENDARS)
    out = [{"id": cid, "label": (live.get(cid, {}).get("label") or label),
            "status": ("connected" if live[cid].get("connected") else str(live[cid].get("status") or "off"))
                      if cid in live else "unavailable"}
           for cid, label in _CALENDARS]
    out += [{"id": cid, "label": str(d.get("label") or cid),
             "status": "connected" if d.get("connected") else str(d.get("status") or "off")}
            for cid, d in live.items() if cid not in known]
    return out


def svc():
    """Lazy import of the Google Calendar connector facade — `data.py` must stay stdlib-only at module scope
    (`widgets/validator.py::_STDLIB_EXEMPT` already covers "agenda"). Returns None when the connector cannot
    even be imported — every caller here degrades to local-only behavior when that happens."""
    try:
        from connectors.calendar import service as _s
        return _s
    except Exception:
        return None


def commit_meeting(db: dict, m: dict) -> dict:
    """Append a NEW meeting to `db['meetings']`, creating it on Google Calendar FIRST when connected — the
    operator's own acceptance test is "I dictate it, and within seconds it's in the real Google Calendar", so
    the write cannot wait for the next background tick. Returns the dict actually stored (the Google-enriched
    one on success, carrying `googleId`/`source` so the next sync recognizes it as the SAME row instead of
    inventing a duplicate). Best-effort: a Google failure still keeps the LOCAL write — the same rule
    `data._schedule_reminder` already follows, a write must never be lost because a side-effect failed."""
    s = svc()
    if s is not None:
        try:
            if s.connected():
                default_cal = (db.get("google") or {}).get("defaultCalendarId") or ""
                res = s.create_event(m, default_cal)
                if res.get("ok"):
                    enriched = res["meeting"]
                    for k in ("reminder_id", "remindAt"):
                        if k in m:
                            enriched[k] = m[k]
                    m = enriched
        except Exception:  # noqa: BLE001
            pass
    db.setdefault("meetings", []).append(m)
    return m


def patch_google(m: dict) -> None:
    """Best-effort mirror of a LOCAL edit onto the Google event this meeting already came from or was already
    pushed to (`m['source'] == 'google'`). Mutates `m` in place with whatever Google echoes back; a failure
    leaves the local edit standing — the operator's change is never lost, it just risks a divergence the next
    sync cannot yet self-heal (named, not solved, in this build)."""
    if m.get("source") != "google":
        return
    s = svc()
    if s is None:
        return
    try:
        r = s.patch_event(m, m)
        if r.get("ok"):
            for k, v in r["meeting"].items():
                m[k] = v
    except Exception:  # noqa: BLE001
        pass


def delete_google(m: dict) -> None:
    if m.get("source") != "google":
        return
    s = svc()
    if s is None:
        return
    try:
        s.delete_event(m)
    except Exception:  # noqa: BLE001
        pass


# How long a pushed CONNECT screen stays fresh. Same shape as `data._VIEW_TTL_S` and shorter on purpose:
# this one asks the operator for a CLICK, and an order to connect that he did not give in this minute must
# not ambush him with a setup screen when the card repaints half an hour later.
_CONNECT_TTL_S = 180


def push_connect_screen(db: dict) -> None:
    """Leave the card ON its connect step (V2-686).

    The voice CANNOT finish an OAuth consent: the popup only survives inside the click that opened it
    (`widget.js`'s own comment, paid for once already), and the turn report drops the action's result, so a
    URL returned from here reaches NOBODY — measured 2026-09-14, `T14·76b6`: the operator said «open the
    google connector in the agenda widget», this action ran, returned a perfectly good consent URL, and the
    screen did not move nor did the mouth say a word.

    So the voice does what the voice CAN do: it puts the button in front of him. Same token shape as the
    pushed view — a counter, so asking twice lands twice, and a timestamp, so a repaint hours later does
    not re-open it."""
    import time as _tm
    prev = db.get("connect") or {}
    db["connect"] = {"n": int(prev.get("n", 0)) + 1, "at": _tm.time()}


def fresh_connect(db: dict) -> dict | None:
    """The pushed connect screen, only while it is still this conversation's."""
    c = db.get("connect") or None
    if not c:
        return None
    import time as _tm
    at = float(c.get("at") or 0)
    return c if at and (_tm.time() - at) <= _CONNECT_TTL_S else None


def ui_action(action: str, payload: dict, db: dict) -> dict | None:
    """The three UI-ONLY actions (never voice-declared credential handling, V2-520 shape). `data.py::
    apply_action` calls this before its own dispatch chain; returning None means "not one of mine"."""
    if action == "connect":
        # The screen moves FIRST and unconditionally — before asking the connector for anything. Whatever
        # the answer is, the operator has to end up looking at the step that explains it: a consent URL when
        # all is well, and the connector's own refusal ("sin app OAuth registrada…") when it is not.
        push_connect_screen(db)
        s = svc()
        if s is None:
            return {"ok": False, "error": "el conector de Google Calendar no está disponible en este build"}
        return s.connect_url(str(payload.get("provider") or "google"), str(payload.get("tier") or ""))
    if action == "disconnect":
        s = svc()
        if s is None:
            return {"ok": False, "error": "el conector de Google Calendar no está disponible en este build"}
        return s.disconnect(str(payload.get("provider") or "google"))
    if action == "set_default_calendar":
        cid = str(payload.get("calendarId") or "").strip()
        if not cid:
            return {"ok": False, "error": "falta calendarId"}
        db.setdefault("google", {"calendars": [], "defaultCalendarId": "", "syncTokens": {}, "lastSync": 0})
        db["google"]["defaultCalendarId"] = cid
        return {"ok": True}
    return None


def tick(ctx) -> None:
    """Background sync with Google Calendar (`widgets/background.py`'s mechanism, called from
    `data.py:tick(ctx)` — the scheduler's contract needs it there, this is just where the body lives).

    A DELIBERATE departure from the video connector's on-demand-only precedent (V2-597: "the operator's
    standing rule is absolute control — the suggestions band fills when ASKED, never on a timer"). That rule
    fits a read-only suggestions feed; it does not fit THIS connector, whose whole point — the operator's own
    words — is "si añado algo en Google Calendar... me gustaría que a los 10 segundos ya estuviera en mi
    agenda". Cheap in the steady state: `service.sync` uses Google's own syncToken, so a calendar with no new
    activity between polls costs one empty round-trip per selected calendar, never a re-list."""
    s = svc()
    if s is None or not s.connected():
        return
    from . import data as ag
    db = ag.load_db()
    res = s.sync(db)
    if not res.get("ok"):
        return
    if res.get("new_ids"):
        # A freshly-synced Google event gets Zaelar's own SPOKEN reminder, same ~2h-before policy as a
        # locally-dictated appointment — Google's own notification is a different, silent channel.
        by_gid = {m.get("googleId"): m for m in db.get("meetings", []) if m.get("source") == "google"}
        for gid in res["new_ids"]:
            m = by_gid.get(gid)
            if m and not m.get("allDay") and not m.get("reminder_id"):
                jid, at = ag._schedule_reminder(m.get("title", "Cita"), m.get("date", ""), m.get("startTime", ""))
                if jid:
                    m["reminder_id"], m["remindAt"] = jid, at
    if res.get("changed"):
        db["currentPlan"] = ag.compute_plan(db)
        ctx.save(db)


def on_calendar_connected() -> None:
    """First contact right after OAuth consent completes (`connectors/calendar/server_api.py`'s callback) —
    an immediate sync so the operator sees their existing Google appointments without waiting for the next
    background tick, PLUS a one-time best-effort migration of pre-existing LOCAL-only future meetings up to
    Google. Operator's explicit requirement: "no quiero que luego haya divergencias... si tienes que
    duplicar los datos por un tema de facilidad, busca la mejor forma de hacerlo" — a meeting already in
    Zaelar must not silently vanish from view the moment Google becomes the source of truth.

    Dedup is the SAME `_titles_overlap` rule the local write path already uses (V2-473): a local meeting that
    already looks like one Google just handed back is left alone, never pushed twice."""
    s = svc()
    if s is None:
        return
    from . import data as ag
    from .. import store
    db = ag.load_db()
    res = s.sync(db)
    if not res.get("ok"):
        store.save(ag.WIDGET_ID, db)
        return
    today = ag._today()
    google_ones = [m for m in db.get("meetings", []) if m.get("source") == "google"]
    default_cal = (db.get("google") or {}).get("defaultCalendarId") or ""
    kept: list[dict] = []
    for m in db.get("meetings", []):
        if m.get("source") == "google" or str(m.get("date") or "") < today:
            kept.append(m)
            continue
        dup = any(m.get("date") == g.get("date") and ag._titles_overlap(m.get("title"), g.get("title"))
                 for g in google_ones)
        if dup:
            kept.append(m)
            continue
        res2 = s.create_event(m, default_cal)
        if res2.get("ok"):
            enriched = res2["meeting"]
            for k in ("reminder_id", "remindAt"):
                if k in m:
                    enriched[k] = m[k]
            kept.append(enriched)
        else:
            kept.append(m)   # a failed migration keeps the meeting LOCAL rather than losing it
    db["meetings"] = kept
    db["currentPlan"] = ag.compute_plan(db)
    store.save(ag.WIDGET_ID, db)
