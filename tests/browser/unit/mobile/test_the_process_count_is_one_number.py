"""The live count of running processes is ONE number on the desktop's bar and the phone's dock (V2-822), RENDERED.

The operator's decision 4 (2026-10-27): a live, interactive counter of running processes on mobile (the bottom bar)
AND desktop, the SAME number on both, read from the engine; tapping it goes to the processes view. One component
(`ProcessCount.js`) reads one number (`store.liveProcessCount`) — the engine's live board, moved by its SSE `task`
events. An event-built chip cannot know whether its task is the engine's own (a memory pass): when a process starts
or ends the count re-reads the board, so it settles on the board's number instead of counting what the panel hides.

Mounted in Chromium from the real WidgetRail (1280 px) and DockBar (375 px) with the real store and SSE router.
Disarms: the SSE router not re-reading the board on start → red; the dock without the count → red.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))
_NOW = int(time.time())
_ROWS = [{"id": "row-1", "session": "1", "title": "Monitores", "state": "running", "started_at": _NOW - 60},
         {"id": "row-2", "session": "2", "title": "Tu estilo", "state": "running", "started_at": _NOW - 30}]
_SHOTS = Path(os.environ.get("V2822_SHOTS", "")) if os.environ.get("V2822_SHOTS") else None

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def server():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    yield port
    srv.terminate(); srv.wait(timeout=10)


def _page(pw, port, width):
    pg = pw.chromium.launch().new_page(viewport={"width": width, "height": 700})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/tasks?*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                   body=json.dumps({"tasks": _ROWS})))
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                        body=json.dumps({"strings": _ES})))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg.evaluate("""async () => {
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
                         '/frontend/app/core/components.css', '/frontend/app/styles.css',
                         '/frontend/mobile/app/styles.css']) {
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
        window.__store = await import('/frontend/app/core/store.js?v=2');
        window.__sse = await import('/frontend/app/services/sse.js?v=6');
        window.__store.setAgentState && window.__store.setAgentState('live'); }""")
    pg._errors = errors
    return pg


_COUNT = """(sel) => { const p = document.querySelector(sel);
    return p ? {n: p.dataset.n, shown: getComputedStyle(p).display !== 'none', text: p.innerText.trim()} : null; }"""


def _one_number(pg, sel):
    pg.evaluate("() => window.__store.fetchTasks()")
    pg.wait_for_function(f"() => (document.querySelector('{sel}') || {{dataset: {{}}}}).dataset.n === '2'", timeout=5000)
    c = pg.evaluate(_COUNT, sel)
    assert c["shown"] and c["text"] == "2", f"the board's two processes: {c}"
    # An engine-internal worker starts: its SSE event builds a chip before anyone knows it is internal…
    pg.evaluate("() => window.__sse.routeEvent({}, {kind: 'task', label: 'start', id: '99', text: 'memoria'})")
    # …and the count settles on the board's number, which never lists it.
    pg.wait_for_function(f"() => document.querySelector('{sel}').dataset.n === '2'", timeout=3000)
    pg.wait_for_timeout(700)
    assert pg.evaluate(_COUNT, sel)["n"] == "2", "the count is the board's, not the event's"


def test_the_desktop_bar_counts_and_opens_the_processes(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg = _page(pw, server, 1280)
        pg.evaluate("""async () => { const m = await import('/frontend/app/components/WidgetRail.js?v=2');
            const el = m.WidgetRail ? m.WidgetRail() : null; if (el && !el.isConnected) document.body.append(el); }""")
        _one_number(pg, "#wrail .pcount")
        if _SHOTS:
            pg.locator("#wrail").screenshot(path=str(_SHOTS / "counter-desktop.png"))
        pg.click("#wrail .pcount")
        got = pg.evaluate("() => ({open: window.__store.chatOpen(), tab: window.__store.chatTab()})")
        assert got == {"open": True, "tab": "procesos"}, f"a tap opens the processes view: {got}"
        assert not pg._errors, pg._errors


def test_the_phone_dock_counts_the_same_and_opens_the_processes(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg = _page(pw, server, 375)
        pg.evaluate("""async () => { const m = await import('/frontend/mobile/app/shell/DockBar.js?v=4');
            document.body.append(m.DockBar()); }""")
        _one_number(pg, ".zm-dock .zm-menu .pcount")
        label = pg.evaluate("() => document.querySelector('.zm-menu').getAttribute('aria-label')")
        assert label == _ES["mobile.menu_processes"].replace("{n}", "2"), label
        assert pg.evaluate("() => document.documentElement.scrollWidth") <= 375, "the dock keeps its width"
        if _SHOTS:
            pg.locator(".zm-dock").screenshot(path=str(_SHOTS / "counter-375.png"))
        pg.click(".zm-dock .zm-menu")
        assert pg.evaluate("() => window.__store.mobileMenuOpen()") is True, "a tap opens the menu, its processes view"
        assert not pg._errors, pg._errors
