"""The video-account connector (V2-597): one normalized shape, and every failure speaks.

The reasoning around the HTTP, never the HTTP itself: the provider registry is DATA, the OAuth pending state
carries everything the callback needs, a refresh that returns no refresh_token keeps the previous one (or the
second refresh of the day silently disconnects the operator — V2-557's measured trap), and the facade tells a
legitimate emptiness (`ok` + `reason`) apart from a failure (`ok: False` + words).
"""
import json
import time

import httpx
import pytest

from connectors.video import oauth, providers, service
from connectors.video import youtube as ytc


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "STORE", tmp_path / "video_oauth.json")


# ── the registry is data ──────────────────────────────────────────────────────────────────────────────────
def test_youtube_is_registered_read_only_and_asks_google_for_offline_access():
    p = providers.get("youtube")
    assert p is not None
    assert [t.id for t in p.tiers] == ["readonly"]          # the write tier is parked (V2-596 T2), not offered
    assert "youtube.readonly" in p.tier().scopes[0]
    # Without these Google returns NO refresh_token and the connection dies within the hour.
    assert p.extra_auth_params.get("access_type") == "offline"
    assert p.extra_auth_params.get("prompt") == "consent"


def test_the_public_list_is_redacted():
    txt = json.dumps(providers.public_list()).lower()
    for secret_shaped in ("token_url", "api_base", "client"):
        assert secret_shaped not in txt


# ── oauth ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_authorize_url_refuses_without_a_client_id_naming_what_is_missing(sandbox, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")
    r = oauth.authorize_url("youtube")
    assert r["ok"] is False and "client_id" in r["error"]


def test_authorize_url_stashes_verifier_and_tier_under_the_state(sandbox, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "cid-123")
    r = oauth.authorize_url("youtube")
    assert r["ok"] and "code_challenge=" in r["url"] and "access_type=offline" in r["url"]
    pend = oauth._load()["pending"]
    assert len(pend) == 1
    entry = next(iter(pend.values()))
    assert entry["provider"] == "youtube" and entry["tier"] == "readonly" and entry["verifier"]


def test_exchange_code_pops_the_pending_state_and_stores_tokens(sandbox, monkeypatch):
    monkeypatch.setattr(oauth, "client_id", lambda pid: "cid-123")
    monkeypatch.setattr(oauth, "client_secret", lambda pid: "")
    r = oauth.authorize_url("youtube")
    state = next(iter(oauth._load()["pending"].keys()))

    class _Resp:
        status_code = 200
        def json(self):
            return {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}
    monkeypatch.setattr(httpx, "post", lambda url, data=None, timeout=30: _Resp())
    out = oauth.exchange_code("code-1", state)
    assert out["ok"] and out["tier"] == "readonly"
    acct = oauth.account("youtube")
    assert acct["refresh_token"] == "rt-1" and acct["tier"] == "readonly"
    assert oauth._load().get("pending") == {}               # consumed — a state never exchanges twice
    assert oauth.exchange_code("code-1", state)["ok"] is False


def test_a_refresh_without_a_refresh_token_keeps_the_previous_one(sandbox):
    oauth._store_tokens("youtube", "readonly", {"access_token": "at-1", "refresh_token": "rt-1"})
    oauth._store_tokens("youtube", "readonly", {"access_token": "at-2"})   # refresh answers often omit it
    assert oauth.account("youtube")["refresh_token"] == "rt-1"
    assert oauth.account("youtube")["access_token"] == "at-2"


def test_a_fresh_access_token_is_served_without_any_network(sandbox, monkeypatch):
    oauth._store_tokens("youtube", "readonly", {"access_token": "at-1", "refresh_token": "rt-1",
                                                "expires_in": 3600})
    def _boom(*a, **k):
        raise AssertionError("no network for a fresh token")
    monkeypatch.setattr(httpx, "post", _boom)
    assert oauth.access_token("youtube") == "at-1"


# ── the client's parsing and its error words ──────────────────────────────────────────────────────────────
class _R:
    def __init__(self, code, body):
        self.status_code = code
        self._body = body
    def json(self):
        return self._body


def test_error_words_distinguish_dead_session_quota_and_disabled_api():
    assert "reconecta" in ytc._err_of(_R(401, {}))
    assert "cuota" in ytc._err_of(_R(403, {"error": {"message": "Quota exceeded", "errors": [{"reason": "quotaExceeded"}]}}))
    assert "no está habilitada" in ytc._err_of(_R(403, {"error": {"message": "API has been disabled", "errors": [{}]}}))


class _FakeClient:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.pages.pop(0)


