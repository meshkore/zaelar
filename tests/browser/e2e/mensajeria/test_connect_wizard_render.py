"""V2-570 — the connect wizard RENDERED: one step at a time, an icon-grid provider picker, a real list
screen, and a retry that moves.

Rendering is the only way to answer any of this. The operator's redesign asked for four things that all
live in pixels and DOM state, none of which a source-level read can confirm:

  · «pon el paso 1, paso 2, paso 3… si comprimo, solo el primer paso, y da a continuar y pasa al segundo» —
    exactly ONE `.wstep` box in the DOM at a time, with a working Atrás/Continuar pager.
  · «pon los proveedores de correo en una caja con el icono en medio» — a `.igrid` of `.ibox` boxes, not a
    `<select>`, for both the email-provider step AND the top-level connector list.
  · «no podemos tener los conectores listados verticalmente en la misma pantalla que el asistente… dos
    pantallas, y un botón para volver atrás» — a breadcrumb (`.crumb`) separating the list screen from a
    single connector's wizard screen.
  · «cuando diga conecta Gmail, entra en el conector de Gmail, no en la lista» — `connect_focus` has to land
    directly on that connector's wizard screen, never the list.

Plus the older invariants this redesign must not break: the middle step is a real link to the page that
creates the app password, spaces the provider prints never reach the field, a refusal keeps the draft, a
retry moves the cursor instead of repainting nothing, and the connect button is reachable on a phone.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "mensajeria", "widget.js")

_OFF = {
    "platforms": {"whatsapp": {"status": "connected"}, "telegram": {"status": "off"},
                  "email": {"status": "off"}},
    "updated": "10:00:00", "items": [], "count": 0, "chats": [],
    "active_chat": None, "active_items": [], "muted_channels": [], "notify_policy": {},
    "connect_focus": {"platform": "email", "ts": 1}, "view": None,
}
# What the connector publishes when the supervisor refuses the order (V2-559): status error + the reason.
_REFUSED = {**_OFF, "connect_focus": None,
            "platforms": {**_OFF["platforms"],
                          "email": {"status": "error",
                                    "detail": "Eso es un ENLACE, no la contraseña. Abre el enlace…"}}}
# Asking for a connector that is already connected must still land on ITS screen — the manifest promises
# "su estado si ya lo está", never silence and never the message list.
_CONNECTED = {**_OFF, "connect_focus": {"platform": "email", "ts": 1},
              "platforms": {**_OFF["platforms"], "email": {"status": "connected"}}}
# Nothing connected at all: the panel opens by itself on the LIST (V2-051's onboarding), with no
# connect_focus needed — this is the fresh-install case, distinct from the header 🔌 toggle (exercised via
# `_open_connector_list` below on an install that already has something connected).
_LIST = {**_OFF, "connect_focus": None,
         "platforms": {"whatsapp": {"status": "off"}, "telegram": {"status": "off"}, "email": {"status": "off"}}}

_PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08"
        b"\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00"
        b"\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202c;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-risk:#e05252;--hb-neutral:#3a4a5c;
      --hb-hover:#1d2a38}
body{margin:0;background:#0a1017}#host{padding:8px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.hb-msg');
  if (!el) return {mounted: false};
  const box = n => { const r = n.getBoundingClientRect(); return {w: r.width, h: r.height, x: r.x, y: r.y}; };
  const crumbCur = el.querySelector('.crumb .cur');
  const steps = [...el.querySelectorAll('.wstep')].map(s => ({
    num: (s.querySelector('.wnum') || {}).textContent,
    title: (s.querySelector('.wtitle') || {}).textContent,
    ...box(s),
  }));
  const wcount = (el.querySelector('.wcount') || {}).textContent || '';
  const link = el.querySelector('.wstep .wlink');
  const pw = el.querySelector('input[type=password]');
  const addr = el.querySelector('input[type=email]');
  const foot = el.querySelector('.wfoot');
  const backBtn = foot ? foot.querySelector('.bt-ghost') : null;
  const nextBtn = foot ? foot.querySelector('.bt-primary') : null;
  const iboxes = [...el.querySelectorAll('.igrid .ibox')].map(b => ({
    label: (b.querySelector('.ilabel') || {}).textContent,
    sel: b.classList.contains('sel'),
    conn: b.classList.contains('conn'),
    ...box(b),
  }));
  return {
    mounted: true,
    crumb: crumbCur ? crumbCur.textContent : null,
    hasCrumb: !!el.querySelector('.crumb'),
    chanhead: !!el.querySelector('.chanhead'),
    steps, wcount, iboxes,
    link: link ? {href: link.getAttribute('href'), text: link.textContent, ...box(link)} : null,
    pw: pw ? pw.value : null,
    addr: addr ? addr.value : null,
    focus_is_pw: !!pw && document.activeElement === pw,
    pw_flagged: !!pw && pw.classList.contains('errfield'),
    errcard: !!el.querySelector('.errcard'),
    err_text: (el.querySelector('.err') && el.querySelector('.err').style.display !== 'none')
              ? el.querySelector('.err').textContent : '',
    backBtn: backBtn ? {text: backBtn.textContent, ...box(backBtn)} : null,
    nextBtn: nextBtn ? {text: nextBtn.textContent, ...box(nextBtn)} : null,
    root: box(el),
    doc_w: document.documentElement.scrollWidth,
    view_w: window.innerWidth,
    acts: window.__acts || [],
    att_maxw: (() => { const i = el.querySelector('.mediaw .matt');
      return i ? getComputedStyle(i).maxWidth : null; })(),
  };
}"""


