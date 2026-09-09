"""V2-648 — a stopped microphone is CROSSED OUT, and a lit control looks lit.

Operator, 2026-09-10 (with the bottom-bar screenshot): «cuando el micro está desactivado, aparte de que se
quede en gris, quiero que se vea un icono de micro tachado, porque si no no hay mucha diferencia entre los
iconos en el color activo y en el desactivado, se aprecia poco. Aumenta si quieres el contraste entre el
brillo de los iconos activos y desactivados, pero sobre todo el micro, que se vea tachado cuando está parado.»

Grey was carrying the whole message, and grey is also what a merely disabled control looks like — so the
SHAPE has to say it. Only a browser can answer the two questions that matter here: does the slash actually
RENDER (the 4.19 lesson — an icon swapped inside a conditional can go missing with no error at all), and
does the shipped cascade really paint ON with more weight than OFF, or does some later rule cancel it out.
Everything below is measured on the rendered page, and the mic is muted by a REAL click on its button.

The same pass took the SPEAKER off the orb (same operator, same day): «el naranja realmente lo quiero poner
cuando la gente nos está escuchando A NOSOTROS, no cuando puede hablar… el altavoz no tiene ningún efecto
sobre el color del orbe». A dimming rule older than the day the orb's colour became the listening signal was
desaturating the orange into a dull brown whenever he silenced zaelar's voice, and he read the brown as «no
me escucha» — two meanings on one surface, newest one losing. So the last case here measures that muting the
speaker changes NOTHING about how the orb is painted.
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

# The mic's rendered face. `slashInk` is the honest one: a <path> that exists in the DOM but paints nothing
# (zero-size box, display:none, a parent that never mounted) is exactly the failure this file is here for.
_MIC = """() => {
  const btn = document.querySelector('[data-ctl="mic"]');
  const svg = btn && btn.querySelector('svg');
  const slash = svg && svg.querySelector('.mic-slash');
  const box = el => { try { const b = el.getBBox(); return {w: Math.round(b.width), h: Math.round(b.height)}; }
                      catch (_) { return {w: 0, h: 0}; } };
  return {
    present: !!btn,
    strokes: svg ? svg.children.length : 0,
    hasSlash: !!slash,
    slashInk: slash ? box(slash) : {w: 0, h: 0},
    slashShown: !!slash && getComputedStyle(slash).display !== 'none'
                && Number(getComputedStyle(slash).opacity) > 0,
    off: !!btn && btn.classList.contains('off'),
    title: btn ? (btn.getAttribute('title') || '') : '',
  };
}"""

# The shipped cascade, measured on REAL elements carrying the real classes (not read out of the source):
# whatever a later rule does, `on` has to end up painted with strictly more weight than `off`.
_WEIGHT = """() => {
  const mk = (cls) => {
    const b = document.createElement('button');
    b.className = 'orbic ' + cls;
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4 20 20"/></svg>';
    document.body.appendChild(b);
    const cs = getComputedStyle(b), sv = getComputedStyle(b.querySelector('svg'));
    const out = {opacity: Number(cs.opacity), color: cs.color, filter: cs.filter,
                 stroke: parseFloat(sv.strokeWidth) || 0, ink: Number(cs.opacity) * Number(sv.opacity)};
    b.remove();
    return out;
  };
  // `on vu` is the LIVE MICROPHONE at rest — the icon he singled out. Its meter dims the svg between beats,
  // and that resting floor is what he was actually comparing against the dark icons.
  return {on: mk('on'), off: mk('off'), micRest: mk('on vu')};
}"""


# How the orb is actually PAINTED — not which classes it happens to carry. A future rule that dims it from
# somewhere else would slip past a class-list check and fail here, which is the point.
_ORB = """() => {
  const c = document.getElementById('orb');
  if (!c) return null;
  const cs = getComputedStyle(c);
  return {opacity: cs.opacity, filter: cs.filter, cls: [...c.classList].sort().join(' ')};
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
        pg.goto(run, wait_until="domcontentloaded")
        pg.wait_for_timeout(2200)
        pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
        pg.wait_for_timeout(300)
        # Start from a known face: the mic's state persists in localStorage, so unmute first whatever it was.
        pg.evaluate("() => { if (document.querySelector('[data-ctl=mic]').querySelector('.mic-slash'))"
                    "         document.querySelector('[data-ctl=mic]').click(); }")
        pg.wait_for_timeout(250)
        out["open"] = pg.evaluate(_MIC)
        # A REAL click on the rendered button is what the operator does.
        pg.evaluate("() => document.querySelector('[data-ctl=mic]').click()")
        pg.wait_for_timeout(250)
        out["muted"] = pg.evaluate(_MIC)
        # …and back, because a swap that only works once is a swap that leaves the icon lying.
        pg.evaluate("() => document.querySelector('[data-ctl=mic]').click()")
        pg.wait_for_timeout(250)
        out["reopened"] = pg.evaluate(_MIC)
        out["weight"] = pg.evaluate(_WEIGHT)
        # The speaker must be inert on the orb: measure the orb's OWN painting either side of a real click.
        out["orb_before_spk"] = pg.evaluate(_ORB)
        pg.evaluate("() => document.querySelector('[data-ctl=\"spk\"]').click()")
        pg.wait_for_timeout(300)
        out["orb_after_spk"] = pg.evaluate(_ORB)
        out["spk_off"] = pg.evaluate("() => document.querySelector('[data-ctl=\"spk\"]').classList.contains('off')")
        out["errors"] = list(errors)
        b.close()
    return out


def test_an_open_microphone_wears_no_slash(measured):
    o = measured["open"]
    assert o["present"], f"the mic control must exist on the lid: {o}"
    assert not o["hasSlash"], f"an open mic must NOT be crossed out: {o}"
    assert measured["errors"] == [], measured["errors"]


def test_a_muted_microphone_is_crossed_out_and_the_slash_really_paints(measured):
    """«que se vea un icono de micro tachado» — and *vea* is the word: the slash must have ink."""
    m = measured["muted"]
    assert m["hasSlash"], f"a muted mic must be crossed out: {m}"
    assert m["slashShown"], f"the slash must be visible, not merely present in the DOM: {m}"
    assert m["slashInk"]["w"] > 8 and m["slashInk"]["h"] > 8, \
        f"the slash must cross the icon, not sit in a zero-size box: {m}"
    assert m["strokes"] > measured["open"]["strokes"], \
        f"the crossed face must ADD the slash to the mic, not replace the mic: {m}"
    assert m["off"], f"and it must still read as an off control (grey), not only as crossed: {m}"


def test_the_swap_works_in_both_directions(measured):
    """A face that only changes once is a face that lies from the second click on."""
    r = measured["reopened"]
    assert not r["hasSlash"], f"unmuting must take the slash away again: {r}"
    assert r["strokes"] == measured["open"]["strokes"], f"and restore the open face exactly: {r}"


def test_a_lit_control_is_painted_with_more_weight_than_a_dark_one(measured):
    """«aumenta el contraste entre el brillo de los iconos activos y desactivados». Measured through the real
    cascade, so a later rule that flattens the difference fails here instead of on his screen."""
    w = measured["weight"]
    assert w["on"]["opacity"] - w["off"]["opacity"] >= 0.3, f"ON must be markedly brighter than OFF: {w}"
    assert w["on"]["color"] != w["off"]["color"], f"ON and OFF must not share a colour: {w}"
    assert w["on"]["stroke"] > w["off"]["stroke"], f"ON must carry more ink than OFF: {w}"
    assert w["on"]["filter"] not in ("none", ""), f"ON must read as LIT, not merely tinted: {w}"


def test_the_speaker_does_not_touch_the_orb(measured):
    """«el altavoz no tiene ningún efecto sobre el color del orbe». The orb answers ONE question — is anybody
    listening to you — so silencing zaelar's own voice must leave it painted exactly as it was."""
    before, after = measured["orb_before_spk"], measured["orb_after_spk"]
    assert before and after, f"the orb canvas must exist to be measured: {before} / {after}"
    assert measured["spk_off"], "the click must really have toggled the speaker control"
    assert after == before, f"muting the speaker repainted the orb: {before} -> {after}"


def test_a_live_microphone_reads_as_lit_between_words(measured):
    """The VU meter dims the mic between beats. At its resting floor it still has to look LIT — «sobre todo el
    micro» is the icon he was comparing, and a lit control that sits near a dark one is the complaint."""
    w = measured["weight"]
    assert w["micRest"]["ink"] >= 0.85, f"a live mic at rest must read as lit, not half-off: {w['micRest']}"
    assert w["micRest"]["ink"] - w["off"]["ink"] >= 0.3, \
        f"and must stand clearly apart from a stopped control: {w}"
