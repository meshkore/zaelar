"""Tests del núcleo OAuth de email (V2-055) — piezas VERIFICABLES sin red: PKCE, authorize URL, token store,
selección de token vigente (el intercambio/refresh en red es dormante y no se ejercita aquí)."""
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
    assert v1 == v2 and c1 == c2            # mismo seed → mismo par
    assert "=" not in v1 and "=" not in c1  # base64url sin padding
    assert v1 != c1                          # el challenge es el SHA256 del verifier, no el verifier


def test_authorize_url_requires_registered_app(store, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")   # sin app registrada
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
    # el state quedó stasheado con su verifier (para el callback)
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
    # token vigente → access_token lo devuelve SIN red
    assert oauth.access_token("gmail", "yo@gmail.com") == "AT"
    oauth.forget("gmail", "yo@gmail.com")
    assert not oauth.tokens_present("gmail", "yo@gmail.com")
    assert oauth.access_token("gmail", "yo@gmail.com") is None


def test_refresh_token_preserved_across_updates(store):
    oauth._store_tokens("gmail", "a@gmail.com", {"access_token": "AT1", "refresh_token": "RT", "expires_in": 3600})
    # un refresh que NO devuelve refresh_token no debe borrar el que ya teníamos
    oauth._store_tokens("gmail", "a@gmail.com", {"access_token": "AT2", "expires_in": 3600})
    acct = oauth._load()["accounts"][oauth._acct_key("gmail", "a@gmail.com")]
    assert acct["refresh_token"] == "RT" and acct["access_token"] == "AT2"


def test_expired_without_refresh_returns_stale_not_crash(store):
    oauth._store_tokens("gmail", "b@gmail.com", {"access_token": "OLD", "expires_in": 0})   # ya caducado
    # sin refresh_token no puede refrescar → devuelve el viejo (o None), nunca lanza
    oauth._load()  # sanity
    tok = oauth.access_token("gmail", "b@gmail.com")
    assert tok in ("OLD", None)


def test_configured_false_without_client_id(store, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")
    assert oauth.configured("gmail") is False
    monkeypatch.setattr(oauth, "client_id", lambda pid: "X")
    assert oauth.configured("gmail") is True
    assert oauth.configured("yahoo") is False     # yahoo no tiene OAuth spec