def _run(steps, actions=None, width=560):
    """`actions` = list of (step_index, async callable(page)) run after that render."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": width, "height": 900})
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
                    " (window.__acts = window.__acts || []).push([name, payload]); return {}; }})", data)
                await pg.wait_for_timeout(90)
                for at, fn in (actions or []):
                    if at == i:
                        await fn(pg)
                        await pg.wait_for_timeout(90)
                m = await pg.evaluate(_MEASURE)
                m["errors"] = errors
                out.append(m)
            await b.close()
            return out
    return asyncio.run(go())


async def _click_ibox(pg, label_substr):
    for b in await pg.query_selector_all(".hb-msg .igrid .ibox"):
        t = (await b.inner_text()).lower()
        if label_substr.lower() in t:
            await b.click()
            return
    raise AssertionError(f"no icon box labelled like {label_substr!r}")


async def _click_next(pg):
    await pg.click(".hb-msg .wfoot .bt-primary")


async def _click_back(pg):
    await pg.click(".hb-msg .wfoot .bt-ghost")


async def _open_connector_list(pg):
    """The header 🔌 button, for an install that already has something connected (the panel does not open
    by itself in that case — only a fresh, nothing-connected install or a named connect_focus does)."""
    await pg.click(".hb-msg .connbtn")


async def _goto_email_step3(pg):
    """gmail is the default provider (step 1 is already valid) — just page forward twice."""
    await _click_next(pg)   # step 1 -> 2
    await _click_next(pg)   # step 2 -> 3


async def _fill_and_submit(pg):
    await _goto_email_step3(pg)
    await pg.fill(".hb-msg input[type=email]", "rjj@proars.com")
    await pg.fill(".hb-msg input[type=password]", "abcdefghijklmnop")
    await _click_next(pg)   # submits on the last step


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


@pytest.fixture(scope="module")
def wizard(playwright_available):
    return _run([_OFF])[0]


def test_connect_focus_lands_on_the_CONNECTORS_wizard_not_the_list(wizard):
    """«cuando diga conecta Gmail, accede DIRECTAMENTE al conector de Gmail»: connect_focus{platform:email}
    must never render the list screen."""
    assert wizard["mounted"] and wizard["errors"] == [], wizard.get("errors")
    assert not wizard["chanhead"], "connect_focus must not land on the connector LIST screen"
    assert wizard["hasCrumb"] and wizard["crumb"] == "Email", wizard["crumb"]


def test_the_list_screen_is_an_ICON_GRID_not_stacked_rows(playwright_available):
    """«no podemos tener los conectores listados verticalmente» — the top-level list is a grid of boxes."""
    out = _run([_LIST])[0]
    assert out["chanhead"], "opening the panel with no platform named must show the connector LIST"
    labels = {b["label"].lower() for b in out["iboxes"]}
    assert {"whatsapp", "telegram", "email"} <= labels, labels
    for b in out["iboxes"]:
        assert b["h"] > 40 and b["w"] > 40, f"icon box {b['label']} has no pixels: {b}"


def test_clicking_a_connector_box_ENTERS_its_own_wizard_screen(playwright_available):
    async def click_email(pg):
        await _click_ibox(pg, "email")
    out = _run([_LIST], actions=[(0, click_email)])[0]
    assert out["hasCrumb"] and out["crumb"] == "Email", out["crumb"]
    assert not out["chanhead"], "clicking a connector must leave the list screen"


_HEADER_ONLY = {**_OFF, "connect_focus": None}   # WhatsApp connected, nothing named -> panel stays CLOSED


def test_the_header_button_opens_the_list_when_nothing_was_named(playwright_available):
    """With something already connected the panel does not open by itself (`showChannels` needs a reason);
    pressing 🔌 is that reason, and it opens the LIST — never a wizard, since no platform was named."""
    out = _run([_HEADER_ONLY], actions=[(0, _open_connector_list)])[0]
    assert out["chanhead"] and not out["hasCrumb"], "🔌 must open the LIST, not a wizard"


def test_the_header_button_is_a_toggle_for_the_whole_channels_area(playwright_available):
    """Pressing 🔌 while a connector's own wizard is showing (reached via connect_focus) collapses the whole
    channels area back to the messages view — the same single on/off switch the header owned before this
    redesign, now covering two screens instead of one."""
    out = _run([_OFF], actions=[(0, _open_connector_list)])[0]
    assert not out["chanhead"] and not out["hasCrumb"], "🔌 must close the area, not switch to the list"


def test_the_BACK_button_on_step_one_returns_to_the_list(playwright_available):
    out = _run([_OFF], actions=[(0, _click_back)])[0]
    assert out["chanhead"], "Atrás on the first step must return to the connector list"


def test_only_ONE_step_is_visible_at_a_time(wizard):
    """The redesign's whole point: «si comprimo… solo el primer paso» — no stacking three boxes any more."""
    assert len(wizard["steps"]) == 1, wizard["steps"]
    s = wizard["steps"][0]
    assert s["num"] == "1" and s["h"] > 40 and s["w"] > 200, s
    assert wizard["wcount"] == "Paso 1 de 3", wizard["wcount"]


