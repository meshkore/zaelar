"""Two agents test at once, and the operator sees both. The ratchets for that.

The Observatory used to serve exactly ONE run: the CLI stopped the previous dashboard and started a
new one bound to the new run directory. With several agents working the same checkout — which is the
normal case in this repo, not the exotic one — the second agent's run silently erased the first
agent's from the screen, and nothing anywhere said so. That failure is invisible by construction: both
runs finish fine, both write their reports, and only the person watching loses.

So these fix the four things that would bring it back:

  1 · the server is bound to the RUNS ROOT and lists every run, live ones first;
  2 · a run id is a directory NAME and can never walk out of that root;
  3 · the CLI REUSES a healthy Observatory instead of killing it — and still refuses a port held by
      something that is not one;
  4 · there is no launch button and no launch endpoint: the agents drive the tests.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.platform import cli as climod
from tests.platform.server import STALE_AFTER_S, DashboardServer, Handler

ENGINE = Path(__file__).resolve().parents[3]


def _write_run(root: Path, run_id: str, *, status: str, actor: str = "", suite: str = "voice",
               age_s: float = 0.0, lines: list[dict] | None = None) -> Path:
    run_dir = root / run_id
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(json.dumps({
        "schema": 1, "run_id": run_id, "suite": suite, "status": status,
        "created_at": time.time() - age_s, "target": f"deterministic · {suite}",
        "launched_by": {"actor": actor, "user": "someone"},
    }), encoding="utf-8")
    events = run_dir / "events.jsonl"
    events.write_text("".join(json.dumps(line) + "\n" for line in (lines or [])), encoding="utf-8")
    if age_s:
        stamp = time.time() - age_s
        import os
        os.utime(events, (stamp, stamp))
    return run_dir


@pytest.fixture()
def observatory(tmp_path: Path):
    """A real server on an ephemeral port, serving a temporary runs root."""
    root = tmp_path / "runs"
    root.mkdir()
    server = DashboardServer(("127.0.0.1", 0), Handler, root, idle_timeout=30)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        yield server, root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=3) as response:
        return json.loads(response.read())


def test_two_agents_testing_at_once_are_both_listed_live_first(observatory) -> None:
    """The whole point. Before this, the second one replaced the first."""
    _, root, url = observatory
    _write_run(root, "20260916-100000-voice-aaaaaa", status="running", actor="codex", suite="voice")
    _write_run(root, "20260916-100500-browser-bbbbbb", status="running", actor="claude-code",
               suite="browser")
    _write_run(root, "20260916-090000-memory-cccccc", status="passed", actor="", suite="memory")

    rows = _get(f"{url}/api/runs")["runs"]
    live = [r for r in rows if r["status"] == "running" and not r["stale"]]
    assert {r["launched_by"]["actor"] for r in live} == {"codex", "claude-code"}
    assert {r["suite"] for r in live} == {"voice", "browser"}
    # Live ones first: the box in the rail reads top-down and the finished ones must not push them off.
    assert rows[0]["status"] == "running" and rows[1]["status"] == "running"


def test_a_run_that_died_without_saying_so_is_marked_stale_not_deleted(observatory) -> None:
    """A killed agent leaves `run.json` saying "running" forever. Treating that as live would keep a
    dead row blinking in the rail; hiding it would be the same disappearance this file exists to stop.
    So it stays listed, flagged, and out of the live set."""
    _, root, url = observatory
    _write_run(root, "20260916-100000-voice-aaaaaa", status="running", age_s=STALE_AFTER_S + 30)
    row = _get(f"{url}/api/runs")["runs"][0]
    assert row["status"] == "running" and row["stale"] is True


def test_the_multiplexed_stream_tags_every_line_with_the_run_it_came_from(observatory) -> None:
    """Without the tag, two agents' events land in one pile and each row overwrites the other's."""
    server, root, url = observatory
    _write_run(root, "20260916-100000-voice-aaaaaa", status="running",
               lines=[{"type": "test.started", "test_id": "a"}])
    _write_run(root, "20260916-100500-browser-bbbbbb", status="running",
               lines=[{"type": "test.started", "test_id": "b"}])

    seen: dict[str, set[str]] = {}
    with urllib.request.urlopen(f"{url}/events", timeout=8) as stream:
        deadline = time.time() + 6
        while time.time() < deadline and len(seen) < 2:
            raw = stream.readline()
            if not raw.startswith(b"data: "):
                continue
            event = json.loads(raw[6:])
            if event.get("type") == "test.started":
                seen.setdefault(event["run_id"], set()).add(event["test_id"])
    assert seen == {"20260916-100000-voice-aaaaaa": {"a"},
                    "20260916-100500-browser-bbbbbb": {"b"}}


def test_a_run_id_is_a_directory_name_and_cannot_walk_out_of_the_runs_root(observatory) -> None:
    """`?run=` comes from a URL. A traversal here would stream any file on the machine into a page
    that is served without authentication."""
    server, root, url = observatory
    _write_run(root, "20260916-100000-voice-aaaaaa", status="running")
    handler = Handler.__new__(Handler)
    handler.server = server
    for hostile in ("../../etc", "..", "/etc/passwd", "sub/dir"):
        handler.path = f"/events?run={hostile}"
        assert handler._followable(hostile) == {}, hostile
    assert set(handler._followable("20260916-100000-voice-aaaaaa")) == {"20260916-100000-voice-aaaaaa"}


def test_only_active_runs_are_followed_when_no_run_is_named(observatory) -> None:
    """600 finished runs live in this directory. Tailing all of them at 6 Hz is how a monitor becomes
    the reason the machine is slow — which is the very complaint that bans broad pytest sweeps here."""
    server, root, url = observatory
    _write_run(root, "20260916-100000-voice-aaaaaa", status="running")
    _write_run(root, "20260916-090000-memory-cccccc", status="passed")
    _write_run(root, "20260916-080000-browser-dddddd", status="failed")
    handler = Handler.__new__(Handler)
    handler.server = server
    assert set(handler._followable("")) == {"20260916-100000-voice-aaaaaa"}


def test_the_cli_reuses_a_healthy_observatory_instead_of_killing_it(observatory, monkeypatch) -> None:
    """The one-line behaviour change that makes concurrency possible at all.

    It used to POST /api/shutdown and wait for the port to free up. Two agents starting a minute apart
    meant the second one killed the first one's dashboard."""
    server, root, url = observatory
    port = server.server_address[1]
    assert climod._existing_dashboard(port) is True

    spawned: list = []
    monkeypatch.setattr(climod.subprocess, "Popen", lambda *a, **k: spawned.append(a) or None)
    monkeypatch.setattr(climod.webbrowser, "open", lambda *_: None)
    run_dir = root / "20260916-110000-voice-eeeeee"
    (run_dir / "artifacts").mkdir(parents=True)
    assert climod._dashboard(run_dir, port, open_browser=False) == f"http://127.0.0.1:{port}"
    assert not spawned, "arrancó un segundo servidor teniendo uno sano delante"


