"""The processes panel tells a running process, collapsed and expanded, from ONE record (V2-822), RENDERED.

The operator (2026-10-27): the work happens in the background and its progress lives in ONE place — the running
process's entry in the processes panel: three or four lines of what it is doing (the plan ✓ ▸ ·, whether the page
needs him), or, when he opens it, the browser's page and capture, how much it has looked at and the narration
(what the results sheet's «Proceso» tab used to show). Both views paint the same record,
`GET /api/tasks/<id>/process`, derived from the live registry; opening it re-reads nothing.

Rendered in Chromium against the real ChatWall, store, stylesheets and Spanish bundle (desktop), and the real
MenuSheet at 375 px (the phone, which has no processes tab: its menu carries the same entry).
Disarm: `paintEntry` ignoring `open` (always collapsed) → red.

V2-822 (the operator's decision 1): the entry's LAST line says what the process waits on him for — «waiting for you
to sign in» while a window is open for him, «blocked: … without the daemon …» when no window can reach him.
Disarm: `paintWait` not called → red.
"""
from __future__ import annotations

import base64
import json
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
_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
_PLAN = ["Leer tus correos enviados", "Extraer los largos", "Analizar cómo escribes", "Crear el documento",
         "Presentártelo"]
_ROW = {"id": "row-7", "session": "7", "title": "Documento con tu estilo", "goal": "g", "state": "running",
        "started_at": _NOW - 90, "phase": "Analizando cómo escribes", "visible": True}
_REC = {"alive": True, "id": "7", "uid": "row-7", "title": "Documento con tu estilo", "surface": "informe",
        "phase": "Analizando cómo escribes", "plan": _PLAN, "done": 2,
        "phases": ["Leyendo la carpeta de enviados", "Quedan 41 mensajes largos", "Analizando cómo escribes"],
        "browser": {"task_id": "7", "shot": "shot-7.png", "shot_rev": 2, "url": "https://mail.example/sent",
                    "page_title": "Enviados", "awaiting_login": True},
        "harvest": {"pages": 3, "rows": 50, "kept": 41}}

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


def _page(pw, port, width, hits, rec=None):
    pg = pw.chromium.launch().new_page(viewport={"width": width, "height": 800})
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    es = json.dumps({"strings": _ES})

    def process(route):
        hits.append(route.request.url.split("/api/tasks/")[1].split("/")[0])
        route.fulfill(status=200, content_type="application/json", body=json.dumps(rec or _REC))

    def tasks(route):
        scope = route.request.url.split("scope=")[-1].split("&")[0]
        route.fulfill(status=200, content_type="application/json",
                      body=json.dumps({"tasks": [_ROW] if scope == "live" else []}))
    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/tasks?*", tasks)
    pg.route("**/api/tasks/*/process", process)
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=es))
    pg.route("**/widgets/navegador/asset/**", lambda r: r.fulfill(status=200, content_type="image/png", body=_PNG))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    pg._errors = errors
    return pg


_CSS = """for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
                       '/frontend/app/core/components.css', '/frontend/app/styles.css']) {
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
          const i18n = await import('/frontend/app/core/i18n.js?v=1');
          await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');"""

_READ = """() => [...document.querySelectorAll('.pe')].map(n => ({
    steps: [...n.querySelectorAll('.pe-step')].map(s => [s.className.replace('pe-step ', ''), s.innerText]),
    toggle: (n.querySelector('.pe-toggle') || {}).innerText || '',
    need: !!n.querySelector('.pe-plan ~ .pe-need'),
    shot: (n.querySelector('.pe-shot img') || {src: ''}).src,
    stats: [...n.querySelectorAll('.pe-stat span')].map(s => s.innerText),
    lines: [...n.querySelectorAll('.pe-line')].map(s => s.innerText),
    wait: [...n.querySelectorAll('.pe-need[data-wait]')].map(x => [x.dataset.wait, x.innerText]),
    lastIsWait: !!(n.querySelector('.pe-toggle') || {}).previousElementSibling?.dataset?.wait,
    h: Math.round(n.getBoundingClientRect().height)}))"""


@pytest.fixture(scope="module")
def server():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    yield port
    srv.terminate(); srv.wait(timeout=10)