def test_step_one_is_an_ICON_GRID_of_providers(wizard):
    """«pon los proveedores de correo en una caja con el icono en medio, para que vea todos los que hay»."""
    labels = {b["label"].lower() for b in wizard["iboxes"]}
    assert {"gmail", "outlook / hotmail", "icloud", "yahoo"} <= labels, labels
    gmail = next(b for b in wizard["iboxes"] if b["label"].lower() == "gmail")
    assert gmail["sel"], "gmail is the default provider and must show as selected"


def test_continuar_ADVANCES_one_step_and_back_returns_one(playwright_available):
    out = _run([_OFF], actions=[(0, _click_next)])[0]
    assert len(out["steps"]) == 1 and out["steps"][0]["num"] == "2", out["steps"]
    assert out["wcount"] == "Paso 2 de 3", out["wcount"]

    back = _run([_OFF], actions=[(0, _click_next), (0, _click_back)])[0]
    assert back["steps"][0]["num"] == "1", back["steps"]


def test_step_two_is_a_real_LINK_to_the_page_that_creates_the_password(playwright_available):
    """The middle step used to be a sentence between two inputs, and it read as optional. It is the step the
    operator actually has to LEAVE for."""
    out = _run([_OFF], actions=[(0, _click_next)])[0]
    link = out["link"]
    assert link and link["href"] == "https://myaccount.google.com/apppasswords", link
    assert link["h"] > 20 and link["w"] > 80, f"the link has no clickable area: {link}"
    assert "contraseñas de aplicación" in link["text"].lower(), link["text"]


def test_the_link_FOLLOWS_the_provider_picker(playwright_available):
    async def pick_outlook_then_advance(pg):
        await _click_ibox(pg, "outlook")
        await _click_next(pg)
    out = _run([_OFF], actions=[(0, pick_outlook_then_advance)])[0]
    assert "account.live.com" in (out["link"] or {}).get("href", ""), out["link"]


def test_the_spaces_the_provider_PRINTS_never_reach_the_field(playwright_available):
    """Google shows the password in four groups. Those spaces are presentation; IMAP AUTH does not want them,
    and `.trim()` — what the form had — only removes the ends."""
    async def to_step3_and_paste(pg):
        await _goto_email_step3(pg)
        await pg.fill(".hb-msg input[type=password]", "abcd efgh ijkl mnop")
    out = _run([_OFF], actions=[(0, to_step3_and_paste)])[0]
    assert out["pw"] == "abcdefghijklmnop", out["pw"]


