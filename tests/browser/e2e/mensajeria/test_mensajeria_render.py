"""V2-543 — messaging RENDERED: the pushed lens moves the screen, media actually paint, and the
placeholder speaks Spanish.

Rendering is the only way to check this half: whether `data.view` really moves the platform lens (and a
plain repaint declines to yank it), whether an image lands as an <img> against the widget's own asset
route instead of the literal `[image received]`, whether a voice note gets native controls that never
autoplay, and whether the archive/trash affordances appear ONLY on email rows — reading widget.js would
only prove the code was written.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f"
        b"\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND"
        b"\xaeB`\x82")

_ITEMS = [
    {"n": 1, "platform": "whatsapp", "from": "JOSE VICENTE", "group": None, "isGroup": False,
     "body": "[image received]", "urgencia": "media", "dirigido_a_mi": True, "motivo": "",
     "messageId": "w1", "chatId": "111", "senderId": "111", "ts": 1756742000, "mediaType": "image",
     "highlight": True,
     "media": [{"url": "/widgets/mensajeria/asset/img_x.jpg", "type": "image", "name": "img_x.jpg"}]},
    {"n": 2, "platform": "whatsapp", "from": "JOSE VICENTE", "group": None, "isGroup": False,
     "body": "[ptt received]", "urgencia": "media", "dirigido_a_mi": True, "motivo": "",
     "messageId": "w2", "chatId": "111", "senderId": "111", "ts": 1756742100, "mediaType": "ptt",
     "highlight": True,
     "media": [{"url": "/widgets/mensajeria/asset/aud_y.ogg", "type": "ptt", "name": "aud_y.ogg"}]},
    {"n": 3, "platform": "email", "from": "Ana", "group": None, "isGroup": False,
     "body": "[Asunto: factura]\n\nAdjunto la factura", "urgencia": "media", "dirigido_a_mi": False,
     "motivo": "", "messageId": "9", "chatId": "a@b.com", "senderId": "a@b.com", "ts": 1756741000,
     "highlight": False,
     "mediaType": "document", "subject": "factura", "msgid": "<x>",
     "media": [{"url": "/widgets/mensajeria/asset/eml_9_0_factura.pdf", "type": "document",
                "name": "factura.pdf"}]},
]
_CHATS = [
    {"n": 1, "platform": "whatsapp", "chatId": "111", "name": "JOSE VICENTE", "isGroup": False,
     "count": 2, "dirigido_a_mi": True, "highlight": True, "urgencia": "media", "lastFrom": "JOSE VICENTE",
     "lastBody": "[image received]", "lastMotivo": "", "lastTs": 1756742000, "lastMediaType": "image"},
    {"n": 2, "platform": "email", "chatId": "a@b.com", "name": "Ana", "isGroup": False,
     "count": 1, "dirigido_a_mi": False, "highlight": False, "urgencia": "media", "lastFrom": "Ana",
     "lastBody": "[Asunto: factura]\n\nAdjunto la factura", "lastMotivo": "",
     "lastTs": 1756741000, "lastMediaType": "document"},
]
_BASE = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "off"},
                  "email": {"status": "connected"}},
    "updated": "10:00:00", "items": _ITEMS, "count": 3, "chats": _CHATS,
    "active_chat": None, "active_items": [], "muted_channels": [], "notify_policy": {},
    "connect_focus": None, "view": None,
}
_WA_THREAD = {**_BASE, "active_chat": {"platform": "whatsapp", "chatId": "111"},
              "active_items": [_ITEMS[0], _ITEMS[1]]}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-neutral:#3a4a5c}
body{margin:0;background:#0a1017}#host{width:520px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.hb-msg');
  if (!el) return {mounted: false};
  return {
    mounted: true,
    chats: [...el.querySelectorAll('.chatrow .tfrom')].map(n => n.textContent),
    previews: [...el.querySelectorAll('.tprev')].map(n => n.textContent),
    whens: [...el.querySelectorAll('.twhen')].map(n => n.textContent).filter(Boolean).length,
    imgs: [...el.querySelectorAll('img.matt')].map(i => i.getAttribute('src')),
    img_painted: [...el.querySelectorAll('img.matt')].map(i => i.naturalWidth > 0),
    audios: [...el.querySelectorAll('audio.maud')].map(a => ({controls: a.controls, autoplay: a.autoplay,
                                                             preload: a.preload, hidden: a.style.display === 'none'})),
    // V2-616 F5 — the custom player replacing native <audio controls>: play button + a fixed bar count + a
    // time label, per audio message.
    playBtns: el.querySelectorAll('.mapbtn').length,
    waveBars: [...el.querySelectorAll('.mawave')].map(w => w.querySelectorAll('.mabar').length),
    docs: [...el.querySelectorAll('a.mdoc')].map(a => a.textContent),
    // V2-680 — a MESSAGE is a chat bubble (.tbrow) on WhatsApp/Telegram and a LETTER (.mltr) on email,
    // which reads like a mail client instead. Both shapes carry the same per-message actions, so the probe
    // has to know both or an email claim silently measures an empty list.
    row_acts: [...el.querySelectorAll('.tbrow, .mltr')].map(r =>
      [...r.querySelectorAll('.tacts button')].map(b => b.textContent).join('')),
    bodies: [...el.querySelectorAll('.tbbody, .mltrbody')].map(n => n.textContent),
    // V2-610 — the email lens's OWN shape: sender+subject+time, no body (`.msubj`/`.mfrom`, not `.tbody`).
    subjects: [...el.querySelectorAll('.msubj')].map(n => n.textContent),
    filt: el.querySelectorAll('.picon.filt').length,
    rest: [...el.querySelectorAll('.rest')].map(n => n.textContent),
    acts: window.__acts || [],
    hasHd: !!el.querySelector('.hd'),
  };
}"""


