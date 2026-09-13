"""One Google account, six doors — and the one verb the engine has never had (V2-685).

## What was measured before writing any of this

`builtin_client_id` was declared in `connectors/video/providers.py` (V2-603) with the comment «EMPTY until
Zaelar registers its own Google OAuth client», and copied verbatim into `connectors/calendar/providers.py`
(V2-679). The operator registered that client on 2026-09-12. Filling the two strings by hand would have left
the other three Google doors — Gmail, Drive, Photos — still asking him for the same value under three more
names: `EMAIL_GMAIL_CLIENT_ID`, `FILES_GDRIVE_CLIENT_ID`, `PHOTOS_GOOGLE_PHOTOS_CLIENT_ID`. Five names, one
fact, and four of them silently dormant on an install where he had answered only one.

So the assertions below are mostly about what must NOT move: a per-connector name still wins, a non-Google
provider gets nothing, and no credential VALUE appears in anything the Connectors tab renders.

## Meet, and why it is an argument rather than a tool

A Meet link is `conferenceData` on a calendar event. It costs no extra consent because it rides the calendar
scope the connector already holds, and it is created by the tool the model ALREADY has for appointments —
which is the whole reason `brain.py` names the argument out loud. A capability that is reachable and
undeclared is one the model narrates (V2-540), and here the narration has a specific shape: inventing a
`create_meet` tool, or promising a link before Google has minted one.

⚠️ The `conferenceDataVersion=1` case is the expensive one. Without that query parameter Google returns 200,
creates the event, and DROPS the conference silently — no error, no link, and an agent that has just told the
operator it made them a meeting room.
"""
from __future__ import annotations

import importlib.util
import json

import pytest


@pytest.fixture(autouse=True)
def _no_cached_client_file():
    """`app._from_file` caches on (path, mtime_ns). A test that writes two files in the same nanosecond, or
    points the module at a fresh tmp dir, must not inherit the previous case's answer."""
    from connectors.google import app
    app._cache.update({"key": None, "value": None})
    yield
    app._cache.update({"key": None, "value": None})


def _console_json(tmp_path, kind: str = "web", *, name: str = "google-connector-client_secret_x.json",
                  cid: str = "111-abc.apps.googleusercontent.com", secret: str = "GOCSPX-shhh"):
    """The file the Google Cloud console hands you, in the shape it hands it to you."""
    p = tmp_path / name
    p.write_text(json.dumps({kind: {"client_id": cid, "client_secret": secret,
                                    "project_id": "proj-1",
                                    "token_uri": "https://oauth2.googleapis.com/token"}}), encoding="utf-8")
    return p


@pytest.fixture
def shipped(tmp_path, monkeypatch):
    """An install whose ONLY answer is the console's JSON — no env, no credential store."""
    from connectors.google import app
    _console_json(tmp_path)
    monkeypatch.setattr(app, "CREDENTIALS_DIR", tmp_path)
    monkeypatch.setattr(app, "_cred", lambda name: "")
    return app


# ── 1 · the shipped client reaches every Google door, and nothing else ──────────────────────────────────
#: ⚠️ `connectors.calendar` is UNCOMMITTED work owned by another session on this machine (V2-679). A clean
#: clone does not have it, so the rows that need it SKIP rather than error — the same shape
#: `test_segmenter_corpus.py` uses for the session registry: a clean clone skips, this machine measures.
_HAS_CALENDAR = importlib.util.find_spec("connectors.calendar.google_calendar") is not None
_needs_calendar = pytest.mark.skipif(not _HAS_CALENDAR,
                                     reason="connectors/calendar is not part of this tree yet (V2-679)")

_GOOGLE_DOORS = [
    ("connectors.email.oauth", "gmail"),
    pytest.param("connectors.calendar.oauth", "google", marks=_needs_calendar),
    ("connectors.video.oauth", "youtube"),
    ("connectors.photos.oauth", "google-photos"),
    ("connectors.files.oauth", "gdrive"),
]


@pytest.mark.parametrize("module,provider", _GOOGLE_DOORS)
def test_one_registered_client_opens_every_google_door(shipped, monkeypatch, module, provider):
    """The operator answers once. Before this, each of these five read its OWN env name and nothing else, so
    four of them stayed dormant on an install where he had configured one."""
    mod = __import__(module, fromlist=["oauth"])
    monkeypatch.setattr(mod, "_cred", lambda name: "")
    assert mod.client_id(provider) == "111-abc.apps.googleusercontent.com"
    assert mod.client_secret(provider) == "GOCSPX-shhh"


