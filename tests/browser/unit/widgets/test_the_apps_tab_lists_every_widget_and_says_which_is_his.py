"""V2-761 — the wall's «Apps» tab: the widget catalogue, Sistema · Custom, RENDERED.

The operator's spec: a new tab beside Conectores whose icon reads as «the list of apps of an operating system»
and must not be confused with the widget rail's arrange buttons; inside it two sub-tabs, Sistema (the shipped
widgets) and Custom (the ones he made); one box per widget with its name, in one or two columns; and a
SYSTEM widget he has customised drawn pale, with a «Custom» mark over it, while the copy he actually runs is
listed under Custom.

Rendered in Chromium against the real ChatWall, store and stylesheet, with `/widgets/registry` answering a
catalogue that carries every case: two plain shipped widgets, a shipped one he forked (`youtube`, `forked`
with origin `user` — exactly what `generator._fork_shipped` stamps), and one he built from scratch.
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
_ES = json.loads((ENGINE / "i18n/bundles/es.json").read_text(encoding="utf-8"))

_REGISTRY = {"registry": [
    {"id": "musica", "name": "Música", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "agenda", "name": "Agenda", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "youtube", "name": "YouTube", "aliases": [], "surface": "user", "origin": "user", "forked": True},
    {"id": "canvas-shows-day", "name": "Mi día", "aliases": [], "surface": "user", "origin": "user", "forked": False},
    {"id": "chat", "name": "Chat", "aliases": [], "surface": "system", "origin": "system"},
]}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def wall():
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
            # The catch-all FIRST: Playwright gives the LAST matching route priority, so registered after the
            # bundle route it would swallow the bundle and every string would render as its raw key.
            pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            pg.route("**/widgets/registry", lambda r: r.fulfill(status=200, content_type="application/json",
                                                                 body=json.dumps(_REGISTRY)))
            pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=es))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async () => {
                for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
                  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
                await new Promise(r => setTimeout(r, 300));
                const i18n = await import('/frontend/app/core/i18n.js?v=1');
                await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
                const store = await import('/frontend/app/core/store.js?v=2');
                const m = await import('/frontend/app/components/ChatWall.js?v=5');
                document.body.append(m.ChatWall());
                window.__store = store;
                window.__opened = [];
                document.addEventListener('hb:open-card', e => window.__opened.push(e.detail.id));
                store.setChatTab('chat'); store.setChatOpen(true);
            }""")
            pg.wait_for_selector("#chatwall.open", timeout=5000)
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _open_apps(pg, tab="apps"):
    pg.evaluate("t => { window.__store.setChatTab('chat'); window.__store.setChatTab(t); }", tab)
    pg.wait_for_selector(".cw-apps .ap-tile", timeout=5000)