def test_a_REFUSED_connection_comes_back_to_a_form_that_still_has_the_data(playwright_available):
    """This is what made «Corregir y reintentar» look dead: the draft was wiped on submit, so the form under
    the error banner was empty and retrying meant retyping the address and sixteen letters."""
    steps = _run([_OFF, _REFUSED], actions=[(0, _fill_and_submit)])
    assert ["connect", {"platform": "email", "email_address": "rjj@proars.com",
                        "email_password": "abcdefghijklmnop", "provider": "gmail"}] in steps[0]["acts"]
    after = steps[1]
    assert after["errcard"], "a refusal has to be visible"
    assert after["hasCrumb"] and after["crumb"] == "Email", "still on the connector's own screen, not the list"
    assert after["addr"] == "rjj@proars.com", after["addr"]
    assert after["pw"] == "abcdefghijklmnop", "the password must survive a refusal"


def test_correct_and_retry_MOVES_something_instead_of_repainting_the_same_screen(playwright_available):
    """The old handler added a key to a set that already had it. From outside that is a dead button."""
    async def retry(pg):
        await pg.click(".hb-msg .errcard .bt")
    steps = _run([_OFF, _REFUSED], actions=[(0, _fill_and_submit), (1, retry)])
    assert steps[1]["focus_is_pw"], "the retry has to land the cursor on the field to fix"


def test_a_missing_field_says_which_one_and_points_at_it(playwright_available):
    async def only_address(pg):
        await _goto_email_step3(pg)
        await pg.fill(".hb-msg input[type=email]", "rjj@proars.com")
        await _click_next(pg)
    out = _run([_OFF], actions=[(0, only_address)])[0]
    assert "contraseña" in out["err_text"].lower(), out["err_text"]
    assert out["pw_flagged"], "the offending field has to be marked, not just described"
    assert not any(a[0] == "connect" for a in out["acts"]), "nothing may be enqueued with a field missing"


def test_a_CONNECTED_channel_does_not_keep_the_password_in_a_form(playwright_available):
    """The draft survives a refusal on purpose; surviving a success is a credential left lying on screen."""
    steps = _run([_OFF, _CONNECTED, _OFF], actions=[(0, _fill_and_submit)])
    assert steps[1]["hasCrumb"], "a connected platform is still its OWN screen, not the list"
    assert steps[2]["pw"] in ("", None), steps[2]["pw"]
    assert steps[2]["addr"] in ("", None), steps[2]["addr"]


def test_a_connected_platform_offers_disconnect_not_a_wizard(playwright_available):
    out = _run([_CONNECTED])[0]
    assert len(out["steps"]) == 0, "a connected connector shows status, not a step wizard"
    assert out["hasCrumb"] and out["crumb"] == "Email"


def test_on_a_PHONE_the_wizard_fits_and_its_button_is_reachable(playwright_available):
    """Second instruction of the same thread: every connect flow has to work in a vertical column. A card
    that overflows the viewport puts «Continuar» off the right edge, where a thumb cannot reach it."""
    out = _run([_OFF], width=375)[0]
    assert out["doc_w"] <= out["view_w"] + 1, \
        f"the page scrolls sideways on a 375px screen: {out['doc_w']} > {out['view_w']}"
    assert out["root"]["w"] <= 375, out["root"]
    for s in out["steps"]:
        assert s["x"] >= -1 and s["x"] + s["w"] <= 376, f"step {s['num']} hangs off the screen: {s}"
    btn = out["nextBtn"]
    assert btn and btn["x"] >= -1 and btn["x"] + btn["w"] <= 376, f"the next button is off-screen: {btn}"
    assert btn["h"] >= 32, f"the next button is too small to tap: {btn}"


# ── the OTHER two wizards, on a phone ─────────────────────────────────────────────────────────────────────
_TG = {**_OFF, "connect_focus": {"platform": "telegram", "ts": 1}}
_WA_QR = {**_OFF, "connect_focus": None,
          "platforms": {**_OFF["platforms"],
                        "whatsapp": {"status": "connecting",
                                     "qr": "data:image/png;base64,iVBORw0KGgo="}}}


