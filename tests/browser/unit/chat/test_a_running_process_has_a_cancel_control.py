"""A running process carries HIS stop on the screen (V2-852 T07, R2), RENDERED.

The operator's rule (2026-11-05): a task runs until it is done or he stops it, and the stop from the screen is a cancel
control on each running process in the list. Rendered in Chromium against the real ChatWall (desktop) and MenuSheet
(phone, 375 px), the real ProcessEntry, stylesheets and both bundles. The control POSTs `/api/tasks/<row>/cancel` for
THAT row and nothing else; pressed it is spent until the answer, and a refusal gives it back. It is there whether the
worker is alive or parked on his answer (a waiting task is still running for him).

Disarm: `actsOf` not drawing the control → red.
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
_BUNDLE = {lang: json.loads((ENGINE / f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8")) for lang in ("es", "en")}
_NOW = int(time.time())
_ROW = {"id": "row-7", "session": "7", "title": "Piso de alquiler en Valencia", "goal": "g", "state": "running",
        "started_at": _NOW - 90, "phase": "Leyendo anuncios", "visible": True}
_ALIVE = {"alive": True, "id": "7", "uid": "row-7", "plan": ["Buscar", "Comparar", "Entregar"], "done": 1}
_PARKED = {"alive": False, "id": "7", "uid": "row-7"}

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


def _page(pw, port, width, lang, rec, answer):
    pg = pw.chromium.launch().new_page(viewport={"width": width, "height": 800})
    pg._errors, pg._cancels, pg._hold = [], [], []
    pg.on("pageerror", lambda e: pg._errors.append(str(e)))
    bundle = json.dumps({"strings": _BUNDLE[lang]})

    def cancel(route):
        pg._cancels.append((route.request.method, route.request.url.split("/api/tasks/")[1]))
        pg._hold.append(lambda: route.fulfill(status=200, content_type="application/json", body=json.dumps(answer)))

    pg.route("**/api/**", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
    pg.route("**/api/tasks?*", lambda r: r.fulfill(status=200, content_type="application/json",
                                                   body=json.dumps({"tasks": [_ROW] if "scope=live" in r.request.url else []})))
    pg.route("**/api/tasks/*/process", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(rec)))
    pg.route("**/api/tasks/*/cancel", cancel)
    pg.route("**/api/i18n/bundle/*", lambda r: r.fulfill(status=200, content_type="application/json", body=bundle))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    css = """for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/shared-surfaces.css',
                       '/frontend/app/core/components.css', '/frontend/app/styles.css']) {
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
          const i18n = await import('/frontend/app/core/i18n.js?v=1');
          await i18n.loadBundle('%s'); if (i18n.applyLang) await i18n.applyLang('%s');""" % (lang, lang)
    return pg, css


def _press_and_answer(pg, lang):
    S = _BUNDLE[lang]
    pg.wait_for_selector(".pe .pe-cancel", timeout=5000)
    assert pg.inner_text(".pe .pe-cancel") == S["chat.procCancel"]
    pg.click(".pe .pe-cancel")
    for _ in range(100):                     # the sync API dispatches the route only while a page call is running
        if pg._cancels:
            break
        pg.wait_for_timeout(50)
    assert pg._cancels == [("POST", "row-7/cancel")], f"the stop names THAT row: {pg._cancels}"
    spent = pg.evaluate("() => { const b = document.querySelector('.pe .pe-cancel'); return [b.disabled, b.innerText]; }")
    assert spent == [True, S["chat.procCancelling"]], f"pressed, it is spent until the answer: {spent}"
    pg._hold.pop()()


def test_the_desktop_row_cancels_its_own_task_and_a_refusal_gives_the_control_back(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg, css = _page(pw, server, 1280, "es", _ALIVE, {"ok": False, "task_id": "row-7", "state": "done"})
        pg.evaluate("async () => {" + css + """
            const store = await import('/frontend/app/core/store.js?v=2');
            const m = await import('/frontend/app/components/ChatWall.js?v=5');
            document.body.append(m.ChatWall());
            store.setChatTab('procesos'); store.setChatOpen(true);
            store.setTaskScope('live'); store.fetchTaskScope('live'); }""")
        _press_and_answer(pg, "es")
        pg.wait_for_function("() => !document.querySelector('.pe .pe-cancel').disabled", timeout=5000)
        assert pg.inner_text(".pe .pe-cancel") == _BUNDLE["es"]["chat.procCancel"]
        assert not pg._errors, pg._errors


def test_the_phone_menu_cancels_a_parked_task_too(server):
    """A worker parked on his answer is not alive, and the task is still his to stop — English this time."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        pg, css = _page(pw, server, 375, "en", _PARKED, {"ok": True, "task_id": "row-7", "state": "cancelled"})
        pg.evaluate("async () => {" + css + """
            const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = '/frontend/mobile/app/styles.css';
            document.head.append(l);
            const store = await import('/frontend/app/core/store.js?v=2');
            const m = await import('/frontend/mobile/app/shell/MenuSheet.js?v=2');
            document.body.append(m.MenuSheet());
            store.startTask('row-7', 'A flat to rent in Valencia'); store.setMobileMenuOpen(true); }""")
        _press_and_answer(pg, "en")
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => document.querySelector('.pe .pe-cancel').disabled"), \
            "an accepted cancel keeps the control spent: the row leaves through the task events, not through the button"
        assert pg.evaluate("() => document.documentElement.scrollWidth") <= 375
        assert not pg._errors, pg._errors
