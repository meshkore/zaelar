"""V2-624 — the activity lens RENDERED: a platform criterion paints a visible bar (label + off switch), the
matching conversations paint as rows whose click opens by IDENTITY (platform+chatId — these rows have no `n`
on purpose), the «traer del conector» button exists exactly where the transport can serve it, and the
autoresponder's state shows in the settings panel with its own off switch. Source reads cannot see any of
this — a criterion whose bar never paints is a silent mode, the exact thing the design forbids.
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body><div id="host"></div></body></html>"""

_NOW = time.time()
_BASE = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "connected"},
                  "email": {"status": "off"}},
    "updated": "10:00:00", "items": [], "count": 0, "chats": [],
    "active_chat": None, "active_items": [], "muted_channels": [], "notify_policy": {},
    "connect_focus": None, "view": None, "lens_criteria": {}, "activity_chats": [], "autoresponder": {},
}
_ROWS = [
    {"platform": "telegram", "chatId": "444", "name": "Marta", "isGroup": False, "lastTs": _NOW - 600,
     "lastFrom": "Marta", "lastBody": "reunión mañana", "lastMediaType": "", "inWindow": 3, "unread": 2},
    {"platform": "telegram", "chatId": "555", "name": "Grupo Viaje", "isGroup": True, "lastTs": _NOW - 7000,
     "lastFrom": "Luis", "lastBody": "del 12 al 19", "lastMediaType": "", "inWindow": 5, "unread": 0},
]
_TG_CRIT = {**_BASE, "view": {"platform": "telegram", "n": 1, "at": _NOW},
            "lens_criteria": {"telegram": {"window_h": 72.0}}, "activity_chats": _ROWS}
# n:2 — the pushed view applies only when its witness counter MOVES (V2-543), and the telegram mounts above
# already consumed n:1 in the same page.
_WA_CRIT = {**_BASE, "platforms": {**_BASE["platforms"], "whatsapp": {"status": "connected"}},
            "view": {"platform": "whatsapp", "n": 2, "at": _NOW},
            "lens_criteria": {"whatsapp": {"window_h": 24.0}}, "activity_chats": []}
_AUTO = {**_BASE, "autoresponder": {"whatsapp": {"enabled": True, "text": "De vacaciones hasta el lunes",
                                                  "hours": "22:00-08:00"}}}

_MEASURE = """() => {
  const el = document.querySelector('.hb-msg');
  return {
    critbar: !!el.querySelector('.critbar'),
    critlbl: (el.querySelector('.critlbl')||{}).textContent || '',
    hasFetch: !!el.querySelector('.critfetch'),
    rows: [...el.querySelectorAll('.chatrow .tfrom')].map(n => n.textContent),
    counts: [...el.querySelectorAll('.chatrow .tcount')].map(n => n.textContent),
    empty: (el.querySelector('.empty')||{}).textContent || '',
    acts: window.__acts || [],
  };
}"""


async def _mount(pg, data):
    await pg.evaluate(
        "d => { window.__acts = []; window.render(document.getElementById('host'), d, "
        "{action: async (name, payload) => { window.__acts.push([name, payload]); return {}; },"
        " top: () => {}}) }", data)
    await pg.wait_for_timeout(60)


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
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(content=src.replace("export function render", "window.render = function render"))

            out = {}
            await _mount(pg, _TG_CRIT)
            out["tg"] = await pg.evaluate(_MEASURE)
            await pg.click(".chatrow")                               # first row: Marta
            await pg.wait_for_timeout(40)
            out["after_open"] = await pg.evaluate("() => window.__acts")

            await _mount(pg, _TG_CRIT)
            await pg.click(".critfetch")
            await pg.wait_for_timeout(40)
            out["after_fetch"] = await pg.evaluate("() => window.__acts")

            await _mount(pg, _TG_CRIT)
            await pg.click(".critoff")
            await pg.wait_for_timeout(40)
            out["after_off"] = await pg.evaluate("() => window.__acts")

            await _mount(pg, _WA_CRIT)
            out["wa"] = await pg.evaluate(_MEASURE)

            await _mount(pg, _AUTO)
            await pg.click(".gear")
            await pg.wait_for_timeout(40)
            out["auto_text"] = await pg.evaluate(
                "() => (document.querySelector('.settings')||{}).textContent || ''")
            await pg.click(".settings .conns .lk")
            await pg.wait_for_timeout(40)
            out["after_clear"] = await pg.evaluate("() => window.__acts")

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


def test_the_criterion_paints_a_visible_bar_with_the_window(result):
    assert result["errors"] == [], result["errors"]
    m = result["tg"]
    assert m["critbar"] is True
    assert "3 días" in m["critlbl"], m["critlbl"]


def test_activity_rows_paint_and_open_by_identity(result):
    m = result["tg"]
    assert m["rows"] == ["Marta", "Grupo Viaje"]
    assert m["counts"] == ["2"], "only the chat with unread wears a badge"
    opens = [a for a in result["after_open"] if a[0] == "open"]
    assert opens and opens[0][1] == {"platform": "telegram", "chatId": "444"}, opens


def test_the_fetch_button_asks_the_connector_with_the_window(result):
    fetches = [a for a in result["after_fetch"] if a[0] == "fetch_now"]
    assert fetches and fetches[0][1] == {"platform": "telegram", "since_hours": 72.0}, fetches


def test_the_off_switch_clears_the_criterion(result):
    offs = [a for a in result["after_off"] if a[0] == "show_view"]
    assert offs and offs[0][1] == {"platform": "telegram", "window_h": 0}, offs


def test_whatsapp_gets_no_fetch_button_and_an_honest_empty(result):
    m = result["wa"]
    assert m["critbar"] is True and m["hasFetch"] is False, \
        "offering a fetch the transport cannot serve is the lie this view exists to avoid"
    assert "Sin conversaciones" in m["empty"]
    assert "Traer del conector" not in m["empty"]


def test_the_autoresponder_shows_in_settings_and_clears(result):
    assert "Autorespondedor" in result["auto_text"]
    assert "De vacaciones" in result["auto_text"] and "22:00-08:00" in result["auto_text"]
    clears = [a for a in result["after_clear"] if a[0] == "clear_autoresponder"]
    assert clears and clears[0][1] == {"platform": "whatsapp"}, clears
