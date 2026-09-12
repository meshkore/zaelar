"""V2-680 — messaging as a real mail client, RENDERED inside the real card chrome.

The operator's report, with a screenshot of an open email: the message was shown through a keyhole while
the card around it sat mostly empty, and the reply box was two lines with the button underneath it. His
spec, verbatim in substance: the widget adapts to the card; an open mail shows the WHOLE body using all the
available surface with its own scroll («si el mensaje tiene tres páginas, lo muestras entero»); the reply
box is pinned at the very bottom with a MINIMUM of five rows and the send button to its RIGHT; a «guardar
borrador» button beside it or automatic saving; and a reply / reply-all selector above the box.

Everything here is measured from LAYOUT, not from source: the whole claim is about pixels, and a rule that
loses by source order or to a missing height chain reads identically in the file. The fixture mounts the
REAL card structure from `desktop.js` (`.hb-win` flex column → `.hb-scroll` flex:1 min-height:0), because
the height chain being tested only exists when the host actually bounds it — a bare `<div>` host would make
every one of these cases pass regardless of the widget's CSS (the V2-608 fixture lesson).
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

CARD_W, CARD_H = 760, 620

# The card chrome copied from `frontend/app/widgets/desktop.js` — the two rules the height chain depends on.
_HOST = """<!doctype html><html><head><meta charset="utf-8"><style>
  body{margin:0;padding:20px;font-family:-apple-system,system-ui,sans-serif}
  .hb-win{position:relative;background:#fff;border:1px solid #e3e8f0;border-radius:16px;
          padding:30px 16px 16px;overflow:hidden;display:flex;flex-direction:column;
          width:%dpx;height:%dpx;box-sizing:border-box}
  .hb-scroll{flex:1 1 auto;min-height:0;overflow:auto}
</style></head><body>
  <div class="hb-win"><div class="hb-scroll"><div id="w"></div></div></div>
</body></html>""" % (CARD_W, CARD_H)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


_PLATFORMS = {"whatsapp": {"status": "connected"}, "telegram": {"status": "connected"},
              "email": {"status": "connected"}}

# Three pages of text, the operator's own example. Built long enough that no card could show it whole.
_LONG = "\n".join(f"Párrafo {i}: " + ("texto de relleno que ocupa una línea entera del cuerpo. " * 3)
                  for i in range(1, 61))

_MAIL = {"n": 1, "platform": "email", "chatId": "ana@x.com", "messageId": "uid-ana", "from": "Ana",
         "subject": "Reunión de mañana", "dirigido_a_mi": True, "highlight": True, "urgencia": "media",
         "ts": 1700003600, "body": f"[Asunto: Reunión de mañana]\n{_LONG}"}

# A SECOND mail, and one that really had other recipients — the only shape where reply-all is honest.
_MAIL2 = {"n": 2, "platform": "email", "chatId": "luis@x.com", "messageId": "uid-luis", "from": "Luis",
          "subject": "Presupuesto", "dirigido_a_mi": True, "highlight": True, "urgencia": "media",
          "ts": 1700003500, "body": "[Asunto: Presupuesto]\n¿Lo revisamos?",
          "recipients": ["marta@x.com", "pedro@x.com"]}


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
            page = browser.new_page(viewport={"width": 900, "height": 760})
            page._hb_widget_url = f"http://127.0.0.1:{port}/widgets/mensajeria/widget.js"
            page._hb_origin = f"http://127.0.0.1:{port}/widgets/mensajeria/"
            yield page
            browser.close()
    finally:
        srv.terminate()


def _mount(page, data: dict, replies: dict | None = None):
    page.goto(page._hb_origin)
    page.set_content(_HOST)
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


def _base(**extra):
    d = {"platforms": _PLATFORMS, "items": [_MAIL, _MAIL2], "chats": [], "active_chat": None,
         "active_items": [], "muted_channels": [], "connect_focus": None, "draft": None, "drafts": {},
         "email_signature": []}
    d.update(extra)
    return d


def _open_email_lens(page):
    """The email rows only render inside the email LENS. ORDER=[whatsapp,telegram,email]."""
    page.locator(".dots .picon.on").nth(2).click()


def _open(page, subject="Reunión de mañana", **extra):
    _mount(page, _base(**extra))
    _open_email_lens(page)
    page.get_by_text(subject).click()
    page.wait_for_timeout(60)


def _box(page, sel):
    return page.locator(sel).bounding_box()


def _calls(page, name=None):
    calls = page.evaluate("window.__calls")
    return [c for c in calls if name is None or c[0] == name]


# ── the card ──────────────────────────────────────────────────────────────────────────────────────────

def test_an_open_mail_takes_the_whole_card_instead_of_a_keyhole(_page):
    """The operator's actual complaint: the message occupied a sliver and the rest of the card was empty."""
    _open(_page)
    card = _box(_page, ".hb-win")
    body = _box(_page, ".mdet")
    # BOTH bounds, and the second one is the whole point. Measured before the fix, the body's box was
    # 2787px tall inside a 620px card: it did not fit, so the CARD scrolled and the reply box went with
    # it. A lower bound alone would have passed on exactly that, which is what the disarm caught.
    assert body["height"] > card["height"] * 0.4, (body, card)      # it fills the card…
    assert body["height"] <= card["height"], (body, card)           # …and stays inside it


