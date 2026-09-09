# V2-632 — the video widget becomes a real player: top TABS (Inicio · Reproductor · Cola · Suscripciones ·
# Listas), a dashboard whose TOP band is the current search (numbered, voice-steerable), a placeholder that
# marks where the video will live, and a connectors SHELF behind the 🔌 that shows every source honestly —
# YouTube disabled WITH its reason (INI-032), the world's other providers as shut doors. None of it is
# testable from source: tabs, CSS-driven visibility, the auto-jump on a video's arrival and the shelf's
# disabled faces all live client-side — every case RENDERS the real widget.js.
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


_RESULTS = [{"videoId": "AAAAAAAAAA%d" % i, "title": t, "channel": "C%d" % i, "url": ""}
            for i, t in enumerate(["Res Uno", "Res Dos", "Res Tres"], 1)]


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


def _mount(page, data, running=True):
    """Fresh document per mount, so the module-lived tab/screen state starts clean each case."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w' style='width:660px'></div>")
    page.evaluate(
        """async ([src, data, running]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__mod = mod; window.__data = data;
             window.__ctx = { action: (n, p) => { window.__calls.push([n, p || {}]);
                                                  return Promise.resolve({ok: true}); },
                              top: () => {}, running: running };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data, running])


def _remount(page, data):
    page.evaluate("(d) => window.__mod.render(document.getElementById('w'), d, window.__ctx)", data)


def _cls(page):
    return page.evaluate("() => document.querySelector('.hb-yt').className")


def test_the_five_tabs_exist_and_empty_defaults_to_the_dashboard(_page):
    _mount(_page, _data())
    tabs = _page.eval_on_selector_all(".hb-yt-tab", "els => els.map(e => e.dataset.tab)")
    assert tabs == ["inicio", "player", "cola", "subs", "listas"]
    assert "hb-yt-t-inicio" in _cls(_page)
    assert "No hay ningún vídeo cargado" in _page.locator(".hb-yt-homemsg").inner_text()


def test_the_player_tab_shows_a_placeholder_where_the_video_will_live(_page):
    """The operator's ask verbatim: «un placeholder… que indique que no hay vídeo, pero que se vea que ese
    es el lugar donde eso se va a representar» — title AND frame."""
    _mount(_page, _data())
    _page.click(".hb-yt-tab[data-tab=player]")
    assert _page.locator(".hb-yt-frame .hb-yt-empty").count() == 1
    assert "Sin vídeo" in _page.locator(".hb-yt-empty").inner_text()
    assert _page.locator(".hb-yt-title").inner_text() == "Sin vídeo"
    # the frame keeps its 16:9 footprint — the placeholder OCCUPIES the video's place, it does not collapse it
    box = _page.locator(".hb-yt-frame").bounding_box()
    assert box and box["height"] > 200


def test_a_video_arriving_jumps_to_the_player_tab(_page):
    """«ponme el vídeo de X» means watching it — the dashboard must not stay up while it plays underneath
    (the exact confusion of his screenshot: the card opened before the video existed)."""
    _mount(_page, _data())
    assert "hb-yt-t-inicio" in _cls(_page)
    _remount(_page, _data(videoId="dQw4w9WgXcQ", title="Llegó"))
    assert "hb-yt-t-player" in _cls(_page)


def test_search_results_render_numbered_on_the_dashboard_and_steer_by_click(_page):
    _mount(_page, _data(search_results=_RESULTS, search_query="gatitos"))
    assert "Resultados: «gatitos»" in _page.locator(".hb-yt-schead").inner_text()
    nums = _page.eval_on_selector_all(".hb-yt-rnum", "els => els.map(e => e.textContent)")
    assert nums == ["1", "2", "3"], "the numbers ARE the voice index («reproduce el tercero»)"
    # the per-tile «+ cola» queues WITHOUT playing and stays on the dashboard
    _page.locator(".hb-yt-radd").nth(1).click()
    assert ["add_results", {"items": "2"}] in _page.evaluate("window.__calls")
    assert "hb-yt-t-inicio" in _cls(_page)
    # a tile click plays that result and jumps to the player
    _page.evaluate("window.__calls = []")
    _page.locator(".hb-yt-home .hb-yt-tile").nth(2).click()
    assert ["play_result", {"item": "3"}] in _page.evaluate("window.__calls")
    assert "hb-yt-t-player" in _cls(_page)


def test_the_subscriptions_tab_lists_authors_and_never_touches_an_account(_page):
    _mount(_page, _data(channels=[{"name": "MUNDO DE LA VELA"}]))
    _page.click(".hb-yt-tab[data-tab=subs]")
    assert "MUNDO DE LA VELA" in _page.locator(".hb-yt-subs").inner_text()
    _page.locator(".hb-yt-subs .hb-yt-chip").click()          # «vídeos → cola»
    assert ["channel_videos", {"channel": "MUNDO DE LA VELA"}] in _page.evaluate("window.__calls")
    assert "hb-yt-t-cola" in _cls(_page)


