"""The chat list of a platform PAINTS: rows, the kind filter, the name search, «Cargar más» and opening a chat.

Verified by RENDERING the widget — the lens is chosen by a pushed view, and a list that the data carries but a
`return` above never draws is invisible to any source-level check (the V2-544 shape).
"""
from __future__ import annotations

import pathlib
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from tests.browser import widget_client


_ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def page():
    with widget_client.serve() as port, sync_playwright() as pw:
        browser = pw.chromium.launch()
        pg = browser.new_page()
        pg._hb_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
        pg.goto(f"http://127.0.0.1:{port}/widgets/mensajeria/")
        yield pg
        browser.close()

def _mount(page, data):
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src + '?v=' + Math.random());
             window.__ctx = { action: (name, payload) => { window.__calls.push([name, payload || {}]); },
                              top: () => {}, openConnector: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


def _data(rows, **v):
    now = time.time()
    return {"platforms": {"telegram": {"status": "connected"}}, "items": [], "chats": [],
            "view": {"platform": "telegram", "n": 1, "at": now},
            "chat_list": {"telegram": {"rows": rows, "recent_h": 72, "total": len(rows), "more": True,
                                       "complete": False, "loading": False, "asked": True, "error": "", **v}}}


_ROWS = [
    {"chatId": "1", "name": "Marta", "kind": "person", "unread": 2, "ts": time.time() - 60, "preview": "¿hoy?"},
    {"chatId": "2", "name": "Viaje Lisboa", "kind": "group", "ts": time.time() - 3600, "preview": "vuelos",
     "fromMe": True},
    {"chatId": "3", "name": "Noticias", "kind": "channel", "ts": time.time() - 7200, "preview": "titular"},
]


def _names(page):
    return page.locator(".cxlist .tfrom").all_inner_texts()


def test_the_list_paints_every_chat_newest_first(page):
    _mount(page, _data(_ROWS))
    assert _names(page) == ["Marta", "Viaje Lisboa", "Noticias"]
    assert "Tú: vuelos" in page.locator(".cxlist").inner_text()


def test_the_kind_filter_and_the_search_narrow_it_without_a_round_trip(page):
    _mount(page, _data(_ROWS))
    page.locator(".cxchip", has_text="Grupos").click()
    assert _names(page) == ["Viaje Lisboa"]
    page.locator(".cxchip", has_text="No leídos").click()
    assert _names(page) == ["Marta"]
    page.locator(".cxchip", has_text="Todos").click()
    page.locator(".cxsearch").fill("noti")
    assert _names(page) == ["Noticias"]
    assert page.evaluate("window.__calls") == [], "filtering is local: nothing is asked of the server"


def test_load_more_and_opening_a_chat_are_the_declared_actions(page):
    _mount(page, _data(_ROWS))
    page.locator(".cxmore").click()
    page.locator(".cxlist .chatrow").first.click()
    assert page.evaluate("window.__calls") == [["chats_more", {"platform": "telegram"}],
                                               ["open", {"platform": "telegram", "chatId": "1"}]]


def test_while_the_first_page_travels_the_list_says_so(page):
    _mount(page, _data([], loading=True, asked=True))
    assert "Cargando" in page.locator(".cxlist").inner_text()


def test_the_media_window_is_chosen_in_settings(page):
    _mount(page, {**_data(_ROWS), "media_days": 14})
    page.locator("button.gear").click()
    active = page.locator(".settings .segbtn.active").all_inner_texts()
    assert "14 días" in active
    page.locator(".settings .segbtn", has_text="30 días").click()
    assert page.evaluate("window.__calls")[-1] == ["set_media_days", {"days": 30}]


def _mount_with_upload(page, data):
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data]) => {
             window.__calls = [];
             const mod = await import(src + '?v=' + Math.random());
             window.__ctx = { action: async (name, payload) => { window.__calls.push([name, payload || {}]); return {ok: true}; },
                              upload: async (file) => ({name: 'up_x1_' + file.name, url: '/widgets/mensajeria/asset/up_x1_' + file.name,
                                                        type: 'image', original: file.name}),
                              top: () => {}, openConnector: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_url, data])


def test_new_chat_and_new_group_use_the_same_doors_as_the_voice(page):
    _mount_with_upload(page, _data(_ROWS))
    page.locator(".cxnew button[aria-label='Nuevo chat']").click()
    page.locator(".newform input").first.fill("Marta")
    page.locator(".newform textarea").fill("¿comemos?")
    page.locator(".newform .bt-primary").click()
    page.wait_for_function("window.__calls.length >= 1")
    assert page.evaluate("window.__calls")[-1] == ["send_to", {"contact": "Marta", "channel": "telegram",
                                                               "text": "¿comemos?", "files": []}]
    page.locator(".cxnew button[aria-label='Nuevo grupo']").click()
    inputs = page.locator(".newform input")
    inputs.nth(0).fill("Viaje")
    inputs.nth(1).fill("Ana, Luis")
    page.locator(".newform .bt-primary").click()
    page.wait_for_function("window.__calls.length >= 2")
    assert page.evaluate("window.__calls")[-1] == ["create_group", {"platform": "telegram", "name": "Viaje",
                                                                    "members": ["Ana", "Luis"], "text": "", "files": []}]


def test_a_file_attached_in_a_conversation_rides_in_its_draft(page):
    data = {**_data(_ROWS), "active_chat": {"platform": "telegram", "chatId": "1"},
            "active_items": [{"messageId": "1:5", "chatId": "1", "platform": "telegram", "from": "Marta",
                              "body": "¿me pasas la foto?", "ts": 1}], "thread_meta": {"count": 1}}
    _mount_with_upload(page, data)
    page.locator(".compose input[type=file]").set_input_files(
        files=[{"name": "foto.jpg", "mimeType": "image/jpeg", "buffer": b"\xff\xd8x"}])
    page.wait_for_function("window.__calls.some(c => c[0] === 'draft')")
    draft = [c for c in page.evaluate("window.__calls") if c[0] == "draft"][-1][1]
    assert draft["files"] == ["up_x1_foto.jpg"]
    assert page.locator(".attchip").count() == 1
    assert not page.locator(".compose .bt-primary").is_disabled(), "a photo alone can be sent"
