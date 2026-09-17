"""V2-718 — «¿me puedes mandar el enlace por mail?»

The operator's assistant had negotiated a meeting on Telegram, agreed an hour, minted a Meet link and
written it into the agenda. The other party's last message asked for a calendar invitation to an address he
gave in that same message, and nothing happened — the agenda had no verb for it.

Two things are measured here, and the FIRST one is the trap:

  · Google's `events.patch` defaults to `sendUpdates=none`. Adding somebody to `attendees` returns 200, puts
    them on the event, and tells them NOTHING. It is the exact shape of the `conferenceDataVersion` bug this
    connector already carries a warning about — one parameter over, same silence, and the whole point of the
    feature is the mail that does not arrive without it.
  · `attendees` is an array and a PATCH carrying an array REPLACES it (the V2-697 scar, on our own event
    this time): adding a guest has to send the roster BACK, or it deletes everybody else.

The second rung — an invitation built and mailed by us, for a meeting with no calendar behind it — is
measured for the property that makes a mail an invitation rather than a mail with a file stuck to it.
"""
import httpx
import pytest

from connectors.calendar import ics
from connectors.calendar import oauth, providers, service


class _R:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("get", url, None, params))
        return self.responses.pop(0)

    def patch(self, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append(("patch", url, json, params))
        return self.responses.pop(0)


_LIVE = {
    "id": "ev1", "status": "confirmed",
    "start": {"dateTime": "2026-09-17T22:00:00+02:00"},
    "end": {"dateTime": "2026-09-17T23:00:00+02:00"},
    "summary": "Meeting with Ivan Mikushin",
    "attendees": [{"email": "me@x.com", "self": True, "organizer": True, "responseStatus": "accepted"}],
}
_MEETING = {"googleId": "ev1", "googleCalendarId": "primary", "source": "google",
            "title": "Meeting with Ivan Mikushin", "date": "2026-09-17",
            "startTime": "22:00", "endTime": "23:00",
            "meetLink": "https://meet.google.com/ydi-zeaz-tri"}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "STORE", tmp_path / "calendar_oauth.json")
    monkeypatch.setattr(service, "_prepared", lambda pid=None: (providers.get("google"), "tok-1", None))
    return None


def _run(monkeypatch, responses, emails=("ivan@charms.dev",), meeting=None):
    client = _Client(responses)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    res = service.invite(dict(meeting or _MEETING), list(emails))
    return res, client


def _echo_with(*mails):
    ev = dict(_LIVE)
    ev["attendees"] = [dict(a) for a in _LIVE["attendees"]] + [{"email": m} for m in mails]
    return ev


# ── the mail that does not arrive without one parameter ───────────────────────────────────────────────────

def test_google_is_ASKED_to_tell_the_guest(wired, monkeypatch):
    res, client = _run(monkeypatch, [_R(200, _LIVE), _R(200, _echo_with("ivan@charms.dev"))])
    assert res["ok"] and res["added"] == ["ivan@charms.dev"]
    params = [c for c in client.calls if c[0] == "patch"][0][3] or {}
    assert params.get("sendUpdates") == "all", \
        "without sendUpdates Google adds the guest and sends them nothing — a 200 that invited nobody"


def test_adding_a_guest_never_deletes_the_others(wired, monkeypatch):
    live = dict(_LIVE)
    live["attendees"] = [dict(a) for a in _LIVE["attendees"]] + [{"email": "otro@x.com"}]
    res, client = _run(monkeypatch, [_R(200, live), _R(200, _echo_with("otro@x.com", "ivan@charms.dev"))])
    assert res["ok"]
    sent = [c for c in client.calls if c[0] == "patch"][0][2]
    assert [a["email"] for a in sent["attendees"]] == ["me@x.com", "otro@x.com", "ivan@charms.dev"]
    assert set(sent) == {"attendees"}, "nothing else about the event is re-sent"


def test_somebody_already_invited_is_not_invited_twice(wired, monkeypatch):
    live = _echo_with("ivan@charms.dev")
    res, client = _run(monkeypatch, [_R(200, live)])
    assert res["ok"] and res["added"] == [] and res["already"] == ["ivan@charms.dev"]
    assert not [c for c in client.calls if c[0] == "patch"], \
        "re-patching would re-notify every guest of a meeting that did not change"


