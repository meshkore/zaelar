"""The LEFT BAR opens the chat wall NESTED to the left; the ORB floats it unless it is already docked. Rendered.

The operator (2026-10-04), with a screenshot of a freshly initialised agent whose wall had opened as a floating
box from the bar's arrow:

    «por defecto, al inicializar un agente, cuando abro la barra izquierda se abre anidada a la izquierda, no
    en ventana flotante. Solo en ventana flotante desde el orbe central, siempre que no se haya abierto ya y
    pegado a la izquierda. En ese caso respetamos el estado actual de UI y abrimos ahí».

Until now the wall's shape was only its own memory (`hb_chat_dock` / `hb_chat_float`), blind to WHO opened it:
on a fresh install both the bar's arrow and the orb's lid gave the same floating box. Now the opener leaves a
hint in the store (`openChatFrom`), the wall reads it ONCE on the open it belongs to, and:
  · from the BAR, a wall with no docked shape docks to the LEFT column;
  · from the ORB, a docked wall stays docked (respected) and anything else floats, as the saved float does.
Rendered against the real ChatWall, WidgetRail, store and stylesheet in Chromium — the wall's shape is CSS
classes plus the reserved column (`--chatdock-l`), and a plain-variable binding has fooled a grep before (V2-608).
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
_EN = json.loads((ENGINE / "i18n/bundles/en.json").read_text(encoding="utf-8"))

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _fresh_page(browser, port):
    """A page with NO remembered shape: a freshly initialised agent's first session."""
    pg = browser.new_page(viewport={"width": 1280, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"strings": _EN})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        localStorage.clear();
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const wall = await import('/frontend/app/components/ChatWall.js?v=5');
        const rail = await import('/frontend/app/components/WidgetRail.js?v=1');
        document.body.append(wall.ChatWall());
        document.body.append(rail.WidgetRail());
        window.__store = store;
    }""")
    pg.wait_for_selector("#chatwall", state="attached", timeout=5000)
    pg._errors = errors
    return pg


def _shape(pg):
    return pg.evaluate("""() => { const w = document.getElementById('chatwall');
        return {open: w.classList.contains('open'), docked: w.classList.contains('docked'),
                left: w.classList.contains('dock-left'), body: document.body.classList.contains('chatdock-l'),
                col: getComputedStyle(document.documentElement).getPropertyValue('--chatdock-l').trim()}; }""")


def test_from_the_bar_a_fresh_wall_opens_nested_to_the_left(browser_and_port):
    b, port = browser_and_port
    pg = _fresh_page(b, port)
    assert not _shape(pg)["open"]
    pg.click("#wrail .wr-fold")                      # the bar's arrow — the real button, the real handler
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    s = _shape(pg)
    assert s["docked"] and s["left"], f"from the bar the wall must be a LEFT column, not a floating box: {s}"
    assert s["body"] and s["col"] not in ("", "0px"), f"a docked wall reserves its column for the desk: {s}"
    assert not pg._errors, pg._errors
    pg.close()


def test_from_the_orb_a_fresh_wall_floats(browser_and_port):
    b, port = browser_and_port
    pg = _fresh_page(b, port)
    pg.evaluate("() => window.__store.openChatFrom('orb')")    # what the orb's lid button calls
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    s = _shape(pg)
    assert not s["docked"], f"from the orb a wall with no docked shape FLOATS: {s}"
    assert s["col"] in ("", "0px") and not s["body"], f"a floating wall reserves no column: {s}"
    pg.close()


def test_the_orb_respects_a_wall_already_docked_to_the_left(browser_and_port):
    b, port = browser_and_port
    pg = _fresh_page(b, port)
    pg.click("#wrail .wr-fold")                                 # docked left by the bar…
    pg.wait_for_selector("#chatwall.open.docked", timeout=5000)
    pg.evaluate("() => window.__store.setChatOpen(false)")     # …closed (the × does exactly this)…
    pg.wait_for_selector("#chatwall:not(.open)", state="attached", timeout=5000)
    pg.evaluate("() => window.__store.openChatFrom('orb')")     # …and reopened from the orb
    pg.wait_for_selector("#chatwall.open", timeout=5000)
    s = _shape(pg)
    assert s["docked"] and s["left"], f"the orb must respect the docked shape and open THERE: {s}"
    pg.close()


def test_the_orbs_lid_button_says_where_it_opens_from():
    """The seam the rendered tests cannot click without the whole orb: its lid button names the opener."""
    orb = (ENGINE / "frontend/app/components/Orb.js").read_text(encoding="utf-8")
    i = orb.index('"data-ctl": "chat"')
    assert 'openChatFrom("orb")' in orb[i:i + 700], "the orb's chat button must open the wall FROM THE ORB"
