"""V2-776 D5 — the Tasks tab shows what the pulse knows about a worker, RENDERED.

The operator (2026-09-27): «cada vez que se lanza un brain worker parece que no tenemos mucha observabilidad
sobre el mismo». The durable row now carries the worker's silence, the pulse's restarts and the class of a
failure (D1-D4); this is the half the operator actually looks at. Rendered in Chromium against the real
ChatWall, store, stylesheet and Spanish bundle, with `/api/tasks` answering the rows the server would send.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_ES = json.loads((ENGINE / "i18n/bundles/es.json").read_text(encoding="utf-8"))
_NOW = int(time.time())
_ROWS = {
    "live": [{"id": "abcdef-1", "title": "Widget de contabilidad", "goal": "g", "state": "running",
              "started_at": _NOW - 400, "phase": "escribiendo widget.js", "silent_s": 190, "attempts": 1,
              "visible": True}],
    "done": [{"id": "abcdef-2", "title": "Enviar el PDF al banco", "goal": "g", "state": "failed",
              "kind": "generic", "finished_at": _NOW - 60, "outcome": "No pude crear el widget.",
              "error_class": "credit", "attempts": 1, "visible": True}],
}

pytest.importorskip("playwright.sync_api")


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


def _tasks_route(route):
    scope = route.request.url.split("scope=")[-1].split("&")[0]
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"tasks": _ROWS.get(scope, [])}))


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
            pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            pg.route("**/api/tasks?*", _tasks_route)
            pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=es))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async () => {
                for (const h of ['/frontend/app/core/palette.css', '/frontend/app/styles.css']) {
                  const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
                const i18n = await import('/frontend/app/core/i18n.js?v=1');
                await i18n.loadBundle('es'); if (i18n.applyLang) await i18n.applyLang('es');
                const store = await import('/frontend/app/core/store.js?v=2');
                const m = await import('/frontend/app/components/ChatWall.js?v=5');
                document.body.append(m.ChatWall());
                window.__store = store;
                store.setChatTab('chat'); store.setChatOpen(true);
            }""")
            pg.wait_for_selector("#chatwall.open", timeout=5000)
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _scope(pg, scope):
    pg.evaluate("s => { window.__store.setTaskScope(s); window.__store.setChatTab('procesos'); "
                "window.__store.fetchTaskScope(s); }", scope)
    pg.wait_for_selector(".cw-proc-row", timeout=5000)
    return pg.evaluate("() => [...document.querySelectorAll('.cw-proc-row')].map(r => r.innerText)")


def test_a_live_worker_says_how_long_it_has_been_silent_and_that_it_was_restarted(wall):
    rows = _scope(wall, "live")
    assert len(rows) == 1
    silent = _ES["chat.procSilent"].split("{")[0].strip()
    restarted = _ES["chat.procRestarted"].split("{")[0].strip()
    assert silent in rows[0], f"the row does not say the worker went quiet: {rows[0]!r}"
    assert restarted in rows[0], f"the row does not say the pulse restarted it: {rows[0]!r}"
    assert not wall._errors, wall._errors


def test_a_failed_row_says_why_in_words(wall):
    rows = _scope(wall, "done")
    assert len(rows) == 1
    assert _ES["chat.errClass.credit"] in rows[0], f"the failed row does not name its cause: {rows[0]!r}"
    assert "chat.errClass" not in rows[0], "a raw i18n key reached the screen"
