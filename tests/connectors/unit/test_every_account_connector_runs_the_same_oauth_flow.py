"""Every account connector runs the SAME OAuth flow (V2-778 F1-13, 2026-10-01).

Six connectors carried their own copy of the authorization-code + PKCE flow, and the copies had drifted:
files, photos and email still sent the provider back to a hardcoded `127.0.0.1:43917` — on an engine opened
from anywhere but that machine the consent returned to an address that never heard of it (V2-603, fixed in
the other three) — email never expired an abandoned consent, and email crashed on a token answer without
`expires_in`. The flow lives once now (`connectors/oauth_base.py`); this pins the behaviour on all six.
"""
from __future__ import annotations

import importlib
import time
import urllib.parse

import pytest

#: the route each connector is called back on — what the operator registers, so it is spelled out here
CALLBACK = {"calendar": "/api/calendar/callback", "video": "/api/video/callback",
            "contacts": "/api/contacts/callback", "files": "/api/cloudfiles/callback",
            "photos": "/api/photos/callback", "email": "/api/email/callback"}
CONNECTORS = [
    ("calendar", "google"), ("video", "youtube"), ("contacts", "google-contacts"),
    ("files", "gdrive"), ("photos", "google-photos"), ("email", "gmail"),
]


class _Resp:
    def __init__(self, body):
        self._b = body

    def json(self):
        return self._b


@pytest.fixture
def flow(tmp_path, monkeypatch):
    def make(name):
        o = importlib.import_module(f"connectors.{name}.oauth")
        monkeypatch.setattr(o, "STORE", tmp_path / f"{name}_oauth.json")
        monkeypatch.setattr(o, "_cred", lambda key: "the-client" if key.endswith("_CLIENT_ID") else "")
        monkeypatch.delenv(f"{name.upper()}_OAUTH_REDIRECT", raising=False)
        return o
    return make


def _authorize(o, name, pid, origin):
    kw = {"origin": origin} if origin else {}
    if name == "email":
        return o.authorize_url(pid, "me@example.com", **kw)
    return o.authorize_url(pid, "", **kw)


@pytest.mark.parametrize("name,pid", CONNECTORS)
def test_the_consent_returns_to_the_origin_the_operator_is_on_and_the_exchange_says_the_same(
        flow, monkeypatch, name, pid):
    o = flow(name)
    r = _authorize(o, name, pid, "https://agent.example.com")
    assert r["ok"], r
    q = urllib.parse.parse_qs(urllib.parse.urlparse(r["url"]).query)
    assert q["redirect_uri"][0] == f"https://agent.example.com{CALLBACK[name]}", q["redirect_uri"]
    sent = {}

    def post(url, data=None, timeout=None):
        sent.update(data or {})
        return _Resp({"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    import httpx
    monkeypatch.setattr(httpx, "post", post)
    res = o.exchange_code("the-code", q["state"][0])
    assert res["ok"], res
    assert sent["redirect_uri"] == q["redirect_uri"][0], "the exchange must present the redirect it consented with"


@pytest.mark.parametrize("name,pid", CONNECTORS)
def test_this_engines_own_listeners_and_a_forged_origin_return_to_loopback(flow, name, pid):
    o = flow(name)
    for origin in ("https://local.zaelar.com:44317", "https://evil.example.com/path?x=1", ""):
        assert o.redirect_uri(origin).startswith("http://127.0.0.1:"), (origin, o.redirect_uri(origin))


@pytest.mark.parametrize("name,pid", CONNECTORS)
def test_an_abandoned_consent_expires(flow, name, pid):
    o = flow(name)
    first = urllib.parse.parse_qs(urllib.parse.urlparse(_authorize(o, name, pid, "")["url"]).query)["state"][0]
    data = o._load()
    data["pending"][first]["ts"] = int(time.time()) - 3600
    o._save(data)
    _authorize(o, name, pid, "")
    assert first not in o._load()["pending"], "a consent started an hour ago must not still be accepted"


@pytest.mark.parametrize("name,pid", CONNECTORS)
def test_a_token_answer_without_expires_in_is_stored(flow, monkeypatch, name, pid):
    o = flow(name)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(_authorize(o, name, pid, "")["url"]).query)["state"][0]
    import httpx
    monkeypatch.setattr(httpx, "post", lambda *a, **k: _Resp({"access_token": "at", "refresh_token": "rt",
                                                               "expires_in": None}))
    assert o.exchange_code("c", state)["ok"]
    tok = o.access_token(pid, "me@example.com") if name == "email" else o.access_token(pid)
    assert tok == "at"