def _tiles(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('.cw-apps .ap-tile')].map(t => ({
        id: t.dataset.app, name: t.querySelector('.ap-name').textContent,
        customized: t.classList.contains('ap-customized'),
        badge: (t.querySelector('.ap-badge') || {}).textContent || '',
        thumbColor: getComputedStyle(t.querySelector('.ap-thumb')).color,
        visible: t.getBoundingClientRect().width > 0, top: t.getBoundingClientRect().top,
        left: t.getBoundingClientRect().left }))""")


def test_the_wall_has_an_apps_tab_whose_icon_is_a_grid_of_dots_not_the_rails_squares(wall):
    info = wall.evaluate("""() => { const b = [...document.querySelectorAll('.cw-tab')].find(x =>
        x.textContent.includes(%s)); if (!b) return null;
        return {dots: b.querySelectorAll('svg circle').length, rects: b.querySelectorAll('svg rect').length}; }"""
                         % json.dumps(_ES["chat.tabApps"]))
    assert info, "there is no «Apps» tab button on the wall"
    assert info["dots"] == 9 and info["rects"] == 0, \
        f"the icon must be the 3×3 launcher of dots (the rail's arrange buttons are squares): {info}"


def test_clicking_the_tab_opens_the_catalogue(wall):
    wall.evaluate("() => window.__store.setChatTab('chat')")
    wall.evaluate("""() => [...document.querySelectorAll('.cw-tab')].find(x =>
        x.textContent.includes(%s)).click()""" % json.dumps(_ES["chat.tabApps"]))
    wall.wait_for_selector(".cw-apps .ap-tile", timeout=5000)
    assert wall.evaluate("() => document.querySelector('#chatwall').classList.contains('tab-apps')")


def test_sistema_lists_every_shipped_widget_and_marks_the_one_he_customised(wall):
    _open_apps(wall)
    tiles = {t["id"]: t for t in _tiles(wall)}
    assert set(tiles) == {"musica", "agenda", "youtube"}, \
        f"Sistema must hold the shipped widgets — his own is not one, a native surface is not one: {sorted(tiles)}"
    assert all(t["visible"] for t in tiles.values())
    yt = tiles["youtube"]
    assert yt["customized"] and yt["badge"] == _ES["chat.appsCustomBadge"], \
        "a forked system widget must carry the «Custom» mark in Sistema"
    assert not tiles["musica"]["customized"] and tiles["musica"]["badge"] == ""
    assert yt["thumbColor"] != tiles["musica"]["thumbColor"], \
        "the customised one must be drawn pale, not in the colour of a native widget"


def test_custom_lists_his_widgets_including_the_fork(wall):
    _open_apps(wall, "apps-custom")
    ids = {t["id"] for t in _tiles(wall)}
    assert ids == {"youtube", "canvas-shows-day"}, f"Custom must hold what he built and what he forked: {ids}"
    assert not any(t["customized"] for t in _tiles(wall)), "under Custom the fork is HIS widget, not a pale one"


def test_the_grid_is_two_columns(wall):
    _open_apps(wall)
    tiles = _tiles(wall)
    lefts = sorted({round(t["left"]) for t in tiles})
    assert len(lefts) == 2, f"«en una o dos columnas»: the tiles sit on {len(lefts)} columns ({lefts})"


def test_a_tile_opens_its_widget_through_the_one_door(wall):
    _open_apps(wall)
    wall.evaluate("() => { window.__opened = []; }")
    wall.click(".cw-apps .ap-tile[data-app='musica']")
    assert wall.evaluate("() => window.__opened") == ["musica"]


@pytest.mark.parametrize("word,scope", [("apps", "system"), ("widgets", "system"), ("aplicaciones", "system"),
                                        ("apps-custom", "custom"), ("custom", "custom")])
def test_the_tab_answers_to_apps_and_widgets_alike(wall, word, scope):
    wall.evaluate("w => { window.__store.setChatTab('chat'); window.__store.setChatTab(w); }", word)
    got = wall.evaluate("() => [window.__store.chatTab(), window.__store.appsScope()]")
    assert got == ["apps", scope], f"setChatTab({word!r}) landed on {got}"


@pytest.mark.parametrize("width", [260, 300, 320, 340, 400, 600, 800])
def test_every_tab_is_reachable_at_every_width_of_the_wall(wall, width):
    """A sixth-width tab behind a hidden scrollbar is a tab he cannot find. Measured before this pass: at the
    default 320px float the strip needed 183px and got 132 — Apps and Conectores sat off the edge."""
    wall.evaluate("w => { document.querySelector('#chatwall').style.width = w + 'px'; }", width)
    wall.wait_for_timeout(200)
    hidden = wall.evaluate("""() => { const t = document.querySelector('.cw-tabs'), tr = t.getBoundingClientRect();
        return [...t.querySelectorAll('.cw-tab')].filter(b => { const r = b.getBoundingClientRect();
            return r.right > tr.right + 1 || r.left < tr.left - 1; }).length; }""")
    wall.evaluate("() => { document.querySelector('#chatwall').style.width = ''; }")
    assert hidden == 0, f"at {width}px, {hidden} tab(s) are off the edge of the strip"


def test_no_script_error(wall):
    assert not wall._errors, wall._errors
