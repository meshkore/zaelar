"""V2-681 T-1/T-2 — two surfaces the operator uses every day, measured in a REAL browser on the REAL page.

T-1: the chat wall went blank on every browser refresh («pierdo el rastro de lo que estábamos diciendo»).
T-2: the feedback panel had no height of its own, so switching to an empty Sent tab collapsed it and
switching back sprang it open again; and it asked, in writing, whether to include what happened in the
session — «bórralo, que nadie vea el rastro, porque se verá una intención fea».

Both claims are about LAYOUT and about module boot order, and neither can be read off the source: a height
that follows content and a fixed one are the same file minus one declaration, and persistence that never
restores looks identical to persistence that does until a page is actually reloaded.

SELF-CONTAINED AND NON-DESTRUCTIVE, the same design as `render_send_failure.py` beside it: it starts its
own preview server (server.pages + /static + i18n) on a free port — never the operator's engine, which
would post real feedback — and every network call this exercises is faked at the wire.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))

PREVIEW = '''
import sys
sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI()
app.include_router(pages.router)
app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

LIFT_VEIL = "() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e => e.remove())"

CHAT_KEY = "hb_chat_log"

# The SAME module instance the app is running, not a second copy: a browser's module cache is keyed by the
# resolved URL, and `/static/app/main.js` imports `../core/store.js?v=2`, which resolves to exactly this.
# Importing it under any other spelling would hand the test a fresh store with an empty list.
STORE_URL = "/static/app/core/store.js?v=2"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def _url():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
        cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            pytest.skip("preview server never came up")
        time.sleep(1.0)
        yield f"http://127.0.0.1:{port}/"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def _pw():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


def _page(browser, url, *, width=1280, height=900):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    pg = ctx.new_page()
    # Nothing leaves the machine: the feedback endpoints answer from here.
    pg.route("**/api/feedback", lambda r: r.fulfill(
        status=200, content_type="application/json", body=json.dumps({"ok": True, "items": []})))
    return ctx, pg


def _boot(pg, url):
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)        # let the i18n bundle land — a label read too early freezes on its key
    pg.evaluate(LIFT_VEIL)
    pg.wait_for_timeout(300)


# ── T-1 · the chat wall survives a refresh ────────────────────────────────────────────────────────────

def _seed_chat(pg, url, msgs, at_ms):
    """Write the stored log the way the store writes it, then RELOAD so the module boots against it —
    that reload is the whole behaviour under test."""
    pg.goto(url, wait_until="domcontentloaded")
    pg.evaluate("([k, v]) => localStorage.setItem(k, v)",
                [CHAT_KEY, json.dumps({"v": 1, "at": at_ms, "msgs": msgs})])


def test_what_was_said_is_still_there_after_a_refresh(_pw, _url):
    """The operator's report, exactly: he refreshes and the wall is blank."""
    ctx, pg = _page(_pw, _url)
    try:
        _seed_chat(pg, _url, [{"role": "you", "text": "lo que dije antes"},
                              {"role": "agent", "text": "lo que contesté antes"}],
                   int(time.time() * 1000) - 120000)
        _boot(pg, _url)
        pg.evaluate("async (u) => (await import(u)).setChatOpen(true)", STORE_URL)
        texts = pg.evaluate("() => [...document.querySelectorAll('.cw-msg-body')].map(n => n.textContent.trim())")
        assert "lo que dije antes" in texts, texts
        assert "lo que contesté antes" in texts, texts
    finally:
        ctx.close()


def test_the_restored_part_is_MARKED_as_earlier(_pw, _url):
    """A conversation from before the refresh must not read as something just said — the V2-582 class,
    and the reason the messaging widget already marks where its stored history begins."""
    ctx, pg = _page(_pw, _url)
    try:
        _seed_chat(pg, _url, [{"role": "you", "text": "antiguo"}], int(time.time() * 1000) - 3600_000)
        _boot(pg, _url)
        divider = pg.evaluate("() => { const d = document.querySelector('.cw-earlier'); return d && d.textContent.trim(); }")
        assert divider, "the restored block was not marked at all"
        assert "cw-earlier" not in (divider or ""), divider          # translated text, not a class name
        assert "chat.earlier" not in divider, divider                # translated text, not the raw i18n key
    finally:
        ctx.close()


