#
# V2-366 — the youtube playlist UI, verified by RENDERING (a source test would bless a disconnected handler:
# `cond ? a : b` leaves a canvas dead with no error — the V2-124 lesson — and `t()`-style truthy fallbacks lie).
# Faces: rows are TEXT (no thumbnail mosaic, operator's design), click drives play_item, ✕ removes without
# also playing, the ENDED message advances the queue ONLY when it comes from OUR player (cross-talk with
# musica's hidden player shares the same window), a stopped agent never advances (V2-092), and the filter
# is display-only.
#
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port

_LIST = [
    {"videoId": "AAAAAAAAAAA", "title": "Primer vídeo", "channel": "Canal Uno", "url": "https://youtu.be/AAAAAAAAAAA"},
    {"videoId": "BBBBBBBBBBB", "title": "Segundo vídeo", "channel": "Canal Dos", "url": "https://youtu.be/BBBBBBBBBBB"},
    {"videoId": "CCCCCCCCCCC", "title": "Tercer clip", "channel": "Otro", "url": "https://youtu.be/CCCCCCCCCCC"},
]


@pytest.fixture(scope="module")
def _page():
    # A REAL http origin: a module cannot be dynamically imported from `about:blank`/`file:` (the failure reads
    # as "Failed to fetch dynamically imported module", which looks like a broken widget). Same pattern as
    # tests/browser/e2e/results/render_process_tab.py.
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
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/youtube/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/youtube/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data: dict, running: bool = True):
    page.goto(page._hb_origin)
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data, running]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]); },
                              running: running };
             window.__data = data;
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data, running],
    )


def test_the_rows_render_as_text_with_the_playing_marker(_page):
    _mount(_page, {"videoId": "BBBBBBBBBBB", "title": "Segundo vídeo", "list": _LIST, "pos": 1})
    rows = _page.locator(".hb-yt-row")
    assert rows.count() == 3
    assert "Primer vídeo" in rows.nth(0).inner_text()
    assert "Canal Uno" in rows.nth(0).inner_text()
    assert _page.locator(".hb-yt-list img").count() == 0        # linear TEXT list, no thumbnails
    assert "▶" in rows.nth(1).inner_text()                       # the playing row is marked
    assert rows.nth(1).evaluate("e => e.classList.contains('playing')")


def test_click_plays_that_item_and_the_cross_removes_without_playing(_page):
    _mount(_page, {"videoId": "", "list": _LIST, "pos": -1})
    _page.locator(".hb-yt-row").nth(1).click()
    calls = _page.evaluate("window.__calls")
    assert calls == [["play_item", {"item": "2"}]]
    _page.evaluate("window.__calls = []")
    _page.locator(".hb-yt-row").nth(2).locator(".hb-yt-rowx").click()
    calls = _page.evaluate("window.__calls")
    assert calls == [["remove", {"item": "3"}]]                  # stopPropagation: no play_item alongside


def test_the_players_ended_message_advances_only_from_our_player(_page):
    _mount(_page, {"videoId": "AAAAAAAAAAA", "list": _LIST, "pos": 0})
    msg = json.dumps({"event": "onStateChange", "info": 0, "id": "hb-youtube"})
    _page.evaluate("m => window.postMessage(m, '*')", msg)
    _page.wait_for_timeout(50)
    assert ["ended", {}] in _page.evaluate("window.__calls")
    # musica's hidden player ending must NEVER advance OUR queue (both listen on the same window)
    _page.evaluate("window.__calls = []")
    other = json.dumps({"event": "onStateChange", "info": 0, "id": "hb-musica"})
    _page.evaluate("m => window.postMessage(m, '*')", other)
    _page.wait_for_timeout(50)
    # The property is that OUR queue does not advance — not that the page stays perfectly silent. Asserting
    # zero calls of ANY kind made this flaky under a full-suite run: the REAL YouTube embed emits its own
    # `player_error` (code 150) when the network is contended, which has nothing to do with whose `ended`
    # this is. Measured 2026-08-28: green in isolation three times, red inside the full suite.
    calls = _page.evaluate("window.__calls")
    assert not [c for c in calls if (c or [None])[0] in ("ended", "next", "play_item")], calls


def test_a_stopped_agent_never_advances_the_queue(_page):
    _mount(_page, {"videoId": "AAAAAAAAAAA", "list": _LIST, "pos": 0}, running=False)
    msg = json.dumps({"event": "onStateChange", "info": 0, "id": "hb-youtube"})
    _page.evaluate("m => window.postMessage(m, '*')", msg)
    _page.wait_for_timeout(50)
    assert _page.evaluate("window.__calls") == []                # V2-092: parar es parar


def test_the_filter_hides_rows_without_touching_the_list_and_the_chip_clears_it(_page):
    _mount(_page, {"videoId": "", "list": _LIST, "pos": -1, "list_filter": "canal"})
    assert _page.locator(".hb-yt-row").count() == 2              # «Tercer clip» (channel «Otro») filtered out
    chip = _page.locator(".hb-yt-chip")
    assert chip.count() == 1
    chip.click()
    assert ["filter_list", {"q": ""}] in _page.evaluate("window.__calls")


def test_pasting_a_link_adds_and_an_empty_list_says_so(_page):
    _mount(_page, {"videoId": "", "list": [], "pos": -1})
    assert "vacía" in _page.locator(".hb-yt-list").inner_text()
    inp = _page.locator(".hb-yt-addinp")
    inp.fill("https://youtu.be/DDDDDDDDDDD")
    inp.press("Enter")
    calls = _page.evaluate("window.__calls")
    assert ["add", {"url": "https://youtu.be/DDDDDDDDDDD"}] in calls
    assert _page.evaluate("document.querySelector('.hb-yt-addinp').value") == ""
