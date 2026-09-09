# V2-636 — the video widget dresses like the product: a defined tab BAND whose active chip is inverted
# (YouTube's dark-chip language) behind a red brand mark, title and date sharing ONE line, icon controls
# in a bar that is pinned and VISIBLE at any card size (the operator grew the card with the mouse and the
# buttons were clipped under its bottom edge), and the voice hint only over an empty player. None of this
# is testable from source — every case renders the real widget.js, and the clipping case mounts it inside
# the REAL card structure (.hb-win > .hb-scroll > root, rules copied verbatim — the V2-608 fixture lesson:
# a harness whose DOM differs from the product's measures a different product).
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

_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002020401003b")


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _data(**over):
    d = {"videoId": "", "title": "", "channel": "", "published": "", "volume": 70, "muted": True,
         "captions": False, "paused": True, "last_cmd": "", "cmd_seq": 0, "loading": False,
         "loading_query": "", "list": [], "player_error": "", "pos": -1, "adding": "", "list_filter": "",
         "list_name": "", "blocked_channels": [], "platforms": [], "platforms_at": 0, "connect_focus": None,
         "suggested": [], "suggested_at": 0, "suggested_channels": 0, "suggesting": False,
         "search_results": [], "search_query": "", "searched_at": 0, "channels": [], "history": [],
         "prefs": {}, "prefs_notes": [], "lists": [], "quality": 0, "platforms_stale": False,
         "accounts_enabled": False, "connector_shelf": [], "blocked_videos": [], "blocked_notice": {},
         "pick_explicit": False, "last_query": ""}
    d.update(over)
    return d


_VID = _data(videoId="dQw4w9WgXcQ", title="Un vídeo con un título francamente largo para forzar la elipsis",
             channel="Canal Real", published="2026-01-05", paused=True)


# The card chrome around the widget, copied VERBATIM from frontend/app/widgets/desktop.js: the card is a
# flex column, .hb-scroll is its only scroller, and the widget root is .hb-scroll's direct child (render
# overwrites the .hb-body div's className).
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
            page.route("**://i.ytimg.com/**", lambda r: r.fulfill(status=200, content_type="image/gif",
                                                                  body=_GIF))
            page.route("**://www.youtube.com/**", lambda r: r.fulfill(status=200, content_type="text/html",
                                                                      body="<html></html>"))
            page._hb_url = f"http://127.0.0.1:{port}/widgets/youtube/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/youtube/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data, *, card_w=660, card_h=0):
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
                              top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


def _remount(page, data):
    page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", data)


# ── the tab band ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_active_tab_is_an_inverted_chip_behind_the_red_brand_mark(_page):
    _mount(_page, _VID)
    assert _page.locator(".hb-yt-nav .hb-yt-brand svg").count() == 1, "the brand mark leads the band"
    brand_bg = _page.evaluate("getComputedStyle(document.querySelector('.hb-yt-brand')).backgroundColor")
    assert brand_bg == "rgb(255, 0, 51)"
    on = _page.locator(".hb-yt-tab.on")
    assert on.count() == 1
    style = _page.evaluate(
        """() => { const s = getComputedStyle(document.querySelector('.hb-yt-tab.on'));
                   return [s.backgroundColor, s.color]; }""")
    # Inverted: the chip's ground is the ink token, its text the page ground (fallbacks in the bare page).
    assert style == ["rgb(13, 22, 34)", "rgb(255, 255, 255)"]
    off = _page.evaluate(
        "getComputedStyle(document.querySelector('.hb-yt-tab:not(.on)')).backgroundColor")
    assert off in ("rgba(0, 0, 0, 0)", "transparent"), "inactive tabs stay quiet — one chip is lit"
    band = _page.evaluate(
        "getComputedStyle(document.querySelector('.hb-yt-nav')).borderBottomWidth")
    assert band == "1px", "the strip is a DEFINED horizontal band, separated from the title below"


def test_the_tabs_lost_their_ascii_glyphs(_page):
    _mount(_page, _VID)
    labels = _page.locator(".hb-yt-tab").all_inner_texts()
    assert "Reproductor" in labels
    assert not any(g in "".join(labels) for g in "⌂▶≡★≣"), labels


# ── one header line ──────────────────────────────────────────────────────────────────────────────────────

def test_title_and_date_share_one_line_title_left_meta_right(_page):
    _mount(_page, _VID)
    tline = _page.locator(".hb-yt-tline")
    assert tline.is_visible()
    boxes = _page.evaluate(
        """() => { const t = document.querySelector('.hb-yt-title').getBoundingClientRect();
                   const m = document.querySelector('.hb-yt-meta').getBoundingClientRect();
                   return {t, m}; }""")
    assert boxes["m"]["left"] >= boxes["t"]["right"] - 1, "meta sits to the RIGHT of the title"
    assert abs(boxes["m"]["top"] - boxes["t"]["top"]) < 12, "…on the SAME row, not a second one"
    assert "Canal Real" in _page.locator(".hb-yt-meta").inner_text()


