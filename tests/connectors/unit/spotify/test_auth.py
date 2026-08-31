"""Spotify OAuth PKCE and token store tests (V2-041). No network: httpx is mocked, and STORE is in tmp."""
import base64
import hashlib
import json
import time

import pytest

from connectors.spotify import auth


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "STORE", tmp_path / "spotify.json")
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid_test")
    # config.credentials.get may read something else; force the env fallback while isolating the real store
    monkeypatch.setattr(auth, "client_id", lambda: "cid_test")
    yield


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._p = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._p


def test_pkce_challenge_matches_verifier():
    # PKCE math moved to connectors/oauth_pkce.py (V2-098, shared with the email connector) — auth._make_pkce
    # is the alias spotify/auth.py imports it under.
    v, challenge = auth._make_pkce()
    assert 43 <= len(v) <= 128
    expect = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    assert challenge == expect


def test_begin_login_returns_authorize_url_and_persists_pending():
    res = auth.begin_login()
    assert res["ok"] and res["url"].startswith("https://accounts.spotify.com/authorize?")
    assert "code_challenge_method=S256" in res["url"] and "client_id=cid_test" in res["url"]
    pending = json.loads(auth.STORE.read_text())["pending"]
    assert pending["verifier"] and pending["state"]


def test_complete_login_state_mismatch_rejected():
    auth.begin_login()
    assert auth.complete_login("code", "WRONG_STATE")["ok"] is False


def test_complete_login_exchanges_and_stores_tokens(monkeypatch):
    res = auth.begin_login()
    state = json.loads(auth.STORE.read_text())["pending"]["state"]
    monkeypatch.setattr(auth.httpx, "post",
                        lambda *a, **k: _Resp(200, {"access_token": "AT", "refresh_token": "RT",
                                                    "expires_in": 3600, "scope": auth._SCOPE}))
    assert auth.complete_login("thecode", state)["ok"]
    assert auth.logged_in()
    data = json.loads(auth.STORE.read_text())
    assert "pending" not in data and data["tokens"]["access_token"] == "AT"


def test_access_token_refreshes_when_expiring(monkeypatch):
    auth._save({"tokens": {"access_token": "OLD", "refresh_token": "RT",
                           "expires_at": int(time.time()) - 5}})       # already expired
    monkeypatch.setattr(auth.httpx, "post",
                        lambda *a, **k: _Resp(200, {"access_token": "NEW", "expires_in": 3600}))
    assert auth.access_token() == "NEW"
    # The refresh preserves the old refresh_token if the server does not send a new one
    assert json.loads(auth.STORE.read_text())["tokens"]["refresh_token"] == "RT"


def test_disconnect_wipes_tokens():
    auth._save({"tokens": {"access_token": "AT", "refresh_token": "RT", "expires_at": 9e9}})
    assert auth.logged_in()
    auth.disconnect()
    assert not auth.logged_in()


def test_status_never_leaks_token():
    auth._save({"tokens": {"access_token": "SECRET", "refresh_token": "RT", "expires_at": 9e9}})
    s = auth.status()
    assert s["logged_in"] is True and "SECRET" not in json.dumps(s)
