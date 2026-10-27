"""V2-823 — the apps window, RENDERED: the rail's corner icon opens it, one click shows a page, two open the app.

The operator's request: bottom right of the desk, beside the hide / show / re-arrange tools, an «apps» icon that
opens a WINDOW over the desk (the desk is not emptied) — the apps on the left, the selected app's page on the
right (owner, created, licence, what it does, its connectors, an «Open» button). A single click selects and shows
the page; a double click opens the app and closes the window. And the page never invents: a field the manifest
does not declare is not on it.

Rendered in Chromium against the real WidgetRail, AppsWindow, store and stylesheets, with `/widgets/registry` and
`/widgets/<id>/about` answering one app that declares everything and one that declares nothing.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))

_REGISTRY = {"registry": [
    {"id": "musica", "name": "Música", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "clock", "name": "Reloj", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "mi-dia", "name": "Mi día", "aliases": [], "surface": "user", "origin": "user", "forked": False},
    {"id": "chat", "name": "Chat", "aliases": [], "surface": "system", "origin": "system"},
]}
# `musica` declares every field; `mi-dia` (his own, generated) declares none but its name.
_PAGES = {
    "musica": {"id": "musica", "name": "Música", "origin": "builtin", "owner": "Zaelar", "created": "2026-07-24",
               "licence": "SUL-1.0", "about": "Un reproductor de música.",
               "connectors": [{"id": "spotify", "label": "Spotify", "connected": True},
                              {"id": "youtube-music", "label": "YouTube Music", "connected": False}]},
    "clock": {"id": "clock", "name": "Reloj", "origin": "builtin", "owner": "Zaelar", "licence": "SUL-1.0",
              "about": "Un reloj grande."},
    "mi-dia": {"id": "mi-dia", "name": "Mi día", "origin": "user"},
}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


pytest.importorskip("playwright.sync_api")


def _about(route):
    wid = route.request.url.rstrip("/").split("/")[-2]
    page = _PAGES.get(wid)
    route.fulfill(status=200 if page else 404, content_type="application/json",
                  body=json.dumps(page or {"error": "unknown widget"}))


@pytest.fixture(scope="module")
def desk():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    es = json.dumps({"strings": _ES})
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 800})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            # The catch-all FIRST: Playwright gives the LAST matching route priority.
            pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            pg.route("**/widgets/registry", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                 body=json.dumps(_REGISTRY)))
            pg.route("**/widgets/*/about", _about)
            pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=es))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async () => {
                for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
                                 '/frontend/app/core/components.css', '/frontend/app/styles.css']) {
                  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
                await new Promise(r => setTimeout(r, 300));
                const i18n = await import('/frontend/app/core/i18n.js?v=1');
                await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
                const store = await import('/frontend/app/core/store.js?v=2');
                store.setLang && store.setLang('es');
                const surfaces = await import('/frontend/app/core/system-surfaces.js?v=5');
                const pick = id => surfaces.SYSTEM_SURFACES.find(s => s.id === id).comp();
                document.body.append(pick('wrail'), pick('apps-window'));
                window.__store = store;
                window.__opened = [];
                document.addEventListener('hb:open-card', e => window.__opened.push(e.detail.id));
            }""")
            pg.wait_for_selector("#wrail .wr-apps", timeout=5000)
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _open(pg):
    pg.evaluate("() => { window.__store.setAppsWindowOpen(false); window.__opened = []; }")
    pg.click("#wrail .wr-apps")
    pg.wait_for_selector("#appswin.open .aw-row", timeout=5000)
    pg.wait_for_selector("#appswin .aw-page .aw-title", timeout=5000)


def _select(pg, wid, name):
    pg.click(f"#appswin .aw-row[data-app='{wid}']")
    pg.wait_for_function("n => (document.querySelector('#appswin .aw-title') || {}).textContent === n", arg=name,
                         timeout=5000)


def _fields(pg):
    return pg.evaluate("() => [...document.querySelectorAll('#appswin .aw-page [data-field]')]"
                       ".map(e => e.dataset.field).sort()")


def test_the_apps_icon_sits_in_the_desks_corner_with_the_layout_tools(desk):
    info = desk.evaluate("""() => { const tools = document.querySelector('#wrail .wr-tools');
        const btns = [...tools.querySelectorAll('button')].map(b => b.className.split(' ')[0]);
        const r = tools.querySelector('.wr-apps').getBoundingClientRect();
        return {btns, right: r.right, vw: innerWidth, title: tools.querySelector('.wr-apps').title}; }""")
    assert info["btns"] == ["wr-hide", "wr-show", "wr-compact", "wr-fitall", "wr-apps"], info
    assert info["vw"] - info["right"] < 40, f"the apps icon is not in the bottom-right corner: {info}"
    assert info["title"] == _ES["rail.apps"]