# ── icon controls ────────────────────────────────────────────────────────────────────────────────────────

def test_the_controls_are_icon_buttons_and_the_main_toggle_follows_paused(_page):
    _mount(_page, _VID)
    btns = _page.locator(".hb-yt-ctrls .hb-yt-cbtn")
    assert btns.count() == 6                      # prev · play/pause · next · vol- · vol+ · mute
    assert _page.locator(".hb-yt-ctrls .hb-yt-cbtn svg").count() == 6
    assert _page.locator(".hb-yt-ctrls").inner_text().strip() == "—", \
        "no button carries prose — the only text in the bar is the volume readout (— while muted)"
    _remount(_page, _data(**{**_VID, "muted": False}))
    assert _page.locator(".hb-yt-ctrls").inner_text().strip() == "70%"
    main = _page.locator(".hb-yt-cbtn.main")
    assert main.get_attribute("title") == "Play"   # paused → the face says what a click will DO
    main.click()
    assert _page.evaluate("window.__calls.pop()") == ["play", {}]
    _remount(_page, _data(**{**_VID, "paused": False}))
    assert main.get_attribute("title") == "Pausa"
    main.click()
    assert _page.evaluate("window.__calls.pop()") == ["pause", {}]


def test_the_voice_hint_only_teaches_over_an_empty_player(_page):
    _mount(_page, _VID)
    assert not _page.locator(".hb-yt-hint").is_visible(), "beside a filled bar the hint is noise"
    _mount(_page, _data())
    _page.click(".hb-yt-tab[data-tab=player]")     # empty store opens on Inicio; the hint lives on the player
    assert _page.locator(".hb-yt-hint").is_visible()


# ── the clipping bug: the bar stays visible at ANY card size ─────────────────────────────────────────────

def test_grown_card_keeps_the_control_bar_visible_and_the_video_fills_the_rest(_page):
    _mount(_page, _VID, card_w=900, card_h=620)
    geo = _page.evaluate(
        """() => { const card = document.querySelector('.hb-win').getBoundingClientRect();
                   const bar = document.querySelector('.hb-yt-ctrls').getBoundingClientRect();
                   const frame = document.querySelector('.hb-yt-frame').getBoundingClientRect();
                   const sc = document.querySelector('.hb-scroll');
                   return {card, bar, frame, overflow: getComputedStyle(sc).overflowY}; }""")
    assert geo["bar"]["bottom"] <= geo["card"]["bottom"] + 1, \
        "the operator grew the card and the buttons were clipped under its edge — never again"
    assert geo["bar"]["height"] > 0
    assert geo["frame"]["height"] > 300, "the video surface takes the spare space, not a fixed ratio"
    assert geo["overflow"] == "hidden", "the player tab fills; it does not scroll its bar out of view"


def test_a_small_card_still_shows_the_whole_bar(_page):
    _mount(_page, _VID, card_w=420, card_h=360)
    geo = _page.evaluate(
        """() => { const card = document.querySelector('.hb-win').getBoundingClientRect();
                   const bar = document.querySelector('.hb-yt-ctrls').getBoundingClientRect();
                   return {card, bar}; }""")
    assert geo["bar"]["bottom"] <= geo["card"]["bottom"] + 1
    assert geo["bar"]["top"] >= geo["card"]["top"]


def test_other_tabs_keep_their_scroll(_page):
    rows = [{"videoId": "AAAAAAAAAA%d" % i, "title": "V%d" % i, "channel": "C", "url": "",
             "thumb": ""} for i in range(1, 30)]
    _mount(_page, _data(**{**_VID, "list": rows}), card_w=520, card_h=380)
    _page.click(".hb-yt-tab[data-tab=cola]")
    overflow = _page.evaluate(
        "getComputedStyle(document.querySelector('.hb-scroll')).overflowY")
    assert overflow == "auto", "the fill rule is the PLAYER tab's; a long queue must still scroll"


# ── playing markers wear the brand red ───────────────────────────────────────────────────────────────────

def test_the_playing_row_marker_is_youtube_red(_page):
    rows = [{"videoId": "dQw4w9WgXcQ", "title": "Sonando", "channel": "C", "url": "", "thumb": ""},
            {"videoId": "AAAAAAAAAA2", "title": "Siguiente", "channel": "C", "url": "", "thumb": ""}]
    _mount(_page, _data(**{**_VID, "list": rows, "pos": 0}))
    _page.click(".hb-yt-tab[data-tab=cola]")
    color = _page.evaluate(
        "getComputedStyle(document.querySelector('.hb-yt-row.playing .hb-yt-rowt')).color")
    assert color == "rgb(255, 0, 51)"
