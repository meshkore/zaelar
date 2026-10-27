"""V2-823 — the apps launcher on the phone lives in the ☰ menu, RENDERED at 375px with touch.

The operator's decision (2026-10-27): «En el móvil, el lanzador de aplicaciones va dentro del menú ☰.» The menu gets
an «Apps» entry that shows the same list as the desk's apps window (System · Custom) and the same per-app page —
owner, created, licence, what it does, connectors, ONLY the fields the manifest declares — with an «Open» button.
On a touch screen a tap selects and shows the page (there is no double click); «Open» opens the app on the deck and
closes the menu. Every control respects the shell's 44px touch floor (CRIT-K31).

Mounted in Chromium (375x812, touch) from the real MenuSheet, DockBar, the real Deck and the real store, with
`/widgets/registry` and `/widgets/<id>/about` answering one app that declares everything, one that declares part and
one of his own that declares nothing — and a stub `clock` widget so the deck has a real card to mount.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))
_SHOTS = Path(os.environ["V2823_SHOTS"]) if os.environ.get("V2823_SHOTS") else None

_REGISTRY = {"registry": [
    {"id": "musica", "name": "Música", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "clock", "name": "Reloj", "aliases": [], "surface": "user", "origin": "builtin", "forked": False},
    {"id": "mi-dia", "name": "Mi día", "aliases": [], "surface": "user", "origin": "user", "forked": False},
    {"id": "chat", "name": "Chat", "aliases": [], "surface": "system", "origin": "system"},
]}
_PAGES = {
    "musica": {"id": "musica", "name": "Música", "origin": "builtin", "owner": "Zaelar", "created": "2026-07-24",
               "licence": "SUL-1.0", "about": "Un reproductor de música.",
               "connectors": [{"id": "spotify", "label": "Spotify", "connected": True},
                              {"id": "youtube-music", "label": "YouTube Music", "connected": False}]},
    "clock": {"id": "clock", "name": "Reloj", "origin": "builtin", "owner": "Zaelar", "licence": "SUL-1.0",
              "about": "Un reloj grande."},
    "mi-dia": {"id": "mi-dia", "name": "Mi día", "origin": "user"},
}
_CLOCK_JS = "export function render(el) { el.innerHTML = '<p class=\"stub-clock\">RELOJ</p>'; }"

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


def _widgets(route):
    path = route.request.url.split("?")[0].split("/widgets", 1)[1]
    js = lambda body: route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    if path in ("", "/"):
        return js({"widgets": [{"id": w["id"]} for w in _REGISTRY["registry"]]})
    if path == "/registry":
        return js(_REGISTRY)
    if path.endswith("/about"):
        page = _PAGES.get(path.split("/")[1])
        return route.fulfill(status=200 if page else 404, content_type="application/json",
                             body=json.dumps(page or {"error": "unknown widget"}))
    if path == "/clock/data":
        return js({})
    if path == "/clock/widget.js":
        return route.fulfill(status=200, content_type="text/javascript", body=_CLOCK_JS)
    return js({})


@pytest.fixture(scope="module")
def phone():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    es = json.dumps({"strings": _ES})
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            ctx = b.new_context(viewport={"width": 375, "height": 812}, has_touch=True)
            pg = ctx.new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            # The catch-all FIRST: Playwright gives the LAST matching route priority.
            pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            pg.route(lambda url: "/widgets" in url and "/frontend/" not in url, _widgets)
            pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=es))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async () => {
                for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
                                 '/frontend/app/core/components.css', '/frontend/mobile/app/styles.css']) {
                  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
                await new Promise(r => setTimeout(r, 300));
                const i18n = await import('/frontend/app/core/i18n.js?v=1');
                await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
                const store = await import('/frontend/app/core/store.js?v=2');
                store.setLang && store.setLang('es');
                const stage = document.createElement('div'); stage.id = 'zm-deck-wrap'; document.body.append(stage);
                const { Deck } = await import('/frontend/mobile/app/shell/Deck.js?v=5');
                window.__deck = new Deck(stage);
                const { MenuSheet } = await import('/frontend/mobile/app/shell/MenuSheet.js?v=2');
                const { DockBar } = await import('/frontend/mobile/app/shell/DockBar.js?v=4');
                document.body.append(MenuSheet(), DockBar());
                window.__store = store;
                window.__opened = [];
                document.addEventListener('hb:open-card', e => window.__opened.push(e.detail.id));
            }""")
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


