"""The Google Calendar connector (V2-679): one normalized meeting shape, incremental sync via syncToken, and
a fail-safe facade the agenda widget can call without ever seeing a raw Google event body or a traceback.

The operator's own acceptance test — "dicto una cita por voz y en segundos está en Google Calendar" — is what
`test_create_event_enriches_and_the_caller_can_replace_its_local_copy` and the sync-merge tests stand in for.
"""
import httpx
import pytest

from connectors.calendar import google_calendar as gc
from connectors.calendar import oauth, providers, service


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "STORE", tmp_path / "calendar_oauth.json")
    # V2-685 — the token store is no longer the only thing that decides «is there an app?». A Google client
    # shared by all five Google doors can now answer, and on the operator's own machine it does, so the
    # dormancy assertions below started measuring his credential store instead of the product. Pinned, not
    # relaxed: «with NO app anywhere it declines and SAYS so» is only a property if the absence is
    # guaranteed. Its counterweight lives in `tests/connectors/unit/google/`.
    monkeypatch.setattr(oauth, "_cred", lambda _name: "")
    monkeypatch.setattr(oauth, "_shipped_google", lambda *a, **k: "")


# ── the registry is data ──────────────────────────────────────────────────────────────────────────────────
def test_google_is_registered_read_write_and_asks_for_offline_access():
    p = providers.get("google")
    assert p is not None
    assert [t.id for t in p.tiers] == ["full"]
    assert "calendar" in p.tier().scopes[0]
    assert p.extra_auth_params.get("access_type") == "offline"
    assert p.extra_auth_params.get("prompt") == "consent"


def test_registry_id_is_google_not_google_calendar():
    """`widgets/agenda/data.py::_CALENDARS` keys its header-strip placeholder on 'google' — a registry id of
    'google-calendar' would leave a stale 'unavailable' row standing NEXT TO this one instead of becoming it
    (the measured T2 trap: a consumer reads a field its producer doesn't send)."""
    assert "google" in providers.ids()
    assert "google-calendar" not in providers.ids()