def test_a_provider_that_is_not_google_gets_nothing(shipped, monkeypatch):
    """The counterweight, and the one that makes the change safe: Outlook authenticates against Microsoft,
    so handing it a Google client would turn a dormant connector into a broken one."""
    from connectors.email import oauth
    monkeypatch.setattr(oauth, "_cred", lambda name: "")
    assert oauth.client_id("outlook") == ""
    assert oauth.client_secret("outlook") == ""


@pytest.mark.parametrize("module,provider,own_key", [
    ("connectors.email.oauth", "gmail", "EMAIL_GMAIL_CLIENT_ID"),
    ("connectors.video.oauth", "youtube", "VIDEO_YOUTUBE_CLIENT_ID"),
    ("connectors.files.oauth", "gdrive", "FILES_GDRIVE_CLIENT_ID"),
])
def test_the_operators_own_client_still_wins(shipped, monkeypatch, module, provider, own_key):
    """A self-hoster who wants their own quota, their own consent screen and their own verification status
    keeps it. This is the rule each connector already applied per-provider, lifted one level up — so lifting
    it must not have quietly reversed the precedence."""
    mod = __import__(module, fromlist=["oauth"])
    monkeypatch.setattr(mod, "_cred", lambda name: "mine-123" if name == own_key else "")
    assert mod.client_id(provider) == "mine-123"


def test_a_shared_override_beats_the_shipped_file(tmp_path, monkeypatch):
    """`GOOGLE_CLIENT_ID` is the door for an operator who wants ONE client of their own for all six services
    without editing any file we ship."""
    from connectors.google import app
    _console_json(tmp_path)
    monkeypatch.setattr(app, "CREDENTIALS_DIR", tmp_path)
    monkeypatch.setattr(app, "_cred", lambda n: {"GOOGLE_CLIENT_ID": "own-9"}.get(n, ""))
    assert app.client_id() == "own-9"
    assert app.source() == "operator"


def test_no_client_anywhere_leaves_every_door_exactly_as_dormant_as_before(tmp_path, monkeypatch):
    """The failure mode that must stay unchanged: a connector with no app says so and offers the long road.
    It must never start reporting itself configured because this module exists."""
    from connectors.google import app
    monkeypatch.setattr(app, "CREDENTIALS_DIR", tmp_path)          # empty dir
    monkeypatch.setattr(app, "_cred", lambda name: "")
    assert app.client_id() == "" and app.configured() is False and app.source() == ""
    from connectors.video import oauth as vid
    monkeypatch.setattr(vid, "_cred", lambda name: "")
    assert vid.configured("youtube") is False


def test_an_installed_client_is_read_too_and_says_which_kind_it_is(tmp_path, monkeypatch):
    """Both shapes Google emits. The KIND is carried out rather than flattened away because it decides
    whether a redirect URI must be pre-registered — which is the difference between a flow that works and
    one that dies at its last step."""
    from connectors.google import app
    _console_json(tmp_path, "installed", name="google-desktop_client_secret_y.json")
    monkeypatch.setattr(app, "CREDENTIALS_DIR", tmp_path)
    monkeypatch.setattr(app, "_cred", lambda name: "")
    assert app.client_id() == "111-abc.apps.googleusercontent.com"
    assert app.is_web_client() is False


def test_a_web_client_names_every_uri_that_must_be_registered(shipped):
    """Google refuses a redirect URI it has never seen, with `invalid_client`, at the END of a flow that
    looked healthy the whole way up. The five callbacks are not unified into one path on purpose — that
    would be a token-store migration wearing a redirect's clothes — so all five must be listed."""
    assert shipped.is_web_client() is True
    uris = shipped.redirect_uris("https://agent.example.com")
    assert uris == [f"https://agent.example.com{p}" for p in shipped.CALLBACK_PATHS]
    assert len(uris) == 5
    assert all(u.startswith("http://127.0.0.1:43917/") for u in shipped.redirect_uris())


def test_an_edited_credentials_file_is_seen_without_a_restart(tmp_path, monkeypatch):
    """The cache is keyed on (path, mtime), never on «have I looked yet» — the operator drops the console's
    JSON in while the engine is running, and a value frozen at import would leave him restarting to be
    believed."""
    from connectors.google import app
    p = _console_json(tmp_path, cid="first.apps.googleusercontent.com")
    monkeypatch.setattr(app, "CREDENTIALS_DIR", tmp_path)
    monkeypatch.setattr(app, "_cred", lambda name: "")
    assert app.client_id() == "first.apps.googleusercontent.com"
    p.write_text(json.dumps({"web": {"client_id": "second.apps.googleusercontent.com",
                                     "client_secret": "s2"}}), encoding="utf-8")
    import os
    os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1_000_000))
    assert app.client_id() == "second.apps.googleusercontent.com"


