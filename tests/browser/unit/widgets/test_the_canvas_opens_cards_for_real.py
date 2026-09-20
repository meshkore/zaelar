"""The canvas RENDERS: every card gesture runs against the real `desktop.js`, in a real browser.

WHY THIS FILE EXISTS (review 2026-09-20). The worker-background fix (adb76984) pasted
`if(!background) this._bringFront(w.card)` into four branches of `desktop.js`: show()'s FRESH branch,
where `w` is still undefined, and three branches — the aliases panel, createWidget's error path, and
maximize — where `background` is not even a name in scope. The first is a TypeError on EVERY new card,
the other three a ReferenceError each. Nothing could be opened at all.

It shipped GREEN. Node 4.149 covered the same fix with a `.mjs` that mounts `sse.js` over a STUB host
(`const desktop = { show(id, opts){ calls.push(...) } }`) plus `.py` source greps. Neither can fail on
anything `desktop.js` does, because neither ever runs it — the one file the fix changed was the one
file nothing executed. The incident pin added afterwards (`test_a_fresh_show_needs_no_stored_card.py`)
is a static ratchet on that exact shape, which is worth keeping and is still not execution.

So this is the missing half: mount the REAL Desktop in chromium and drive it. The assertion that earns
its keep is `pageerror` — a canvas that throws is a canvas that is broken, whatever it looks like — and
around it the focus contract fix04 actually asked for: background work opens BESIDE, never OVER.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]

# A widget module that mounts without needing anything of ours — the canvas is what is under test.
_STUB_WIDGET = "export function mount(el){ el.textContent = 'mounted'; }\nexport default { mount };\n"
_REGISTRY = {"widgets": [{"id": "uno", "name": "Uno"}, {"id": "dos", "name": "Dos"}]}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def _canvas():
    """A real http origin (a module cannot be imported from `file:`), with every BACKEND call stubbed.

    Stubbed on purpose, and not left to 404: an unrouted request comes back as the server's HTML error
    page, `r.json()` throws inside a `catch(_){}`, and the canvas quietly runs its fallback path — a
    harness that measures the fallback instead of the product.
    """
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
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def _json(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            page.route("**/widgets", lambda r: _json(r, _REGISTRY))
            page.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
            page.route("**/widgets/*/widget.js", lambda r: r.fulfill(
                status=200, content_type="application/javascript", body=_STUB_WIDGET))
            page.route("**/widgets/*/data*", lambda r: _json(r, {}))
            page.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
            page.route("**/api/**", lambda r: _json(r, {}))

            page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            page.evaluate("""async (port) => {
                document.body.innerHTML = '<div id="stage"></div><div id="activity"></div>';
                const m = await import(`http://127.0.0.1:${port}/frontend/app/widgets/desktop.js?v=1`);
                window.__desk = new m.Desktop(document.getElementById('stage'));
            }""", port)
            assert not errors, f"the canvas threw before a single card was asked for: {errors}"
            page._hb_errors = errors
            yield page
            browser.close()
    finally:
        srv.terminate()
        srv.wait(timeout=10)


def _z(page, wid: str) -> int:
    return page.evaluate(
        "(id) => { const c = document.querySelector(`[data-wid='${id}']`);"
        "          return c ? (parseInt(getComputedStyle(c).zIndex) || 0) : -1; }", wid)


def _show(page, wid: str, **opts):
    page.evaluate("([id, o]) => window.__desk.show(id, o)", [wid, opts])
    page.wait_for_selector(f"[data-wid='{wid}']", timeout=5000)


def test_a_fresh_card_actually_appears_on_the_canvas(_canvas):
    """THE incident, executed: `show()` on a card nobody has opened yet must produce a card.

    This is the assertion adb76984 could not have passed — `this._bringFront(w.card)` with `w`
    undefined threw before `_place`, before the fetch, before the card was ever placed.
    """
    _show(_canvas, "uno", data={"ok": True})
    assert _canvas.evaluate("() => document.querySelectorAll('#stage .hb-win').length") == 1
    assert not _canvas._hb_errors, f"opening a card threw: {_canvas._hb_errors}"


def test_a_worker_card_opens_beside_his_card_and_never_over_it(_canvas):
    """fix04's actual contract, measured on the canvas rather than grepped from the source.

    Session 6d19df41: the ghost errand's `documento` came to the front over his email flow. A
    background show must still OPEN — and must not outrank what he is looking at.
    """
    front = _z(_canvas, "uno")
    _show(_canvas, "dos", data={"ok": True}, background=True)
    assert _canvas.evaluate("() => document.querySelectorAll('#stage .hb-win').length") == 2, \
        "a background card must still OPEN — background is about focus, not about hiding"
    assert _z(_canvas, "dos") < front, "the worker's card took the front over his"
    assert _z(_canvas, "uno") == front, "his card must not have been demoted either"
    assert not _canvas._hb_errors, _canvas._hb_errors


def test_a_second_show_of_an_open_card_honours_background_too(_canvas):
    """The already-open branch has its own `_bringFront` — a re-show from a worker must not front."""
    front = _z(_canvas, "uno")
    _canvas.evaluate("() => window.__desk.show('dos', { background: true, data: { again: 1 } })")
    _canvas.wait_for_timeout(200)
    assert _z(_canvas, "dos") < front, "re-showing a worker card fronted it"
    _canvas.evaluate("() => window.__desk.show('dos', { data: { again: 2 } })")
    _canvas.wait_for_timeout(200)
    assert _z(_canvas, "dos") > front, "his OWN re-show must come to the front, as it always did"
    assert not _canvas._hb_errors, _canvas._hb_errors


def test_every_card_gesture_runs_without_throwing(_canvas):
    """maximize, the aliases panel, minimize/restore — the three branches that held a ReferenceError.

    Each was reached by a normal gesture and each threw `background is not defined`. None of them is
    asserted on here for what it PAINTS: the point is that the canvas survives being used at all.
    """
    before = len(_canvas._hb_errors)
    _canvas.evaluate("""() => {
        const d = window.__desk;
        d.maximize('uno'); d.maximize('uno');          // maximize, then restore
        d.minimize('uno'); d.restore && d.restore('uno');
        const w = d.wins.get('uno');
        d._toggleAliases(w); d._toggleAliases(w);      // the ⚙ panel, open and shut
    }""")
    _canvas.wait_for_timeout(400)
    assert len(_canvas._hb_errors) == before, \
        f"a normal gesture threw on the canvas: {_canvas._hb_errors[before:]}"
