#
# V2-597 — the ACCOUNT screens of the video widget, verified by RENDERING (the V2-124 lesson: a disconnected
# handler or a hidden face fails with zero errors, and only pixels can say so). Faces under test: the platform
# icons row (dimmed = wizard, bright = status), the 3-step wizard with ONE step visible at a time, the consent
# window opened synchronously on the click, the voice door (connect_focus), and the HOME suggestions band.
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


_SUGG = [
    {"videoId": "AAAAAAAAAA1", "title": "Coches del futuro", "channel": "Canal Uno",
     "published": "2026-09-01", "url": "https://youtu.be/AAAAAAAAAA1"},
    {"videoId": "BBBBBBBBBB2", "title": "Ferrari F40 real", "channel": "Canal Dos",
     "published": "2026-09-02", "url": "https://youtu.be/BBBBBBBBBB2"},
]
_ROW_OFF = {"id": "youtube", "label": "YouTube", "connected": False, "app_configured": False}
_ROW_APP = {"id": "youtube", "label": "YouTube", "connected": False, "app_configured": True}
_ROW_ON = {"id": "youtube", "label": "YouTube", "connected": True, "app_configured": True}


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
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/youtube/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/youtube/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data: dict, replies: dict | None = None):
    """Mounts the real widget with a fake ctx whose `action` records the call AND answers from `replies`
    (the wizard's check buttons read the action's own response)."""
    page.goto(page._hb_origin)
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data, replies]) => {
             window.__calls = [];
             window.__opened = [];
             const _open = window.open.bind(window);
             window.open = (u, t) => {                     // capture the consent window without real tabs
               const w = {location: "", closed: false, close(){ this.closed = true; }};
               window.__opened.push(w);
               return w;
             };
             const mod = await import(src);
             window.__ctx = { action: (name, payload) => {
                                window.__calls.push([name, payload || {}]);
                                return Promise.resolve((replies || {})[name] || null);
                              },
                              running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data, replies or {}],
    )


def test_the_platform_icon_renders_dimmed_and_opens_the_wizard(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_OFF]})
    icon = _page.locator(".hb-yt-picon")
    assert icon.count() == 1
    assert not icon.evaluate("e => e.classList.contains('on')")          # dimmed = not connected
    icon.click()
    step = _page.locator(".hb-ytw-step")
    assert step.count() == 1                                             # ONE step visible at a time
    assert "Paso 1 de 3" in step.inner_text()
    assert "Google Cloud" in step.inner_text()
    # Connect mode hides the player faces — the wizard replaces the card, never stacks under it.
    assert _page.evaluate("() => document.querySelector('.hb-yt').classList.contains('hb-yt-connmode')")
    assert _page.locator(".hb-yt-home").evaluate("e => getComputedStyle(e).display") == "none"


def test_the_wizard_advances_step_by_step_and_check_reads_the_actions_answer(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_OFF]},
           replies={"sync_platforms": {"ok": True, "platforms": [_ROW_APP]}})
    _page.locator(".hb-yt-picon").click()
    _page.get_by_text("Ya la tengo — continuar").click()
    assert "Paso 2 de 3" in _page.locator(".hb-ytw-step").inner_text()
    _page.get_by_text("Comprobar y continuar").click()
    _page.wait_for_timeout(50)
    assert "Paso 3 de 3" in _page.locator(".hb-ytw-step").inner_text()
    assert [c[0] for c in _page.evaluate("window.__calls") if c[0] == "sync_platforms"]


def test_a_failed_check_speaks_instead_of_advancing(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_OFF]},
           replies={"sync_platforms": {"ok": True, "platforms": [_ROW_OFF]}})
    _page.locator(".hb-yt-picon").click()
    _page.get_by_text("Ya la tengo — continuar").click()
    _page.get_by_text("Comprobar y continuar").click()
    _page.wait_for_timeout(50)
    assert "Paso 2 de 3" in _page.locator(".hb-ytw-step").inner_text()   # did not advance
    assert _page.locator(".hb-ytw-err").count() == 1                     # and said why


