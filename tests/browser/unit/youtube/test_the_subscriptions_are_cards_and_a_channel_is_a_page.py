# 2026-09-29 — the subscriptions tab, RENDERED: channels as cards (picture, subscribers, videos, how many he
# follows, and that the subscription is ours), and a click opens the channel's PAGE — its sections, its
# videos with the 24 h / 72 h flags, «load more», its playlists — refreshed on every visit with a loader
# that says so («Buscando últimos vídeos del canal»). The data half is tested without a browser in
# test_a_channel_page_is_read_without_an_account.py.
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
         "accounts_enabled": False,
         "connector_shelf": [
             {"id": "youtube", "label": "YouTube", "state": "planned", "connected": False,
              "note": "falta registrar el cliente OAuth (INI-032)"},
             {"id": "vimeo", "label": "Vimeo", "state": "planned", "connected": False,
              "note": "aún no construido"}]}
    d.update(over)
    return d



_CARDS = [{"name": "José Luis Cárpatos", "id": "UCx", "handle": "@cárpatos", "avatar": "https://yt3.example/a.jpg",
           "subscribers": 77200, "videos": 10000, "resolved": True, "tried": True},
          {"name": "Canal Sin Datos", "id": "", "handle": "", "avatar": "", "subscribers": 0, "videos": 0,
           "resolved": False, "tried": False}]


def _items(now):
    return [{"id": "AAAAAAAAAA1", "kind": "video", "title": "Hace una hora", "views": 2300, "ts": now - 3600,
             "live": False, "duration": "14:56"},
            {"id": "AAAAAAAAAA2", "kind": "video", "title": "Hace dos días", "views": 15000, "ts": now - 2 * 86400,
             "live": False, "duration": "3:59"},
            {"id": "AAAAAAAAAA3", "kind": "video", "title": "Hace una semana", "views": 9000, "ts": now - 7 * 86400,
             "live": False, "duration": "1:21:18"},
            {"id": "AAAAAAAAAA4", "kind": "live", "title": "En directo ahora", "views": 120, "ts": 0,
             "live": True, "duration": ""}]


def _page_data(now, **over):
    pg = {"id": "UCx", "name": "José Luis Cárpatos", "tab": "videos",
          "tabs": ["videos", "streams", "shorts", "playlists"],
          "meta": {"title": "José Luis Cárpatos", "avatar": "https://yt3.example/a.jpg", "handle": "@cárpatos",
                   "subscribers": 77200, "videos": 10000},
          "items": _items(now), "total": 4, "has_more": True, "loaded": True, "refreshed_at": now - 60,
          "new_ids": ["AAAAAAAAAA1"], "rev": 1}
    pg.update(over)
    return {"channel_cards": _CARDS, "channel_page": pg, "channels": [{"name": c["name"]} for c in _CARDS]}


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


