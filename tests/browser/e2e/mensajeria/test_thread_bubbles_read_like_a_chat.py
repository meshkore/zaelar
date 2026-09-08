"""V2-616 — the open thread reads as a bubble timeline: THEIRS on the left, HIS on the right, and a sender
name repeated on every single line only where the header cannot already say it once.

The operator's screenshot: a 1:1 WhatsApp thread with "JOSE VICENTE" printed on every one of three consecutive
lines — pure noise, since the thread's own header already names the contact. His words: "solo necesito ver a
la izquierda los mensajes de [him] y a la derecha los míos". RENDERED against the real widget.js, because the
defect and the fix are both about the visible SHAPE (which side a row sits on, whether a name prints at all),
not about data the source can be read for.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;background:#0a1017}#host{width:520px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.hb-msg');
  return {
    mounted: !!el,
    fromNames: [...el.querySelectorAll('.tbfrom')].map(n => n.textContent),
    inRows: el.querySelectorAll('.tbrow:not(.out)').length,
    outRows: el.querySelectorAll('.tbrow.out').length,
    outBodies: [...el.querySelectorAll('.tbrow.out .tbbody')].map(n => n.textContent),
  };
}"""

_DM_ACTIVE = {"platform": "whatsapp", "chatId": "38203901878473@lid"}
_DM_ITEMS = [
    {"n": 1, "platform": "whatsapp", "from": "JOSE VICENTE", "dir": "in", "chatId": _DM_ACTIVE["chatId"],
     "messageId": "m1", "body": "Estoy aquí", "ts": 1, "urgencia": "media", "dirigido_a_mi": True},
    {"n": 2, "platform": "whatsapp", "from": "JOSE VICENTE", "dir": "in", "chatId": _DM_ACTIVE["chatId"],
     "messageId": "m2", "body": "Y no hay nadie", "ts": 2, "urgencia": "media", "dirigido_a_mi": True},
    {"platform": "whatsapp", "from": "Tú", "dir": "out", "chatId": _DM_ACTIVE["chatId"],
     "messageId": "m3", "body": "Ya voy para allá", "ts": 3},
]
_DM_DATA = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "off"}, "email": {"status": "off"}},
    "updated": "10:00:00", "items": [], "count": 0, "chats": [],
    "active_chat": _DM_ACTIVE, "active_items": _DM_ITEMS, "thread_meta": {"isGroup": False, "complete": True},
    "muted_channels": [], "notify_policy": {}, "connect_focus": None, "view": None,
}

_GROUP_ACTIVE = {"platform": "whatsapp", "chatId": "111-222@g.us"}
_GROUP_ITEMS = [
    {"n": 1, "platform": "whatsapp", "from": "Elena", "dir": "in", "chatId": _GROUP_ACTIVE["chatId"],
     "messageId": "g1", "body": "Hola a todos", "ts": 1, "urgencia": "media", "dirigido_a_mi": False},
    {"n": 2, "platform": "whatsapp", "from": "Raquel", "dir": "in", "chatId": _GROUP_ACTIVE["chatId"],
     "messageId": "g2", "body": "Yo también puedo", "ts": 2, "urgencia": "media", "dirigido_a_mi": False},
]
_GROUP_DATA = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "off"}, "email": {"status": "off"}},
    "updated": "10:00:00", "items": [], "count": 0, "chats": [],
    "active_chat": _GROUP_ACTIVE, "active_items": _GROUP_ITEMS, "thread_meta": {"isGroup": True, "complete": True},
    "muted_channels": [], "notify_policy": {}, "connect_focus": None, "view": None,
}


def _run(data):
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
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            await pg.evaluate(
                "d => window.render(document.getElementById('host'), d, "
                "{action: async () => ({})})", data)
            await pg.wait_for_timeout(80)
            m = await pg.evaluate(_MEASURE)
            m["errors"] = errors
            await b.close()
            return m
    return asyncio.run(go())


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_a_1to1_thread_never_repeats_the_contacts_name(playwright_available):
    """The header above the list already says who this is — repeating "JOSE VICENTE" on every bubble is the
    operator's literal complaint."""
    m = _run(_DM_DATA)
    assert m["mounted"] and m["errors"] == [], m.get("errors")
    assert m["fromNames"] == [], m["fromNames"]


def test_a_group_thread_still_names_each_sender(playwright_available):
    """A group has no single "who this is" for the header to say once — the name has to stay on the bubble."""
    m = _run(_GROUP_DATA)
    assert m["mounted"] and m["errors"] == [], m.get("errors")
    assert m["fromNames"] == ["Elena", "Raquel"], m["fromNames"]


def test_his_own_replies_sit_on_the_right_and_are_visible(playwright_available):
    """"He answered but doesn't see his own messages" — the outgoing row must actually render, on the .out
    side, with its own text intact."""
    m = _run(_DM_DATA)
    assert m["inRows"] == 2, m["inRows"]
    assert m["outRows"] == 1, m["outRows"]
    assert m["outBodies"] == ["Ya voy para allá"], m["outBodies"]