def test_the_divider_sits_BETWEEN_the_old_and_the_new(_pw, _url):
    """Where it goes is the claim that can actually break. It marks the end of what was restored, so a new
    line said after the refresh must land BELOW it — a divider pinned to the bottom of the list would keep
    sliding under whatever he says next and stop meaning anything.

    («A fresh wall draws no divider» is deliberately not a case of its own: with nothing restored the
    counter is 0 and the wall clamps it to the message count on its first paint, so that claim cannot fail
    by construction — a disarm proved it, and a test that cannot go red is not a test. It is asserted here
    as one line instead, on a wall that really has content.)"""
    ctx, pg = _page(_pw, _url)
    try:
        _seed_chat(pg, _url, [{"role": "you", "text": "de antes 1"}, {"role": "agent", "text": "de antes 2"}],
                   int(time.time() * 1000) - 600000)
        _boot(pg, _url)
        pg.evaluate("async (u) => (await import(u)).pushChat({role: 'you', text: 'dicho despues'})", STORE_URL)
        pg.wait_for_timeout(300)
        order = pg.evaluate("""() => [...document.querySelectorAll('.cw-list > *')]
                                   .map(n => n.classList.contains('cw-earlier') ? '|' : n.textContent.trim())""")
        assert order.count("|") == 1, order
        assert order.index("|") == 2, order                           # after both restored lines…
        assert order[-1] == "dicho despues", order                    # …and the new one is below it
    finally:
        ctx.close()


def test_what_is_said_NOW_is_stored_for_the_next_load(_pw, _url):
    """The other half: restoring is worthless if nothing is ever written. Driven through the store's own
    exported door, which is the single chokepoint every one of the seven writers goes through."""
    ctx, pg = _page(_pw, _url)
    try:
        pg.goto(_url, wait_until="domcontentloaded")
        pg.evaluate("(k) => localStorage.removeItem(k)", CHAT_KEY)
        _boot(pg, _url)
        pg.evaluate("async (u) => (await import(u)).pushChat({role: 'you', text: 'dicho ahora mismo'})", STORE_URL)
        pg.wait_for_timeout(700)                                     # past the write debounce
        stored = pg.evaluate("(k) => localStorage.getItem(k)", CHAT_KEY)
        assert stored, "nothing was written at all"
        assert [m["text"] for m in json.loads(stored)["msgs"]] == ["dicho ahora mismo"], stored
    finally:
        ctx.close()


def test_clearing_the_wall_clears_what_was_stored(_pw, _url):
    """A reset must not leave the previous conversation waiting to come back on the next load. It goes
    through the same setter every other writer uses, which is why one door was the whole design."""
    ctx, pg = _page(_pw, _url)
    try:
        _seed_chat(pg, _url, [{"role": "you", "text": "esto debe desaparecer"}], int(time.time() * 1000))
        _boot(pg, _url)
        pg.evaluate("async (u) => (await import(u)).setChatMsgs([])", STORE_URL)
        pg.wait_for_timeout(700)
        assert not pg.evaluate("(k) => localStorage.getItem(k)", CHAT_KEY)
    finally:
        ctx.close()


def test_leaving_a_page_where_he_said_NOTHING_erases_nothing(_pw, _url):
    """A defect this very feature introduced, caught by its own test and worth a case of its own: the
    close-the-tab flush wrote the message list unconditionally, and an empty list means REMOVE. So
    opening the app, staying quiet and navigating away wiped the previous conversation — the exact
    failure the persistence exists to end, reintroduced by its own flush."""
    ctx, pg = _page(_pw, _url)
    try:
        _seed_chat(pg, _url, [{"role": "you", "text": "de la sesión anterior"}], int(time.time() * 1000))
        _boot(pg, _url)                                              # loads it, and says nothing
        pg.goto(_url, wait_until="domcontentloaded")                 # …and navigates away
        pg.wait_for_timeout(800)
        # PARSED, never matched against the raw text: JSON escapes a non-ASCII character, so
        # `"sesión" in raw` is false even when the message is right there as `sesi\\u00f3n`.
        stored = pg.evaluate("(k) => localStorage.getItem(k)", CHAT_KEY)
        assert stored, "the previous conversation was erased"
        assert [m["text"] for m in json.loads(stored)["msgs"]] == ["de la sesión anterior"], stored
    finally:
        ctx.close()


