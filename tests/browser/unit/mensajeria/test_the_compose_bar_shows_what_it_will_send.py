"""V2-611 — the compose bar RENDERED (the V2-124 lesson: a click handler that never fires fails silently).

Operator's spec: dictate or type, see the box, then send by voice or by the button — same text either way.
This pins the box (a) prefills from a server-side draft that matches the CURRENT screen and no other, (b)
the Send button is disabled with nothing to send, and (c) clicking it sends the box's live value.
"""
from __future__ import annotations

import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


_PLATFORMS = {"whatsapp": {"status": "connected"}, "telegram": {"status": "connected"},
              "email": {"status": "connected"}}
_MAIL = {"n": 1, "platform": "email", "chatId": "ana@x.com", "messageId": "uid-ana", "from": "Ana",
         "subject": "Reunión de mañana", "dirigido_a_mi": True, "highlight": True, "urgencia": "media",
         "ts": 1700003600, "body": "[Asunto: Reunión de mañana]\nHola, ¿confirmamos a las 10?"}
_WA_ACTIVE = {"platform": "whatsapp", "chatId": "111"}
_WA_ITEM = {"n": 2, "platform": "whatsapp", "chatId": "111", "messageId": "wa1", "from": "Marta",
            "dirigido_a_mi": True, "highlight": True, "urgencia": "media", "ts": 1700000000, "body": "¿Vienes?"}


@pytest.fixture(scope="module")
def _page():
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
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/mensajeria/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data: dict, replies: dict | None = None):
    page.goto(page._hb_origin)
    page.set_content("<div id='w'></div>")
    page.evaluate(
        """async ([src, data, replies]) => {
             window.__calls = [];
             const mod = await import(src);
             window.__ctx = { action: (name, payload) => {
                                window.__calls.push([name, payload || {}]);
                                return Promise.resolve((replies || {})[name] || null);
                              },
                              top: () => {}, running: true };
             mod.render(document.getElementById('w'), data, window.__ctx);
           }""",
        [page._hb_widget_url, data, replies or {}],
    )


def _open_email_lens(page):
    """The email row and its detail screen only render inside the email LENS — see the discovery in
    test_the_default_screen_answers_and_the_title_goes_home.py. ORDER=[whatsapp,telegram,email]."""
    page.locator(".dots .picon.on").nth(2).click()


def _base(**extra):
    d = {"platforms": _PLATFORMS, "items": [_MAIL], "chats": [], "active_chat": None, "active_items": [],
         "muted_channels": [], "connect_focus": None, "draft": None, "email_signature": []}
    d.update(extra)
    return d


def test_the_box_is_empty_and_send_is_disabled_with_no_draft(_page):
    _mount(_page, _base())
    _open_email_lens(_page)
    _page.get_by_text("Reunión de mañana").click()          # into mailDetail
    box = _page.locator(".composebox")
    assert box.count() == 1 and box.input_value() == ""
    assert _page.locator(".compose button").is_disabled()


def test_a_matching_draft_prefills_the_box(_page):
    _mount(_page, _base(draft={"text": "Sí, a las 10", "target": {"messageId": "uid-ana", "n": 1}}))
    _open_email_lens(_page)
    _page.get_by_text("Reunión de mañana").click()
    assert _page.locator(".composebox").input_value() == "Sí, a las 10"
    assert not _page.locator(".compose button").is_disabled()


def test_a_draft_for_a_different_mail_does_not_leak_into_this_screen(_page):
    other = {**_MAIL, "n": 9, "messageId": "uid-other", "subject": "Otro asunto"}
    _mount(_page, _base(items=[_MAIL, other],
                        draft={"text": "Esto es de OTRO correo", "target": {"messageId": "uid-other", "n": 9}}))
    _open_email_lens(_page)
    _page.get_by_text("Reunión de mañana", exact=True).click()
    assert _page.locator(".composebox").input_value() == ""


def test_typing_enables_send_and_queues_a_draft_call(_page):
    _mount(_page, _base())
    _open_email_lens(_page)
    _page.get_by_text("Reunión de mañana").click()
    _page.locator(".composebox").fill("Perfecto a las 10")
    assert not _page.locator(".compose button").is_disabled()


def test_clicking_send_sends_the_boxs_own_text_via_draft_then_send_draft(_page):
    _mount(_page, _base())
    _open_email_lens(_page)
    _page.get_by_text("Reunión de mañana").click()
    _page.locator(".composebox").fill("Perfecto a las 10")
    _page.locator(".compose button").click()
    calls = _page.evaluate("() => window.__calls")
    names = [c[0] for c in calls]
    assert "draft" in names and "send_draft" in names
    draft_call = next(c for c in calls if c[0] == "draft")
    assert draft_call[1]["text"] == "Perfecto a las 10"
    assert draft_call[1]["n"] == 1 and draft_call[1]["messageId"] == "uid-ana"


def test_the_compose_bar_also_renders_inside_an_open_thread_with_no_target_id(_page):
    """A thread reply addresses the CONVERSATION, not a specific message — the server resolves it from
    `active_chat` alone (V2-611's `_resolve_target`), so the widget sends no n/messageId at all here."""
    _mount(_page, _base(items=[_WA_ITEM], active_chat=_WA_ACTIVE, active_items=[_WA_ITEM]))
    assert _page.locator(".composebox").count() == 1
    _page.locator(".composebox").fill("Nos vemos luego")
    _page.locator(".compose button").click()
    draft_call = next(c for c in _page.evaluate("() => window.__calls") if c[0] == "draft")
    assert "n" not in draft_call[1] or draft_call[1].get("n") is None
    assert draft_call[1]["text"] == "Nos vemos luego"


def test_an_outgoing_mail_gets_no_compose_bar(_page):
    """There is nothing to reply TO on the operator's own echoed message."""
    out = {**_MAIL, "dir": "out", "n": None}
    _mount(_page, _base(items=[out]))
    _open_email_lens(_page)
    _page.get_by_text("Reunión de mañana").click()
    assert _page.locator(".composebox").count() == 0
