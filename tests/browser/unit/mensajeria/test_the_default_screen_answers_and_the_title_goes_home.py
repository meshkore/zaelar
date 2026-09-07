#
# V2-610 — three defects from one manually-driven session, all in the SCREEN NAVIGATION of this widget,
# verified by RENDERING (the V2-124 lesson: a click handler that forgets to clear a flag fails with zero
# errors, and only pixels can say so).
#
#   1. Clicking a platform dot while the Conectores screen was open did NOTHING VISIBLE — it changed
#      `_platFilter` and asked the server for that lens, but never cleared `_screen`, so the connectors
#      screen kept covering the messages underneath. Measured live: «cada vez que clico, debo ir a la
#      sección que sea [...] y no se va la vista de conectores».
#   2. The «Mensajería» title had no way BACK to the unified dashboard — the operator's own words: it is
#      «la única que voy a querer mirar en principio», so the name that labels it is the shortest path to it.
#   3. Email defaulted to the SAME expanded/inline-clamp shape as a WhatsApp thread. The operator asked, by
#      voice, four times in one session, to compact it to «el asunto y la hora, como en cualquier cliente de
#      correo electrónico», and no action existed to do it — `show_view` only ever moved the LENS, never the
#      density. The fix ships the classic shape (sender + subject + time, no body) as the hardcoded DEFAULT,
#      with a second screen for the full mail — never a settings toggle (the operator's own words: a fork
#      can change it later).
#
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

_ITEMS = [
    {"n": 1, "platform": "whatsapp", "chatId": "111", "messageId": "wa1", "from": "Marta",
     "dirigido_a_mi": True, "highlight": True, "urgencia": "media", "body": "¿Comemos mañana?", "ts": 1700000000},
    {"n": 2, "platform": "email", "chatId": "ana@x.com", "messageId": "uid-ana", "from": "Ana",
     "subject": "Reunión de mañana", "dirigido_a_mi": True, "highlight": True, "urgencia": "media", "ts": 1700003600,
     "body": "[Asunto: Reunión de mañana]\nHola, ¿confirmamos a las 10 en la sala grande? Un saludo, Ana."},
    {"n": 3, "platform": "email", "chatId": "banco@x.com", "messageId": "uid-banco", "from": "Banco Ejemplo",
     "subject": "Extracto mensual", "dirigido_a_mi": False, "highlight": False, "urgencia": "baja", "ts": 1700007200,
     "body": "[Asunto: Extracto mensual]\nAdjuntamos el extracto del mes."},
]

# The unified dashboard (no lens) renders `data.chats` — the `_group_chats` shape — not raw `items`; every
# platform's traffic is grouped into one row per (platform, chatId) regardless of which platform it is.
_CHATS = [
    {"n": 1, "platform": "whatsapp", "chatId": "111", "name": "Marta", "isGroup": False, "count": 1,
     "dirigido_a_mi": True, "highlight": True, "urgencia": "media",
     "lastFrom": "Marta", "lastBody": "¿Comemos mañana?", "lastMotivo": "", "lastTs": 1700000000, "lastMediaType": ""},
    {"n": 2, "platform": "email", "chatId": "ana@x.com", "name": "Ana", "isGroup": False, "count": 1,
     "dirigido_a_mi": True, "highlight": True, "urgencia": "media",
     "lastFrom": "Ana", "lastBody": "[Asunto: Reunión de mañana]\nHola, ¿confirmamos a las 10?",
     "lastMotivo": "", "lastTs": 1700003600, "lastMediaType": ""},
    {"n": 3, "platform": "email", "chatId": "banco@x.com", "name": "Banco Ejemplo", "isGroup": False, "count": 1,
     "dirigido_a_mi": False, "highlight": False, "urgencia": "baja",
     "lastFrom": "Banco Ejemplo", "lastBody": "[Asunto: Extracto mensual]\nAdjuntamos el extracto.",
     "lastMotivo": "", "lastTs": 1700007200, "lastMediaType": ""},
]


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
                              running: true };
             window.__mod = mod;
             window.__data = data;
             window.__mount = () => mod.render(document.getElementById('w'), window.__data, window.__ctx);
             window.__mount();
           }""",
        [page._hb_widget_url, data, replies or {}],
    )


def _base_data(**extra):
    d = {"platforms": _PLATFORMS, "items": list(_ITEMS), "chats": list(_CHATS), "active_chat": None,
         "active_items": [], "muted_channels": [], "connect_focus": None}
    d.update(extra)
    return d


def test_a_platform_click_leaves_the_connectors_screen_it_was_stuck_in(_page):
    """The exact bug: open Conectores, then click a CONNECTED platform dot. Before the fix, `_screen` never
    cleared and `.chanhead` (the Conectores header) kept covering the click's own effect."""
    _mount(_page, _base_data())
    _page.locator(".connbtn").click()
    assert _page.locator(".chanhead").count() == 1               # stuck here before the fix
    _page.locator(".dots .picon.on").nth(2).click()               # ORDER=[whatsapp,telegram,email] → email
    assert _page.locator(".chanhead").count() == 0, "el clic en un canal no salió de Conectores"
    assert _page.locator(".mrow").count() >= 1, "debería estar viendo la bandeja de email, no Conectores"


