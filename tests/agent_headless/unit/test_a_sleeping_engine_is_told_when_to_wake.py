"""A deployment that stops idle engines learns when the next notice is due (V2-796, node 2.802).

The loop that fires notices runs inside the engine; a stopped process sleeps straight through next Tuesday's
reminder. `nucleo/wake.py` reports the NEXT due instant after every schedule change, debounced, and does nothing at
all where nobody is listening (self-host).
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import wake
from nucleo.pulse import scheduler


class _Client:
    posts: list = []

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None):
        _Client.posts.append((url, json, headers))
        return type("R", (), {"status_code": 200})()


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    wake._reset_for_tests()
    _Client.posts = []
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    yield
    wake._reset_for_tests()


def test_self_host_reports_nothing(monkeypatch):
    monkeypatch.delenv("ZAELAR_WAKE_URL", raising=False)
    monkeypatch.delenv("CONTROL_PLANE_URL", raising=False)
    assert asyncio.run(wake.flush(1000.0)) is False and not _Client.posts


def test_the_next_due_instant_is_reported_once(monkeypatch):
    monkeypatch.setenv("CONTROL_PLANE_URL", "https://cp.example")
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "tok")
    monkeypatch.setattr(scheduler, "next_due", lambda: 1_900_000_000.5)
    assert asyncio.run(wake.flush(1000.0)) is True
    assert _Client.posts == [("https://cp.example/wake", {"next_due": 1_900_000_000}, {"X-Service-Token": "tok"})]
    monkeypatch.setattr(scheduler, "next_due", lambda: None)
    wake.note_changed()
    assert asyncio.run(wake.flush(1005.0)) is False, "debounced inside the gap after a send"
    assert asyncio.run(wake.flush(1020.0)) is True and _Client.posts[-1][1] == {"next_due": None}
    wake.note_changed()
    assert asyncio.run(wake.flush(2000.0)) is False and len(_Client.posts) == 2, "same value: not sent again"


def test_a_schedule_change_marks_the_report_stale(monkeypatch):
    import time
    wake._state["dirty"] = False
    stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() + 7200))
    job = scheduler.create("Recuerda la ITV", stamp, name="aviso: ITV")
    try:
        assert wake._state["dirty"] is True
        assert scheduler.next_due() is not None
    finally:
        scheduler.cancel(str(job["id"]))