def _mount(page, data):
    """Fresh document per mount. Actions named in window.__hold stay PENDING until window.__release(),
    so a loader can be seen while its request is in flight."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:900px'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = []; window.__hold = window.__hold || []; window.__pending = [];
             window.__release = () => { window.__pending.splice(0).forEach((f) => f({ok: true})); };
             const mod = await import(src);
             window.__mod = mod;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                if(window.__hold.includes(n)) return new Promise((r) => window.__pending.push(r));
                                return Promise.resolve({ok: true}); },
                              top: () => {}, running: true, lang: "es" };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])
    page.click(".hb-yt-tab[data-tab=subs]")


def _names(page):
    return [c[0] for c in page.evaluate("window.__calls")]


def test_the_channels_are_cards_with_picture_subscribers_videos_and_the_count(_page):
    _mount(_page, {"channel_cards": _CARDS, "channels": [{"name": c["name"]} for c in _CARDS]})
    cards = _page.locator(".hb-yt-chcard")
    assert cards.count() == 2
    first = cards.nth(0).inner_text()
    assert "José Luis Cárpatos" in first and "@cárpatos" in first
    assert "77,2" in first and "suscriptores" in first and "vídeos" in first, first
    assert cards.nth(0).locator("img.hb-yt-av").get_attribute("src") == "https://yt3.example/a.jpg"
    assert cards.nth(1).locator(".hb-yt-av").inner_text() == "C", "no picture yet: its initial, never a hole"
    assert "Buscando datos del canal" in cards.nth(1).inner_text()
    assert _page.locator(".hb-yt-subs .hb-yt-homecount").inner_text() == "2", "how many he follows, by the title"
    assert "no te suscribe en YouTube" in _page.locator(".hb-yt-secnote").inner_text()
    assert "sync_channels" in _names(_page), "a card without its facts asks for them"


def test_a_card_click_opens_the_channel_and_its_buttons_do_not(_page):
    _mount(_page, {"channel_cards": _CARDS, "channels": []})
    _page.locator(".hb-yt-chcard").nth(0).locator(".hb-yt-chip").click()
    assert _names(_page)[-1] == "channel_videos"
    _page.click(".hb-yt-tab[data-tab=subs]")
    _page.locator(".hb-yt-chcard").nth(0).locator(".hb-yt-chx").click()
    assert _names(_page)[-1] == "unfollow_channel"
    _page.locator(".hb-yt-chcard").nth(0).click()
    assert ["open_channel", {"channel": "José Luis Cárpatos", "hl": "es"}] in _page.evaluate("window.__calls")


def test_walking_into_a_channel_refreshes_it_ONCE_with_its_loader_up(_page):
    now = int(time.time())
    _mount(_page, _page_data(now))
    # the refresh fires on entry…
    _page.wait_for_function("window.__calls.some(c => c[0] === 'refresh_channel')")
    assert _names(_page).count("refresh_channel") == 1


def test_the_loader_is_on_screen_while_the_refresh_is_in_flight(_page):
    now = int(time.time())
    _page.goto(_page._hb_origin)
    _page.set_content("<div id='w' style='width:900px'></div>")
    _page.evaluate(
        """async ([src, data]) => {
             window.__calls = []; window.__hold = ['refresh_channel']; window.__pending = [];
             window.__release = () => { window.__pending.splice(0).forEach((f) => f({ok: true})); };
             const mod = await import(src); window.__mod = mod;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                if(window.__hold.includes(n)) return new Promise((r) => window.__pending.push(r));
                                return Promise.resolve({ok: true}); }, top: () => {}, running: true, lang: "es" };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""", [_page._hb_url, _page_data(now)])
    _page.click(".hb-yt-tab[data-tab=subs]")
    _page.wait_for_function("window.__pending.length === 1")
    assert "Buscando últimos vídeos del canal" in _page.locator(".hb-yt-chstatus").inner_text()
    assert _page.locator(".hb-yt-chstatus .hb-yt-spin").count() == 1
    assert _page.locator(".hb-yt-vgrid .hb-yt-tile").count() == 4, "what was cached stays visible meanwhile"
    _page.evaluate("window.__release()")
    _page.wait_for_function("!document.querySelector('.hb-yt-chstatus .hb-yt-spin')")
    assert "1 nuevos" in _page.locator(".hb-yt-chstatus").inner_text()
    # a repaint of the same page does not refresh again
    _page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", _page_data(now))
    assert _names(_page).count("refresh_channel") == 1


def test_the_last_24h_and_72h_wear_their_own_flag_and_word(_page):
    now = int(time.time())
    _mount(_page, _page_data(now))
    tiles = _page.locator(".hb-yt-vgrid .hb-yt-tile")
    assert tiles.nth(0).locator(".hb-yt-flag.d1").inner_text() == "24 h"
    assert tiles.nth(1).locator(".hb-yt-flag.d3").inner_text() == "72 h"
    assert tiles.nth(2).locator(".hb-yt-flag").count() == 0, "a week old is not new"
    assert tiles.nth(3).locator(".hb-yt-flag.live").count() == 1
    c1 = tiles.nth(0).locator(".hb-yt-flag").evaluate("e => getComputedStyle(e).backgroundColor")
    c3 = tiles.nth(1).locator(".hb-yt-flag").evaluate("e => getComputedStyle(e).backgroundColor")
    assert c1 != c3, "two ages, two colours"
    assert "14:56" in tiles.nth(0).inner_text() and "visualizaciones" in tiles.nth(0).inner_text()


def test_sections_more_playlists_and_the_crumb_are_all_actions(_page):
    now = int(time.time())
    _mount(_page, _page_data(now))
    labels = _page.locator(".hb-yt-subtab").all_inner_texts()
    assert labels == ["Vídeos", "En directo", "Shorts", "Listas"]
    _page.locator(".hb-yt-subtab[data-section=playlists]").click()
    assert ["channel_tab", {"tab": "playlists", "hl": "es"}] in _page.evaluate("window.__calls")
    _mount(_page, _page_data(now))
    _page.locator(".hb-yt-more").click()
    assert "channel_more" in _names(_page)
    _page.locator(".hb-yt-vgrid .hb-yt-tile").nth(0).click()
    assert ["load", {"videoId": "AAAAAAAAAA1", "title": "Hace una hora"}] in _page.evaluate("window.__calls")
    assert "hb-yt-t-player" in _page.evaluate("document.querySelector('.hb-yt').className")
    _mount(_page, _page_data(now, tab="playlists", items=[{"id": "PL1", "kind": "playlist", "title": "Mi lista",
                                                         "count": 6, "thumb": ""}], has_more=False))
    assert "6 vídeos" in _page.locator(".hb-yt-vgrid").inner_text()
    _page.locator(".hb-yt-vgrid .hb-yt-tile").nth(0).click()
    assert ["channel_playlist", {"playlist": "PL1", "title": "Mi lista", "hl": "es"}] in _page.evaluate("window.__calls")
    _mount(_page, _page_data(now, playlist={"id": "PL1", "title": "Mi lista"}))
    assert _page.locator(".hb-yt-crumb").inner_text() == "‹ Listas"
    _page.locator(".hb-yt-crumb").click()
    assert ["channel_playlist", {"playlist": "", "hl": "es"}] in _page.evaluate("window.__calls")
    _mount(_page, _page_data(now))
    _page.locator(".hb-yt-crumb").click()
    assert "close_channel" in _names(_page)


def test_an_empty_section_says_so(_page):
    now = int(time.time())
    _mount(_page, _page_data(now, items=[], has_more=False, tab="streams"))
    _page.wait_for_function("!document.querySelector('.hb-yt-chmsg .hb-yt-spin')")
    assert "no tiene nada" in _page.locator(".hb-yt-chmsg").inner_text()