def _check_collapsed_then_expanded(pg, hits):
    pg.wait_for_selector(".pe .pe-step", timeout=5000)
    c = pg.evaluate(_READ)[0]
    assert c["steps"] == [["done", "✓\n" + _PLAN[1]], ["now", "▸\n" + _PLAN[2]], ["next", "·\n" + _PLAN[3]]], \
        f"collapsed = the plan around the step it is on: {c['steps']}"
    assert c["need"], "collapsed still says the page needs him"
    assert c["wait"] == [["auth", _ES["chat.procAwaitingAuth"]]] and c["lastIsWait"], \
        f"the last line says it waits for him to sign in: {c['wait']}"
    assert not (c["shot"] or c["stats"] or c["lines"]), "collapsed shows no capture, harvest or narration"
    assert c["toggle"] == _ES["chat.procMore"]
    before = len(hits)
    pg.click(".pe-toggle")
    e = pg.evaluate(_READ)[0]
    assert len(hits) == before, "opening it re-reads nothing: both views paint the SAME record"
    assert [s[1].split("\n")[-1] for s in e["steps"]] == _PLAN, "expanded = the whole declared plan"
    assert e["shot"].endswith("/widgets/navegador/asset/shot-7.png?v=2"), e["shot"]
    assert e["stats"][:2] == [_ES["chat.procTally.pages"], _ES["chat.procTally.rows"]], e["stats"]
    assert e["lines"][0] == _REC["phases"][-1], "the narration reads newest first"
    assert e["toggle"] == _ES["chat.procLess"] and e["h"] > c["h"]
    assert e["wait"] == c["wait"] and e["lastIsWait"], "expanded, the wait is still its last line"
    assert set(hits) <= {"7", "row-7"}, hits
    assert not pg._errors, pg._errors
    pg.click(".pe-toggle")                                              # leave it as he found it


def test_the_desktop_panel_tells_it_collapsed_and_expanded(server):
    from playwright.sync_api import sync_playwright
    hits: list = []
    with sync_playwright() as pw:
        pg = _page(pw, server, 1280, hits)
        pg.evaluate("async () => {" + _CSS + """
            const store = await import('/frontend/app/core/store.js?v=2');
            const m = await import('/frontend/app/components/ChatWall.js?v=5');
            document.body.append(m.ChatWall());
            store.setChatTab('procesos'); store.setChatOpen(true);
            store.setTaskScope('live'); store.fetchTaskScope('live'); }""")
        _check_collapsed_then_expanded(pg, hits)
        assert hits[0] == "7", "the entry is keyed by the session id the SSE events name"


def test_the_phone_menu_carries_the_same_entry(server):
    from playwright.sync_api import sync_playwright
    hits: list = []
    with sync_playwright() as pw:
        pg = _page(pw, server, 375, hits)
        pg.evaluate("async () => {" + _CSS + """
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/frontend/mobile/app/styles.css';
            document.head.append(l);
            const store = await import('/frontend/app/core/store.js?v=2');
            const m = await import('/frontend/mobile/app/shell/MenuSheet.js?v=2');
            document.body.append(m.MenuSheet());
            store.startTask('7', 'Documento con tu estilo'); store.setMobileMenuOpen(true); }""")
        _check_collapsed_then_expanded(pg, hits)
        width = pg.evaluate("() => document.documentElement.scrollWidth")
        assert width <= 375, f"the phone scrolls sideways ({width}px)"


def test_a_blocked_process_says_why_on_its_last_line(server):
    """No window can reach him (no display, no daemon): the entry says it is blocked and why, in his language."""
    from playwright.sync_api import sync_playwright
    rec = {**_REC, "browser": {**_REC["browser"], "awaiting_login": False, "blocked": "no_window"}}
    with sync_playwright() as pw:
        pg = _page(pw, server, 375, [], rec)
        pg.evaluate("async () => {" + _CSS + """
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/frontend/mobile/app/styles.css';
            document.head.append(l);
            const store = await import('/frontend/app/core/store.js?v=2');
            const m = await import('/frontend/mobile/app/shell/MenuSheet.js?v=2');
            document.body.append(m.MenuSheet());
            store.startTask('7', 'Documento con tu estilo'); store.setMobileMenuOpen(true); }""")
        pg.wait_for_selector(".pe .pe-need[data-wait]", timeout=5000)
        c = pg.evaluate(_READ)[0]
        assert c["wait"] == [["blocked", _ES["chat.procBlockedNoWindow"]]] and c["lastIsWait"], c["wait"]
        assert not pg._errors, pg._errors
