"""V2-626 — the header and the body are ONE state, RENDERED: naming a channel (by voice or by tap) leaves
whatever screen was underneath, and the specific request wins when a payload carries both.

The operator's screenshot (2026-09-09): he asked for his mail, the email dot lit up — and the WhatsApp
connector screen stayed sitting below it. `_platFilter` had moved and `_screen` had not, so `showChannels`
returned early and the whole lens never rendered. Selecting a channel is state MECHANICS, not routing logic:
whoever asks, the body follows. Only a render can see this — the source assigns the filter either way.
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest
from tests.browser import widget_client

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body><div id="host"></div></body></html>"""

_NOW = time.time()
_ITEMS = [
    {"n": 1, "platform": "email", "from": "Ana", "subject": "Presupuesto", "body": "te paso el número",
     "ts": _NOW - 600, "urgencia": "media", "dirigido_a_mi": True, "highlight": True, "chatId": "ana@x.com"},
    {"n": 2, "platform": "whatsapp", "from": "Luis", "body": "¿comemos?", "ts": _NOW - 900,
     "urgencia": "media", "dirigido_a_mi": True, "highlight": True, "chatId": "34600"},
]
_BASE = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "connected"},
                  "email": {"status": "connected"}},
    "updated": "10:00:00", "items": _ITEMS, "count": 2,
    "chats": [{"platform": "whatsapp", "chatId": "34600", "name": "Luis", "n": 2, "count": 1,
               "highlight": True, "dirigido_a_mi": True, "last": "¿comemos?", "ts": _NOW - 900}],
    "active_chat": None, "active_items": [], "muted_channels": [], "notify_policy": {},
    "connect_focus": None, "view": None, "lens_criteria": {}, "activity_chats": [], "autoresponder": {},
}
# A store still carrying a connect order from before connectors left the card.
_ON_WIZARD = {**_BASE, "connect_focus": {"platform": "whatsapp", "ts": 1000}}
# «Enséñame el correo» — the SAME payload the server pushes for show_view {platform:'email'}.
_SAY_EMAIL = {**_BASE, "connect_focus": {"platform": "whatsapp", "ts": 1000},
              "view": {"platform": "email", "n": 1, "at": _NOW}}
# One payload carrying BOTH a lens change and an old connect order: the lens lands, nothing else is drawn.
_BOTH = {**_BASE, "connect_focus": {"platform": "telegram", "ts": 4000},
         "view": {"platform": "email", "n": 2, "at": _NOW}}
# «Vuelve al WhatsApp» while an email is open on screen (a detail screen is a screen too).
_SAY_WA = {**_BASE, "view": {"platform": "whatsapp", "n": 3, "at": _NOW}}

_MEASURE = """() => {
  const el = document.querySelector('.hb-msg');
  return {
    // The setup area has two screens: the connector LIST (.chanhead) and one connector's wizard
    // (.crumb). Either of them being on screen means the messages are not.
    onSetupScreen: !!el.querySelector('.crumb, .chanhead'),
    onMailDetail: !!el.querySelector('.mdet'),
    pendingConfirm: !!el.querySelector('.cfm'),
    mails: [...el.querySelectorAll('.mrow .mfrom')].map(n => n.textContent),
    chats: [...el.querySelectorAll('.chatrow .tfrom')].map(n => n.textContent),
    lit: [...el.querySelectorAll('.dots .filt')].map(n => (n.title||'').split(':')[0]),
    acts: window.__acts || [],
  };
}"""


async def _mount(pg, data):
    await pg.evaluate(
        "d => { window.__acts = []; window.render(document.getElementById('host'), d, "
        "{action: async (name, payload) => { window.__acts.push([name, payload]); return {}; },"
        " top: () => {}, openConnector: (cx) => { window.__acts.push(['openConnector', cx]); }}) }", data)
    await pg.wait_for_timeout(60)


async def _click(pg, sel):
    """Click if it is there. A missing element is a MEASUREMENT here, not a harness crash: when this
    regresses, the screen that should have yielded is still on top and the row simply is not on the page —
    that has to reach the assertions as a red assertion, not as a 30 s timeout that errors every case."""
    try:
        await pg.click(sel, timeout=1500)
    except Exception:
        return False
    await pg.wait_for_timeout(60)
    return True


