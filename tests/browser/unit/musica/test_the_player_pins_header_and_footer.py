# V2-667 — the music widget gets a real player's frame: a header that never moves, a footer (playback bar)
# that never moves, and ONLY the middle content (the list of tracks) scrolls between them. Operator, with two
# screenshots: opening the widget showed a track-shaped bar reading "Nada sonando" as if that were a song's
# own title, and a growing playlist visibly pushed the playback bar DOWN, off the bottom of the card, instead
# of it staying pinned like Spotify's own transport bar.
#
# Neither is testable by reading the source: the idle/loaded split runs client-side inside a closure
# render() never exports, and "does the footer stay visible while the list overflows" is a layout property —
# only a browser answers it. The clipping cases mount the REAL card chrome (.hb-win > .hb-scroll > root,
# rules copied verbatim from frontend/app/widgets/desktop.js — the V2-608 fixture lesson: a harness whose DOM
# differs from the product's measures a different product).
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


def _track(title, artist="", **extra):
    t = {"title": title, "artist": artist, "album": "", "art": "", "query": title, "uri": "", "videoId": ""}
    t.update(extra)
    return t


def _data(playlists=None, now_playing=None, yt=None, top=None, recent=None, view=None, fav_current=False):
    return {
        "connected": bool(now_playing), "can_connect": False, "own_client_id_set": False,
        "default_available": False, "redirect_uri": "", "now_playing": now_playing, "mode": "idle",
        "yt": yt or {}, "playlists": playlists or [], "recent": recent or [], "counts": {}, "top": top or [],
        "fav_current": fav_current, "view": view or {"kind": "home", "id": ""},
    }