def test_the_stored_history_never_exceeds_the_cap(_pw, _url):
    """«Siguiendo las reglas que ya tenemos» — the 100-message cap is one of them, and a store that
    persisted past it would grow without bound in a place nobody trims."""
    ctx, pg = _page(_pw, _url)
    try:
        pg.goto(_url, wait_until="domcontentloaded")
        pg.evaluate("(k) => localStorage.removeItem(k)", CHAT_KEY)
        _boot(pg, _url)
        pg.evaluate("async (u) => { const s = await import(u); for (let i = 0; i < 130; i++) s.pushChat({role:'you', text:'m'+i}); }", STORE_URL)
        pg.wait_for_timeout(700)
        n = pg.evaluate("(k) => JSON.parse(localStorage.getItem(k)).msgs.length", CHAT_KEY)
        assert n == 100, n
    finally:
        ctx.close()


# ── T-2 · the feedback box ────────────────────────────────────────────────────────────────────────────

def _open_feedback(pg):
    pg.click(".fw-launcher")
    pg.wait_for_timeout(400)


def _panel_h(pg):
    return pg.evaluate("() => Math.round(document.querySelector('.fw-panel').getBoundingClientRect().height)")


def test_the_panel_keeps_ONE_size_across_both_tabs(_pw, _url):
    """His report: «cuando clico el send, si no hay nada en la lista, esa cajita se hace súper pequeña y
    baja y sube. Si le vuelvo a dar a new, vuelve a hacerse grande.» Measured before the fix: 390 then
    138. The Sent list is empty here, which is the state that produced it."""
    ctx, pg = _page(_pw, _url)
    try:
        _boot(pg, _url)
        _open_feedback(pg)
        new_h = _panel_h(pg)
        pg.click(".fw-tab:nth-of-type(2)")
        pg.wait_for_timeout(400)
        sent_h = _panel_h(pg)
        pg.click(".fw-tab:nth-of-type(1)")
        pg.wait_for_timeout(400)
        back_h = _panel_h(pg)
        assert new_h == sent_h == back_h, (new_h, sent_h, back_h)
    finally:
        ctx.close()


def test_the_form_FILLS_the_panel_with_no_dead_space(_pw, _url):
    """⚠️ This case used to assert `570 <= h <= 600` — 390 × 1.5, the fixed height V2-681 gave the panel so
    it would stop shrinking and springing back between tabs. That number was ours, and the operator's answer
    when asked was «que lo pueda redimensionar yo» (V2-695), so the height is now a default and the grip
    decides. What survives is the DURABLE property underneath it, which is also what he actually reported:
    «use all size of the box… may be too big».

    The cause was one missing declaration — `.fw-new` had no `flex:1 1 auto` inside a fixed-height column
    flex parent, so the pane was sized by its own content and ~240px sat empty under the send button. The
    measurement is the gap between the last control and the panel's floor: that is the dead space, and no
    amount of re-picking a height would have closed it."""
    ctx, pg = _page(_pw, _url)
    try:
        _boot(pg, _url)
        _open_feedback(pg)
        gap = pg.evaluate(
            """() => { const p = document.querySelector('.fw-panel').getBoundingClientRect();
                       const r = document.querySelector('.fw-row').getBoundingClientRect();
                       return Math.round(p.bottom - r.bottom); }""")
        assert gap < 40, f"{gap}px of dead space under the last control"
        ta = pg.evaluate("() => Math.round(document.querySelector('.fw-textarea').getBoundingClientRect().height)")
        assert ta > 150, f"the textarea has to eat the slack, got {ta}"
    finally:
        ctx.close()


