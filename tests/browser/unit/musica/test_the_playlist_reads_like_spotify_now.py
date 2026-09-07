#
# V2-XXX — musica PRO redesign, RENDERED. The operator's complaint on a real playlist: every row's title was
# literally "Madonna Papa Don't Preach" (the artist baked into the title with no separator, a legacy shape of
# `add_to_playlist{query}` with no explicit artist), the play button sat BELOW the whole header instead of on
# the cover art, and nothing on screen showed which track was currently playing. None of this is testable by
# reading the source: the derivation runs client-side inside a closure `render()` never exports, so every case
# here RENDERS the real widget.js (same harness as test_anothers_player_never_advances_the_music_queue.py) and
# reads the resulting DOM.
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


def _track(title, artist="", query="", **extra):
    t = {"title": title, "artist": artist, "album": "", "art": "", "query": query, "uri": "", "videoId": ""}
    t.update(extra)
    return t


def _data(playlists=None, now_playing=None, top=None, recent=None, view=None):
    return {
        "connected": bool(now_playing), "can_connect": False, "own_client_id_set": False,
        "default_available": False, "redirect_uri": "", "now_playing": now_playing, "mode": "idle",
        "yt": {}, "playlists": playlists or [], "recent": recent or [], "counts": {}, "top": top or [],
        "view": view or {"kind": "home", "id": ""},
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
    """Yields (page, browser, mount(data)) — mount() re-renders with fresh data and returns nothing; the test
    reads the DOM off `page` after each call."""
    srv = _Server()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
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


# --- the artist gets factored out of every row when it is the SAME everywhere ---

def test_a_uniform_legacy_title_shows_the_artist_once_in_the_header_and_strips_it_from_every_row(mounted):
    page, mount = mounted
    pl = {"id": "true-blue", "name": "True Blue", "art": "", "tracks": [
        _track("Madonna Papa Don't Preach"),
        _track("Madonna Open Your Heart"),
        _track("Madonna White Heat"),
    ]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "true-blue"}))
    assert page.inner_text(".hb-mus2-plsub") == "Madonna · 3 canciones"
    titles = page.eval_on_selector_all(".hb-mus2-trt", "els => els.map(e => e.textContent)")
    assert titles == ["Papa Don't Preach", "Open Your Heart", "White Heat"]
    # the artist line per row is gone — it would be pure repetition of the header now
    assert page.eval_on_selector_all(".hb-mus2-tr .hb-mus2-tra", "els => els.length") == 0


def test_an_explicit_uniform_artist_field_also_collapses_to_the_header(mounted):
    page, mount = mounted
    pl = {"id": "p", "name": "P", "art": "", "tracks": [
        _track("Song A", artist="Same Artist"),
        _track("Song B", artist="Same Artist"),
    ]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "p"}))
    assert "Same Artist" in page.inner_text(".hb-mus2-plsub")
    titles = page.eval_on_selector_all(".hb-mus2-trt", "els => els.map(e => e.textContent)")
    assert titles == ["Song A", "Song B"]


def test_a_mixed_playlist_never_guesses_and_keeps_the_per_row_artist(mounted):
    page, mount = mounted
    pl = {"id": "mix", "name": "Mix", "art": "", "tracks": [
        _track("One", artist="Artist A"),
        _track("Two", artist="Artist B"),
    ]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "mix"}))
    assert "Artist" not in page.inner_text(".hb-mus2-plsub")   # no single artist to promote
    subs = page.eval_on_selector_all(".hb-mus2-tra", "els => els.map(e => e.textContent)")
    assert subs == ["Artist A", "Artist B"]


def test_a_mixed_tagging_quality_playlist_is_left_alone_rather_than_guessed(mounted):
    """One track tagged, one not: guessing which word of the untagged title IS the artist would be inventing
    a fact the data does not carry — safer to show both rows exactly as given."""
    page, mount = mounted
    pl = {"id": "half", "name": "Half", "art": "", "tracks": [
        _track("Real Artist Real Song", artist="Real Artist"),
        _track("Something Else"),
    ]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "half"}))
    assert page.inner_text(".hb-mus2-plsub") == "2 canciones"
    titles = page.eval_on_selector_all(".hb-mus2-trt", "els => els.map(e => e.textContent)")
    assert titles == ["Real Artist Real Song", "Something Else"]


