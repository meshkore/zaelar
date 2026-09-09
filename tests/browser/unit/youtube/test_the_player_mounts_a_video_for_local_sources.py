# V2-638 — the player mounts a plain <video> for a library file or a live torrent, and the YouTube embed for
# everything else. None of this is testable from source: which element exists, whether a second local file
# REBUILDS the player (both carry videoId ""), and whether the control funnel actually reaches a media element
# instead of postMessaging into a null iframe — all of it only exists once the widget has rendered.
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

_LOCAL_A = "/api/library/stream?path=video%2Fa.mp4"
_LOCAL_B = "/api/library/stream?path=video%2Fb.mp4"
_TORRENT = "/api/torrent/stream/HASH"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _data(**over):
    d = {"videoId": "", "source": "youtube", "src": "", "title": "", "channel": "", "published": "",
         "volume": 70, "muted": True, "captions": False, "paused": True, "last_cmd": "", "cmd_seq": 0,
         "loading": False, "loading_query": "", "list": [], "player_error": "", "pos": -1, "adding": "",
         "list_filter": "", "list_name": "", "blocked_channels": [], "platforms": [], "platforms_at": 0,
         "connect_focus": None, "suggested": [], "suggested_at": 0, "suggested_channels": 0,
         "suggesting": False, "search_results": [], "search_query": "", "searched_at": 0, "channels": [],
         "history": [], "prefs": {}, "prefs_notes": [], "lists": [], "quality": 0, "platforms_stale": False,
         "accounts_enabled": False, "download": {}, "connector_shelf": []}
    d.update(over)
    return d


def _local(src=_LOCAL_A, **over):
    return _data(source="local", src=src, title="a.mp4", channel="Biblioteca", **over)


@pytest.fixture(scope="module")
def _page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            # The media routes answer an empty 200: the element only has to EXIST and carry the src — no case
            # here asserts decoding, which would be testing Chromium rather than the widget.
            page.route("**/api/library/**", lambda r: r.fulfill(status=200, content_type="video/mp4", body=b""))
            page.route("**/api/torrent/**", lambda r: r.fulfill(status=200, content_type="video/mp4", body=b""))
            page.route("**://www.youtube.com/**",
                       lambda r: r.fulfill(status=200, content_type="text/html", body="<html></html>"))
            page._hb_url = f"http://127.0.0.1:{port}/widgets/youtube/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/youtube/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, running=True):
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:660px'></div>")
    page.evaluate(
        """async ([src, data, running]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod; window.__ctx = {
               action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok: true}); },
               top: () => {}, running: running };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data, running])


def _remount(page, data):
    page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", data)


def _video_src(page):
    return page.evaluate(
        "() => { const v = document.querySelector('.hb-yt-video'); return v ? v.getAttribute('src') : null; }")


# ── which element gets mounted ──────────────────────────────────────────────────────────────────────────────

def test_a_library_row_mounts_a_video_and_no_iframe(_page):
    _mount(_page, _local())
    assert _page.locator(".hb-yt-video").count() == 1
    assert _page.locator(".hb-yt-frame iframe").count() == 0
    assert _video_src(_page) == _LOCAL_A


def test_a_torrent_row_mounts_a_video_pointed_at_the_piece_aware_route(_page):
    _mount(_page, _data(source="torrent", src=_TORRENT, title="Descarga"))
    assert _page.locator(".hb-yt-video").count() == 1
    assert _video_src(_page) == _TORRENT


def test_a_youtube_row_still_mounts_the_embed_and_no_video(_page):
    _mount(_page, _data(videoId="abcdefghijk", title="Un vídeo"))
    assert _page.locator(".hb-yt-frame iframe").count() == 1
    assert _page.locator(".hb-yt-video").count() == 0


def test_with_a_local_row_the_card_reads_as_having_a_video(_page):
    """`hasvid` drove the player/home split off `videoId` alone, which every non-YouTube row leaves empty."""
    _mount(_page, _local())
    assert "hb-yt-hasvid" in _page.evaluate("() => document.querySelector('.hb-yt').className")


# ── the rebuild key: two local files both carry videoId "" ──────────────────────────────────────────────────

def test_switching_between_two_local_files_actually_swaps_the_player(_page):
    """The defect the rebuild key closes: keyed on videoId alone, both rows are "" — so the FIRST file would
    stay mounted forever and the second would silently never play."""
    _mount(_page, _local(_LOCAL_A))
    assert _video_src(_page) == _LOCAL_A
    _remount(_page, _local(_LOCAL_B))
    assert _video_src(_page) == _LOCAL_B


def test_going_from_a_local_file_to_a_youtube_video_swaps_the_element(_page):
    _mount(_page, _local())
    _remount(_page, _data(videoId="abcdefghijk", title="Un vídeo"))
    assert _page.locator(".hb-yt-video").count() == 0
    assert _page.locator(".hb-yt-frame iframe").count() == 1


# ── the control funnel reaches a media element ─────────────────────────────────────────────────────────────

def test_a_volume_command_reaches_the_video_element(_page):
    """`post` translates the IFrame API vocabulary into media-element operations. Without it every control
    silently postMessaged into a null iframe and nothing moved."""
    _mount(_page, _local(muted=False, volume=70))
    _remount(_page, _local(muted=False, volume=30, last_cmd="set_volume", cmd_seq=1))
    assert _page.evaluate("() => document.querySelector('.hb-yt-video').volume") == pytest.approx(0.30, abs=0.01)


def test_a_mute_command_reaches_the_video_element(_page):
    _mount(_page, _local(muted=False))
    _remount(_page, _local(muted=False, last_cmd="mute", cmd_seq=1))
    assert _page.evaluate("() => document.querySelector('.hb-yt-video').muted") is True


def test_finishing_a_local_video_advances_the_queue(_page):
    """The native `ended` event has to reach the same action the embed's own end handler calls."""
    _mount(_page, _local())
    _page.evaluate("() => document.querySelector('.hb-yt-video').dispatchEvent(new Event('ended'))")
    assert any(c[0] == "ended" for c in _page.evaluate("() => window.__calls"))


# ── the origin boundary ────────────────────────────────────────────────────────────────────────────────────

def test_a_src_from_a_foreign_origin_is_refused(_page):
    """A widget plays OUR routes or nothing (the V2-620 boundary). The row's src arrives from the server, so
    a poisoned one must not become an outbound request to somebody else's host."""
    _mount(_page, _data(source="local", src="https://evil.example/movie.mp4", title="x"))
    assert _page.locator(".hb-yt-video").count() == 1      # the element is there…
    assert not _video_src(_page)                            # …and was never pointed at the foreign origin
