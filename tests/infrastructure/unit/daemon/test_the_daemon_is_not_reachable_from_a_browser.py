"""The daemon's HTTP guards (V2-575 · P0) — why binding 127.0.0.1 is not the end of the reasoning.

Loopback keeps the daemon off the network, and that is usually where the thinking stops. It should not:
127.0.0.1 is reachable by every other process on the machine AND by any web page the user has open, because a
browser will happily `fetch('http://127.0.0.1:45817/files/read')` from any site in the world. A daemon that
serves the user's documents to whoever asks first would be a bigger hole than the one it exists to close.

Three guards, tested here, none of them trusted alone:
  1. a bearer token on everything but `/health`;
  2. any request carrying `Origin` or `Sec-Fetch-Site` is refused — a browser always sends those cross-origin,
     a server-side Python client never does, so this holds EVEN IF the token leaked into a page;
  3. no CORS headers are ever sent and `OPTIONS` is refused, so the preflight never succeeds.

Guard 2 is the one that makes the browser vector structurally impossible rather than merely unlikely, which is
why it is asserted together with a valid token: the test would pass without it if only guard 1 existed.
"""
import json
import threading
import urllib.error
import urllib.request

import pytest


@pytest.fixture()
def live(tmp_path, monkeypatch):
    """A real daemon on a real ephemeral port, serving a real temp folder. Not a mock: the guards live in the
    HTTP layer, and a fake handler would be a second implementation of the thing under test."""
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from daemon import config as dcfg, server as dsrv
    dcfg.reset_cache()

    docs = tmp_path / "Docs"
    docs.mkdir()
    (docs / "note.txt").write_text("hello", encoding="utf-8")
    dcfg.save({"roots": [str(docs)], "configured": True})

    srv = dsrv.build(port=0)                      # port 0: the OS picks a free one, so this never collides
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}", dcfg.token(), docs
    finally:
        srv.shutdown()
        srv.server_close()
        dcfg.reset_cache()


def _call(base, path, *, token=None, headers=None, body=None, method=None):
    """Returns (status, parsed-json). Errors come back as a status too — an HTTP guard's job is to answer, not
    to hang up, and a test that only ever sees exceptions cannot check what it said."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data is not None else "GET"))
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read().decode()), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}"), dict(e.headers)


# ── guard 1: the token ────────────────────────────────────────────────────────────────────────────────────

def test_a_request_without_the_token_is_refused(live):
    base, _token, _docs = live
    status, body, _ = _call(base, "/permissions")
    assert status == 401 and body["error"] == "unauthorized"


def test_a_request_with_the_wrong_token_is_refused(live):
    base, _token, _docs = live
    status, _body, _ = _call(base, "/permissions", token="0" * 64)
    assert status == 401


def test_a_request_with_the_right_token_works(live):
    """The other direction. Without this, a daemon that refuses everything would pass this whole file."""
    base, token, docs = live
    status, body, _ = _call(base, "/files/read", token=token, body={"path": str(docs / "note.txt")})
    assert status == 200 and body["text"] == "hello"


def test_health_is_the_only_route_that_needs_no_token(live):
    """It has to be reachable before the engine has read `daemon.json`, so the status icon can tell "not
    installed" from "installed but not paired". It therefore says nothing about the user."""
    base, _token, _docs = live
    status, body, _ = _call(base, "/health")
    assert status == 200 and body["daemon"] == "zaelar"
    for leak in ("roots", "token", "path", "folders"):
        assert leak not in body, f"/health leaks {leak!r} to an unauthenticated caller"


# ── guard 2: anything that smells like a browser is refused, token or not ─────────────────────────────────

@pytest.mark.parametrize("header", ["Origin", "Sec-Fetch-Site"])
def test_a_browser_request_is_refused_even_with_a_valid_token(live, header):
    """The guard that matters. A malicious page cannot read `daemon.json`, but a page in the user's own browser
    that somehow held the token would still be refused here — and this is the assertion that fails if somebody
    later "simplifies" the check down to the token alone."""
    base, token, docs = live
    status, body, _ = _call(base, "/files/read", token=token,
                            headers={header: "https://evil.example"},
                            body={"path": str(docs / "note.txt")})
    assert status == 401, f"a request carrying {header} was served"
    assert "text" not in body