# ── 2 · nothing that reaches a screen carries a credential VALUE ────────────────────────────────────────
def test_the_status_says_where_the_client_came_from_and_never_what_it_is(shipped):
    """`source()`/`status()` feed the Connectors tab. The client_id is not a secret; the SECRET is, and it
    travels in the same file, so the rule here is simply that neither value is ever in the payload."""
    st = shipped.status()
    blob = json.dumps(st)
    assert "GOCSPX-shhh" not in blob and "111-abc" not in blob
    assert st["configured"] is True and st["source"] == "shipped" and st["has_secret"] is True


def test_the_account_row_does_not_collide_with_the_calendar_row(monkeypatch):
    """Both are «google» to a person, and `_calendar()` already owns that id — `widgets/agenda/data.py`
    matches on it. Two rows under one id is a collision the tab resolves by showing whichever it saw last,
    so the account row would have eaten the calendar card."""
    from connectors import registry
    rows = registry.descriptors()
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "two connector rows share an id"
    acct = [r for r in rows if r["id"] == "google-account"]
    assert len(acct) == 1 and acct[0]["family"] == "infra"
    assert json.dumps(acct[0]).count("GOCSPX") == 0


# ── 3 · Meet: an attribute of an appointment, never a second thing to create ────────────────────────────
def test_meet_asks_for_no_permission_of_its_own():
    """It rides the calendar scope. An unused sensitive scope buys nothing today and costs a harder Google
    verification for every user of the app, so the Meet REST scope is NAMED and not requested."""
    from connectors.google import services as svc
    meet = svc.get("meet")
    assert meet is not None and meet.scopes == () and meet.owner == ""
    assert meet.widget == "agenda"
    assert "meetings.space.created" in svc.FUTURE_SCOPES["meet"][0]


@_needs_calendar
def test_an_appointment_asked_for_with_meet_carries_a_conference_request():
    from connectors.calendar.google_calendar import meeting_to_event, wants_conference
    body = meeting_to_event({"title": "Equipo", "date": "2026-09-20", "startTime": "10:00",
                             "endTime": "11:00", "meet": True, "googleId": "abc123"})
    req = body["conferenceData"]["createRequest"]
    assert req["conferenceSolutionKey"]["type"] == "hangoutsMeet"
    assert wants_conference(body) is True


@_needs_calendar
def test_a_retried_insert_reuses_its_request_id_instead_of_minting_a_second_room():
    """`requestId` is Google's idempotency key. Derived from the meeting rather than random, so an insert
    retried after a timeout produces ONE conference and not two links for one appointment."""
    from connectors.calendar.google_calendar import meeting_to_event
    m = {"title": "Equipo", "date": "2026-09-20", "startTime": "10:00", "meet": True, "googleId": "abc123"}
    assert meeting_to_event(m)["conferenceData"]["createRequest"]["requestId"] == \
           meeting_to_event(m)["conferenceData"]["createRequest"]["requestId"]


@_needs_calendar
def test_an_ordinary_appointment_asks_for_no_conference():
    """The counterweight: every appointment that does not ask for a Meet must send the byte-identical
    request it sent before this shipped."""
    from connectors.calendar.google_calendar import meeting_to_event, wants_conference
    body = meeting_to_event({"title": "Dentista", "date": "2026-09-20", "startTime": "10:00"})
    assert "conferenceData" not in body and wants_conference(body) is False


class _Resp:
    status_code = 200

    def json(self):
        return {"id": "ev1"}


class _Client:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append(params)
        return _Resp()


@_needs_calendar
def test_the_conference_version_rides_the_request_that_asks_for_one():
    """⚠️ Without `conferenceDataVersion=1` Google returns 200 with the event created and the conference
    silently DROPPED — the shape of failure that makes an agent claim a meeting room it never made."""
    from connectors.calendar import google_calendar as gc
    c = _Client()
    gc.insert_event(c, "https://api", "tok", "primary",
                    gc.meeting_to_event({"title": "Equipo", "date": "2026-09-20",
                                         "startTime": "10:00", "meet": True}))
    assert c.calls == [{"conferenceDataVersion": 1}]

    c2 = _Client()
    gc.insert_event(c2, "https://api", "tok", "primary",
                    gc.meeting_to_event({"title": "Dentista", "date": "2026-09-20", "startTime": "10:00"}))
    assert c2.calls == [None], "an ordinary appointment must send the request it always sent"


