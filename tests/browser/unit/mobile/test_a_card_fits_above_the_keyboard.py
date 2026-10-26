"""A field typed into inside a card — or inside a sheet — keeps itself in sight above the keyboard (V2-813, V2-815).

Measured on an iPhone 14 and a Pixel 7: both browsers shrink only the VISUAL viewport when the keyboard opens, so the
deck kept its full height, its bottom half sat under the keyboard and the dock covered what was left — agenda's
«Nueva cita» lost Save and Cancel. `shell/keyboard.js` lays the deck over the visible part and steps the dock aside.

RENDERED: the real stylesheet and the real module, in Chromium with a phone viewport; the keyboard is the viewport
getting shorter while the field has focus, which is what the browser itself reports.
"""
from __future__ import annotations

import os

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
W, H, KEYBOARD = 390, 750, 336

PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/mobile/app/styles.css">
<div class="zm-deck" style="position:fixed;inset:0"><div class="zm-card live" style="position:absolute;inset:0">
  <div class="zm-scroll"><input id="in-card" placeholder="in a card"></div></div></div>
<input id="outside" style="position:fixed;top:0;left:0">
<section class="zm-sheet zm-chat open">
  <input id="in-sheet" placeholder="in the chat"></section>
<nav class="zm-dock"></nav>
<script type="module">
  import { initKeyboard } from "/static/mobile/app/shell/keyboard.js";
  initKeyboard(); window.__ready = true;
</script>"""


@pytest.fixture()
def page():
    pw = pytest.importorskip("playwright.sync_api")
    with pw.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:  # noqa: BLE001 — no browser on this machine is a skip, not a failure
            pytest.skip(f"chromium unavailable: {e}")
        ctx = browser.new_context(viewport={"width": W, "height": H}, is_mobile=True, has_touch=True)
        pg = ctx.new_page()

        def route(r):
            path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
            if path in ("", "page"):
                return r.fulfill(status=200, body=PAGE, headers={"content-type": "text/html; charset=utf-8"})
            fp = os.path.join(ENGINE, "frontend", path[len("static/"):]) if path.startswith("static/") else ""
            if not fp or not os.path.isfile(fp):
                return r.fulfill(status=404, body="")
            ct = "text/css" if fp.endswith(".css") else "application/javascript"
            with open(fp, "rb") as fh:
                r.fulfill(status=200, body=fh.read(), headers={"content-type": ct})

        pg.route("**/*", route)
        pg.goto("http://phone.test/page")
        pg.wait_for_function("window.__ready === true")
        yield pg
        browser.close()


def _state(pg):
    return pg.evaluate("""() => ({kbd: document.documentElement.classList.contains('zm-kbd'),
        where: document.documentElement.dataset.kbd || '',
        dock: getComputedStyle(document.querySelector('.zm-dock')).display,
        deckH: Math.round(document.querySelector('.zm-deck').getBoundingClientRect().height),
        sheet: (() => { const r = document.querySelector('.zm-sheet').getBoundingClientRect();
                        return { top: Math.round(r.top), h: Math.round(r.height) }; })()})""")


def _keyboard(pg, open_: bool):
    pg.set_viewport_size({"width": W, "height": H - KEYBOARD if open_ else H})
    pg.wait_for_timeout(200)


def test_typing_in_a_card_lays_the_deck_over_the_visible_part_and_steps_the_dock_aside(page):
    page.focus("#in-card")
    _keyboard(page, True)
    st = _state(page)
    assert st["kbd"] and st["where"] == "deck" and st["dock"] == "none", st
    assert st["deckH"] == H - KEYBOARD, st
    assert st["sheet"]["top"] > 0, st            # a sheet is not touched by a field in a card


def test_typing_in_the_chat_sheet_lays_the_sheet_over_the_visible_part_and_steps_the_dock_aside(page):
    """iPhone 14, 2026-10-26: composer · the whole dock · the keyboard's accessory row · the keys — half the screen of
    chrome around one field. With the keyboard up the open sheet IS the visible screen and the dock is gone."""
    page.focus("#in-sheet")
    _keyboard(page, True)
    st = _state(page)
    assert st["kbd"] and st["where"] == "sheet" and st["dock"] == "none", st
    assert st["sheet"] == {"top": 0, "h": H - KEYBOARD}, st


def test_closing_the_keyboard_gives_the_screen_back(page):
    page.focus("#in-card")
    _keyboard(page, True)
    page.evaluate("document.activeElement.blur()")
    _keyboard(page, False)
    st = _state(page)
    assert not st["kbd"] and st["dock"] != "none", st


def test_a_field_outside_the_deck_and_the_sheets_is_nobodys_business(page):
    """Only focus inside `.zm-deck` or a `.zm-sheet` counts."""
    page.focus("#outside")
    _keyboard(page, True)
    assert not _state(page)["kbd"]