# The right edge of the furthest-reaching box inside the menu sheet: a launcher that overflows 375px pushes the
# sheet sideways. (The document's own scrollWidth is the static server's directory listing here, not the shell.)
_WIDEST = ("Math.max(...[document.querySelector('.zm-menu'), ...document.querySelectorAll('.zm-menu *')]"
           ".map(e => e.getBoundingClientRect().right))")


def _menu_to_apps(pg):
    pg.evaluate("() => { window.__store.setMobileMenuOpen(false); window.__store.setMobileMenuOpen(true); "
                "window.__opened = []; }")
    pg.wait_for_selector(".zm-menu.open .zm-apps-entry .zm-row", timeout=5000)
    pg.wait_for_timeout(300)                      # the sheet's slide-up, so the tap lands on the row
    if _SHOTS and not (_SHOTS / "phone-menu.png").exists():
        pg.screenshot(path=str(_SHOTS / "phone-menu.png"))
    pg.tap(".zm-menu .zm-apps-entry .zm-row")
    pg.wait_for_selector(".zm-menu .zm-apps:not(.is-off) .aw-row", timeout=5000)


def _tap_app(pg, wid, name):
    pg.tap(f".zm-menu .zm-apps .aw-row[data-app='{wid}']")
    pg.wait_for_function("n => (document.querySelector('.zm-menu .zm-apps-page .aw-title') || {}).textContent === n",
                         arg=name, timeout=5000)


def _fields(pg):
    return pg.evaluate("() => [...document.querySelectorAll('.zm-menu .zm-apps-page [data-field]')]"
                       ".map(e => e.dataset.field).sort()")


def _box(pg, sel):
    return pg.evaluate("s => { const r = document.querySelector(s).getBoundingClientRect(); "
                       "return {w: r.width, h: r.height}; }", sel)


def test_the_menu_entry_lists_the_apps_in_system_and_custom(phone):
    _menu_to_apps(phone)
    got = phone.evaluate("""() => { const p = document.querySelector('.zm-menu .zm-apps');
        return {ids: [...p.querySelectorAll('.aw-row')].map(r => r.dataset.app),
                groups: [...p.querySelectorAll('.aw-group')].map(g => g.textContent),
                title: p.querySelector('.zm-apps-t').textContent,
                sheet: (() => { const m = document.querySelector('.zm-menu');
                    return {pos: getComputedStyle(m).position, bottom: m.getBoundingClientRect().bottom, vh: innerHeight}; })(),
                rowsHidden: getComputedStyle(document.querySelector('.zm-menu .zm-rows')).display === 'none',
                minRow: Math.min(...[...p.querySelectorAll('.aw-row')].map(r => r.getBoundingClientRect().height)),
                width: _WIDEST()}; }""".replace("_WIDEST()", _WIDEST))
    assert got["ids"] == ["musica", "clock", "mi-dia"], f"the apps and only the apps, System then Custom: {got}"
    assert got["groups"] == [_ES["chat.appsSystem"], _ES["chat.appsCustom"]], got
    assert got["title"] == _ES["mobile.apps"]
    assert got["rowsHidden"], "the menu's own rows step aside while the launcher is up"
    assert got["sheet"]["pos"] == "fixed" and got["sheet"]["bottom"] <= got["sheet"]["vh"], \
        f"the ☰ sheet must float over the deck, inside the screen: {got['sheet']}"
    assert got["minRow"] >= 44, f"an app row is under the touch floor: {got}"
    assert got["width"] <= 375, f"the sheet pushes the page sideways: {got}"
    assert phone.evaluate("() => window.__opened") == []
    if _SHOTS:
        phone.screenshot(path=str(_SHOTS / "phone-apps-list.png"))


