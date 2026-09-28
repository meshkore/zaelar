"""The canvas that counts is the one of the tab holding the voice session (demo pass 2026-09-28, M4).

Two tabs reported different canvases and the server took the last word: the operator's watching tab, which had no
chart, «closed» Markets 268 ms into «ok close that» — the verdict then no longer saw the chart and the agenda was
closed instead. While a live session holds the lock, another tab's report is ignored.
"""
import asyncio
import json
import time

import pytest


@pytest.fixture
def lock(monkeypatch):
    from server import livekit_api as lk
    monkeypatch.setitem(lk._active, "sid", "voice-tab")
    monkeypatch.setitem(lk._active, "ts", time.time())
    return lk


def _post(payload):
    from server import voice_api
    r = asyncio.run(voice_api.canvas_state(payload))
    return json.loads(r.body)


def test_another_tabs_canvas_is_not_the_operators_screen(lock):
    assert _post({"open": [], "sid": "watching-tab"}).get("ignored")


def test_the_voice_tabs_canvas_counts(lock):
    assert not _post({"open": ["markets"], "sid": "voice-tab"}).get("ignored")


def test_with_no_live_session_every_report_counts(monkeypatch):
    from server import livekit_api as lk
    monkeypatch.setitem(lk._active, "sid", None)
    assert not _post({"open": ["markets"], "sid": "any-tab"}).get("ignored")


def test_the_desktop_sends_its_session_id():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "frontend/app/widgets/desktop.js").read_text("utf-8")
    i = src.index('fetch("/api/canvas/state"')
    assert 'sessionStorage.getItem("zaelar_sid")' in src[i:i + 400]


def test_a_report_with_no_session_id_is_not_the_voice_screen_either(lock):
    """A tab loaded before this rule sends no sid: M4 of the next pass closed the agenda again through it."""
    assert _post({"open": []}).get("ignored")