def test_the_title_returns_to_the_unified_dashboard_from_any_screen(_page):
    """The operator's own words: the unified inbox is «la única que voy a querer mirar en principio» — one
    click on the name that labels it, from a platform lens, from Conectores, from anywhere."""
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()               # narrow to email
    assert _page.locator(".mrow").count() == 2                    # only email's own items
    _page.locator(".hdtitle").click()
    # Back to the unified dashboard: `highlight`-filtered, so WhatsApp's item is visible again and the
    # non-highlighted bank email (item 3) is not — exactly the V2-607 shape the summary already promises.
    assert _page.get_by_text("Marta", exact=True).count() == 1
    assert _page.get_by_text("Ana", exact=True).count() == 1
    assert _page.get_by_text("Banco Ejemplo", exact=True).count() == 0
    calls = _page.evaluate("() => window.__calls")
    assert ["show_view", {"platform": "all"}] in calls


def test_the_title_also_exits_the_connectors_screen(_page):
    _mount(_page, _base_data())
    _page.locator(".connbtn").click()
    assert _page.locator(".chanhead").count() == 1
    _page.locator(".hdtitle").click()
    assert _page.locator(".chanhead").count() == 0


# ── the Gmail-style default (V2-610) ─────────────────────────────────────────────────────────────────────

def test_email_defaults_to_sender_subject_time_and_shows_no_body(_page):
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()
    rows = _page.locator(".mrow")
    assert rows.count() == 2
    txt = rows.nth(0).inner_text()
    assert "Ana" in txt and "Reunión de mañana" in txt
    assert "confirmamos a las 10" not in txt, "el cuerpo del correo no debe verse en la lista compacta"
    assert _page.locator(".mrow .tbody").count() == 0, "esta vista no es la de mensajería expandida"


def test_the_subject_shown_is_the_real_field_not_a_guess_from_the_body(_page):
    """`subject` is a first-class field on the item (mailbox.py/service.py); the body's own first line is
    a live-arrival convention («[Asunto: X]\\n…»), not the source of truth. A body that carries no such
    prefix (a shape the pipeline can legitimately produce, and the one `load_more`'s own comment in data.py
    warns is «half a mail» without it) must still show the real subject."""
    it = dict(_ITEMS[1], body="Hola, ¿confirmamos a las 10 en la sala grande? Un saludo, Ana.")
    _mount(_page, _base_data(items=[it]))
    _page.locator(".dots .picon.on").nth(2).click()
    txt = _page.locator(".mrow").inner_text()
    assert "Reunión de mañana" in txt
    assert "Hola" not in txt, "cayó al primer renglón del cuerpo en vez de leer `subject`"


