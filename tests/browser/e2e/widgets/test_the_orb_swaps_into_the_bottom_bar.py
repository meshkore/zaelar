"""V2-623 — the orb swaps between the EYE and the bottom system bar, and the memory control moved upstairs.

The operator's spec (2026-09-08): «move the left bar to bottom. orbe goes to center, left and right side
contains the open widgets and the other icons in the bar respectively. initially the hor bar orbe is
deactivated and we show the eye orbe. but if someone click the bar orbe swap icon, or the eye orbe new swap
icon, then the big orbe is hidden.» Plus: «quita el icono de la memoria del orbe. ponlo arriba a la derecha.»

The one rule only a BROWSER can check is the 4.19 lesson: there is ONE orb canvas, ever — swapping REPARENTS
the same element, and a canvas re-created inside a conditional renders blank with no error. So every case
here measures the rendered page: where the canvas's parent is, whether it has size, and what a real click
moves.
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
  const orb = document.getElementById('orb');
  const wrap = document.getElementById('orbwrap');
  const slot = document.querySelector('#wrail .wr-orbslot');
  const swap = document.querySelector('#wrail .wr-swap');
  const rail = document.querySelector('#wrail');
  const lid = [...document.querySelectorAll('.orbctl button')];
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none'; };
  const rr = rail ? rail.getBoundingClientRect() : null;
  const orbR = orb ? orb.getBoundingClientRect() : null;
  return {
    barMode: document.body.classList.contains('hb-orb-bar'),
    orbParent: orb && orb.parentElement ? (orb.parentElement.classList[0] || orb.parentElement.tagName) : null,
    orbVisible: vis(orb),
    orbW: orbR ? Math.round(orbR.width) : 0,
    eyeChromeShown: vis(document.querySelector('#orbwrap .orbctl')),
    activityShown: !!wrap && getComputedStyle(document.getElementById('activity')).display !== 'none',
    slotShown: vis(slot),
    slotTag: slot ? slot.tagName : '',
    slotOff: slot ? slot.classList.contains('off') : null,
    slotTitle: slot ? slot.getAttribute('title') || '' : '',
    pwrFaceShown: (() => { const f = document.querySelector('#wrail .wr-orbpwr');
                           return !!f && getComputedStyle(f).visibility === 'visible'; })(),
    flankL: [...document.querySelectorAll('#wrail .wr-orbl button')].map(b => b.getAttribute('data-ctl')),
    flankR: [...document.querySelectorAll('#wrail .wr-orbr button')].map(b => b.getAttribute('data-ctl') || b.className.split(' ')[0]),
    swapShown: vis(swap), swapTitle: swap ? swap.getAttribute('title') || '' : '',
    rail: rr ? {top: Math.round(rr.top), bottom: Math.round(rr.bottom),
                left: Math.round(rr.left), w: Math.round(rr.width), h: Math.round(rr.height)} : null,
    lidCount: lid.length,
    lidTitles: lid.map(b => b.getAttribute('title') || ''),
    pwrSlot: lid.findIndex(b => (b.className || '').includes('pwr-')) + 1,
    memOnLid: lid.some(b => ((b.getAttribute('title') || '').toLowerCase().includes('memor'))),
    memBtn: !!document.getElementById('memBtn'),
    memBtnOn: !!(document.getElementById('memBtn') || {classList:{contains:()=>false}}).classList.contains('on'),
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


def _boot(pg, url):
    pg.goto(url, wait_until="domcontentloaded")
    pg.wait_for_timeout(2200)
    pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
    pg.wait_for_timeout(300)


@pytest.fixture(scope="module")
def measured(run):
    from playwright.sync_api import sync_playwright
    out = {}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = b.new_context(viewport={"width": 1280, "height": 800})
        pg = ctx.new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _boot(pg, run)
        out["eye"] = pg.evaluate(_STATE)

        # The lid's corner swap sends the orb into the bar (a REAL click on the rendered button).
        pg.evaluate("() => document.querySelector('.orbctl button').click()")
        pg.wait_for_timeout(400)
        out["bar"] = pg.evaluate(_STATE)
        out["boot_and_swap_errors"] = list(errors)

        # A reload with the choice persisted must come back in bar mode (the retry path: the bar's slot may
        # mount after the orb on a persisted-"bar" boot).
        _boot(pg, run)
        out["bar_reload"] = pg.evaluate(_STATE)

        # The bar's own centre button is the way back up.
        pg.evaluate("() => document.querySelector('#wrail .wr-swap').click()")
        pg.wait_for_timeout(400)
        out["back"] = pg.evaluate(_STATE)

        # The memory button now lives in the TopBar; clicking it must flip its own on-state (the same
        # store.memOpen the orb's old lid button drove). Done LAST: the map's own fetches are not this
        # preview server's problem and must not poison the swap flow's error ledger above.
        pg.evaluate("() => document.getElementById('memBtn').click()")
        pg.wait_for_timeout(300)
        out["mem_after_click"] = pg.evaluate(_STATE)
        b.close()
    return out


def test_the_eye_orb_is_the_default_and_the_bar_orb_starts_deactivated(measured):
    """«initially the hor bar orbe is deactivated and we show the eye orbe»."""
    e = measured["eye"]
    assert not e["barMode"], e
    assert e["orbVisible"] and e["orbParent"] == "orbcore", f"the orb must rest in the eye: {e}"
    assert not e["slotShown"], f"the bar's orb slot must start hidden: {e}"
    assert e["swapShown"], f"the bar's swap button must show even while deactivated: {e}"
    assert measured["boot_and_swap_errors"] == [], measured["boot_and_swap_errors"]


def test_the_bar_owns_the_bottom_edge(measured):
    """«move the left bar to bottom» — full width, bottom edge, a shallow band."""
    r = measured["eye"]["rail"]
    assert r and r["left"] <= 1 and r["w"] >= 1280 * 0.95, r
    assert r["bottom"] >= 799 and r["h"] < 80, r


def test_the_lids_corner_swap_hides_the_eye_and_parks_the_orb_in_the_bar(measured):
    """ONE canvas, reparented — measured by its PARENT and its rendered SIZE, never by reading source (the
    4.19 lesson: a re-created canvas renders blank with no error)."""
    b = measured["bar"]
    assert b["barMode"], b
    assert b["orbParent"] == "wr-orbslot", f"the SAME canvas must move into the bar's slot: {b}"
    assert b["orbVisible"] and 0 < b["orbW"] <= 60, f"the bar orb must render small and real: {b}"
    assert not b["eyeChromeShown"], f"the eye chrome must hide: {b}"
    # #activity has an :empty→none rule of its own, so the honest check is PARITY: whatever it showed in eye
    # mode, bar mode must not change it — the bar-mode hiding rule must never reach it.
    assert b["activityShown"] == measured["eye"]["activityShown"], \
        f"bar mode changed #activity's visibility: {b} vs {measured['eye']}"


def test_the_lid_controls_flank_the_bar_orb_three_a_side(measured):
    """Operator, 2026-09-08: «el orbe tiene que estar en el centro y a los lados tiene que haber los tres
    iconos a un lado y los tres al otro… el icono de arrancar y parar en el centro del orbe». mic·spk·cap
    left; chat·robot·swap right; ⏻ does NOT travel — the slot IS the switch (the V2-124 mobile pattern):
    a BUTTON whose ⏻ face shows exactly while the agent is not live."""
    b = measured["bar"]
    assert b["flankL"] == ["mic", "spk", "cap"], f"left flank must be the three voice-side controls: {b['flankL']}"
    assert b["flankR"] == ["chat", "bot", "wr-swap"], f"right flank must be chat·robot·swap: {b['flankR']}"
    assert b["slotTag"] == "BUTTON", f"the slot must be clickable — it is the power switch: {b['slotTag']}"
    assert "pwr" not in b["flankL"] + b["flankR"], "⏻ must never sit beside the orb — it IS the orb's click"
    # This preview has no live agent, so the switch must wear its ⏻ face over the (kept, hidden) canvas.
    assert b["slotOff"] and b["pwrFaceShown"], f"no live agent → the ⏻ face shows: {b}"
    assert b["slotTitle"] and "." not in b["slotTitle"].split(" ")[0], f"raw i18n key on the switch: {b['slotTitle']!r}"


def test_the_choice_survives_a_reload(measured):
    b = measured["bar_reload"]
    assert b["barMode"] and b["orbParent"] == "wr-orbslot" and b["orbVisible"], b


def test_the_bar_swap_brings_the_eye_back(measured):
    k = measured["back"]
    assert not k["barMode"], k
    assert k["orbParent"] == "orbcore" and k["orbVisible"], f"the canvas must return home whole: {k}"
    assert k["eyeChromeShown"], k
    assert not k["slotShown"], k
    # The lid recovered ALL seVEN controls in canonical order — the flanked ones came home too.
    assert k["lidCount"] == 7 and k["pwrSlot"] == 4, f"the lid must come back whole and ordered: {k['lidTitles']}"
    assert k["flankL"] == [] and k["flankR"] == ["wr-swap"], f"the bar must give the controls back: {k}"


def test_the_memory_control_moved_to_the_top_bar(measured):
    """«quita el icono de la memoria del orbe. ponlo arriba a la derecha» — and the lid keeps SEVEN slots with
    ⏻ at the apex (slot 4), because the arc's nth-child geometry is keyed by slot index."""
    e = measured["eye"]
    assert e["memBtn"], "the TopBar must carry the memory button now"
    assert not e["memOnLid"], f"the lid must NOT carry a memory control any more: {e['lidTitles']}"
    assert e["lidCount"] == 7, f"the lid keeps 7 slots so the arc geometry holds: {e['lidTitles']}"
    assert e["pwrSlot"] == 4, f"⏻ must stay at the apex (slot 4): {e['lidTitles']}"
    assert measured["mem_after_click"]["memBtnOn"], "clicking the TopBar memory button must open the map"