def test_health_is_refused_to_a_browser_too(live):
    """Even the harmless route: a page must not be able to fingerprint that a Zaelar daemon is installed."""
    base, _token, _docs = live
    status, _body, _ = _call(base, "/health", headers={"Origin": "https://evil.example"})
    assert status == 401


# ── guard 3: no CORS, ever ────────────────────────────────────────────────────────────────────────────────

def test_no_response_ever_carries_a_cors_header(live):
    base, token, docs = live
    for path, body in (("/health", None), ("/permissions", None),
                       ("/files/list", {"path": str(docs)})):
        _status, _payload, headers = _call(base, path, token=token, body=body)
        lowered = {k.lower() for k in headers}
        assert not any(h.startswith("access-control-") for h in lowered), f"{path} sent a CORS header"


def test_the_preflight_is_refused(live):
    base, _token, _docs = live
    status, body, headers = _call(base, "/files/read", method="OPTIONS")
    assert status == 405 and body["error"] == "no_cors"
    assert not any(k.lower().startswith("access-control-") for k in headers)


# ── refusals are answers, not failures ────────────────────────────────────────────────────────────────────

def test_a_path_outside_the_allowlist_returns_403_naming_the_boundary(live, tmp_path):
    """403 with the reason and the allowlist attached, so the engine can tell the user something true instead of
    inventing an explanation for a bare status code (V2-421/V2-507)."""
    base, token, docs = live
    outside = tmp_path / "Elsewhere"
    outside.mkdir()
    (outside / "secret.txt").write_text("no", encoding="utf-8")
    status, body, _ = _call(base, "/files/read", token=token, body={"path": str(outside / "secret.txt")})
    assert status == 403
    assert body["error"] == "outside_allowlist"
    assert body["folders"] == [str(docs)]
    assert str(docs) in body["message"]


def test_an_unknown_route_is_a_404_not_a_hang(live):
    base, token, _docs = live
    status, body, _ = _call(base, "/files/delete", token=token, body={"path": "/tmp/x"})
    assert status == 404 and body["error"] == "unknown_route"


# ── the audit log records both halves ─────────────────────────────────────────────────────────────────────

def test_both_the_allowed_read_and_the_refused_one_land_in_the_audit_log(live, tmp_path):
    """Refusals are the half that earns the file: a run of `outside_allowlist` against the same folder is the
    signal that something is probing the boundary, and it is invisible if only successes are kept."""
    from daemon import audit
    base, token, docs = live
    outside = tmp_path / "Elsewhere"
    outside.mkdir()

    _call(base, "/files/read", token=token, body={"path": str(docs / "note.txt")})
    _call(base, "/files/read", token=token, body={"path": str(outside / "nope.txt")})

    entries = audit.tail(20)
    outcomes = {(e["op"], e["outcome"]) for e in entries}
    assert ("files.read", "ok") in outcomes
    assert ("files.read", "refused") in outcomes
    refused = next(e for e in entries if e["outcome"] == "refused")
    assert refused["reason"] == "outside_allowlist"
    assert refused["caller"] == "local"


def test_the_audit_log_distinguishes_a_cloud_caller_from_the_local_engine(live, tmp_path):
    """The distinction the user cares about most, since only one of those is on their machine. The relay is P3;
    the marker is honoured now so the audit trail is not retrofitted after the fact."""
    from daemon import audit
    base, token, docs = live
    _call(base, "/files/list", token=token, headers={"X-Zaelar-Relay": "1"}, body={"path": str(docs)})
    assert any(e["caller"] == "relay" for e in audit.tail(20))


# ── the daemon does not advertise itself ──────────────────────────────────────────────────────────────────

def test_the_server_header_does_not_leak_the_python_version(live):
    base, _token, _docs = live
    _status, _body, headers = _call(base, "/health")
    server = headers.get("Server", "")
    assert server.startswith("zaelar-daemon/")
    assert "Python" not in server


def test_health_advertises_only_the_capabilities_that_exist(live):
    """A capability the engine believes in is a promise to the user. The browser hand-off is P2 and must not
    appear here until it is really there, or the agent will offer to open a window it cannot open."""
    base, _token, _docs = live
    _status, body, _ = _call(base, "/health")
    assert body["capabilities"] == ["files.list", "files.read", "files.search"]