def test_the_telegram_wizard_is_stepped_too(playwright_available):
    """«todos los procesos del asistente de conexión» — one visual language for the three channels."""
    out = _run([_TG], width=375)[0]
    assert len(out["steps"]) == 1 and out["steps"][0]["num"] == "1", out["steps"]
    assert "my.telegram.org" in (out["link"] or {}).get("href", ""), out["link"]
    for s in out["steps"]:
        assert s["h"] > 40 and s["x"] + s["w"] <= 376, f"telegram step {s['num']} on a phone: {s}"
    assert out["doc_w"] <= out["view_w"] + 1, out["doc_w"]

    advanced = _run([_TG], actions=[(0, _click_next)], width=375)[0]
    assert advanced["steps"][0]["num"] == "2", advanced["steps"]


def test_the_wizard_screen_fits_a_phone_even_with_an_error_banner_showing(playwright_available):
    """The connector-scoped screen is icon + name (in the breadcrumb) + status (the error banner) + action
    (Continuar/Conectar). «No se pudo conectar» is a long status, and on a narrow screen the action is the
    part that falls off — the one thing the operator needs to press."""
    m = _run([_OFF, _REFUSED], width=375)[1]
    assert m["doc_w"] <= m["view_w"] + 1, f"sideways scroll: {m['doc_w']}"
    assert m["errcard"], "the reason has to be on screen"
    assert m["nextBtn"] and m["nextBtn"]["x"] + m["nextBtn"]["w"] <= 376, m["nextBtn"]


def test_the_QR_card_fits_a_phone(playwright_available):
    out = _run([_WA_QR], width=375)[0]
    assert out["doc_w"] <= out["view_w"] + 1, f"the QR pushes the card sideways: {out['doc_w']}"


_PHOTO_ITEM = {"n": 1, "platform": "whatsapp", "from": "Ana", "group": None, "isGroup": False,
               "body": "[image received]", "urgencia": "media", "dirigido_a_mi": True, "motivo": "",
               "messageId": "w1", "chatId": "111", "senderId": "111", "ts": 1756742000,
               "mediaType": "image",
               "media": [{"url": "/widgets/mensajeria/asset/x.jpg", "type": "image", "name": "x.jpg"}]}
_PHOTO_THREAD = {**_OFF, "connect_focus": None,
                 "platforms": {**_OFF["platforms"], "whatsapp": {"status": "connected"}},
                 "items": [_PHOTO_ITEM], "count": 1,
                 "chats": [{"n": 1, "platform": "whatsapp", "chatId": "111", "name": "Ana",
                            "isGroup": False, "count": 1, "dirigido_a_mi": True, "urgencia": "media",
                            "lastFrom": "Ana", "lastBody": "[image received]", "lastMotivo": "",
                            "lastTs": 1756742000, "lastMediaType": "image"}],
                 "active_chat": {"platform": "whatsapp", "chatId": "111"},
                 "active_items": [_PHOTO_ITEM]}


def test_a_received_photo_uses_the_WHOLE_card_on_a_phone(playwright_available):
    """The only layout rule the measurement justified keeping: a 220px thumbnail is a desktop number, and on a
    phone it wastes a third of the card the photo could be using."""
    narrow = _run([_PHOTO_THREAD], width=375)[0]
    wide = _run([_PHOTO_THREAD], width=900)[0]
    assert wide["att_maxw"] == "220px", f"the desktop thumbnail must stay a thumbnail: {wide['att_maxw']}"
    assert narrow["att_maxw"] != "220px",         f"on a phone the photo must not be capped at a desktop pixel width: {narrow['att_maxw']}"


def test_the_widget_never_scrolls_SIDEWAYS_in_any_of_its_states(playwright_available):
    """A RATCHET, and it is worth saying that it does not prove this pass fixed anything: measured on the
    version before it, all states already fit — the widget was responsive and what was broken was the
    wizard. This keeps it that way."""
    states = {"connect panel with failures": [_OFF, _REFUSED], "email wizard": [_OFF],
              "telegram wizard": [_TG], "QR": [_OFF, _WA_QR], "thread with media": [_PHOTO_THREAD],
              "connector list": [_LIST]}
    for label, seq in states.items():
        m = _run(seq, width=375)[-1]
        assert m["doc_w"] <= m["view_w"] + 1, f"{label} scrolls sideways at 375px: {m['doc_w']}"
        assert m["errors"] == [], f"{label}: {m['errors']}"
