"""An incident stays auditable after the host that had it (V2-831 T-31, engine half).

Events lived only in the frozen host's database. With `ZAELAR_SUMMARY_URL` set, a thread pushes a compact summary —
turns, the voice's worst lag, the workers, free memory, the self watchdog's state — counts and numbers, never words.
Measured here against a real local HTTP listener: the POST lands with its token and its parts; without the URL
nothing starts; a target that refuses never raises.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from nucleo.pulse import offhost


@pytest.fixture
def listener():
    got: list = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length") or 0))
            got.append(({k.lower(): v for k, v in self.headers.items()}, json.loads(body)))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            return None
    srv = HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/summary", got
    srv.shutdown()


def test_the_summary_lands_off_the_host_with_its_parts(listener, monkeypatch):
    url, got = listener
    from voice import lag, observer
    monkeypatch.setitem(lag._state, "worst", 1.7)
    monkeypatch.setattr(observer, "_events", [{"i": 10_000_001, "kind": "trace", "label": "turno", "t_ms": 5,
                                               "text": "his private words"}])
    monkeypatch.setitem(offhost._state, "seen", 10_000_000)
    monkeypatch.setenv("ZAELAR_SUMMARY_TOKEN", "tok-test")
    assert offhost.push(url) is True
    headers, body = got[0]
    assert headers.get("authorization") == "Bearer tok-test"
    assert body["activity"]["turns"] == 1 and body["voice"]["worst_lag_s"] == 1.7
    assert {"workers", "host", "watchdog", "boot"} <= set(body) and "error" not in body["workers"]
    assert "his private words" not in json.dumps(body), "counts and numbers only, never his words"
    assert lag._state["worst"] == 0.0, "the worst lag is per summary"


def test_without_a_target_nothing_starts_and_a_refusal_never_raises(monkeypatch):
    monkeypatch.delenv("ZAELAR_SUMMARY_URL", raising=False)
    assert offhost.start() is False and offhost.push() is False
    assert offhost.push("http://127.0.0.1:9/summary") is False          # nothing listens there


def test_it_is_started_with_the_engine_and_declared():
    import importlib, inspect
    from server.boot import surfaces
    assert "offhost.start()" in inspect.getsource(surfaces)
    assert "nucleo.pulse.offhost" in inspect.getsource(importlib.import_module("server.lifespan"))
    from nucleo.pulse import self_watchdog
    from nucleo.workers import envelope
    assert envelope.policy().get("summary_push_s") == offhost.period_s() == 30
    assert self_watchdog.policy()["stuck_s"] == float(envelope.policy()["stuck_s"]), "the declared file is read"
