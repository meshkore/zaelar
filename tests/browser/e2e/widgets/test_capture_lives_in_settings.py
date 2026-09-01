"""V2-542 — deleting the desktop's bottom line must not delete what it CARRIED.

The operator, with the desktop in front of him: «toda esta mierda que aparece abajo no tiene sentido tenerla.
Ya tenemos una barra a la izquierda, las opciones principales arriba a la derecha… No quiero selectores de
micrófono ni ciertas cosas aquí porque ahora mismo no me hacen ningún sentido.»

«Aquí» is the load-bearing word. Removing a diagnostic strip from the desktop is the ask; removing the ability
to pick a microphone is not, and the difference between the two is a place for it to go. So the two capture
controls moved to ⚙ → Voz, and this file is what says they ARRIVED — a source check could only prove the HTML
was written, never that the panel builds it, that the session fills it, or that the rows survive.

Rendered, because the whole point is a place in a UI. Its own preview server against the real frontend, never
the operator's engine: opening his page would take the one-voice-per-machine lock out from under his tab.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

# `livekit_api` is mounted ON PURPOSE: it serves `session-lk.js` AT the `session.js` URL, which is the engine
# the operator actually runs. Without it the preview loads the legacy Pipecat module, which has no capture-MODE
# picker — and the test would then be measuring an engine nobody uses.
PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api, livekit_api
app = FastAPI()
app.include_router(pages.router); app.include_router(i18n_api.router); app.include_router(livekit_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

_MEASURE = """() => {
  const card = document.querySelector('#cf_voice_device');
  const ms = document.getElementById('micsel'), mm = document.getElementById('micmode');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none'; };
  const save = document.querySelector('.cf-save-voice');
  return {
    card: !!card,
    // The card sits AFTER the server card, so «Guardar voz» is never a button under controls it does not save.
    after_save: !!(card && save && (card.compareDocumentPosition(save) & Node.DOCUMENT_POSITION_PRECEDING)),
    inside_server_card: !!(card && save && card.contains(save)),
    mic_visible: vis(ms), mode_visible: vis(mm),
    mic_options: ms ? ms.options.length : 0,
    mode_values: mm ? [...mm.options].map(o => o.value) : [],
    on_desktop: [...document.querySelectorAll('#desk select')].length,
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def voice_tab():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
            except OSError:
                time.sleep(0.5)
        else:  # pragma: no cover
            pytest.skip("preview server never came up")
        time.sleep(1.0)
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=["--no-sandbox",
                                                        "--use-fake-device-for-media-stream",
                                                        "--use-fake-ui-for-media-stream"])
            ctx = b.new_context(viewport={"width": 1280, "height": 800}, permissions=["microphone"])
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil')"
                        ".forEach(e => e.remove())")
            pg.click("#cfgBtn")
            pg.wait_for_timeout(700)
            pg.click('.cf-nav-item[data-sec="voice"]')     # the section lives in the LEFT nav, not the top tabs
            pg.wait_for_timeout(900)                       # the device list is filled asynchronously
            out = pg.evaluate(_MEASURE)
            out["errors"] = errors
            b.close()
        return out
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


def test_the_panel_paints_without_a_single_error(voice_tab):
    assert voice_tab["errors"] == [], voice_tab["errors"]


def test_the_capture_controls_ARRIVED_and_are_usable(voice_tab):
    """The half that makes the deletion safe. Not «the HTML exists» — the selects have to be VISIBLE and
    actually FILLED, because the session fills them asynchronously and an empty select is a dead control."""
    assert voice_tab["card"], "the capture card never rendered in Settings"
    assert voice_tab["mic_visible"] and voice_tab["mic_options"] > 0, json.dumps(voice_tab)
    assert voice_tab["mode_visible"], json.dumps(voice_tab)
    assert voice_tab["mode_values"] == ["isolate", "full", "raw"], voice_tab["mode_values"]


def test_the_save_button_is_not_sitting_under_controls_it_does_not_save(voice_tab):
    """The server knobs above are written by «Guardar voz»; these two are applied the moment they change. In
    one card the button would claim both, so the capture card is a SEPARATE one that comes after it."""
    assert not voice_tab["inside_server_card"], "the capture rows are inside the card the Save button owns"
    assert voice_tab["after_save"], "the capture card must come after the server card, not before it"


def test_and_they_are_NOT_on_the_desktop_any_more(voice_tab):
    """Moving means leaving. A copy left behind on the desktop would be the clutter he asked to remove, only
    now duplicated — which is worse than not having moved it at all."""
    assert voice_tab["on_desktop"] == 0, json.dumps(voice_tab)
