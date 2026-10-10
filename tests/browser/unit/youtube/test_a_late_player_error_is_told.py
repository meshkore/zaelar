"""A play the agent just started that the PLAYER then refuses is said to the operator (V2-781).

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-10): «Ponla ya y dime qué está sonando» →
`youtube:play` ok → «Voy con ella.», and 1.2 s later the embedded player reported `player_error` 150 for the first
video (swapped to the second) and 150 for the second (`blocked_notice: exhausted`). Nothing could play and the
conversation never heard it: the report arrives through the card's UI route, which only answers the browser.

  · the widget: only a TERMINAL notice (exhausted / explicit) carries a `tell`; a swap keeps something playing.
  · the seam (`widgets/late_report.py`): the `tell` is handed to `voice.proactive.notify` only when an AGENT order
    touched the card within the window — the operator's own click on a dead video is already in front of him.
  · the routes: `brain_action` notes the agent order, the UI route delivers.
"""
from __future__ import annotations

import asyncio
import io
import json
import urllib.request

import pytest

from widgets import late_report, server_api, store
from widgets.youtube import data as yt

_V1, _V2 = "dQw4w9WgXcQ", "9bZkp7q19f0"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(
        json.dumps({"title": "Vídeo", "author_name": "Canal"}).encode()))
    monkeypatch.setattr(late_report, "_last_agent_order", {})
    from widgets import hint_lang
    monkeypatch.setattr(hint_lang, "en", lambda: False)        # the measured session spoke Spanish


@pytest.fixture
def told(monkeypatch):
    said: list = []

    async def _notify(title, text, **kw):
        said.append(text)
        return True
    from voice import proactive
    monkeypatch.setattr(proactive, "notify", _notify)
    return said


def _the_measured_list():
    yt.apply_action("add", {"url": f"https://www.youtube.com/watch?v={_V1} y https://youtu.be/{_V2}"})
    yt.apply_action("play", {})
    assert yt.view_data()["videoId"] == _V1


def test_a_swap_is_not_told_and_the_exhausted_list_is():
    _the_measured_list()
    first = yt.apply_action("player_error", {"code": "150", "videoId": _V1})
    assert yt.view_data()["blocked_notice"]["kind"] == "swapped"
    assert not first.get("tell"), "a swap keeps something playing: nothing to correct"
    second = yt.apply_action("player_error", {"code": "150", "videoId": _V2})
    assert yt.view_data()["blocked_notice"]["kind"] == "exhausted"
    assert "no se puede reproducir aquí" in second.get("tell", ""), second


def test_a_pasted_link_that_cannot_play_is_told():
    yt.apply_action("load", {"videoId": _V1, "title": "El que pegó él"})
    r = yt.apply_action("player_error", {"code": "101", "videoId": _V1})
    assert "El que pegó él" in r.get("tell", "")


def test_an_english_session_hears_it_in_english(monkeypatch):
    from widgets import hint_lang
    monkeypatch.setattr(hint_lang, "en", lambda: True)
    _the_measured_list()
    yt.apply_action("player_error", {"code": "150", "videoId": _V1})
    assert "can't be played here" in yt.apply_action("player_error", {"code": "150", "videoId": _V2}).get("tell", "")


def test_a_non_fatal_error_carries_nothing():
    _the_measured_list()
    assert not yt.apply_action("player_error", {"code": "5", "videoId": _V1}).get("tell")


async def _ui(wid, action, payload):
    return json.loads((await server_api.widget_action(wid, {"action": action, "payload": payload})).body)


def test_the_ui_route_says_it_after_an_agent_play(told):
    async def run():
        _the_measured_list()
        late_report.note_agent_order("youtube")           # what `brain_action` does for the agent's `play`
        await _ui("youtube", "player_error", {"code": "150", "videoId": _V1})
        await _ui("youtube", "player_error", {"code": "150", "videoId": _V2})
        await asyncio.sleep(0)
    asyncio.run(run())
    assert len(told) == 1 and "no se puede reproducir aquí" in told[0], told


def test_his_own_click_on_a_dead_video_is_not_narrated(told):
    async def run():
        _the_measured_list()
        await _ui("youtube", "player_error", {"code": "150", "videoId": _V1})
        await _ui("youtube", "player_error", {"code": "150", "videoId": _V2})
        await asyncio.sleep(0)
    asyncio.run(run())
    assert told == []


def test_the_window_closes():
    late_report.note_agent_order("youtube", now=1000.0)
    assert late_report.agent_ordered_recently("youtube", now=1000.0 + late_report.WINDOW_S - 1)
    assert not late_report.agent_ordered_recently("youtube", now=1000.0 + late_report.WINDOW_S + 1)


def test_brain_action_notes_the_agent_order(monkeypatch):
    async def _dispatch(wid, action, payload):
        return {"ok": True}
    monkeypatch.setattr(server_api, "_dispatch", _dispatch)
    asyncio.run(server_api.brain_action("youtube", "play", {}))
    assert late_report.agent_ordered_recently("youtube")