def _run():
    async def go():
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
            await widget_client.mount(pg, "mensajeria")

            out = {}
            await _mount(pg, _ON_WIZARD)
            out["wizard"] = await pg.evaluate(_MEASURE)      # the starting screen, as in the screenshot
            await _mount(pg, _SAY_EMAIL)                     # …and now he asks for his mail
            out["voice_email"] = await pg.evaluate(_MEASURE)

            # The same order given by TAP, from the setup screen: one door, one behaviour.
            await _mount(pg, _ON_WIZARD)
            await _mount(pg, {**_ON_WIZARD, "connect_focus": {"platform": "whatsapp", "ts": 3000}})
            await _click(pg, ".dots .picon[title^='WhatsApp']")
            out["tap"] = await pg.evaluate(_MEASURE)

            # Both in one payload: the specific request (open Telegram's wizard) is the one left standing.
            await _mount(pg, _BOTH)
            out["both"] = await pg.evaluate(_MEASURE)

            # A mail detail is a screen too: open one, then name another channel by voice.
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 5, "at": _NOW}})
            await _click(pg, ".mrow")
            out["mail_open"] = await pg.evaluate(_MEASURE)
            await _mount(pg, {**_SAY_WA, "view": {"platform": "whatsapp", "n": 6, "at": _NOW}})
            out["voice_wa"] = await pg.evaluate(_MEASURE)

            # SAME channel, from its own detail screen: «enséñame el correo» with a mail open asks for
            # that channel's LIST. The platform guard cannot catch this one — the lens does not change.
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 7, "at": _NOW}})
            await _click(pg, ".mrow")
            out["mail_open2"] = await pg.evaluate(_MEASURE)
            await _mount(pg, {**_BASE, "view": {"platform": "email", "n": 8, "at": _NOW}})
            out["same_lens"] = await pg.evaluate(_MEASURE)

            # The plug, from a channel: the ⚙ Conectores section on THAT channel, through the host's one door.
            await _mount(pg, {**_BASE, "view": {"platform": "telegram", "n": 9, "at": _NOW}})
            await _click(pg, ".connbtn")
            out["plug"] = await pg.evaluate(_MEASURE)

            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


@pytest.fixture(scope="module")
def result(playwright_available):
    return _run()


# 2026-10-04 the connector screens LEFT the card for ⚙ Conectores (one door, `ctx.openConnector`): an old
# `connect_focus` in the store must never bring a setup screen back over his messages.
def test_a_connect_order_never_draws_a_setup_screen_over_the_messages(result):
    assert result["errors"] == [], result["errors"]
    assert result["wizard"]["onSetupScreen"] is False
    assert result["wizard"]["chats"] == ["Luis"], result["wizard"]


def test_a_voiced_channel_leaves_the_setup_screen_and_paints_its_own(result):
    """The bug in the screenshot: the dot lit, the body did not move."""
    m = result["voice_email"]
    assert m["onSetupScreen"] is False, "the connectors screen survived a pushed view"
    assert m["mails"] == ["Ana"], m


def test_a_tapped_channel_does_the_same_thing(result):
    assert result["tap"]["onSetupScreen"] is False


def test_a_pushed_view_lands_even_when_the_payload_also_carries_a_connect_order(result):
    m = result["both"]
    assert m["onSetupScreen"] is False and m["mails"] == ["Ana"], m


def test_an_open_mail_is_a_screen_and_yields_too(result):
    assert result["mail_open"]["onMailDetail"] is True
    m = result["voice_wa"]
    assert m["onMailDetail"] is False, "the mail detail survived a change of channel"
    assert m["chats"] == ["Luis"], m


def test_the_same_channel_from_its_detail_lands_on_that_channels_list(result):
    """The platform guard cannot see this one: the lens does not change, only the screen has to."""
    assert result["mail_open2"]["onMailDetail"] is True
    m = result["same_lens"]
    assert m["onMailDetail"] is False, "asking for the mail while reading one kept the detail"
    assert m["mails"] == ["Ana"], m


def test_the_plug_opens_the_connectors_section_on_the_channel_on_screen(result):
    m = result["plug"]
    assert ["openConnector", "telegram"] in m["acts"], m["acts"]
    assert m["onSetupScreen"] is False and m["pendingConfirm"] is False, "the card holds no connector screen"
