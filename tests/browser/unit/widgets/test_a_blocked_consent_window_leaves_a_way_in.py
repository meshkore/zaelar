"""A consent window the browser blocks is SAID, and a link the operator can click himself is offered. Rendered.

The operator (2026-10-04), with Chrome's «reload this page to apply the updated site settings» bar in his screenshot
— the bar Chrome shows after you allow pop-ups for a site: «he intentado conectar google, y se ha quedado ahí».
The panel opens Google's consent in a window from the click (V2-679: a window opened after an `await` is blocked
by every browser), but when the blocker refuses even that one the panel said «connecting…» and waited three
minutes for a consent that could never be given. Now: the refusal is detected (`window.open` returns null), the
message says so, and the connector's own form carries a link to the same URL — a click of the operator's own is
never blocked. Rendered against the real ConfigPanel, strings and stylesheet; `window.open` is the browser's.
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from tests.waiting import until_sync

ENGINE = Path(__file__).resolve().parents[4]
_EN = json.loads((ENGINE / "i18n/bundles/en.json").read_text(encoding="utf-8"))
CONSENT = "https://accounts.google.com/o/oauth2/v2/auth?client_id=test&scope=calendar"
pytest.importorskip("playwright.sync_api")

_CX = {"connectors": [
    {"id": "google", "label": "Google Calendar", "family": "agenda", "connected": False, "status": "off", "detail": ""},
    {"id": "google-contacts", "label": "Google Contacts", "family": "contactos", "connected": True, "status": "connected", "detail": ""},
    {"id": "google-account", "label": "Google", "family": "google", "connected": True, "status": "connected", "detail": "",
     "config": {"app_configured": True}},
]}


def _listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
        return True
    except OSError:
        return False


@pytest.fixture(scope="module")
def browser_and_port():
    from playwright.sync_api import sync_playwright
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    until_sync(lambda: _listening(port), "the static server to accept connections", timeout_s=10)
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            yield b, port
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _panel_on_google(browser, port, blocked: bool):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    errors: list[str] = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    j = lambda r, o: r.fulfill(status=200, content_type="application/json", body=json.dumps(o))  # noqa: E731
    pg.route("**/api/**", lambda r: j(r, {}))
    pg.route("**/api/config", lambda r: j(r, {"catalog": {}, "v2": {}, "credentials": [], "cloud_profile": False}))
    pg.route("**/api/connectors", lambda r: j(r, _CX))
    pg.route("**/api/widgets/registry", lambda r: j(r, {"registry": []}))
    pg.route("**/api/i18n/state", lambda r: j(r, {"picker": [], "active": "en"}))
    pg.route("**/api/i18n/bundle/*", lambda r: j(r, {"strings": _EN}))
    pg.route("**/api/calendar/connect", lambda r: j(r, {"ok": True, "url": CONSENT}))
    ctx.route("https://accounts.google.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<title>consent</title>"))
    pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
    if blocked:   # a pop-up blocker: the browser answers the click's window.open with null, silently
        pg.evaluate("() => { window.open = () => null; }")
    pg.evaluate("""async () => {
        for (const h of ['/frontend/app/core/palette.css', '/frontend/app/core/components.css', '/frontend/app/styles.css']) {
          const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = h; document.head.append(l); }
        const i18n = await import('/frontend/app/core/i18n.js?v=1');
        await i18n.loadBundle('en'); if (i18n.applyLang) await i18n.applyLang('en');
        const store = await import('/frontend/app/core/store.js?v=2');
        const m = await import('/frontend/app/components/ConfigPanel.js?v=9');
        document.body.append(m.ConfigPanel());
        store.setConfigConnector('google'); store.setConfigOpen(true);
    }""")
    pg.wait_for_selector(".cf-gsvc .cf-cx-act[data-act='calendar-connect']", timeout=8000)
    pg._errors = errors
    return ctx, pg


def _state(pg):
    return pg.evaluate("""() => { const a = document.querySelector('.cf-consent-link');
        return {link: a ? a.getAttribute('href') : null, target: a ? a.getAttribute('target') : null,
                said: (document.querySelector('.cf-wiz-blocked') || {}).innerText || '',
                msg: (document.querySelector('.cf-msg') || {}).textContent || ''}; }""")


def test_a_blocked_consent_window_is_said_and_offered_as_a_link(browser_and_port):
    b, port = browser_and_port
    ctx, pg = _panel_on_google(b, port, blocked=True)
    pg.click(".cf-gsvc .cf-cx-act[data-act='calendar-connect']")
    pg.wait_for_selector(".cf-consent-link", timeout=5000)
    s = _state(pg)
    assert s["link"] == CONSENT, f"the link must lead to the SAME consent URL the window would have opened: {s}"
    assert s["target"] == "_blank"
    assert _EN["config.cx.popup_blocked"] in s["said"], f"the panel must SAY the browser blocked the window: {s}"
    assert _EN["config.cx.popup_blocked_short"] in s["msg"], s
    assert not pg._errors, pg._errors
    ctx.close()


def test_a_consent_window_that_opens_needs_no_link(browser_and_port):
    b, port = browser_and_port
    ctx, pg = _panel_on_google(b, port, blocked=False)
    with ctx.expect_page():
        pg.click(".cf-gsvc .cf-cx-act[data-act='calendar-connect']")
    pg.wait_for_timeout(400)
    s = _state(pg)
    assert s["link"] is None, f"with the window open there is nothing to offer: {s}"
    assert _EN["config.msg.connecting"].split("{")[0].strip() in s["msg"] or "connecting" in s["msg"], s
    ctx.close()