def _run(steps, clicks=None):
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

            async def _asset(route):
                await route.fulfill(status=200, content_type="image/png", body=_PNG)
            await pg.route("http://zaelar.test/widgets/mensajeria/asset/*", _asset)
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            out = []
            for i, data in enumerate(steps):
                await pg.evaluate(
                    "d => window.render(document.getElementById('host'), d, "
                    "{action: async (name, payload) => {"
                    " (window.__acts = window.__acts || []).push([name, payload]); return {}; },"
                    " top: () => {}})", data)
                await pg.wait_for_timeout(80)
                for at, sel in (clicks or []):
                    if at == i:
                        await pg.click(sel)
                        await pg.wait_for_timeout(50)
                m = await pg.evaluate(_MEASURE)
                m["errors"] = errors
                out.append(m)
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
def plain(playwright_available):
    return _run([_BASE])[0]


def test_it_mounts_the_chat_list_with_spanish_media_labels_and_times(plain):
    assert plain["mounted"] and plain["errors"] == [], plain.get("errors")
    # V2-607 — the SUMMARY is not the mailbox. Ana's mail is not addressed to him, so it is not here; JOSE
    # VICENTE's is. This used to assert both, back when the main list was everything that had been let in.
    assert plain["chats"] == ["JOSE VICENTE"], plain["chats"]
    assert any("📷 Foto" in p for p in plain["previews"]), \
        f"the bridge's placeholder must never reach the operator's eyes: {plain['previews']}"
    # V2-622 — the dashboard header belongs to the DASHBOARD itself.
    assert plain["hasHd"] is True
    assert not any("received]" in p for p in plain["previews"]), plain["previews"]
    assert plain["whens"] >= 1, "real timestamps must show"


def test_the_summary_says_out_loud_what_it_is_not_showing(plain):
    """A filtered list that looks exactly like an empty one is how the operator concludes a connector is broken —
    which is the road to V2-606. So the summary states the remainder instead of just dropping it."""
    assert plain["rest"] == ["1 mensaje más en sus canales"], plain["rest"]


def test_a_lens_shows_EVERYTHING_that_channel_brought(playwright_available):
    """The other half of the split, and the one that makes the filtering safe: Ana never reaches the summary, and
    is right there the moment he looks at his email. Nothing was dropped, only ranked.

    V2-610 — email's OWN shape is the classic client (sender+subject+time), NOT the body: the assertion moved
    from `.tbody` to `.msubj`, and a `.tbody` still showing here would mean the compact default regressed
    back to the old inline-expand list the operator asked, by voice, four times in one session to leave."""
    lens = _run([{**_BASE, "view": {"platform": "email", "n": 1, "at": 0}}])[0]
    assert lens["subjects"] and any("factura" in s for s in lens["subjects"]), lens["subjects"]
    assert lens["bodies"] == [], "la vista de email por defecto no enseña el cuerpo, solo asunto/remitente/hora"
    assert lens["rest"] == [], "inside a channel there is no remainder to announce"


def test_a_pushed_view_MOVES_the_lens_and_a_repaint_does_not_yank_it(playwright_available):
    steps = _run([_BASE,
                  {**_BASE, "view": {"platform": "whatsapp", "n": 1, "at": 0}},
                  {**_BASE, "view": {"platform": "whatsapp", "n": 1, "at": 0}}])
    assert steps[0]["chats"] == ["JOSE VICENTE"]
    assert steps[1]["chats"] == ["JOSE VICENTE"], "«solo el WhatsApp» has to move the screen"
    assert steps[1]["filt"] == 1, "the active lens must be visible on its header icon"
    assert steps[1]["rest"] == [], "a lens shows the whole channel: nothing left over to announce"
    assert steps[2]["chats"] == ["JOSE VICENTE"], "same token again: keep, never re-apply nor undo"