def test_two_words_of_genuine_coincidence_are_not_enough_to_leave_an_empty_title(mounted):
    """Guard against stripping the WHOLE title: if every word is shared, nothing legible would remain — the
    derivation must always leave at least one word behind."""
    page, mount = mounted
    pl = {"id": "same", "name": "Same", "art": "", "tracks": [_track("Echo"), _track("Echo")]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "same"}))
    titles = page.eval_on_selector_all(".hb-mus2-trt", "els => els.map(e => e.textContent)")
    assert titles == ["Echo", "Echo"]                 # single-word titles: nothing to factor out


# --- the play button lives ON the cover art, not below the header ---

def test_the_play_button_is_inside_the_cover_art_wrapper(mounted):
    page, mount = mounted
    pl = {"id": "p", "name": "P", "art": "", "tracks": [_track("A")]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "p"}))
    assert page.eval_on_selector_all(".hb-mus2-artwrap > .hb-mus2-playfab", "els => els.length") == 1
    # and it is NOT floating loose in the scroll column, below the header, the old layout
    assert page.eval_on_selector_all(".hb-mus2-scroll > .hb-mus2-playfab", "els => els.length") == 0


def test_the_play_button_disables_on_an_empty_playlist(mounted):
    page, mount = mounted
    pl = {"id": "empty", "name": "Empty", "art": "", "tracks": []}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "empty"}))
    assert page.is_disabled(".hb-mus2-playfab")


# --- the currently-playing track is marked wherever it appears (playlist, top, recent) ---

def test_the_playing_row_is_marked_with_an_equalizer_in_the_playlist(mounted):
    page, mount = mounted
    pl = {"id": "p", "name": "P", "art": "", "tracks": [_track("A", artist="X"), _track("B", artist="X")]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "p"},
                now_playing={"title": "B", "artist": "X", "playing": True}))
    rows = page.query_selector_all(".hb-mus2-tr")
    assert "playing" not in rows[0].get_attribute("class")
    assert "playing" in rows[1].get_attribute("class")
    assert rows[1].query_selector(".hb-mus2-eq") is not None
    assert rows[0].query_selector(".hb-mus2-eq") is None


def test_the_playing_track_is_also_marked_in_top_and_recent_on_the_home_screen(mounted):
    page, mount = mounted
    mount(_data(top=[_track("Hit One", artist="X"), _track("Hit Two", artist="Y")],
                recent=[_track("Hit Two", artist="Y")],
                now_playing={"title": "Hit Two", "artist": "Y", "playing": True},
                view={"kind": "home", "id": ""}))
    rows = page.query_selector_all(".hb-mus2-tr")
    playing_titles = [r.query_selector(".hb-mus2-trt").text_content() for r in rows
                      if "playing" in r.get_attribute("class")]
    assert playing_titles == ["Hit Two", "Hit Two"]   # both the top-tracks row AND the recent row


def test_the_bottom_bar_shows_the_equalizer_badge_only_while_actually_playing(mounted):
    page, mount = mounted
    mount(_data(now_playing={"title": "X", "artist": "", "playing": True}))
    assert page.query_selector(".hb-mus2-bar .hb-mus2-areq") is not None
    mount(_data(now_playing={"title": "X", "artist": "", "playing": False}))
    assert page.query_selector(".hb-mus2-bar .hb-mus2-areq") is None


# --- click selects (visual only, no server call); double-click plays ---

def test_a_single_click_selects_without_calling_the_server(mounted):
    page, mount = mounted
    pl = {"id": "p", "name": "P", "art": "", "tracks": [_track("A"), _track("B")]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "p"}))
    page.click(".hb-mus2-tr:nth-child(1)")
    assert page.eval_on_selector_all(".hb-mus2-tr.selected", "els => els.length") == 1
    assert page.evaluate("window.__calls") == []
    # selecting a second row moves the highlight, it does not add a second one
    page.click(".hb-mus2-tr:nth-child(2)")
    selected = page.eval_on_selector_all(".hb-mus2-tr.selected .hb-mus2-trt", "els => els.map(e => e.textContent)")
    assert selected == ["B"]


def test_a_double_click_plays_that_exact_track(mounted):
    page, mount = mounted
    pl = {"id": "p", "name": "P", "art": "", "tracks": [_track("A", artist="X"), _track("B", artist="Y")]}
    mount(_data(playlists=[pl], view={"kind": "playlist", "id": "p"}))
    page.dblclick(".hb-mus2-tr:nth-child(2)")
    calls = page.evaluate("window.__calls")
    assert ["play", {"query": "B Y"}] in calls
