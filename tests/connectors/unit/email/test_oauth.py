"""Tests of the email OAuth core (V2-055) — VERIFIABLE pieces without the network: PKCE, authorize URL, token store,
selection of the current token (the network exchange/refresh is dormant and is not exercised here)."""
import time
import urllib.parse

import pytest

from connectors.email import oauth


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(oauth, "STORE", tmp_path / "email_oauth.json")
    yield


def test_pkce_deterministic_and_s256():
    v1, c1 = oauth.make_pkce(seed=b"\x00" * 48)
    v2, c2 = oauth.make_pkce(seed=b"\x00" * 48)
    assert v1 == v2 and c1 == c2            # same seed → same pair
    assert "=" not in v1 and "=" not in c1  # base64url without padding
    assert v1 != c1                          # the challenge is the verifier's SHA256, not the verifier


def test_authorize_url_requires_registered_app(store, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")   # without a registered app
    res = oauth.authorize_url("gmail", "yo@gmail.com")
    assert res["ok"] is False and "CLIENT_ID" in res["error"]


def test_authorize_url_builds_consent_and_stashes_state(store, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "CID123")
    res = oauth.authorize_url("gmail", "yo@gmail.com")
    assert res["ok"] is True
    u = urllib.parse.urlparse(res["url"])
    q = urllib.parse.parse_qs(u.query)
    assert u.netloc == "accounts.google.com"
    assert q["client_id"] == ["CID123"]
    assert q["code_challenge_method"] == ["S256"] and q["code_challenge"]
    assert q["response_type"] == ["code"]
    assert "mail.google.com" in q["scope"][0]
    # the state was stashed with its verifier (for the callback)
    state = q["state"][0]
    pend = oauth._load().get("pending", {}).get(state)
    assert pend and pend["provider"] == "gmail" and pend["verifier"]


def test_authorize_url_microsoft_endpoint(store, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "MSID")
    res = oauth.authorize_url("outlook", "yo@outlook.com")
    assert res["ok"] and "login.microsoftonline.com" in res["url"]
    assert "offline_access" in urllib.parse.parse_qs(urllib.parse.urlparse(res["url"]).query)["scope"][0]


def test_token_store_roundtrip_and_forget(store):
    oauth._store_tokens("gmail", "yo@gmail.com", {"access_token": "AT", "refresh_token": "RT", "expires_in": 3600})
    assert oauth.tokens_present("gmail", "yo@gmail.com")
    # current token → returns access_token WITHOUT the network
    assert oauth.access_token("gmail", "yo@gmail.com") == "AT"
    oauth.forget("gmail", "yo@gmail.com")
    assert not oauth.tokens_present("gmail", "yo@gmail.com")
    assert oauth.access_token("gmail", "yo@gmail.com") is None


def test_refresh_token_preserved_across_updates(store):
    oauth._store_tokens("gmail", "a@gmail.com", {"access_token": "AT1", "refresh_token": "RT", "expires_in": 3600})
    # a refresh that does NOT return refresh_token must not delete the one we already had
    oauth._store_tokens("gmail", "a@gmail.com", {"access_token": "AT2", "expires_in": 3600})
    acct = oauth._load()["accounts"][oauth._acct_key("gmail", "a@gmail.com")]
    assert acct["refresh_token"] == "RT" and acct["access_token"] == "AT2"


def test_expired_without_refresh_returns_stale_not_crash(store):
    oauth._store_tokens("gmail", "b@gmail.com", {"access_token": "OLD", "expires_in": 0})   # already expired
    # without refresh_token it cannot refresh → returns the old one (or None), never raises
    oauth._load()  # sanity
    tok = oauth.access_token("gmail", "b@gmail.com")
    assert tok in ("OLD", None)


def test_configured_false_without_client_id(store, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")
    assert oauth.configured("gmail") is False
    monkeypatch.setattr(oauth, "client_id", lambda pid: "X")
    assert oauth.configured("gmail") is True
    assert oauth.configured("yahoo") is False     # yahoo has no OAuth spec