def test_asking_for_the_main_list_lands_even_after_a_manual_change(playwright_available):
    """email lens pushed → (screen filtered to Ana) → «vuelve a la lista principal» pushes platform '' with a
    MOVED counter: the summary comes back. The counter is the token, not the value.

    Pushed through the EMAIL lens on purpose since V2-607: it is the channel whose chat does NOT make the
    summary, so this measures the lens moving AND the summary re-filtering, instead of two identical lists."""
    steps = _run([{**_BASE, "view": {"platform": "email", "n": 1, "at": 0}},
                  {**_BASE, "view": {"platform": "", "n": 2, "at": 0}}])
    # Email renders as a FLAT mail list, not chat rows (its natural shape) — so its presence is measured on the
    # subject line (V2-610's compact default), not on `.chatrow` and not on a body it no longer shows.
    assert steps[0]["chats"] == [] and any("factura" in s for s in steps[0]["subjects"]), steps[0]["subjects"]
    assert steps[1]["chats"] == ["JOSE VICENTE"], "the main list must come back"
    assert steps[1]["rest"] == ["1 mensaje más en sus canales"]


def test_an_open_thread_has_no_dashboard_header_stacked_above_it(playwright_available):
    # V2-622 — the operator's screenshot on a hard refresh: the dashboard header ("Mensajes · N para ti" +
    # every platform dot + connectors/settings) sat stacked ABOVE the thread's own header ("← Volver ·
    # contact"), which already carries everything a thread screen needs. An open thread is its own screen now.
    m = _run([_WA_THREAD])[0]
    assert m["hasHd"] is False, "an open thread must not stack the dashboard header above its own"


def test_inside_a_thread_media_actually_paint(playwright_available):
    m = _run([_WA_THREAD])[0]
    assert m["imgs"] == ["/widgets/mensajeria/asset/img_x.jpg"], m["imgs"]
    assert m["img_painted"] == [True], "the <img> must decode real bytes from the asset route"
    # V2-616 F5 — native <audio controls> retired for a custom player: the element itself stays hidden and
    # driven by the play button/waveform, never autoplaying. preload moved to "metadata" (duration has to be
    # known for the bar and for a pre-play drag-to-seek to compute a real target time) — it fetches only the
    # file's header, never the audio bytes, so "never autoplays" still holds.
    assert m["audios"] and m["audios"][0]["controls"] is False and m["audios"][0]["autoplay"] is False
    assert m["audios"][0]["hidden"] is True
    assert m["audios"][0]["preload"] == "metadata"
    assert m["playBtns"] >= 1, "the custom play button must render"
    assert m["waveBars"] and m["waveBars"][0] > 0, "the waveform needs a fixed, non-zero bar count"
    # V2-622 — the operator: "no hace falta poner 'audio', ya se ve no?" A bare "[image received]"/"[ptt
    # received]" placeholder used to surface as a redundant "📷 Foto"/"🎤 Nota de voz" text line ABOVE the
    # image/player that already shows exactly that. Once the real media block renders, the label is noise —
    # so with no real caption, `.tbbody` must not render at all for these two messages.
    assert m["bodies"] == [], m["bodies"]


def test_archive_and_trash_appear_ONLY_on_email_rows(playwright_available):
    """Fake buttons on platforms with no archive API would be lies; email rows get both."""
    email_thread = {**_BASE, "active_chat": {"platform": "email", "chatId": "a@b.com"},
                    "active_items": [_ITEMS[2]]}
    wa = _run([_WA_THREAD])[0]
    em = _run([email_thread])[0]
    assert all("🗄" not in a and "🗑" not in a for a in wa["row_acts"]), wa["row_acts"]
    assert any("🗄" in a and "🗑" in a for a in em["row_acts"]), em["row_acts"]
    assert any("📄 factura.pdf" in d for d in em["docs"]), em["docs"]


def test_clicking_a_header_icon_goes_through_the_same_action_as_the_voice(playwright_available):
    out = _run([_BASE], clicks=[(0, ".hb-msg .dots .picon.on")])
    acts = out[0]["acts"]
    assert ["show_view", {"platform": "whatsapp"}] in acts, \
        f"UI and voice must share ONE state — the click has to stamp the server view: {acts}"
