"""V2-646 — with ⏻ OFF, the chat composer refuses instead of swallowing the message.

The operator, 2026-09-09: «estaba el agente parado y me he puesto a escribir… si lo mando y nadie está
escuchando se pierde… he tenido que escribir dos veces el mensaje, la primera lo ha mandado al vacío».
He was right about the outcome and about the cause. `session.sendText` queues the text and calls `start()`,
but `start()` has its OWN gate against the server's truth: with the agent stopped it refuses and returns —
so the queue never flushed, while the wall had already shown the message as sent and the composer had
already been cleared. The typed sentence was gone.

Only a browser can check this: it is about a disabled control, a composer that keeps its text, and the
Enter key — which bypasses a button's `disabled` and needs its own guard.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

_STATE = """() => {
  const btn = document.querySelector('.cw-send');
  const ta = document.querySelector('.cw-input textarea');
  const bubbles = [...document.querySelectorAll('.cw-msg, .cw-you, .cw-row')].length;
  return {
    hasBtn: !!btn,
    disabled: btn ? !!btn.disabled : null,
    off: btn ? btn.classList.contains('off') : null,
    title: btn ? (btn.getAttribute('title') || '') : '',
    cursor: btn ? getComputedStyle(btn).cursor : '',
    text: ta ? ta.value : null,
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def run():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


def _boot(pg, url, *, power_off):
    pg.goto(url, wait_until="domcontentloaded")
    pg.evaluate("(off) => { try { localStorage.setItem('hb_power_off', off ? '1' : '0'); } catch (_) {} }",
                power_off)
    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
    # Open the wall on its chat tab, the way the operator finds it.
    pg.evaluate("""() => import('/static/app/core/store.js?v=2').then(m => {
        m.setChatTab('chat'); m.setChatOpen(true);
    })""")
    pg.wait_for_timeout(700)


@pytest.fixture(scope="module")
def measured(run):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        # ── ⏻ OFF: the state that lost his message ──
        _boot(pg, run, power_off=True)
        out["off_idle"] = pg.evaluate(_STATE)
        pg.fill(".cw-input textarea", "ponme la peli de minions and monsters")
        pg.wait_for_timeout(150)
        # Enter is the path a button's `disabled` does NOT cover — it must refuse on its own.
        pg.press(".cw-input textarea", "Enter")
        pg.wait_for_timeout(400)
        out["off_after_enter"] = pg.evaluate(_STATE)
        # …and so must a click on the button itself.
        pg.evaluate("() => document.querySelector('.cw-send').click()")
        pg.wait_for_timeout(400)
        out["off_after_click"] = pg.evaluate(_STATE)

        # ── ⏻ ON: nothing about the composer changes for the normal case ──
        _boot(pg, run, power_off=False)
        out["on_idle"] = pg.evaluate(_STATE)
        out["errors"] = list(errors)
        ctx.close(); b.close()
    return out


def test_with_the_agent_off_the_send_button_is_disabled_and_says_why(measured):
    st = measured["off_idle"]
    assert st["hasBtn"], "no send button rendered — the harness is measuring the wrong thing"
    assert st["disabled"] is True, "with ⏻ off the send button must be disabled"
    assert st["off"] is True and st["cursor"] == "not-allowed", \
        f"a disabled control must READ disabled: {st}"
    assert "apagado" in st["title"].lower() or "off" in st["title"].lower(), \
        f"the button must say WHY it refuses, got {st['title']!r}"


def test_the_typed_text_survives_both_the_enter_key_and_the_click(measured):
    """The compounding half of his report: the composer was cleared too, so he had to retype from scratch.
    Enter bypasses `disabled` — it needs the guard inside `send()`, which is what this measures."""
    for state in ("off_after_enter", "off_after_click"):
        assert measured[state]["text"] == "ponme la peli de minions and monsters", \
            f"[{state}] the operator's words must stay where he wrote them, got {measured[state]['text']!r}"


def test_with_the_agent_on_the_composer_behaves_normally(measured):
    st = measured["on_idle"]
    assert st["disabled"] is False and st["off"] is False, \
        "the guard must apply ONLY to the off state — a live agent takes messages as always"
    assert st["cursor"] == "pointer"
    assert not measured["errors"], f"no page errors during the whole ride: {measured['errors']}"