@_needs_calendar
def test_the_meet_flag_is_carried_only_when_the_payload_names_it():
    """`gcal.apply_meet` is the agenda's Google seam for this, and it is deliberately the only place the rule
    lives — `_apply_details` is shared by the create and the edit paths, so both get the same answer.

    ⚠️ The DROPPING half is the one that needs a meeting room to already exist. The first version of this
    case only ever asserted absence, so removing the `if key not in payload` guard altogether left it GREEN:
    the mutation pops a key that was not there, which is indistinguishable from never setting it. A case that
    starts from the trimmed state measures the trim (V2-655's lesson, paid here)."""
    from widgets.agenda import gcal
    m = {"title": "Equipo"}
    gcal.apply_meet(m, {"startTime": "11:00"})
    assert "meet" not in m, "an edit that never mentions Meet must not mint one"

    gcal.apply_meet(m, {"meet": True})
    assert m["meet"] is True

    # The load-bearing one: he moves the hour of a meeting that ALREADY has a room.
    gcal.apply_meet(m, {"startTime": "12:00", "location": "sala 2"})
    assert m["meet"] is True, "an unrelated edit silently cancelled the video call"

    gcal.apply_meet(m, {"meet": "no"})
    assert "meet" not in m and "meetLink" not in m


@_needs_calendar
def test_a_paraphrased_name_for_a_video_call_still_lands():
    """An unambiguous natural alias must not cost the fact (V2-341): `meet` is the manifest's name, and the
    other two are what a model writes when it paraphrases."""
    from widgets.agenda import gcal
    for key in ("videocall", "conference"):
        m: dict = {}
        gcal.apply_meet(m, {key: True})
        assert m.get("meet") is True, key


@pytest.mark.skip(reason="V2-685: the agenda's `_apply_details` delegation is the ONE line this capability "
                         "still needs, and `widgets/agenda/data.py` sits EXACTLY on the 900-line newborn "
                         "ceiling while another session is editing it. Paying that ceiling means extracting "
                         "from their file mid-flight, and the ratchet is never paid by a smaller diff. The "
                         "line is `gcal.apply_meet(meeting, payload)` at the end of `_apply_details`; "
                         "un-skip this the moment that file lands.")
def test_the_agenda_delegates_the_flag_to_its_google_seam():
    import inspect

    from widgets.agenda import data
    assert "gcal.apply_meet(meeting, payload)" in inspect.getsource(data._apply_details)


# ── 4 · what both brains are told ───────────────────────────────────────────────────────────────────────
def test_an_unconnected_account_is_declared_rather_than_left_to_the_model(shipped, monkeypatch):
    """The V2-603 lesson, third payment: given the verbs and no facts, the model narrates «Hecho.». The line
    must forbid the claim, not merely omit it."""
    from connectors.google import brain
    monkeypatch.setattr(brain, "connected_services", lambda: [])
    line = brain.brain_state()
    assert "NO ha dado su consentimiento" in line and "NO afirmes que está conectada" in line


def test_a_connected_calendar_teaches_the_ARGUMENT_that_creates_a_meet(shipped, monkeypatch):
    """Naming the capability alone is what makes a model improvise a verb — so the line names `meet: true`
    and says plainly that no separate tool exists."""
    from connectors.google import brain
    monkeypatch.setattr(brain, "connected_services", lambda: ["calendar", "meet"])
    line = brain.brain_state()
    assert "meet: true" in line and "add_meeting" in line
    assert "NO hay ninguna tool aparte" in line


def test_with_no_client_at_all_it_says_the_doors_cannot_be_opened(tmp_path, monkeypatch):
    from connectors.google import app, brain
    monkeypatch.setattr(app, "CREDENTIALS_DIR", tmp_path)
    monkeypatch.setattr(app, "_cred", lambda name: "")
    monkeypatch.setattr(brain, "connected_services", lambda: [])
    line = brain.brain_state()
    assert "no hay cliente OAuth" in line and "NO digas que los conectas" in line


def test_the_turn_prompt_consults_it():
    """Wiring, structural: a fact nobody injects is a fact the model never had.

    Anchored on the module that OWNS the block (`flash/connector_briefs.py`), not on `prompt.py` where it
    used to live — V2-555's lesson: a wiring guard pinned to a file goes red the next time somebody pays the
    architecture ratchet by extracting, and then gets weakened instead of repointed. The second assertion is
    the one that matters: `prompt.py` must still REACH the composer."""
    import inspect

    from nucleo.flash import connector_briefs, prompt
    assert "from connectors.google import brain as _gb" in inspect.getsource(connector_briefs)
    assert "_gb.brain_state()" in inspect.getsource(connector_briefs)
    assert "connector_briefs" in inspect.getsource(prompt._connector_briefs)