def test_the_reply_box_is_pinned_to_the_BOTTOM_of_the_card(_page):
    """«Anclada abajo» — the box must not travel with the body's scroll, at any body length."""
    _open(_page)
    card = _box(_page, ".hb-win")
    compose = _box(_page, ".compose")
    card_bottom = card["y"] + card["height"]
    compose_bottom = compose["y"] + compose["height"]
    # Inside the card's own bottom padding (16px in the real chrome), never floating mid-card.
    assert card_bottom - compose_bottom < 30, (card_bottom, compose_bottom)


def test_a_SHORT_mail_still_pins_the_box_to_the_bottom(_page):
    """The case that actually proves the height chain resolves. With a long mail the compose bar could
    land at the bottom simply because the content pushed it there — a widget with no height at all would
    look identical. A two-line mail has nothing to push with: only a card-height widget puts the box on
    the bottom edge."""
    short = dict(_MAIL2)
    _mount(_page, _base(items=[short]))
    _open_email_lens(_page)
    _page.get_by_text("Presupuesto").click()
    _page.wait_for_timeout(60)
    card = _box(_page, ".hb-win")
    compose = _box(_page, ".compose")
    assert (card["y"] + card["height"]) - (compose["y"] + compose["height"]) < 30, (card, compose)


def test_a_three_page_mail_scrolls_INSIDE_the_body_and_not_the_whole_card(_page):
    """«Si el mensaje tiene tres páginas, lo muestras entero» — entire, through its OWN scroll, so the
    header and the reply box stay put while it moves."""
    _open(_page)
    metrics = _page.evaluate("""() => {
        const b = document.querySelector('.mdet');
        const host = document.querySelector('.hb-scroll');
        return {inner: b.scrollHeight - b.clientHeight, host: host.scrollHeight - host.clientHeight};
    }""")
    assert metrics["inner"] > 200, metrics          # there IS more mail than fits — it can be scrolled to
    assert metrics["host"] <= 1, metrics            # and the CARD itself does not scroll


def test_scrolling_the_body_does_not_move_the_reply_box(_page):
    """The counterweight to the case above: an inner scroller that merely exists proves nothing if the
    pinned parts ride along with it."""
    _open(_page)
    before = _box(_page, ".compose")["y"]
    _page.evaluate("document.querySelector('.mdet').scrollTop = 400")
    _page.wait_for_timeout(60)
    after = _box(_page, ".compose")["y"]
    assert abs(after - before) < 2, (before, after)
    assert _page.evaluate("document.querySelector('.mdet').scrollTop") > 300   # it really did scroll


def test_the_dashboard_list_still_scrolls_as_one_page(_page):
    """The counterweight to the whole feature: only a READING screen takes the card. Giving the dashboard
    a fixed height would pin its own header against a short card for no gain."""
    _mount(_page, _base())
    assert _page.locator(".hb-msg.full").count() == 0
    assert _page.evaluate("getComputedStyle(document.querySelector('.hb-scroll')).overflow") != "hidden"


# ── the reply box ─────────────────────────────────────────────────────────────────────────────────────

def test_the_box_has_at_least_five_rows(_page):
    """His stated minimum. Measured as ROWS and as rendered height: `rows` alone is overridable by CSS,
    and a height alone would pass on a box declaring rows=1 with a tall line-height."""
    _open(_page)
    rows = _page.evaluate("document.querySelector('.composebox').rows")
    assert rows >= 5, rows
    h = _box(_page, ".composebox")["height"]
    line = _page.evaluate("""() => {
        const cs = getComputedStyle(document.querySelector('.composebox'));
        return parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.2;
    }""")
    assert h >= line * 5, (h, line)


def test_the_send_button_is_to_the_RIGHT_of_the_box_not_underneath_it(_page):
    """«El botón de enviar a su derecha» — to the right OF THE BOX, which is also what keeps a box the
    operator drags taller from pushing the button off the bottom edge of the card."""
    _open(_page)
    box = _box(_page, ".composebox")
    send = _box(_page, ".compose .bt-primary")
    assert send["x"] >= box["x"] + box["width"] - 1, (box, send)      # entirely to its right
    # …and beside it, not below: their vertical extents overlap.
    assert send["y"] < box["y"] + box["height"] and box["y"] < send["y"] + send["height"], (box, send)


def test_saving_a_draft_writes_it_WITHOUT_sending_and_says_so(_page):
    """«Un botón de guardar borrador al lado» — and a save nobody can see is indistinguishable from a
    button that does nothing."""
    _open(_page)
    _page.locator(".composebox").fill("Te confirmo mañana")
    save = _page.get_by_role("button", name="Guardar borrador")
    save.click()
    _page.wait_for_timeout(80)
    drafts = _calls(_page, "draft")
    assert drafts and drafts[-1][1]["text"] == "Te confirmo mañana"
    assert _calls(_page, "send_draft") == []                          # saving is NOT sending
    assert "Guardado" in _page.locator(".composeside .bt:not(.bt-primary)").inner_text()


