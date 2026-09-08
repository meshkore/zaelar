"""V2-616 F2 — opening/leaving a screen resets the outer card scroller.

The operator's screenshot: opening a WhatsApp thread while the chat list behind it was scrolled down left the
thread's own header ("← Volver · Mónica Cirera") rendered scrolled PAST the visible area on first paint — his
words: "se ha metido como por debajo el header del otro". Scrolling by hand only fixed it by accident, forcing
a browser reflow. `ctx.top()` exists for exactly this ("opening a record, changing tabs, returning to the
list" — `frontend/app/widgets/desktop.js`) and `widget.js` never called it once, on any of its screen swaps.

RENDERED against the real widget.js with a SPY `ctx.top`, because the fix is "does this click call the seam
that resets the scroller", not something a source-level assertion about scroll state could see.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body><div id="host"></div></body></html>"""

_CHATS = [
    {"n": 1, "platform": "whatsapp", "chatId": "111", "name": "JOSE VICENTE", "isGroup": False,
     "count": 1, "dirigido_a_mi": True, "highlight": True, "urgencia": "media", "lastFrom": "JOSE VICENTE",
     "lastBody": "Hola", "lastMotivo": "", "lastTs": 1, "lastMediaType": ""},
]
_BASE = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "off"}, "email": {"status": "off"}},
    "updated": "10:00:00", "items": [], "count": 0, "chats": _CHATS,
    "active_chat": None, "active_items": [], "muted_channels": [], "notify_policy": {},
    "connect_focus": None, "view": None,
}
_THREAD_DATA = {**_BASE, "active_chat": {"platform": "whatsapp", "chatId": "111"},
                 "active_items": [{"n": 1, "platform": "whatsapp", "from": "JOSE VICENTE", "dir": "in",
                                    "chatId": "111", "messageId": "m1", "body": "Hola", "ts": 1,
                                    "urgencia": "media", "dirigido_a_mi": True}],
                 "thread_meta": {"isGroup": False, "complete": True}}


async def _mount_and_click(data, sel):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        pg = await b.new_page(viewport={"width": 560, "height": 900})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        async def _page(route):
            await route.fulfill(status=200, content_type="text/html", body=_HTML)
        await pg.route("http://zaelar.test/", _page)
        await pg.goto("http://zaelar.test/")
        src = open(_WIDGET, encoding="utf-8").read()
        await pg.add_script_tag(content=src.replace("export function render", "window.render = function render"))
        await pg.evaluate(
            "d => { window.__topCalls = 0; "
            "window.render(document.getElementById('host'), d, "
            "{action: async () => ({}), top: () => { window.__topCalls++; }})}", data)
        await pg.wait_for_timeout(60)
        await pg.click(sel)
        await pg.wait_for_timeout(60)
        calls = await pg.evaluate("() => window.__topCalls")
        await b.close()
        return calls, errors


def _run(data, sel):
    return asyncio.run(_mount_and_click(data, sel))


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_opening_a_thread_from_the_chat_list_resets_the_scroller(playwright_available):
    calls, errors = _run(_BASE, ".chatrow")
    assert errors == [], errors
    assert calls >= 1, "opening a thread must call ctx.top()"


def test_leaving_a_thread_resets_the_scroller(playwright_available):
    calls, errors = _run(_THREAD_DATA, ".thd .back")
    assert errors == [], errors
    assert calls >= 1, "closing a thread must call ctx.top()"


def test_the_dashboard_title_resets_the_scroller(playwright_available):
    # V2-621 — the dashboard header (title included) only renders for the dashboard itself: an open thread
    # has its OWN header now, with nothing to click back to the title from, so this exercises the title from
    # the dashboard's own chat-list screen instead of `_THREAD_DATA`.
    calls, errors = _run(_BASE, ".hdtitle")
    assert errors == [], errors
    assert calls >= 1, "the title always returns to the dashboard — a navigation, not a filter"


def test_the_connectors_toggle_resets_the_scroller(playwright_available):
    calls, errors = _run(_BASE, ".connbtn")
    assert errors == [], errors
    assert calls >= 1, "opening the connectors screen swaps the whole content, same as a thread"