def test_the_lists_tab_opens_and_saves(_page):
    _mount(_page, _data(lists=[{"name": "vela", "items": [{"videoId": "x"}]}]))
    _page.click(".hb-yt-tab[data-tab=listas]")
    _page.locator(".hb-yt-mylists .hb-yt-chip").click()       # «abrir → cola»
    assert ["open_list", {"name": "vela"}] in _page.evaluate("window.__calls")
    assert "hb-yt-t-cola" in _cls(_page)
    _page.click(".hb-yt-tab[data-tab=listas]")
    inp = _page.locator(".hb-yt-saverow .hb-yt-addinp")
    inp.fill("tarde")
    inp.press("Enter")
    assert ["save_list", {"name": "tarde"}] in _page.evaluate("window.__calls")


def test_the_shelf_shows_every_source_disabled_with_its_reason(_page):
    """INI-027's wishlist rule on this widget: what we do NOT have is SHOWN — YouTube disabled says WHY
    (INI-032), a planned provider says it is not built. A box that cannot open never wears an active face."""
    _mount(_page, _data())
    _page.click(".hb-yt-conbtn")
    boxes = _page.locator(".hb-yt-ibox")
    assert boxes.count() == 2
    assert all(_page.locator(".hb-yt-ibox").nth(i).evaluate("e => e.classList.contains('off')")
               for i in range(2))
    boxes.nth(0).click()
    note = _page.locator(".hb-yt-shnote").inner_text()
    assert "OAuth" in note and "YouTube" in note
    assert _page.evaluate("window.__calls") == [], "a disabled source must never fire a connect action"


def test_choosing_a_tab_closes_the_connectors_screen(_page):
    """The V2-626 rule, applied at birth instead of paid later: a tab choice is ONE transition — the shelf
    cannot stay rendered underneath (mensajería's measured bug, and this widget's own named latent one)."""
    _mount(_page, _data())
    _page.click(".hb-yt-conbtn")
    assert "hb-yt-connmode" in _cls(_page)
    _page.click(".hb-yt-tab[data-tab=cola]")
    assert "hb-yt-connmode" not in _cls(_page)
    assert "hb-yt-t-cola" in _cls(_page)
    assert _page.locator(".hb-yt-igrid").count() == 0
    # …and it STAYS closed across the next data render: clearing only the pixels while the screen state
    # survives would resurrect the shelf on the first SSE repaint (the exact bug shape this guards).
    _remount(_page, _data())
    assert "hb-yt-connmode" not in _cls(_page)
    assert _page.locator(".hb-yt-igrid").count() == 0


def test_recently_watched_band_renders_from_our_own_history(_page):
    _mount(_page, _data(history=[{"videoId": "h1", "title": "Visto Uno", "channel": "Z"}]))
    assert "Vistos hace poco" in _page.locator(".hb-yt-home").inner_text()
    _page.locator(".hb-yt-home .hb-yt-tile").first.click()
    calls = _page.evaluate("window.__calls")
    assert ["load", {"videoId": "h1", "title": "Visto Uno"}] in calls
    assert "hb-yt-t-player" in _cls(_page)


def test_the_block_banner_says_what_happened_and_only_when_something_did(_page):
    """V2-634 — the owner's embed block is SAID on the card, not left as YouTube's raw error screen. The
    harness ctx has no `t`, so this also proves the i18n fallback interpolates the {from}/{to} params."""
    _mount(_page, _data(videoId="dQw4w9WgXcQ", title="El Sustituto",
                        blocked_notice={"kind": "swapped", "from": "El Brujo", "to": "El Sustituto",
                                        "code": "150"}))
    txt = _page.locator(".hb-yt-blockmsg").inner_text()
    assert "El Brujo" in txt and "El Sustituto" in txt and "{from}" not in txt
    assert _page.locator(".hb-yt-blockmsg").is_visible(), "the banner belongs on the player tab"
    # explicit link: the honest copyright message, no swap wording
    _remount(_page, _data(videoId="dQw4w9WgXcQ", title="El que pegó él",
                          blocked_notice={"kind": "explicit", "from": "El que pegó él", "code": "101"}))
    assert "YouTube" in _page.locator(".hb-yt-blockmsg").inner_text()
    # nothing happened → no banner
    _remount(_page, _data(videoId="dQw4w9WgXcQ", title="Sano"))
    assert not _page.locator(".hb-yt-blockmsg").is_visible()
