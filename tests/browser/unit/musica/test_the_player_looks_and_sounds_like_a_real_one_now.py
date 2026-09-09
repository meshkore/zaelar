#
# V2-629 — the music widget gets real cover art, "our line" SVG icons, and a fast-first enrichment path. The
# operator's ask: a nicer design that respects margins, icons matching our own visual language, real
# album/song artwork brought in — but music has to SOUND fast, the enrichment can arrive after. None of this
# is testable by reading the source: icon choice, the favorited-heart state, the lazy enrichment call and the
# dead-art fallback all run client-side inside a closure `render()` never exports, so every case here RENDERS
# the real widget.js (same harness as its neighbour, test_the_playlist_reads_like_spotify_now.py).
#
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


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _track(title, artist="", art="", query="", **extra):
    t = {"title": title, "artist": artist, "album": "", "art": art, "query": query or title, "uri": "",
         "videoId": ""}
    t.update(extra)
    return t


def _data(playlists=None, now_playing=None, yt=None, top=None, recent=None, view=None, fav_current=False):
    return {
        "connected": bool(now_playing), "can_connect": False, "own_client_id_set": False,
        "default_available": False, "redirect_uri": "", "now_playing": now_playing, "mode": "idle",
        "yt": yt or {}, "playlists": playlists or [], "recent": recent or [], "counts": {}, "top": top or [],
        "fav_current": fav_current, "view": view or {"kind": "home", "id": ""},
    }