def test_an_address_that_is_not_one_never_reaches_google(wired, monkeypatch):
    res, client = _run(monkeypatch, [], emails=["ivan"])
    assert not res["ok"] and "correo" in res["error"]
    assert client.calls == []


def test_a_meeting_with_no_calendar_behind_it_is_the_other_rung(wired, monkeypatch):
    res, client = _run(monkeypatch, [], meeting={"title": "Café", "date": "2026-09-18"})
    assert not res["ok"] and "Google Calendar" in res["error"]
    assert client.calls == []


# ── the second rung: an invitation we build ourselves ─────────────────────────────────────────────────────

def test_the_invitation_object_says_when_the_meeting_is_in_UTC():
    text = ics.build(_MEETING, organizer="me@x.com", attendees=["ivan@charms.dev"], offset_minutes=120)
    assert "METHOD:REQUEST" in text
    assert "DTSTART:20260917T200000Z" in text, "22:00 in a UTC+2 install is 20:00Z — an hour off is the bug"
    assert "DTEND:20260917T210000Z" in text
    assert "ORGANIZER:mailto:me@x.com" in text
    assert "RSVP=TRUE" in text.replace("\r\n ", "")
    assert "mailto:ivan@charms.dev" in text.replace("\r\n ", ""), "folded lines still say the address"


def test_the_invitation_carries_the_meeting_link_where_a_calendar_shows_it():
    text = ics.build(_MEETING, organizer="me@x.com", attendees=["ivan@charms.dev"], offset_minutes=120)
    unfolded = text.replace("\r\n ", "")
    assert "meet.google.com/ydi-zeaz-tri" in unfolded
    assert "LOCATION:" in unfolded


def test_the_same_meeting_is_always_the_same_invitation():
    """UID is identity for the rest of its life: two mails with the same UID are ONE meeting in the guest's
    calendar, two with different UIDs are two meetings."""
    a = ics.uid_for(_MEETING)
    b = ics.uid_for(dict(_MEETING))
    assert a == b and a.endswith("@zaelar")
    assert ics.uid_for({"title": "Café", "date": "2026-09-18"}) != a


def test_an_invitation_with_nobody_to_invite_is_refused_not_sent():
    with pytest.raises(ValueError):
        ics.build(_MEETING, organizer="me@x.com", attendees=[])
    with pytest.raises(ValueError):
        ics.build({"title": "x"}, organizer="me@x.com", attendees=["a@b.com"])


def test_the_mail_is_shaped_like_an_invitation_not_like_an_attachment(monkeypatch):
    """What makes a client show Accept / Decline is the `text/calendar; method=REQUEST` PART — and the .ics
    attachment beside it is what the clients that only offer «add to calendar» from a file need."""
    from connectors.email import mailbox as mb

    sent = {}

    class _SMTP:
        def send_message(self, msg):
            sent["msg"] = msg

        def quit(self):
            pass

        def close(self):
            pass

    box = mb.Mailbox.__new__(mb.Mailbox)
    box.address = "me@x.com"
    monkeypatch.setattr(mb.Mailbox, "_connect_smtp", lambda self: _SMTP())
    monkeypatch.setattr(mb.Mailbox, "_smtp_login", lambda self, s: None)
    text = ics.build(_MEETING, organizer="me@x.com", attendees=["ivan@charms.dev"], offset_minutes=120)
    ok, _mid = box.send_invitation("ivan@charms.dev", "Meeting with Ivan Mikushin", "Te paso la invitación.",
                                   text)
    assert ok
    parts = list(sent["msg"].walk())
    cal = [p for p in parts if p.get_content_type() == "text/calendar"]
    assert cal, "with no text/calendar part the mail is not an invitation, it is a mail"
    assert "method=REQUEST" in cal[0]["Content-Type"], \
        "a text/calendar part with no method is a published calendar — no buttons at all"
    files = [p for p in parts if (p.get("Content-Disposition") or "").startswith("attachment")]
    assert [p.get_filename() for p in files] == ["invite.ics"]
    assert [p for p in parts if p.get_content_type() == "text/plain"], \
        "a client that understands neither still has to be able to read it"