def test_a_tap_shows_the_page_with_only_the_declared_fields(phone):
    _menu_to_apps(phone)
    _tap_app(phone, "musica", "Música")
    assert phone.evaluate("() => window.__opened") == [], "a tap on a row shows its page; it opens nothing"
    assert _fields(phone) == ["about", "connectors", "created", "licence", "owner"]
    page = phone.evaluate("""() => { const p = document.querySelector('.zm-menu .zm-apps-page');
        const v = f => { const e = p.querySelector(`[data-field="${f}"] dd`); return e ? e.textContent : null; };
        return {owner: v('owner'), licence: v('licence'), created: v('created'),
                conns: [...p.querySelectorAll('.aw-conn')].map(c => c.dataset.conn),
                list: !!document.querySelector('.zm-menu .zm-apps-list .aw-row')}; }""")
    assert page["owner"] == "Zaelar" and page["licence"] == _ES["apps.licence.SUL-1.0"], page
    assert "julio" in page["created"], page
    assert page["conns"] == ["spotify", "youtube-music"], page
    assert not page["list"], "one screen at a time: the page replaces the list"
    for sel in (".zm-menu .zm-apps-page .aw-open", ".zm-menu .zm-apps-back"):
        b = _box(phone, sel)
        assert b["h"] >= 44 and b["w"] >= 44, f"{sel} is under the touch floor: {b}"
    assert phone.evaluate("() => " + _WIDEST) <= 375, "the page pushes the sheet sideways"
    if _SHOTS:
        phone.screenshot(path=str(_SHOTS / "phone-apps-page.png"))
    # ‹ goes back to the list, and the other pages declare less — the page shows exactly that.
    phone.tap(".zm-menu .zm-apps-back")
    phone.wait_for_selector(".zm-menu .zm-apps-list .aw-row", timeout=5000)
    _tap_app(phone, "clock", "Reloj")
    assert _fields(phone) == ["about", "licence", "owner"], "no created date and no connectors were declared"
    phone.tap(".zm-menu .zm-apps-back")
    _tap_app(phone, "mi-dia", "Mi día")
    assert _fields(phone) == ["custom"], "an app that declares nothing gets its name and its Custom mark"
    text = phone.evaluate("() => document.querySelector('.zm-menu .zm-apps-page').textContent")
    for word in (_ES["appsWin.owner"], _ES["appsWin.created"], _ES["appsWin.licence"], _ES["appsWin.about"],
                 _ES["appsWin.connectors"]):
        assert word not in text, f"«{word}» is on a page that declares no such field"


def test_open_puts_the_app_on_the_deck_and_closes_the_menu(phone):
    _menu_to_apps(phone)
    _tap_app(phone, "clock", "Reloj")
    phone.tap(".zm-menu .zm-apps-page .aw-open")
    phone.wait_for_function("() => !window.__store.mobileMenuOpen()", timeout=5000)
    phone.wait_for_selector("#zm-deck-wrap .zm-card[data-wid='clock'] .stub-clock", timeout=5000)
    assert phone.evaluate("() => window.__opened") == ["clock"], "one open, through the one door"
    assert phone.evaluate("() => window.__deck.list()") == ["clock"], "the deck holds the app"
    if _SHOTS:
        phone.wait_for_timeout(400)
        phone.screenshot(path=str(_SHOTS / "phone-apps-opened.png"))
    # The ☰ opens on its own rows again, never on the launcher it was closed from.
    phone.evaluate("() => window.__store.setMobileMenuOpen(true)")
    phone.wait_for_timeout(100)
    assert phone.evaluate("() => getComputedStyle(document.querySelector('.zm-menu .zm-rows')).display") != "none"
    assert phone.evaluate("() => document.querySelector('.zm-menu .zm-apps').classList.contains('is-off')")
    phone.evaluate("() => window.__store.setMobileMenuOpen(false)")


def test_no_script_error(phone):
    assert not phone._errors, phone._errors