def test_the_icon_opens_a_window_over_the_desk_not_a_full_screen(desk):
    _open(desk)
    geo = desk.evaluate("""() => { const s = document.querySelector('#appswin .aw-shell').getBoundingClientRect();
        const rail = document.querySelector('#wrail').getBoundingClientRect();
        const ovl = document.querySelector('#appswin').getBoundingClientRect();
        return {w: s.width, h: s.height, vw: innerWidth, vh: innerHeight, ovlBottom: ovl.bottom, railTop: rail.top,
                on: document.querySelector('#wrail .wr-apps').classList.contains('on')}; }""")
    assert geo["w"] < geo["vw"] and geo["h"] < geo["vh"] - 58, f"the window covers the desk: {geo}"
    assert geo["ovlBottom"] <= geo["railTop"] + 1, f"the window hides the rail: {geo}"
    assert geo["on"], "the rail's apps icon must say the window is open"


def test_the_list_holds_the_apps_and_only_the_apps(desk):
    _open(desk)
    ids = desk.evaluate("() => [...document.querySelectorAll('#appswin .aw-row')].map(r => r.dataset.app)")
    assert sorted(ids) == ["clock", "mi-dia", "musica"], f"a native surface is not an app: {ids}"
    assert desk.evaluate("() => [...document.querySelectorAll('#appswin .aw-row')].every(r => r.querySelector('.aw-icon svg'))")


def test_a_single_click_shows_the_page_and_opens_nothing(desk):
    _open(desk)
    _select(desk, "musica", "Música")
    assert desk.evaluate("() => window.__opened") == [], "a single click must not open the app"
    assert desk.evaluate("() => document.querySelector('#appswin').classList.contains('open')")
    assert desk.evaluate("() => document.querySelector(\"#appswin .aw-row[data-app='musica']\").classList.contains('is-selected')")
    page = desk.evaluate("""() => { const p = document.querySelector('#appswin .aw-page');
        const v = f => { const e = p.querySelector(`[data-field="${f}"] dd`); return e ? e.textContent : null; };
        return {owner: v('owner'), licence: v('licence'), created: v('created'),
                about: (p.querySelector('[data-field="about"] p') || {}).textContent,
                conns: [...p.querySelectorAll('.aw-conn')].map(c => [c.dataset.conn, c.querySelector('.hb-badge').textContent]),
                open: (p.querySelector('.aw-open') || {}).textContent}; }""")
    assert page["owner"] == "Zaelar"
    assert page["licence"] == _ES["apps.licence.SUL-1.0"], "the licence id must be shown as its translated name"
    assert "2026" in page["created"] and "julio" in page["created"], page["created"]
    assert page["about"] == "Un reproductor de música."
    assert page["conns"] == [["spotify", _ES["appsWin.connected"]], ["youtube-music", _ES["appsWin.notConnected"]]]
    assert page["open"] == _ES["appsWin.open"]


def test_the_page_shows_only_the_fields_the_manifest_declares(desk):
    _open(desk)
    _select(desk, "musica", "Música")
    assert _fields(desk) == ["about", "connectors", "created", "licence", "owner"]
    _select(desk, "clock", "Reloj")
    assert _fields(desk) == ["about", "licence", "owner"], "no created date and no connectors were declared"
    _select(desk, "mi-dia", "Mi día")
    assert _fields(desk) == ["custom"], "an app that declares nothing gets a name and its Custom mark, nothing invented"
    text = desk.evaluate("() => document.querySelector('#appswin .aw-page').textContent")
    for word in (_ES["appsWin.owner"], _ES["appsWin.created"], _ES["appsWin.licence"], _ES["appsWin.about"],
                 _ES["appsWin.connectors"]):
        assert word not in text, f"«{word}» is on a page that declares no such field"


def test_a_double_click_opens_the_app_through_the_one_door_and_closes_the_window(desk):
    _open(desk)
    desk.dblclick("#appswin .aw-row[data-app='clock']")
    desk.wait_for_function("() => !document.querySelector('#appswin').classList.contains('open')", timeout=5000)
    assert desk.evaluate("() => window.__opened") == ["clock"]
    assert not desk.evaluate("() => document.querySelector('#wrail .wr-apps').classList.contains('on')")


def test_the_open_button_opens_the_selected_app_and_closes_the_window(desk):
    _open(desk)
    _select(desk, "musica", "Música")
    desk.click("#appswin .aw-open")
    desk.wait_for_function("() => !document.querySelector('#appswin').classList.contains('open')", timeout=5000)
    assert desk.evaluate("() => window.__opened") == ["musica"]


def test_escape_and_the_icon_close_it_without_opening_anything(desk):
    _open(desk)
    desk.keyboard.press("Escape")
    desk.wait_for_function("() => !document.querySelector('#appswin').classList.contains('open')", timeout=5000)
    _open(desk)
    desk.click("#wrail .wr-apps")
    desk.wait_for_function("() => !document.querySelector('#appswin').classList.contains('open')", timeout=5000)
    assert desk.evaluate("() => window.__opened") == []


def test_no_script_error(desk):
    assert not desk._errors, desk._errors
