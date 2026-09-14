"""V2-697 — answering an invitation somebody else convened.

The operator compared our appointment card against Google's own and asked for the missing half: being able
to say whether he is going. In the Google API an RSVP is one field of one row of the event's `attendees`
array — and that is exactly what makes it dangerous, because a PATCH carrying an array REPLACES it. Sending
only our own row would delete every other guest from the organizer's meeting and return 200 while doing it.

So the whole point of these cases is the read-modify-write: the live roster comes back, OUR row alone is
edited, and the full list goes up again.
"""
import httpx
import pytest

from connectors.calendar import google_calendar as gc
from connectors.calendar import oauth, providers, service


class _R:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class _Client:
    """Records every call so a test can assert what was SENT, which is the whole question here."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("get", url, None))
        return self.responses.pop(0)

    def patch(self, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append(("patch", url, json))
        return self.responses.pop(0)


#: The event as Google holds it: the organizer, us, and a third guest nobody asked about.
_LIVE = {
    "id": "ev1", "status": "confirmed",
    "start": {"dateTime": "2026-09-15T15:00:00+02:00"},
    "end": {"dateTime": "2026-09-15T15:30:00+02:00"},
    "organizer": {"displayName": "Gavin Hayes", "email": "gavin@zerohash.com"},
    "attendees": [
        {"email": "gavin@zerohash.com", "responseStatus": "accepted", "organizer": True},
        {"email": "me@x.com", "self": True, "responseStatus": "needsAction"},
        {"email": "third@x.com", "responseStatus": "accepted"},
    ],
}

_MEETING = {"googleId": "ev1", "googleCalendarId": "primary", "selfEmail": "me@x.com", "source": "google"}


@pytest.fixture
def wired(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "STORE", tmp_path / "calendar_oauth.json")
    monkeypatch.setattr(service, "_prepared",
                        lambda pid=None: (providers.get("google"), "tok-1", None))
    return None


def _run(monkeypatch, responses, answer="accepted", meeting=None):
    client = _Client(responses)
    monkeypatch.setattr(httpx, "Client", lambda *a, **k: client)
    res = service.rsvp(dict(meeting or _MEETING), answer)
    return res, client


def test_the_whole_roster_travels_back_with_only_our_own_answer_changed(wired, monkeypatch):
    echoed = dict(_LIVE)
    echoed["attendees"] = [dict(a) for a in _LIVE["attendees"]]
    echoed["attendees"][1]["responseStatus"] = "accepted"
    res, client = _run(monkeypatch, [_R(200, _LIVE), _R(200, echoed)])
    assert res["ok"]
    sent = [c for c in client.calls if c[0] == "patch"][0][2]
    # EVERY guest is still there — this is the assertion the feature exists for.
    assert [a["email"] for a in sent["attendees"]] == ["gavin@zerohash.com", "me@x.com", "third@x.com"]
    assert [a["responseStatus"] for a in sent["attendees"]] == ["accepted", "accepted", "accepted"]
    # …and nothing ELSE about somebody else's event was re-sent.
    assert set(sent) == {"attendees"}
    assert res["meeting"]["myRsvp"] == "accepted"


def test_declining_sets_only_our_row(wired, monkeypatch):
    echoed = dict(_LIVE)
    echoed["attendees"] = [dict(a) for a in _LIVE["attendees"]]
    echoed["attendees"][1]["responseStatus"] = "declined"
    res, client = _run(monkeypatch, [_R(200, _LIVE), _R(200, echoed)], answer="declined")
    assert res["ok"]
    sent = [c for c in client.calls if c[0] == "patch"][0][2]
    by_mail = {a["email"]: a["responseStatus"] for a in sent["attendees"]}
    assert by_mail == {"gavin@zerohash.com": "accepted", "me@x.com": "declined", "third@x.com": "accepted"}


def test_an_answer_we_do_not_understand_never_reaches_google(wired, monkeypatch):
    res, client = _run(monkeypatch, [], answer="perhaps not")
    assert not res["ok"] and "perhaps not" in res["error"]
    assert client.calls == []


def test_a_meeting_we_were_never_invited_to_has_nothing_to_answer(wired, monkeypatch):
    res, client = _run(monkeypatch, [], meeting={"googleId": "ev1", "googleCalendarId": "primary"})
    assert not res["ok"] and "invitados" in res["error"]
    assert client.calls == []


def test_a_meeting_the_operator_dictated_is_not_a_google_invitation(wired, monkeypatch):
    res, client = _run(monkeypatch, [], meeting={"selfEmail": "me@x.com"})
    assert not res["ok"] and "Google Calendar" in res["error"]
    assert client.calls == []


def test_being_dropped_from_the_guest_list_is_reported_and_writes_nothing(wired, monkeypatch):
    """The organizer removed us between the sync and the click. Patching anyway would ADD us back."""
    without_us = dict(_LIVE)
    without_us["attendees"] = [a for a in _LIVE["attendees"] if not a.get("self")]
    res, client = _run(monkeypatch, [_R(200, without_us)])
    assert not res["ok"] and "invitados" in res["error"]
    assert [c for c in client.calls if c[0] == "patch"] == []


def test_a_failed_read_never_becomes_a_write(wired, monkeypatch):
    res, client = _run(monkeypatch, [_R(404, {})])
    assert not res["ok"]
    assert [c for c in client.calls if c[0] == "patch"] == []
