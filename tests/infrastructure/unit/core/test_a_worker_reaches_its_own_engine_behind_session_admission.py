"""A worker reaches its own engine on a process behind session admission (V2-789).

On a process that takes part in session routing, `server/ingress.py` refused every request without a session
cookie with 401. The engine's own workers call it back over loopback (`ZAELAR_BASE`): `agent_report` («report
error: HTTP Error 401: Unauthorized»), `nav_cli` («ERROR: HTTP Error 401»), `mem_cli`, `widget_cli`, the worker
bridge. They never hold a session — the session belongs to the browser — so the worker lost its reports and its
browser on every call. A loopback caller to one of the worker doors is now admitted; every door still verifies
the worker itself, and a loopback caller still gets no operator route nor a door from off the machine.

Disarm: make `ingress.is_own_worker_door` return False → red.
"""
from __future__ import annotations

import pytest

from nucleo.energy import routing as ar
from server import ingress, operator_gate

MINE = "d8d0793f04d5e8"

#: Every bridge a worker drives, with the path it posts to — one per CLI, so a new door that a worker uses and the
#: admission forgets shows up here.
_WORKER_CALLS = ["/api/agent/report", "/api/navegador/act", "/api/memory/recall", "/api/memory/remember",
                 "/api/worker/act", "/api/worker/say", "/api/search/find"]


def _decide(path, *, peer_loopback, cookie=False):
    return ingress.decide(path=path, has_cookie=cookie, resolver_configured=True, outcome=None, target=None,
                          mine=MINE, peer_loopback=peer_loopback)


@pytest.mark.parametrize("path", _WORKER_CALLS)
def test_a_loopback_worker_door_is_served_without_a_session(path):
    assert path.startswith(operator_gate.WORKER_DOORS)
    assert _decide(path, peer_loopback=True) == (ingress.SERVE, "own_worker_door")


@pytest.mark.parametrize("path", _WORKER_CALLS)
def test_the_same_door_from_off_the_machine_still_needs_a_session(path):
    assert _decide(path, peer_loopback=False) == (ingress.DENY, "no_session")


@pytest.mark.parametrize("path", ["/api/lists", "/widgets/agenda/action", "/api/memory/map", "/api/flash/say"])
def test_a_loopback_caller_gets_no_operator_route(path):
    assert _decide(path, peer_loopback=True) == (ingress.DENY, "no_session")


def test_the_middleware_admits_the_worker_and_refuses_the_rest(monkeypatch):
    """End to end through the real middleware, with a real loopback peer and a non-loopback one."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    async def _never(token, control_plane_url):          # the worker has no cookie: no lookup is made
        raise AssertionError("resolver called for a worker door")

    monkeypatch.setattr(ar, "is_account_routing_machine", lambda: True)
    monkeypatch.setattr(ar, "my_machine_id", lambda: MINE)
    monkeypatch.setattr(ar, "resolve_session_machine", _never)
    monkeypatch.setenv("CONTROL_PLANE_URL", "http://resolver.invalid")

    app = FastAPI()

    @app.post("/api/agent/report")
    def _report():
        return {"ok": True}

    @app.post("/api/lists")
    def _lists():
        return {"ok": True}

    ingress.install(app)
    local = TestClient(app, client=("127.0.0.1", 50123))
    remote = TestClient(app, client=("203.0.113.9", 50123))

    assert local.post("/api/agent/report", json={}).status_code == 200
    assert remote.post("/api/agent/report", json={}).status_code == 401
    assert local.post("/api/lists", json={}).status_code == 401