def test_opening_a_mail_shows_the_full_detail_on_a_second_screen(_page):
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()
    _page.get_by_text("Reunión de mañana").click()
    assert _page.locator(".mrow").count() == 0                    # left the list — a second SCREEN, not an inline expand
    detail = _page.locator(".mdet")
    assert detail.count() == 1
    txt = detail.inner_text()
    assert "Reunión de mañana" in txt and "Ana" in txt
    assert "confirmamos a las 10" in txt, "el detalle SÍ debe traer el cuerpo completo"
    assert _page.locator(".thd .back").count() == 1


def test_the_back_button_returns_to_the_compact_list_not_the_old_expanded_one(_page):
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()
    _page.get_by_text("Reunión de mañana").click()
    _page.locator(".thd .back").click()
    assert _page.locator(".mdet").count() == 0
    assert _page.locator(".mrow").count() == 2
    assert _page.locator(".mrow .tbody").count() == 0


def test_the_detail_screen_carries_the_same_five_actions_as_the_row_used_to(_page):
    """messageActions() was extracted so the row and the detail screen never drift into two different sets
    of buttons — this pins that they stay the SAME five (read/dismiss/archive/trash/hide)."""
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()
    _page.get_by_text("Reunión de mañana").click()
    buttons = _page.locator(".mdet ~ .tacts button, .tacts button")
    titles = _page.eval_on_selector_all(".tacts button", "els => els.map(e => e.title)")
    assert titles == ["Marcar como leído", "Descartar (no marcar leído)",
                       "Archivar en tu buzón real", "Borrar en tu buzón real (pide confirmación)",
                       "Silenciar este canal"]


def test_reading_the_open_mail_returns_to_the_list_instead_of_a_dead_screen(_page):
    """`_openMail` is a client-only pointer into `items` BY NUMBER, and numbering is POSITIONAL
    (`_renumber` assigns 1..len by order — data.py:128). Mark item n=2 (Ana) read: the server drops it and
    RENUMBERS what remains, so the mail that used to be n=3 (Banco) becomes n=2. Without clearing
    `_openMail` on the way out, the stale pointer would resolve to n=2 again on the next repaint — and now
    that is Banco's mail, not Ana's: the detail screen would silently show the WRONG message instead of
    falling back to the list."""
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()
    _page.get_by_text("Reunión de mañana").click()
    _page.locator(".tacts button").first.click()                  # "read" — server would drop item n=2 (Ana)
    remaining = [dict(it, n=i) for i, it in enumerate(  # positional renumbering, exactly like data.py
        [x for x in _ITEMS if x["n"] != 2], start=1)]
    assert remaining[-1]["from"] == "Banco Ejemplo" and remaining[-1]["n"] == 2   # Banco inherits n=2
    _page.evaluate("(data) => { window.__data = data; window.__mount(); }", _base_data(items=remaining))
    assert _page.locator(".mdet").count() == 0, "no debe reabrir el correo de Banco bajo el n reciclado de Ana"
    assert _page.locator(".mrow").count() == 1


def test_an_open_thread_still_wins_over_an_open_mail(_page):
    """V2-544's precedence, extended: a navigation the operator (or a click) just performed stays on screen
    no matter what else changed underneath it. Belt-and-braces — the server itself already clears
    `active_chat` on every `show_view` — but the client must not paint a stale mail screen either."""
    _mount(_page, _base_data())
    _page.locator(".dots .picon.on").nth(2).click()
    _page.get_by_text("Reunión de mañana").click()
    assert _page.locator(".mdet").count() == 1
    _page.evaluate("""(data) => {
        window.__data = data; window.__mount();
    }""", _base_data(active_chat={"platform": "whatsapp", "chatId": "111"},
                     active_items=[_ITEMS[0]]))
    assert _page.locator(".mdet").count() == 0
    assert _page.locator(".thdname").count() == 1