def test_the_draft_is_ALSO_saved_on_its_own_while_he_types(_page):
    """The button is the explicit half of the same promise; the autosave is what makes an interrupted
    reply survive without him remembering to press anything."""
    _open(_page)
    _page.locator(".composebox").fill("A medias")
    _page.wait_for_timeout(700)                                       # past the 500ms debounce
    assert [c[1]["text"] for c in _calls(_page, "draft")] == ["A medias"]


# ── one draft per conversation ────────────────────────────────────────────────────────────────────────

def test_each_conversation_shows_its_OWN_draft(_page):
    """Before this there was exactly ONE draft in the whole widget, so starting a reply to a second
    conversation silently destroyed the first."""
    drafts = {"m:uid-ana": {"key": "m:uid-ana", "text": "Para Ana"},
              "m:uid-luis": {"key": "m:uid-luis", "text": "Para Luis"}}
    _open(_page, drafts=drafts)
    assert _page.locator(".composebox").input_value() == "Para Ana"
    _page.locator(".thd .back").click()                               # ← back to the list
    _page.wait_for_timeout(60)
    _page.get_by_text("Presupuesto").click()
    _page.wait_for_timeout(60)
    assert _page.locator(".composebox").input_value() == "Para Luis"


def test_a_draft_for_ANOTHER_conversation_never_prefills_this_one(_page):
    """The counterweight: keying by conversation is only worth anything if a foreign key does not match."""
    _open(_page, drafts={"m:uid-luis": {"key": "m:uid-luis", "text": "Para Luis"}})
    assert _page.locator(".composebox").input_value() == ""


def test_the_send_NAMES_its_conversation(_page):
    """With a draft per conversation, a bare send_draft reaches for the most recently TOUCHED one, which
    is not necessarily the screen the button is on."""
    _open(_page)
    _page.locator(".composebox").fill("Vale")
    _page.locator(".compose .bt-primary").click()
    _page.wait_for_timeout(120)
    sends = _calls(_page, "send_draft")
    assert sends and sends[-1][1].get("messageId") == "uid-ana", sends


# ── reply / reply-all ─────────────────────────────────────────────────────────────────────────────────

def test_reply_all_is_offered_only_when_the_original_HAD_other_recipients(_page):
    """Offering it on a mail with nobody else on it would send the identical single reply under a second
    name — the operator would believe the others were answered."""
    _open(_page, subject="Presupuesto")
    assert _page.get_by_role("button", name="Responder a todos").count() == 1
    _open(_page)                                                      # the mail with no other recipients
    assert _page.get_by_role("button", name="Responder a todos").count() == 0


def test_choosing_reply_all_carries_it_into_the_draft(_page):
    """The choice has to reach the send, or the selector is decoration."""
    _open(_page, subject="Presupuesto")
    _page.get_by_role("button", name="Responder a todos").click()
    _page.wait_for_timeout(60)
    _page.locator(".composebox").fill("A todos")
    _page.locator(".compose .bt-primary").click()
    _page.wait_for_timeout(120)
    drafts = _calls(_page, "draft")
    assert drafts and drafts[-1][1].get("reply_all") is True, drafts


def test_a_plain_reply_stays_a_plain_reply(_page):
    """The default, and the counterweight to the case above."""
    _open(_page, subject="Presupuesto")
    _page.locator(".composebox").fill("Solo a ti")
    _page.locator(".compose .bt-primary").click()
    _page.wait_for_timeout(120)
    drafts = _calls(_page, "draft")
    assert drafts and drafts[-1][1].get("reply_all") is False, drafts


def test_the_selector_NAMES_who_a_reply_all_would_copy(_page):
    """A promise about who gets a copy is only worth making if he can see it before pressing send."""
    _open(_page, subject="Presupuesto")
    assert "2 destinatarios más" in _page.locator(".composehint").inner_text()
    _page.get_by_role("button", name="Responder a todos").click()
    _page.wait_for_timeout(60)
    hint = _page.locator(".composehint").inner_text()
    assert "marta@x.com" in hint and "pedro@x.com" in hint, hint


def test_the_choice_does_not_follow_him_to_the_next_mail(_page):
    """Reply-all is a property of the reply being written, not of the widget."""
    _open(_page, subject="Presupuesto")
    _page.get_by_role("button", name="Responder a todos").click()
    _page.wait_for_timeout(60)
    _page.locator(".thd .back").click()
    _page.wait_for_timeout(60)
    _page.get_by_text("Reunión de mañana").click()                    # no other recipients at all
    _page.wait_for_timeout(60)
    _page.locator(".composebox").fill("Otra cosa")
    _page.locator(".compose .bt-primary").click()
    _page.wait_for_timeout(120)
    drafts = _calls(_page, "draft")
    assert drafts and drafts[-1][1].get("reply_all") is False, drafts
