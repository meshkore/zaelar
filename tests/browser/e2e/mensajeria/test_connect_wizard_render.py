"""V2-559 — the email connect wizard RENDERED: three steps, a retry that moves, and a draft that survives.

Rendering is the only way to answer any of this. The operator's three complaints were about pixels and about
state that lives in the DOM, and every one of them would have passed a source-level read:

  · «pon el paso 1, paso 2, paso 3» — a step that exists in the DOM with no height explains nothing.
  · «ese botón de corregir y reintentar no hace nada, no lleva a ningún sitio» — it was wired, it repainted,
    and it was `_expandConnect.add(pl)` on a set that already had it. Only measuring what MOVED can tell a
    dead button from a live one.
  · the form came back EMPTY after a refusal, so «reintentar» meant retyping the address and sixteen letters.

Plus the second instruction of the same thread: all of it has to work in a phone-shaped column.
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
_CONNECTED = {**_OFF, "connect_focus": None,
              "platforms": {**_OFF["platforms"], "email": {"status": "connected"}}}

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
  const card = el.querySelector('.linkcard');
  const steps = [...el.querySelectorAll('.wstep')].map(s => ({
    num: (s.querySelector('.wnum') || {}).textContent,
    title: (s.querySelector('.wtitle') || {}).textContent,
    ...box(s),
  }));
  const link = el.querySelector('.wstep .wlink');
  const pw = el.querySelector('.linkcard input[type=password]');
  const addr = el.querySelector('.linkcard input[type=email]');
  const btn = card && [...card.querySelectorAll('button.btn')].pop();
  return {
    mounted: true,
    steps,
    link: link ? {href: link.getAttribute('href'), text: link.textContent, ...box(link)} : null,
    pw: pw ? pw.value : null,
    addr: addr ? addr.value : null,
    focus_is_pw: !!pw && document.activeElement === pw,
    pw_flagged: !!pw && pw.classList.contains('errfield'),
    errcard: !!el.querySelector('.errcard'),
    err_text: (el.querySelector('.err') && el.querySelector('.err').style.display !== 'none')
              ? el.querySelector('.err').textContent : '',
    btn: btn ? {text: btn.textContent, ...box(btn)} : null,
    card: card ? box(card) : null,
    root: box(el),
    doc_w: document.documentElement.scrollWidth,
    view_w: window.innerWidth,
    acts: window.__acts || [],
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


def test_the_wizard_paints_THREE_numbered_steps_with_real_pixels(wizard):
    assert wizard["mounted"] and wizard["errors"] == [], wizard.get("errors")
    nums = [s["num"] for s in wizard["steps"]]
    assert nums == ["1", "2", "3"], f"the operator asked for step 1, step 2, step 3: {nums}"
    for s in wizard["steps"]:
        assert s["h"] > 40 and s["w"] > 200, f"step {s['num']} has no pixels: {s}"
    ys = [s["y"] for s in wizard["steps"]]
    assert ys == sorted(ys), f"the steps must read top to bottom: {ys}"
    # Real gaps between boxes — «respeto por los márgenes» is the point of the redesign.
    gaps = [ys[i + 1] - (ys[i] + wizard["steps"][i]["h"]) for i in range(len(ys) - 1)]
    assert all(g >= 6 for g in gaps), f"the step boxes are glued together: {gaps}"


def test_step_two_is_a_real_LINK_to_the_page_that_creates_the_password(wizard):
    """The middle step used to be a sentence between two inputs, and it read as optional. It is the step the
    operator actually has to LEAVE for."""
    link = wizard["link"]
    assert link and link["href"] == "https://myaccount.google.com/apppasswords", link
    assert link["h"] > 20 and link["w"] > 80, f"the link has no clickable area: {link}"
    assert "contraseñas de aplicación" in link["text"].lower(), link["text"]


def test_the_link_FOLLOWS_the_provider_picker(playwright_available):
    async def pick_outlook(pg):
        await pg.select_option(".hb-msg .linkcard select", "outlook")
    out = _run([_OFF], actions=[(0, pick_outlook)])[0]
    assert "account.live.com" in (out["link"] or {}).get("href", ""), out["link"]


def test_the_spaces_the_provider_PRINTS_never_reach_the_field(playwright_available):
    """Google shows the password in four groups. Those spaces are presentation; IMAP AUTH does not want them,
    and `.trim()` — what the form had — only removes the ends."""
    async def paste(pg):
        await pg.fill(".hb-msg .linkcard input[type=password]", "abcd efgh ijkl mnop")
    out = _run([_OFF], actions=[(0, paste)])[0]
    assert out["pw"] == "abcdefghijklmnop", out["pw"]


async def _fill_and_submit(pg):
    await pg.fill(".hb-msg .linkcard input[type=email]", "rjj@proars.com")
    await pg.fill(".hb-msg .linkcard input[type=password]", "abcdefghijklmnop")
    await pg.click(".hb-msg .linkcard button.btn")


def test_a_REFUSED_connection_comes_back_to_a_form_that_still_has_the_data(playwright_available):
    """This is what made «Corregir y reintentar» look dead: the draft was wiped on submit, so the form under
    the error banner was empty and retrying meant retyping the address and sixteen letters."""
    steps = _run([_OFF, _REFUSED], actions=[(0, _fill_and_submit)])
    assert ["connect", {"platform": "email", "email_address": "rjj@proars.com",
                        "email_password": "abcdefghijklmnop", "provider": "gmail"}] in steps[0]["acts"]
    after = steps[1]
    assert after["errcard"], "a refusal has to be visible"
    assert after["addr"] == "rjj@proars.com", after["addr"]
    assert after["pw"] == "abcdefghijklmnop", "the password must survive a refusal"


def test_correct_and_retry_MOVES_something_instead_of_repainting_the_same_card(playwright_available):
    """The old handler added a key to a set that already had it. From outside that is a dead button."""
    async def retry(pg):
        await pg.click(".hb-msg .errcard .cbtn")
    steps = _run([_OFF, _REFUSED], actions=[(0, _fill_and_submit), (1, retry)])
    assert steps[1]["focus_is_pw"], "the retry has to land the cursor on the field to fix"


def test_a_missing_field_says_which_one_and_points_at_it(playwright_available):
    async def only_address(pg):
        await pg.fill(".hb-msg .linkcard input[type=email]", "rjj@proars.com")
        await pg.click(".hb-msg .linkcard button.btn")
    out = _run([_OFF], actions=[(0, only_address)])[0]
    assert "contraseña" in out["err_text"].lower(), out["err_text"]
    assert out["pw_flagged"], "the offending field has to be marked, not just described"
    assert not any(a[0] == "connect" for a in out["acts"]), "nothing may be enqueued with a field missing"


def test_a_CONNECTED_channel_does_not_keep_the_password_in_a_form(playwright_available):
    """The draft survives a refusal on purpose; surviving a success is a credential left lying on screen."""
    steps = _run([_OFF, _CONNECTED, _OFF],
                 actions=[(0, _fill_and_submit)])
    assert steps[2]["pw"] in ("", None), steps[2]["pw"]
    assert steps[2]["addr"] in ("", None), steps[2]["addr"]


def test_on_a_PHONE_the_wizard_fits_and_its_button_is_reachable(playwright_available):
    """Second instruction of the same thread: every connect flow has to work in a vertical column. A card
    that overflows the viewport puts «Conectar» off the right edge, where a thumb cannot reach it."""
    out = _run([_OFF], width=375)[0]
    assert out["doc_w"] <= out["view_w"] + 1, \
        f"the page scrolls sideways on a 375px screen: {out['doc_w']} > {out['view_w']}"
    assert out["root"]["w"] <= 375, out["root"]
    for s in out["steps"]:
        assert s["x"] >= -1 and s["x"] + s["w"] <= 376, f"step {s['num']} hangs off the screen: {s}"
    btn = out["btn"]
    assert btn and btn["x"] >= -1 and btn["x"] + btn["w"] <= 376, f"the connect button is off-screen: {btn}"
    assert btn["h"] >= 32, f"the connect button is too small to tap: {btn}"


# ── the OTHER two wizards, on a phone ─────────────────────────────────────────────────────────────────────
_TG = {**_OFF, "connect_focus": {"platform": "telegram", "ts": 1}}
_WA_QR = {**_OFF, "connect_focus": None,
          "platforms": {**_OFF["platforms"],
                        "whatsapp": {"status": "connecting",
                                     "qr": "data:image/png;base64,iVBORw0KGgo="}}}


def test_the_telegram_wizard_is_stepped_too(playwright_available):
    """«todos los procesos del asistente de conexión» — one visual language for the three channels."""
    out = _run([_TG], width=375)[0]
    nums = [s["num"] for s in out["steps"]]
    assert nums == ["1", "2", "3"], nums
    assert "my.telegram.org" in (out["link"] or {}).get("href", ""), out["link"]
    for s in out["steps"]:
        assert s["h"] > 40 and s["x"] + s["w"] <= 376, f"telegram step {s['num']} on a phone: {s}"
    assert out["doc_w"] <= out["view_w"] + 1, out["doc_w"]


def test_a_channel_ROW_wraps_instead_of_pushing_its_button_off_the_edge(playwright_available):
    """The row is icon + name + status + action. «No se pudo conectar» is a long status, and on a narrow card
    the action is the part that falls off — the one thing the operator needs to press."""
    m = _run([_OFF, _REFUSED], width=375)[1]
    assert m["doc_w"] <= m["view_w"] + 1, f"sideways scroll: {m['doc_w']}"
    assert m["errcard"], "the reason has to be on screen"
    assert m["btn"] and m["btn"]["x"] + m["btn"]["w"] <= 376, m["btn"]


def test_the_QR_card_fits_a_phone(playwright_available):
    out = _run([_WA_QR], width=375)[0]
    assert out["doc_w"] <= out["view_w"] + 1, f"the QR pushes the card sideways: {out['doc_w']}"
