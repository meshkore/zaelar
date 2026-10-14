"""A worker's curl is refused on a real socket; his side of the machine is admitted (2026-10-14).

The decision is pure (node 2.620) and the process attribution is measured (2.621); this is the two wired together
over TCP, the way the incident happened. A small app carries the real `operator_gate` (+ `api_guard`) and the
real `POST /widgets/{id}/action` shape, served by uvicorn in its own process — that process is «the engine»:

  · this test process is NOT its descendant (it is its parent): a POST from here is his terminal / the harness —
    admitted, and the response mints the UI cookie; the cookie then admits on the fast path;
  · a client the engine spawns in a session of its own (how every worker backend starts) is refused;
  · a client orphaned out of such a session (`( curl … & )`) is refused;
  · a page of another site posting the same route is refused by `api_guard` before anything else.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(not hasattr(os, "getsid"), reason="POSIX sessions")

_CLIENT = textwrap.dedent("""
    import sys, time, urllib.request, urllib.error
    port, out, delay = sys.argv[1], sys.argv[2], float(sys.argv[3])
    time.sleep(delay)
    req = urllib.request.Request(f"http://127.0.0.1:{port}/widgets/contactos/action", method="POST",
                                 data=b'{"action": "add_contact", "payload": {}}',
                                 headers={"Content-Type": "application/json"})
    try:
        code = urllib.request.urlopen(req, timeout=10).status
    except urllib.error.HTTPError as e:
        code = e.code
    open(out, "w").write(str(code))
""")

_SERVER = textwrap.dedent("""
    import os, subprocess, sys, time
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse
    from server import api_guard, operator_gate
    from nucleo.workers import spawned

    port, client = int(sys.argv[1]), sys.argv[2]
    app = FastAPI()
    operator_gate.install(app)
    api_guard.install(app)

    @app.get("/")
    async def shell():
        return PlainTextResponse("shell")

    @app.post("/widgets/{wid}/action")
    async def action(wid: str, payload: dict):
        return {"ok": True, "wid": wid}

    @app.get("/spawn")
    def spawn(mode: str, out: str):
        py = sys.executable
        if mode == "worker":
            p = subprocess.Popen([py, client, str(port), out, "0"], start_new_session=True)
            spawned.remember(p.pid)
        else:   # an orphan: the session leader backgrounds the client in a subshell and exits at once
            cmd = f'( "{py}" "{client}" {port} "{out}" 0.5 & )'
            p = subprocess.Popen(["/bin/sh", "-c", cmd], start_new_session=True)
            spawned.remember(p.pid)
            p.wait()
        for _ in range(400):
            if os.path.exists(out) and open(out).read().strip():
                return PlainTextResponse(open(out).read().strip())
            time.sleep(0.025)
        return PlainTextResponse("timeout")

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
""")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    d = tmp_path_factory.mktemp("gate")
    (d / "client.py").write_text(_CLIENT)
    (d / "gate_engine.py").write_text(_SERVER)
    port = _free_port()
    env = {**os.environ, "PYTHONPATH": str(ENGINE) + os.pathsep + os.environ.get("PYTHONPATH", ""),
           "ZAELAR_ENGINE": "off"}
    proc = subprocess.Popen([sys.executable, str(d / "gate_engine.py"), str(port), str(d / "client.py")],
                            cwd=str(ENGINE), env=env)
    base = f"http://127.0.0.1:{port}"
    up = False
    for _ in range(300):
        if proc.poll() is not None:
            break
        try:
            urllib.request.urlopen(base + "/healthz-none", timeout=1)
        except urllib.error.HTTPError:
            up = True
            break
        except OSError:
            time.sleep(0.1)
    if not up:
        proc.kill()
        pytest.fail("the gate's test server never came up")
    yield base, d
    proc.kill()
    proc.wait()


def _post(base, path, headers=None):
    req = urllib.request.Request(base + path, method="POST", data=json.dumps({"action": "x"}).encode(),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, r.headers.get_all("set-cookie") or []
    except urllib.error.HTTPError as e:
        return e.code, []


def test_his_side_of_the_machine_is_admitted_and_minted(engine):
    base, _ = engine
    code, cookies = _post(base, "/widgets/contactos/action")
    assert code == 200
    ui = [c for c in cookies if c.startswith("zaelar_ui=")]
    assert ui and "httponly" in ui[0].lower() and "samesite=strict" in ui[0].lower()
    value = ui[0].split(";", 1)[0]
    assert _post(base, "/widgets/contactos/action", {"Cookie": value}) == (200, []), "fast path, no re-mint"


def test_the_shell_mints_his_cookie(engine):
    base, _ = engine
    r = urllib.request.urlopen(base + "/", timeout=10)
    assert any(c.startswith("zaelar_ui=") for c in (r.headers.get_all("set-cookie") or []))


def test_a_worker_spawned_by_the_engine_is_refused(engine):
    base, d = engine
    out = d / "worker.out"
    assert urllib.request.urlopen(f"{base}/spawn?mode=worker&out={out}", timeout=20).read() == b"403"


def test_an_orphan_out_of_a_worker_session_is_refused(engine):
    base, d = engine
    out = d / "orphan.out"
    assert urllib.request.urlopen(f"{base}/spawn?mode=orphan&out={out}", timeout=20).read() == b"403"


def test_a_page_of_another_site_is_refused_before_anything_else(engine):
    base, _ = engine
    code, _ = _post(base, "/widgets/contactos/action",
                    {"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert code == 403
