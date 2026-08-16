"""server/feedback_api.py — send a suggestion to the developers (V2-100, 2026-08-16).

Covers the branch that matters most: self-host (no CONTROL_PLANE_URL/ZAELAR_USER_ID) must go to the
ANONYMOUS control-plane route with only its stable install id, never to the MACHINE-authenticated one —
crossing that wire would either send a self-hoster's feedback nowhere (no credential to present) or,
worse, silently attach it to whatever ZAELAR_USER_ID happens to be set."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.feedback_api import router


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response=None, capture=None):
        self._response = response or _FakeResponse()
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        if self._capture is not None:
            self._capture.update(method="GET", url=url, params=params, headers=headers)
        return self._response

    async def post(self, url, json=None, headers=None):
        if self._capture is not None:
            self._capture.update(method="POST", url=url, json=json, headers=headers)
        return self._response


def test_self_host_submit_goes_to_the_anonymous_route_with_the_install_id(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)
    from observability import identity as _identity
    monkeypatch.setattr(_identity, "user_id", lambda: "inst-1234")

    captured = {}
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _FakeClient(_FakeResponse(200, {"id": "fb-1", "status": "received"}), captured),
    )
    r = _client().post("/api/feedback", json={"message": "the mic button is missing on Firefox"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert captured["url"].endswith("/feedback/anonymous")
    assert captured["json"]["install_id"] == "inst-1234"
    assert captured["json"]["message"] == "the mic button is missing on Firefox"
    assert "email" not in captured["json"]


def test_cloud_account_submit_goes_to_the_machine_route_with_the_service_token(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://zaelar-control-plane.example.workers.dev")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "wl-secret")

    captured = {}
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _FakeClient(_FakeResponse(200, {"id": "fb-2", "status": "received"}), captured),
    )
    r = _client().post("/api/feedback", json={"message": "slow to reply", "email": "op@example.com"})
    assert r.status_code == 200
    assert captured["url"] == "https://zaelar-control-plane.example.workers.dev/feedback"
    assert captured["headers"] == {"X-Service-Token": "wl-secret"}
    assert captured["json"]["message"] == "slow to reply"
    assert captured["json"]["email"] == "op@example.com"
    assert "install_id" not in captured["json"]  # the credential derives the account server-side


def test_empty_message_never_reaches_the_network(monkeypatch):
    async def _boom(*a, **kw):
        raise AssertionError("must not attempt a network call for an empty message")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    r = _client().post("/api/feedback", json={"message": "   "})
    assert r.status_code == 200
    assert r.json() == {"ok": False, "error": "empty_message"}


def test_send_failure_fails_open_with_a_clear_error_not_a_500(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _Boom())
    r = _client().post("/api/feedback", json={"message": "hello"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"] == "send_failed"


def test_session_evidence_is_omitted_when_not_opted_in(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)

    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(capture=captured))
    _client().post("/api/feedback", json={"message": "hi", "include_session_evidence": False})
    assert "session_evidence" not in captured["json"]


def test_session_evidence_opt_in_uses_the_current_session_only(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)
    from observability import flows as _flows
    from observability import identity as _identity

    monkeypatch.setattr(_identity, "session_info", lambda: {"session_id": "sess-1"})
    monkeypatch.setattr(_flows, "session", lambda sid: {"session_id": sid, "events": 3} if sid == "sess-1" else {})
    monkeypatch.setattr(_flows, "events", lambda session_id, limit: [{"id": 1, "kind": "flash"}] if session_id == "sess-1" else [])

    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(capture=captured))
    _client().post("/api/feedback", json={"message": "hi", "include_session_evidence": True})
    ev = captured["json"]["session_evidence"]
    assert ev["summary"]["session_id"] == "sess-1"
    assert ev["events"] == [{"id": 1, "kind": "flash"}]


def test_evidence_build_fails_open_to_no_evidence_rather_than_blocking_the_send(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)
    from observability import flows as _flows
    from observability import identity as _identity

    monkeypatch.setattr(_identity, "session_info", lambda: {"session_id": "sess-1"})

    def _boom(sid):
        raise RuntimeError("db locked")

    monkeypatch.setattr(_flows, "session", _boom)

    captured = {}
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient(capture=captured))
    r = _client().post("/api/feedback", json={"message": "hi", "include_session_evidence": True})
    assert r.status_code == 200
    assert "session_evidence" not in captured["json"]


def test_list_self_host_queries_the_anonymous_route_by_install_id(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)
    from observability import identity as _identity
    monkeypatch.setattr(_identity, "user_id", lambda: "inst-1234")

    captured = {}
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kw: _FakeClient(_FakeResponse(200, {"items": [{"id": "fb-1"}]}), captured),
    )
    r = _client().get("/api/feedback")
    assert r.status_code == 200
    assert r.json()["items"] == [{"id": "fb-1"}]
    assert captured["url"].endswith("/feedback/anonymous")
    assert captured["params"] == {"install_id": "inst-1234"}


def test_list_fails_open_to_an_empty_list_on_network_error(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)

    class _Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, *a, **kw):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _Boom())
    r = _client().get("/api/feedback")
    assert r.status_code == 200
    assert r.json() == {"ok": False, "items": []}