# ── oauth (same shape as video's, exercised once here rather than re-proving the shared mechanism) ─────────
def test_authorize_url_refuses_without_a_client_id(sandbox, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")
    r = oauth.authorize_url("google")
    assert r["ok"] is False and "client_id" in r["error"]


def test_authorize_url_carries_pkce_and_the_scope(sandbox, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "cid-123")
    r = oauth.authorize_url("google")
    assert r["ok"] and "code_challenge=" in r["url"] and "calendar" in r["url"]


def test_redirect_uri_falls_back_to_loopback_without_a_valid_origin():
    assert oauth.redirect_uri("") == "http://127.0.0.1:43917/api/calendar/callback"
    assert oauth.redirect_uri("javascript:alert(1)") == "http://127.0.0.1:43917/api/calendar/callback"
    assert oauth.redirect_uri("https://my.zaelar.com") == "https://my.zaelar.com/api/calendar/callback"


# ── event <-> meeting normalization ──────────────────────────────────────────────────────────────────────
def test_a_timed_event_becomes_a_meeting_in_LOCAL_time():
    ev = {"id": "ev1", "status": "confirmed", "updated": "2026-09-12T10:00:00.000Z",
          "summary": "Dentista", "location": "Clínica Ruiz", "description": "Llevar el seguro",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"}}
    m = gc.event_to_meeting(ev, "primary", "#4285F4")
    assert m["title"] == "Dentista" and m["date"] == "2026-09-15"
    assert m["startTime"] == "11:30" and m["endTime"] == "12:30"
    assert m["location"] == "Clínica Ruiz" and m["notes"] == "Llevar el seguro"
    assert m["source"] == "google" and m["googleId"] == "ev1" and m["googleCalendarId"] == "primary"
    assert m["calendarColor"] == "#4285F4"
    assert "allDay" not in m


def test_an_allday_event_carries_no_hour():
    ev = {"id": "ev2", "status": "confirmed", "summary": "Vacaciones", "start": {"date": "2026-09-20"},
          "end": {"date": "2026-09-22"}}
    m = gc.event_to_meeting(ev, "primary")
    assert m["allDay"] is True and m["date"] == "2026-09-20"
    assert "startTime" not in m


def test_a_cancelled_event_is_not_a_meeting():
    assert gc.event_to_meeting({"id": "x", "status": "cancelled"}, "primary") is None


def test_the_operators_own_answer_and_the_other_partys_are_two_different_fields():
    """V2-697 — `status` used to hold the OPERATOR's own responseStatus while the card labelled it «sin
    confirmar por la otra parte», so an invitation he had accepted read as though THEY had agreed. The two
    facts are separate now: `status` is about the other guests, `myRsvp` is his own answer."""
    ev = {"id": "ev3", "status": "confirmed",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"},
          "attendees": [{"email": "me@x.com", "self": True, "responseStatus": "needsAction"},
                        {"displayName": "Ana", "email": "ana@x.com", "responseStatus": "accepted"}]}
    m = gc.event_to_meeting(ev, "primary")
    assert m["attendees"] == ["Ana"]                 # the plain-name view every older caller still reads
    assert m["myRsvp"] == "needsAction"              # the OPERATOR has not answered yet — still visible
    assert m["selfEmail"] == "me@x.com"              # which roster row an RSVP would patch
    assert m["status"] == "confirmed"                # …and Ana, who is the other party, HAS accepted
    assert m["guests"] == [{"name": "Ana", "email": "ana@x.com", "rsvp": "accepted"}]


def test_the_other_party_not_having_answered_leaves_the_meeting_pending():
    """The counterweight to the case above: `status` has to still MOVE, or it would be a constant."""
    ev = {"id": "ev3b", "status": "confirmed",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"},
          "attendees": [{"email": "me@x.com", "self": True, "responseStatus": "accepted"},
                        {"displayName": "Ana", "email": "ana@x.com", "responseStatus": "needsAction"}]}
    m = gc.event_to_meeting(ev, "primary")
    assert m["myRsvp"] == "accepted"
    assert m["status"] == "pending"


def test_a_guest_whose_answer_google_does_not_report_is_not_counted_as_accepted():
    """Not knowing is not the same as being confirmed — claiming otherwise is a claim about somebody else."""
    ev = {"id": "ev3c", "status": "confirmed",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"},
          "attendees": [{"email": "me@x.com", "self": True, "responseStatus": "accepted"},
                        {"displayName": "Ana", "email": "ana@x.com"}]}
    m = gc.event_to_meeting(ev, "primary")
    assert "rsvp" not in m["guests"][0]
    assert m["status"] == "pending"


def test_the_organizer_is_marked_on_the_roster_row_that_holds_it():
    ev = {"id": "ev3d", "status": "confirmed",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"},
          "organizer": {"displayName": "Gavin Hayes", "email": "g@z.com"},
          "attendees": [{"email": "me@x.com", "self": True, "responseStatus": "accepted"},
                        {"email": "g@z.com", "responseStatus": "accepted", "organizer": True}]}
    m = gc.event_to_meeting(ev, "primary")
    assert m["organizer"] == "Gavin Hayes"           # absent when it is OURS — that is the «who invited me»
    assert m["guests"][0]["organizer"] is True
    assert m["guests"][0]["name"] == "g@z.com"       # no displayName → the address is the only honest name


def test_a_join_link_that_is_not_http_never_reaches_the_card():
    """Anybody who can send an invitation writes `conferenceData`, and the card turns it into an href."""
    base = {"id": "ev3e", "status": "confirmed",
            "start": {"dateTime": "2026-09-15T11:30:00+02:00"},
            "end": {"dateTime": "2026-09-15T12:30:00+02:00"}}
    hostile = dict(base, conferenceData={"entryPoints": [
        {"entryPointType": "video", "uri": "javascript:alert(1)"}]})
    assert "meetLink" not in gc.event_to_meeting(hostile, "primary")
    good = dict(base, hangoutLink="https://meet.google.com/cgh-pouq-gje")
    assert gc.event_to_meeting(good, "primary")["meetLink"] == "https://meet.google.com/cgh-pouq-gje"


def test_a_phone_bridge_is_never_offered_as_a_way_in():
    """The operator's own words about the dial-in numbers and the PIN: «extras y absurdas»."""
    ev = {"id": "ev3f", "status": "confirmed",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"},
          "conferenceData": {"entryPoints": [
              {"entryPointType": "phone", "uri": "tel:+34910489510", "pin": "341785453"}]}}
    assert "meetLink" not in gc.event_to_meeting(ev, "primary")


def test_no_attendees_at_all_is_confirmed_by_default():
    ev = {"id": "ev4", "status": "confirmed",
          "start": {"dateTime": "2026-09-15T11:30:00+02:00"}, "end": {"dateTime": "2026-09-15T12:30:00+02:00"}}
    assert gc.event_to_meeting(ev, "primary")["status"] == "confirmed"


def test_meeting_to_event_roundtrips_a_timed_meeting():
    m = {"title": "Reunión", "date": "2026-09-15", "startTime": "09:00", "endTime": "10:00",
         "location": "Oficina", "notes": "Traer portátil", "attendees": ["ana@x.com", "sin-email"]}
    body = gc.meeting_to_event(m)
    assert body["summary"] == "Reunión"
    assert body["start"]["dateTime"].startswith("2026-09-15T09:00:00")
    assert body["end"]["dateTime"].startswith("2026-09-15T10:00:00")
    assert body["location"] == "Oficina" and body["description"] == "Traer portátil"
    # A bare name with no email cannot be invited on Google's side — it is simply not sent, never guessed.
    assert body["attendees"] == [{"email": "ana@x.com"}]


def test_meeting_to_event_allday_end_is_exclusive():
    body = gc.meeting_to_event({"title": "Festivo", "date": "2026-09-20", "allDay": True})
    assert body["start"]["date"] == "2026-09-20"
    assert body["end"]["date"] == "2026-09-21"   # Google's all-day end is the day AFTER


# ── the client's parsing and its error words ─────────────────────────────────────────────────────────────
class _R:
    def __init__(self, code, body):
        self.status_code = code
        self._body = body

    def json(self):
        return self._body


def test_error_words_distinguish_dead_session_and_quota():
    assert "reconecta" in gc._err_of(_R(401, {}))
    assert "cuota" in gc._err_of(_R(403, {"error": {"message": "Quota exceeded", "errors": [{"reason": "quotaExceeded"}]}}))


class _FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("get", url, dict(params or {})))
        return self.pages.pop(0)

    # `params` mirrors what httpx actually accepts here. Without it this double was NARROWER than the real
    # client, so V2-685's `conferenceDataVersion=1` raised a TypeError that `insert_event`'s own except
    # swallowed into `{"ok": False}` — a test double with the wrong shape measures the double.
    def post(self, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append(("post", url, json))
        self.params = dict(params or {})
        return self.pages.pop(0)

    def patch(self, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append(("patch", url, json))
        self.params = dict(params or {})
        return self.pages.pop(0)

    def delete(self, url, headers=None, timeout=None):
        self.calls.append(("delete", url, None))
        return self.pages.pop(0)


def test_list_events_singleEvents_and_pagination():
    c = _FakeClient([
        _R(200, {"items": [{"id": "e1", "status": "confirmed"}], "nextPageToken": "p2"}),
        _R(200, {"items": [{"id": "e2", "status": "cancelled"}], "nextSyncToken": "st-1"}),
    ])
    r = gc.list_events(c, "https://api", "tok", "primary", time_min="2026-01-01T00:00:00Z")
    assert r["ok"] and [e["id"] for e in r["events"]] == ["e1"]
    assert r["deleted"] == ["e2"] and r["next_sync_token"] == "st-1"
    assert c.calls[0][2]["singleEvents"] == "true"
    assert c.calls[1][2]["pageToken"] == "p2"


def test_list_events_reports_an_expired_sync_token():
    c = _FakeClient([_R(410, {})])
    r = gc.list_events(c, "https://api", "tok", "primary", sync_token="stale")
    assert r["ok"] is False and r.get("expired") is True


def test_insert_patch_delete_travel_the_normalized_shape():
    c = _FakeClient([_R(200, {"id": "new1", "status": "confirmed",
                              "start": {"dateTime": "2026-09-15T09:00:00+02:00"},
                              "end": {"dateTime": "2026-09-15T10:00:00+02:00"}, "summary": "Reunión"})])
    r = gc.insert_event(c, "https://api", "tok", "primary", {"summary": "Reunión"})
    assert r["ok"] and r["event"]["id"] == "new1"
    c2 = _FakeClient([_R(404, {})])
    assert gc.delete_event(c2, "https://api", "tok", "primary", "gone")["ok"] is True   # already gone = done


# ── the facade ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_facade_names_the_missing_piece_at_each_rung(sandbox, monkeypatch):
    assert "desconocido" in service.list_calendars("bing")["error"]
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")
    assert "Configuración" in service.list_calendars("google")["error"]
    monkeypatch.setattr(oauth, "client_id", lambda pid: "cid")
    assert "no está conectado" in service.list_calendars("google")["error"]


def test_sync_merges_new_changed_and_deleted_events(sandbox, monkeypatch):
    monkeypatch.setattr(service, "_prepared", lambda pid="google": (providers.get("google"), "tok", None))
    monkeypatch.setattr(gc, "list_calendars", lambda c, base, tok: {"ok": True, "calendars": [
        {"id": "primary", "summary": "Principal", "backgroundColor": "#4285F4", "primary": True, "selected": True}]})

    def _first_list(*a, **k):
        return {"ok": True, "next_sync_token": "st-1", "deleted": [], "events": [
            {"id": "e1", "status": "confirmed", "updated": "u1", "summary": "Uno",
             "start": {"dateTime": "2026-09-15T09:00:00+02:00"}, "end": {"dateTime": "2026-09-15T10:00:00+02:00"}}]}
    monkeypatch.setattr(gc, "list_events", _first_list)

    db = {"meetings": []}
    res = service.sync(db)
    assert res["ok"] and res["changed"] is True and res["new_ids"] == ["e1"]
    assert db["meetings"][0]["title"] == "Uno" and db["google"]["syncTokens"]["primary"] == "st-1"

    # second sync: e1 is deleted upstream, nothing new — a real change (removed), still detected.
    def _second_list(*a, **k):
        return {"ok": True, "next_sync_token": "st-2", "deleted": ["e1"], "events": []}
    monkeypatch.setattr(gc, "list_events", _second_list)
    res2 = service.sync(db)
    assert res2["changed"] is True and res2["removed_ids"] == ["e1"]
    assert db["meetings"] == []


def test_sync_falls_back_to_a_full_pull_when_the_token_expired(sandbox, monkeypatch):
    monkeypatch.setattr(service, "_prepared", lambda pid="google": (providers.get("google"), "tok", None))
    monkeypatch.setattr(gc, "list_calendars", lambda c, base, tok: {"ok": True, "calendars": [
        {"id": "primary", "summary": "P", "backgroundColor": "", "primary": True, "selected": True}]})
    calls = []

    def _list(client, base, tok, cid, sync_token="", time_min="", time_max=""):
        calls.append(sync_token)
        if sync_token:
            return {"ok": False, "error": "expired", "expired": True}
        return {"ok": True, "next_sync_token": "fresh", "deleted": [], "events": []}
    monkeypatch.setattr(gc, "list_events", _list)
    db = {"meetings": [], "google": {"calendars": [], "defaultCalendarId": "", "syncTokens": {"primary": "stale"},
                                     "lastSync": 0}}
    res = service.sync(db)
    assert res["ok"] and calls == ["stale", ""]     # tried the stale token, then fell back to a full pull
    assert db["google"]["syncTokens"]["primary"] == "fresh"


def test_create_event_enriches_and_the_caller_can_replace_its_local_copy(sandbox, monkeypatch):
    monkeypatch.setattr(service, "_prepared", lambda pid="google": (providers.get("google"), "tok", None))
    monkeypatch.setattr(gc, "insert_event", lambda c, base, tok, cal, body: {"ok": True, "event": {
        "id": "new1", "status": "confirmed", "summary": body["summary"],
        "start": {"dateTime": "2026-09-15T09:00:00+02:00"}, "end": {"dateTime": "2026-09-15T10:00:00+02:00"}}})
    r = service.create_event({"title": "Reunión", "date": "2026-09-15", "startTime": "09:00", "endTime": "10:00"},
                             calendar_id="primary")
    assert r["ok"] and r["meeting"]["googleId"] == "new1" and r["meeting"]["source"] == "google"


def test_patch_and_delete_require_a_google_origin_meeting(sandbox, monkeypatch):
    monkeypatch.setattr(service, "_prepared", lambda pid="google": (providers.get("google"), "tok", None))
    assert "no viene de Google" in service.patch_event({"title": "x"}, {"title": "y"})["error"]
    assert "no viene de Google" in service.delete_event({"title": "x"})["error"]


def test_brain_state_declines_before_promising_anything(sandbox):
    assert "TODAVÍA NO ESTÁ DISPONIBLE" in service.brain_state()