def test_subscriptions_parse_to_channel_rows_and_follow_pagination():
    c = _FakeClient([
        _R(200, {"items": [{"snippet": {"title": "Canal Uno", "resourceId": {"channelId": "UCaaa"}}}],
                 "nextPageToken": "p2"}),
        _R(200, {"items": [{"snippet": {"title": "Canal Dos", "resourceId": {"channelId": "UCbbb"}}}]}),
    ])
    r = ytc.list_subscriptions(c, "https://api", "tok", max_n=50)
    assert r["ok"] and r["channels"] == [{"channel_id": "UCaaa", "channel": "Canal Uno"},
                                         {"channel_id": "UCbbb", "channel": "Canal Dos"}]
    assert c.calls[1][1]["pageToken"] == "p2"


def test_uploads_derive_the_UU_playlist_and_skip_untitled_hits():
    c = _FakeClient([
        _R(200, {"items": [
            {"contentDetails": {"videoId": "AAAAAAAAAA1"},
             "snippet": {"title": "Bueno", "publishedAt": "2026-09-01T10:00:00Z"}},
            {"contentDetails": {"videoId": "BBBBBBBBBB2"}, "snippet": {"title": ""}},   # unnamed → not a candidate
        ]}),
    ])
    rows = ytc.channel_recent_uploads(c, "https://api", "tok", "UCaaa", "Canal Uno", n=3)
    assert [r["videoId"] for r in rows] == ["AAAAAAAAAA1"]
    assert rows[0]["channel"] == "Canal Uno" and rows[0]["url"].endswith("AAAAAAAAAA1")
    assert c.calls[0][1]["playlistId"] == "UUaaa"           # derived, never fetched
    # A non-UC id has no derivable uploads playlist: answer nothing rather than guess.
    assert ytc.channel_recent_uploads(c, "https://api", "tok", "HCxxx", "X", n=3) == []


# ── the facade ────────────────────────────────────────────────────────────────────────────────────────────
def test_the_facade_names_the_missing_piece_at_each_rung(sandbox, monkeypatch):
    assert "desconocido" in service.suggestions("vimeo")["error"]
    monkeypatch.setattr(oauth, "client_id", lambda pid: "")
    assert "Configuración" in service.suggestions("youtube")["error"]
    monkeypatch.setattr(oauth, "client_id", lambda pid: "cid")
    assert "no está conectado" in service.suggestions("youtube")["error"]


def test_suggestions_normalize_sort_and_tell_a_legitimate_emptiness_apart(sandbox, monkeypatch):
    monkeypatch.setattr(service, "_prepared",
                        lambda pid: (providers.get("youtube"), "tok", None))
    monkeypatch.setattr(service._yt, "list_subscriptions",
                        lambda client, base, tok, max_n=50: {"ok": True, "channels": [
                            {"channel_id": "UCaaa", "channel": "Uno"},
                            {"channel_id": "UCbbb", "channel": "Dos"}]})
    monkeypatch.setattr(service._yt, "channel_recent_uploads",
                        lambda client, base, tok, cid, title, n=2: [
                            {"videoId": "A" * 11, "title": "Viejo", "channel": title,
                             "published": "2026-08-01T00:00:00Z", "url": "u"}] if cid == "UCaaa" else [
                            {"videoId": "B" * 11, "title": "Nuevo", "channel": title,
                             "published": "2026-09-01T00:00:00Z", "url": "u"}])
    r = service.suggestions("youtube")
    assert r["ok"] and [it["title"] for it in r["items"]] == ["Nuevo", "Viejo"]   # newest first
    assert r["channels"] == 2 and r["fetched_at"] > 0
    for key in ("videoId", "title", "channel", "published", "url"):
        assert key in r["items"][0], key
    # zero subscriptions is ok + reason, never an error (the drive-looks-empty confound, V2-557 T1)
    monkeypatch.setattr(service._yt, "list_subscriptions",
                        lambda client, base, tok, max_n=50: {"ok": True, "channels": []})
    r2 = service.suggestions("youtube")
    assert r2["ok"] is True and r2["items"] == [] and "suscripciones" in r2["reason"]


def test_an_upstream_failure_travels_as_words(sandbox, monkeypatch):
    monkeypatch.setattr(service, "_prepared",
                        lambda pid: (providers.get("youtube"), "tok", None))
    monkeypatch.setattr(service._yt, "list_subscriptions",
                        lambda client, base, tok, max_n=50: {"ok": False,
                                                             "error": "cuota diaria de la API de YouTube agotada"})
    r = service.suggestions("youtube")
    assert r["ok"] is False and "cuota" in r["error"]
