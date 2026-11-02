"""The page player says when the browser keeps it silent, and offers the tap that fixes it (V2-812 T-01).

When the music plays in the page of the screen that asked (no device of the connected account sits with it), it
starts muted — the only autoplay every browser allows — and is unmuted a moment later. A phone browser may refuse
that unmute, or refuse to start at all, until a real tap. Before, the store said «playing», the card drew the song
and the agent said «it's playing» over a silent phone. Now the card REPORTS what its player does (`player_audio`,
from the IFrame API's own `infoDelivery`), the store holds `audio_blocked`, the card shows a tap row, the brain's
digest says it, and an agent order it contradicts is told (`late_report`).
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys

import pytest

from widgets.musica import data as md

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def store_tmp(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors.spotify import auth
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": True, "can_connect": True})
    import widgets.store as st
    st.save("musica", {"yt": {"videoId": "VID00000001", "title": "Dai Dai", "paused": False, "cmd_seq": 3,
                              "volume": 70}, "source": {"provider": "youtube", "screen": "mobile:aa11"}})


def test_a_silent_report_blocks_tells_once_and_a_heard_one_clears(store_tmp):
    r = md.apply_action("player_audio", {"muted": True, "videoId": "VID00000001"})
    assert r["audio_blocked"] and r.get("tell"), "the first silence carries the sentence the agent says"
    assert md._load_db()["yt"]["audio_blocked"] is True
    again = md.apply_action("player_audio", {"muted": True, "videoId": "VID00000001"})
    assert again["audio_blocked"] and not again.get("tell"), "a repeated report is not told twice"
    assert md.apply_action("player_audio", {"muted": True, "videoId": "OTHER000001"}).get("stale")
    assert md.apply_action("player_audio", {"muted": False, "videoId": "VID00000001"})["audio_blocked"] is False
    assert md._load_db()["yt"]["audio_blocked"] is False


def test_a_paused_song_is_not_a_blocked_one(store_tmp):
    db = md._load_db()
    db["yt"]["paused"] = True
    md._persist(db)
    assert md.apply_action("player_audio", {"muted": True})["audio_blocked"] is False


def test_the_page_player_is_what_the_card_shows_even_with_spotify_connected(store_tmp):
    live = md._live_fields(md._load_db())
    assert live["mode"] == "youtube" and live["now_playing"] is None, (
        "the song sounds in the page: a Spotify reading of a device elsewhere is not what he hears")


def test_the_digest_says_where_it_sounds_and_that_it_is_silent(store_tmp):
    md.apply_action("player_audio", {"muted": True, "videoId": "VID00000001"})
    d = md.prompt_digest()
    assert "Dai Dai" in d and "page player" in d and "phone" in d and "volume 70%" in d
    assert "BLOCKED" in d, "the brain must not say «it's playing» over a silent page"


def test_a_page_start_by_the_agent_is_an_order_its_silence_is_told_against(monkeypatch):
    """The voice road (`music_flow`) notes the start as an AGENT order on the card, so the card's silent report is
    said (`late_report.deliver`), not left for him to find. A start by his own hands is never noted here."""
    import asyncio

    from connectors.music.base import MusicResult
    from nucleo.flash import music_flow
    from widgets import late_report
    monkeypatch.setattr(late_report, "_last_agent_order", {})
    monkeypatch.setattr(music_flow, "_on_success", lambda res, q: None)
    monkeypatch.setattr("connectors.music.control", lambda *a, **k: MusicResult(
        ok=True, provider="youtube", action="play", extra={"surface": "widget", "widget": "musica"}))
    asyncio.run(music_flow.run("play", "shakira"))
    assert late_report.agent_ordered_recently("musica")


# ── the card, rendered ───────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def _page():
    pytest.importorskip("playwright.sync_api")
    from playwright.sync_api import sync_playwright
    from tests.waiting import port_listening
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page._hb_port = port
            yield page
            browser.close()
    finally:
        srv.terminate()


def _data(**yt):
    y = {"videoId": "VID00000001", "title": "Dai Dai", "artist": "Shakira", "paused": False, "cmd_seq": 1,
         "art": "", "volume": 70}
    y.update(yt)
    return {"connected": True, "mode": "youtube", "now_playing": None, "yt": y, "local": {}, "playlists": [],
            "recent": [], "counts": {}, "top": [], "fav_current": False, "fav": {"id": "", "name": "Favoritos"},
            "modes": {"shuffle": False, "repeat": "off", "supported": True}, "volume": {"level": 70, "muted": False},
            "queue": {"items": [], "editable": True, "source": "youtube"}, "browse": {},
            "view": {"kind": "home", "id": ""}}


def _mount(page, data):
    port = page._hb_port
    page.goto(f"http://127.0.0.1:{port}/widgets/musica/")
    page.set_content("<div style='width:420px;height:520px;display:flex;flex-direction:column'><div id='w'></div></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__ctx = {action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
                             running: true};
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [f"http://127.0.0.1:{port}/widgets/musica/widget.js", data])


def _player_says(page, info):
    page.evaluate("(info) => window.dispatchEvent(new MessageEvent('message', {data: JSON.stringify("
                  "{event: 'infoDelivery', id: 'hb-musica', info})}))", info)


def test_the_card_reports_a_silent_player_after_the_grace(_page):
    _mount(_page, _data())
    _player_says(_page, {"muted": True, "playerState": -1})
    assert not [c for c in _page.evaluate("() => window.__calls") if c[0] == "player_audio"], (
        "a player that has not had time to unmute is not yet a verdict")
    _page.wait_for_timeout(2700)
    _player_says(_page, {"muted": True, "playerState": -1})
    reports = [c[1] for c in _page.evaluate("() => window.__calls") if c[0] == "player_audio"]
    assert reports == [{"muted": True, "videoId": "VID00000001"}]


def test_a_blocked_player_shows_the_tap_and_a_heard_one_does_not(_page):
    _mount(_page, _data(audio_blocked=True))
    tap = _page.query_selector(".hb-mus2-tapsound")
    assert tap is not None and tap.is_visible(), "the card says the browser keeps it silent and offers the tap"
    tap.click()
    _mount(_page, _data())
    assert _page.query_selector(".hb-mus2-tapsound") is None


def test_a_player_that_never_says_a_word_is_reported_silent(_page):
    """2026-11-02: on a phone the embed sent no `infoDelivery` at all, so the report — which only ran on a frame —
    never fired, the tap row never appeared and the song stayed mute through six volume changes."""
    _page.route("**/*youtube*/**", lambda route: route.abort())
    try:
        _mount(_page, _data(videoId="VIDQUIET001"))
        _page.wait_for_timeout(5400)
        reports = [c[1] for c in _page.evaluate("() => window.__calls") if c[0] == "player_audio"]
        assert reports == [{"muted": True, "videoId": "VIDQUIET001"}], reports
    finally:
        _page.unroute("**/*youtube*/**")