class _Server:
    def __init__(self):
        self.port = _free_port()
        self.proc = subprocess.Popen([sys.executable, "-m", "http.server", str(self.port), "--bind", "127.0.0.1"],
                                      cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", self.port), 0.2).close()
                return
            except OSError:
                time.sleep(0.1)

    def stop(self):
        self.proc.terminate()


@pytest.fixture()
def mounted():
    """Yields (page, mount) — mount() re-renders with fresh data; the test reads the DOM off `page` after."""
    srv = _Server()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        # Any request to a real image host (the YouTube thumbnail CDN, iTunes artwork) is answered with a
        # tiny inline GIF instead of hitting the real network — deterministic, offline-safe, and fast.
        page.route("**://i.ytimg.com/**", lambda r: r.fulfill(
            status=200, content_type="image/gif",
            body=bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002020401003b")))
        page.route("**://dead.invalid/**", lambda r: r.abort())
        page.goto(f"http://127.0.0.1:{srv.port}/widgets/musica/")
        page.set_content("<div id='w'></div>")
        page.evaluate(
            "async (src) => { window.__mod = await import(src); window.__calls = []; }",
            f"http://127.0.0.1:{srv.port}/widgets/musica/widget.js",
        )

        def mount(data):
            page.evaluate(
                "(data) => window.__mod.render(document.getElementById('w'), data, "
                "{action: (n, p) => { window.__calls.push([n, p || {}]); return Promise.resolve({ok:true}); }, "
                " running: true})",
                data,
            )

        yield page, mount
        browser.close()
    srv.stop()


def _calls(page):
    return page.evaluate("() => window.__calls")


# --- icons: no emoji glyph left anywhere the redesign touched ---

def test_every_control_is_an_inline_svg_never_an_emoji_glyph(mounted):
    page, mount = mounted
    mount(_data(yt={"videoId": "abc", "title": "Song", "artist": "Artist", "paused": False, "cmd_seq": 1,
                     "art": "https://i.ytimg.com/vi/abc/hqdefault.jpg"}))
    bar_text = page.inner_text(".hb-mus2-barc")
    for glyph in ("⏮", "⏸", "▶", "⏭", "🔉", "🔊", "♥"):
        assert glyph not in bar_text, f"emoji glyph {glyph!r} survived the redesign"
    assert page.eval_on_selector_all(".hb-mus2-barc button", "els => els.length") == 5 + 1  # 5 controls + heart
    assert page.eval_on_selector_all(".hb-mus2-barc button svg", "els => els.length") == 6


def test_a_missing_cover_shows_the_note_icon_not_a_fallback_emoji(mounted):
    page, mount = mounted
    mount(_data(recent=[_track("No Art Yet", artist="Nobody")]))
    row_art = page.query_selector(".hb-mus2-tr .hb-mus2-art")
    assert row_art.query_selector("svg") is not None
    assert (row_art.text_content() or "").strip() == ""  # no emoji text node either


# --- real cover art: the YouTube thumbnail arrives for free, and it is USED ---

def test_the_bar_shows_the_yt_connectors_free_thumbnail_and_split_artist(mounted):
    page, mount = mounted
    mount(_data(yt={"videoId": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up", "artist": "Rick Astley",
                     "paused": False, "cmd_seq": 1, "art": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"}))
    assert page.inner_text(".hb-mus2-bart") == "Never Gonna Give You Up"
    assert page.inner_text(".hb-mus2-bara") == "Rick Astley"
    img = page.query_selector(".hb-mus2-bar .hb-mus2-art img")
    assert img is not None
    assert "i.ytimg.com" in img.get_attribute("src")


def test_a_dead_cover_url_falls_back_to_the_note_icon_not_a_broken_image(mounted):
    page, mount = mounted
    mount(_data(recent=[_track("Ghost Track", artist="Nobody", art="https://dead.invalid/nope.jpg")]))
    page.wait_for_timeout(300)
    row_art = page.query_selector(".hb-mus2-tr .hb-mus2-art")
    assert row_art.query_selector("img") is None, "a dead image must not stay in the DOM as a broken glyph"
    assert row_art.query_selector("svg") is not None


# --- the favorited heart is a STATE indicator, not only a button ---

def test_the_heart_is_filled_when_the_current_track_is_already_a_favorite(mounted):
    page, mount = mounted
    mount(_data(yt={"videoId": "x", "title": "Song", "paused": False, "cmd_seq": 1}, fav_current=True))
    heart = page.query_selector(".hb-mus2-barc .fav")
    assert heart is not None
    assert "fill" in (heart.query_selector("svg").get_attribute("stroke") or "") or \
        heart.query_selector("svg").get_attribute("fill") == "currentColor"


def test_the_heart_is_outline_when_nothing_is_saved_yet(mounted):
    page, mount = mounted
    mount(_data(yt={"videoId": "x", "title": "Song", "paused": False, "cmd_seq": 1}, fav_current=False))
    assert page.query_selector(".hb-mus2-barc .fav") is None
    heart_svg = page.query_selector(".hb-mus2-barc button:last-child svg")
    assert heart_svg.get_attribute("fill") == "none"


def test_the_main_transport_button_is_a_genuinely_solid_icon(mounted):
    """Guards the duplicate-attribute trap directly: an outline base (`fill="none"`) followed by a
    `fill="currentColor"` override on the SAME tag is not "the last one wins" — the HTML parser keeps the
    FIRST `fill` and drops the rest, so a naively-built solid icon renders as a hairline outline forever.
    `ICON_PLAY`/`ICON_PAUSE` must be built from a clean attribute set, never `_SW` plus an override."""
    page, mount = mounted
    mount(_data(yt={"videoId": "x", "title": "Song", "paused": True, "cmd_seq": 1}))  # paused -> shows PLAY
    main_svg = page.query_selector(".hb-mus2-cbtn.main svg")
    assert main_svg.get_attribute("fill") == "currentColor", "the play icon resolved to an outline, not solid"


# --- lazy enrichment: fast first, enhancement after, once per song ---

def test_a_track_missing_art_asks_the_server_after_paint_and_only_once(mounted):
    page, mount = mounted
    mount(_data(recent=[_track("Unknown Cover", artist="Some Artist")]))
    page.wait_for_timeout(150)
    calls = [c for c in _calls(page) if c[0] == "enrich_art"]
    assert calls == [["enrich_art", {"title": "Unknown Cover", "artist": "Some Artist"}]]
    # a second render of the SAME track must not ask again — the dedup is per song, per page life
    mount(_data(recent=[_track("Unknown Cover", artist="Some Artist")]))
    page.wait_for_timeout(150)
    calls_again = [c for c in _calls(page) if c[0] == "enrich_art"]
    assert calls_again == calls, "the widget re-asked for a song it already asked about"


def test_a_track_that_already_has_art_never_triggers_an_enrichment_call(mounted):
    page, mount = mounted
    mount(_data(recent=[_track("Already Has Art", artist="X", art="https://i.ytimg.com/vi/abc/hqdefault.jpg")]))
    page.wait_for_timeout(150)
    assert [c for c in _calls(page) if c[0] == "enrich_art"] == []


def test_enrichment_never_blocks_or_delays_what_is_already_on_screen(mounted):
    """The fast-first contract: the row/bar paints immediately with its fallback, before any enrichment
    round trip could possibly have returned — this is the difference between "sonar rápido" and waiting."""
    page, mount = mounted
    mount(_data(recent=[_track("Immediate", artist="Now")]))
    # No wait_for_timeout before this assertion: if the row only appeared after enrichment resolved, this
    # would be flaky/failing depending on timing. It must be there on the FIRST synchronous frame.
    assert page.inner_text(".hb-mus2-tr .hb-mus2-trt") == "Immediate"