def test_the_HEIGHT_is_his_and_it_comes_back(_pw, _url):
    """«Que lo pueda redimensionar yo.» The grip is on the TOP edge because the panel is anchored
    bottom-right, so pulling up is what makes it taller — and the gesture can never push the box off the
    screen. What he sets has to survive closing it, or it is a nuisance rather than a setting."""
    ctx, pg = _page(_pw, _url)
    try:
        _boot(pg, _url)
        _open_feedback(pg)
        before = _panel_h(pg)
        grip = pg.locator(".fw-grip").first
        box = grip.bounding_box()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        pg.mouse.down()
        pg.mouse.move(box["x"] + box["width"] / 2, box["y"] - 120, steps=6)
        pg.mouse.up()
        pg.wait_for_timeout(200)
        taller = _panel_h(pg)
        assert taller > before + 80, (before, taller)

        pg.click(".fw-x")
        pg.wait_for_timeout(200)
        _open_feedback(pg)
        assert abs(_panel_h(pg) - taller) <= 2, (taller, _panel_h(pg))
    finally:
        ctx.close()


def test_nobody_is_asked_about_including_the_session(_pw, _url):
    """«Bórralo, que nadie vea el rastro.» Deleted, not hidden: a hidden control is still in the DOM and
    still reads as an intention to anyone who looks — including the string in the language bundles."""
    ctx, pg = _page(_pw, _url)
    try:
        _boot(pg, _url)
        _open_feedback(pg)
        assert pg.evaluate("() => document.querySelectorAll('.fw-check').length") == 0
        assert pg.evaluate("() => document.querySelectorAll('.fw-panel input[type=checkbox]').length") == 0
        body = pg.evaluate("() => document.querySelector('.fw-panel').textContent")
        assert "sesión" not in body and "session" not in body.lower(), body
    finally:
        ctx.close()


def test_the_mic_sits_in_the_SEND_row(_pw, _url):
    """«El icono del micrófono lo puedes poner en la fila del botón de send my feedback.»"""
    ctx, pg = _page(_pw, _url)
    try:
        _boot(pg, _url)
        _open_feedback(pg)
        m = pg.evaluate("""() => {
            const mic = document.querySelector('.fw-mic'), snd = document.querySelector('.fw-send');
            if (!mic || !snd) return null;
            const a = mic.getBoundingClientRect(), b = snd.getBoundingClientRect();
            return {sameRow: Math.abs(a.y - b.y) < 20, micFirst: a.x < b.x, sndArea: Math.round(b.width * b.height)};
        }""")
        assert m and m["sameRow"], m
        assert m["micFirst"], m
        assert m["sndArea"] > 3000, m                                 # the send is still the big one
    finally:
        ctx.close()


def test_on_a_PHONE_it_takes_the_screen_and_the_way_out_is_obvious(_pw, _url):
    """His ask: full screen on mobile, «y que quede muy claro el botón de cerrar». A full-screen surface
    with no findable way out is the one state a person cannot escape."""
    ctx, pg = _page(_pw, _url, width=390, height=780)
    try:
        _boot(pg, _url)
        _open_feedback(pg)
        m = pg.evaluate("""() => {
            const p = document.querySelector('.fw-panel').getBoundingClientRect();
            const x = document.querySelector('.fw-x').getBoundingClientRect();
            return {w: Math.round(p.width), h: Math.round(p.height),
                    xw: Math.round(x.width), xh: Math.round(x.height),
                    onScreen: x.x >= 0 && x.y >= 0 && x.x + x.width <= innerWidth};
        }""")
        assert m["w"] >= 380 and m["h"] >= 760, m                     # it really is the screen
        assert m["xw"] >= 40 and m["xh"] >= 40, m                     # a real touch target, not a glyph
        assert m["onScreen"], m
        pg.click(".fw-x")
        pg.wait_for_timeout(300)
        assert pg.evaluate("() => document.querySelectorAll('.fw-panel.open').length") == 0
    finally:
        ctx.close()