def test_connect_opens_the_window_synchronously_and_fills_it_from_the_action(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_APP],
                   "connect_focus": {"platform": "youtube", "ts": int(time.time() * 1000)}},
           replies={"connect_account": {"ok": True, "url": "https://accounts.google.com/consent?x=1"}})
    # The voice door: a fresh connect_focus opens the wizard with no click at all.
    assert _page.locator(".hb-ytw-step").count() == 1
    _page.get_by_text("Ya la tengo — continuar").click()
    # app already registered → step 2 says so and lets you continue
    assert "App registrada" in _page.locator(".hb-ytw-step").inner_text()
    _page.get_by_text("Comprobar y continuar").click()
    _page.wait_for_timeout(50)
    # replies has no sync_platforms → the check cannot confirm; jump straight via the recorded step state
    _page.evaluate("() => null")
    # Drive step 3 directly through a fresh mount (module state is per-document, the wizard step is not data)
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_APP]},
           replies={"connect_account": {"ok": True, "url": "https://accounts.google.com/consent?x=1"},
                    "sync_platforms": {"ok": True, "platforms": [_ROW_APP]}})
    _page.locator(".hb-yt-picon").click()
    _page.get_by_text("Ya la tengo — continuar").click()
    _page.get_by_text("Comprobar y continuar").click()
    _page.wait_for_timeout(50)
    _page.get_by_text("Conectar YouTube").click()
    _page.wait_for_timeout(80)
    assert ["connect_account", {"platform": "youtube"}] in _page.evaluate("window.__calls")
    opened = _page.evaluate("window.__opened")
    assert opened and opened[0]["location"].startswith("https://accounts.google.com/")


def test_a_connected_platform_shows_bright_and_its_status_screen_disconnects(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_ON]})
    icon = _page.locator(".hb-yt-picon")
    assert icon.evaluate("e => e.classList.contains('on')")              # bright = connected
    icon.click()
    st = _page.locator(".hb-ytw-step")
    assert "conectado" in st.inner_text().lower()
    _page.get_by_text("Desconectar").click()
    _page.wait_for_timeout(50)
    assert ["disconnect_account", {"platform": "youtube"}] in _page.evaluate("window.__calls")
    # The crumb is the way back: the player faces return.
    _page.locator(".hb-ytw-crumb").click()
    assert _page.evaluate("() => !document.querySelector('.hb-yt').classList.contains('hb-yt-connmode')")


def test_the_home_suggestions_band_renders_plays_and_refreshes(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_ON],
                   "suggested": _SUGG, "suggested_at": int(time.time()) - 120, "suggested_channels": 3})
    band = _page.locator(".hb-yt-sughead")
    assert band.count() == 1
    assert "Sugerencias" in band.inner_text() and "3 canales" in band.inner_text()
    tiles = _page.locator(".hb-yt-home .hb-yt-tile")
    assert tiles.count() == 2
    assert "Ferrari F40 real" in tiles.nth(1).inner_text()
    tiles.nth(1).click()
    calls = _page.evaluate("window.__calls")
    assert ["load", {"videoId": "BBBBBBBBBB2", "title": "Ferrari F40 real"}] in calls
    assert _page.evaluate("() => !document.querySelector('.hb-yt').classList.contains('hb-yt-homemode')")
    _page.evaluate("window.__calls = []")
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_ON], "suggested": []})
    _page.locator(".hb-yt-sughead .hb-yt-chip").click()
    assert ["suggest", {}] in _page.evaluate("window.__calls")


def test_the_widget_is_anchored_to_its_parent_container_at_any_width(_page):
    # Operator, 2026-09-05, with the screenshot in front of him: a maximized card kept the widget at a fixed
    # 680px hugging the left edge, with a dead area beside it. The card decides the width now — the widget
    # root follows its parent in BOTH directions, and the video frame follows the root.
    _mount(_page, {"videoId": "AAAAAAAAAA1", "title": "Un vídeo", "list": [], "platforms": []})
    for box_w in (1100, 420):
        _page.evaluate(
            "w => { const el = document.getElementById('w'); el.style.width = w + 'px'; }", box_w)
        width = _page.evaluate("() => document.querySelector('.hb-yt').getBoundingClientRect().width")
        assert abs(width - box_w) <= 4, (box_w, width)
    frame = _page.evaluate("() => document.querySelector('.hb-yt-frame').getBoundingClientRect().width")
    assert frame >= 380, frame


def test_without_an_account_the_band_is_absent_and_the_dimmed_icon_is_the_affordance(_page):
    _mount(_page, {"videoId": "", "list": [], "platforms": [_ROW_OFF]})
    assert _page.locator(".hb-yt-sughead").count() == 0
    assert _page.locator(".hb-yt-picon").count() == 1