# The card chrome around the widget, copied VERBATIM from frontend/app/widgets/desktop.js: the card is a
# flex column, .hb-scroll is its only scroller, and the widget root is .hb-scroll's direct child.
_CARD_CSS = """
  .hb-win{position:fixed;left:20px;top:20px;display:flex;flex-direction:column;
          padding:30px 16px 16px;overflow:hidden;box-sizing:border-box;background:#fff}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
"""


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
            page._hb_url = f"http://127.0.0.1:{port}/widgets/musica/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/musica/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, card_w=440, card_h=0):
    """Fresh document per mount; card_h > 0 mounts inside the real card chrome at that fixed size."""
    page.goto(page._hb_origin)
    if card_h:
        page.set_content(
            f"<style>{_CARD_CSS}</style>"
            f"<div class='hb-win' style='width:{card_w}px;height:{card_h}px'>"
            f"<div class='hb-scroll'><div id='w'></div></div></div>")
    else:
        page.set_content(f"<div id='w' style='width:{card_w}px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod; window.__data = data;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve({ok: true}); },
                              running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


# ── two REAL states, never one row wearing a fake song title ───────────────────────────────────────────────

def test_idle_playback_bar_is_not_shaped_like_a_track(_page):
    _mount(_page, _data())
    bar = _page.query_selector(".hb-mus2-bar")
    assert "empty" in bar.get_attribute("class")
    assert _page.inner_text(".hb-mus2-baridle") == "Dime qué quieres escuchar"
    # No fake title/artist pair — "Nada sonando" must never read as a song's own name again.
    assert _page.query_selector(".hb-mus2-bart") is None
    assert _page.query_selector(".hb-mus2-bara") is None
    buttons = _page.query_selector_all(".hb-mus2-barc button")
    assert len(buttons) == 5, "prev/play/next/vol-down/vol-up, still all present — just inert"
    assert all(b.is_disabled() for b in buttons), "nothing loaded: the transport has nothing to act on"


def test_a_loaded_track_never_shows_the_idle_hint(_page):
    _mount(_page, _data(yt={"videoId": "abc", "title": "Song", "artist": "Artist", "paused": False,
                            "cmd_seq": 1, "art": ""}))
    bar = _page.query_selector(".hb-mus2-bar")
    assert "empty" not in (bar.get_attribute("class") or "")
    assert _page.query_selector(".hb-mus2-baridle") is None
    assert _page.inner_text(".hb-mus2-bart") == "Song"
    assert _page.inner_text(".hb-mus2-bara") == "Artist"
    buttons = _page.query_selector_all(".hb-mus2-barc button")
    assert not any(b.is_disabled() for b in buttons), "a real track: the transport must be usable"


# ── header and footer never travel with the list — only the middle scrolls ─────────────────────────────────

def test_a_long_playlist_never_pushes_the_header_or_footer_out_of_a_small_card(_page):
    tracks = [_track(f"Canción {i}", artist="Alguien") for i in range(30)]
    pl = {"id": "long", "name": "Larga", "art": "", "tracks": tracks}
    _mount(_page, _data(playlists=[pl], view={"kind": "playlist", "id": "long"}), card_w=440, card_h=420)
    geo = _page.evaluate(
        """() => {
             const card = document.querySelector('.hb-win').getBoundingClientRect();
             const head = document.querySelector('.hb-mus2-headfix').getBoundingClientRect();
             const bar = document.querySelector('.hb-mus2-bar').getBoundingClientRect();
             const mid = document.querySelector('.hb-mus2-scroll');
             const outer = document.querySelector('.hb-scroll');
             return {
               card, head, bar,
               midOverflowY: getComputedStyle(mid).overflowY,
               midOverflows: mid.scrollHeight > mid.clientHeight + 1,
               outerOverflowY: getComputedStyle(outer).overflowY,
             };
           }""")
    assert geo["head"]["top"] >= geo["card"]["top"] - 1, "the header must never scroll above the card"
    assert geo["head"]["bottom"] <= geo["card"]["bottom"] + 1, "the header must stay inside the visible card"
    assert geo["bar"]["top"] >= geo["card"]["top"] - 1
    assert geo["bar"]["bottom"] <= geo["card"]["bottom"] + 1, \
        "the playback bar must stay pinned at the foot of the card, never pushed off by a long list"
    assert geo["midOverflowY"] == "auto" and geo["midOverflows"], \
        "thirty tracks in a 420px card must overflow SOMEWHERE — the middle region is where"
    assert geo["outerOverflowY"] == "hidden", \
        "the card's own outer scroll must be switched off; an internal one owns the overflow instead"


def test_a_long_home_list_also_pins_header_and_footer(_page):
    top_tracks = [_track(f"Hit {i}", artist="X") for i in range(20)]
    recent = [_track(f"Reciente {i}", artist="Y") for i in range(20)]
    _mount(_page, _data(top=top_tracks, recent=recent, yt={"videoId": "abc", "title": "Song", "cmd_seq": 1}),
           card_w=440, card_h=420)
    geo = _page.evaluate(
        """() => {
             const card = document.querySelector('.hb-win').getBoundingClientRect();
             const head = document.querySelector('.hb-mus2-headfix').getBoundingClientRect();
             const bar = document.querySelector('.hb-mus2-bar').getBoundingClientRect();
             return {card, head, bar};
           }""")
    assert geo["head"]["top"] >= geo["card"]["top"] - 1 and geo["head"]["bottom"] <= geo["card"]["bottom"] + 1
    assert geo["bar"]["top"] >= geo["card"]["top"] - 1 and geo["bar"]["bottom"] <= geo["card"]["bottom"] + 1


def test_a_short_list_shows_everything_with_no_internal_scroll(_page):
    """The fill rule must not over-fire: a card roomy enough for its content needs no scroll at all."""
    pl = {"id": "short", "name": "Corta", "art": "", "tracks": [_track("Una canción", artist="Alguien")]}
    _mount(_page, _data(playlists=[pl], view={"kind": "playlist", "id": "short"}), card_w=440, card_h=900)
    mid_overflows = _page.evaluate(
        "() => { const m = document.querySelector('.hb-mus2-scroll'); return m.scrollHeight > m.clientHeight + 1; }")
    assert not mid_overflows, "a single track in a 900px card has nothing to scroll"