def test_a_port_held_by_something_else_is_a_refusal_never_a_kill() -> None:
    """8765 is a fixed local port and whatever else answers on it belongs to somebody."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    assert climod._existing_dashboard(free) is False   # nothing there at all: ours to start

    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Impostor(BaseHTTPRequestHandler):
        def log_message(self, *a): return
        def do_GET(self):
            body = b'{"hello":"not an observatory"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Impostor)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    try:
        with pytest.raises(RuntimeError, match="no es Test Observatory"):
            climod._existing_dashboard(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()


def test_nothing_launches_tests_from_the_browser(observatory) -> None:
    """Operator's call, 2026-09-16: «no necesitamos que haya un play en el frontend que testee nada
    […] siempre va a ser un agente el que los conduzca». Both halves are checked, because removing
    the button while leaving the endpoint would be a door with the handle painted over."""
    _, _, url = observatory
    request = urllib.request.Request(f"{url}/api/run", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.urlopen(request, timeout=3)
    assert caught.value.code == 404

    dashboard = (ENGINE / "tests/platform/dashboard/index.html").read_text(encoding="utf-8")
    # `"/api/run"` exactly — `/api/runs` (the listing the rail's agent box reads) is a different path
    # and a bare substring check would forbid it too.
    assert '"/api/run"' not in dashboard
    assert 'method: "POST"' not in dashboard, "el visor todavía escribe algo en el servidor"
    assert 'class="go"' not in dashboard, "el visor todavía pinta un botón de lanzar"


def test_the_dashboard_follows_the_agent_and_lets_go_when_touched() -> None:
    """The follow rules live in the page, and they are the operator's exact words. Asserted on the
    source because there is no other place they exist — a headless browser run belongs in
    `tests/browser/e2e`, and what would break here is the RULE being edited away, not the render.

    The rules: the screen follows the first live run; a second one never steals it; touching anything
    by hand stops the automatic following; clicking an agent pins it."""
    dashboard = (ENGINE / "tests/platform/dashboard/index.html").read_text(encoding="utf-8")
    assert "function maybeFollow" in dashboard
    # Busy with someone else → hands off. This single line IS the "no steal" rule.
    assert "if (current && isLive(current) && S.focus !== runId) return;" in dashboard
    assert "function takeOver" in dashboard and "S.autofollow = false" in dashboard
    assert "function watchRun" in dashboard and "S.pinned = id" in dashboard
    # Oldest first: on a fresh load with two agents already going, follow the one that started first.
    assert "(a[1].startedAt || 0) - (b[1].startedAt || 0)" in dashboard
