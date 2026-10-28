"""V2-831 T-18 — mic + speaker LILAC while listening, GREY while the tap waits for the wake word (node 4.327).

A parked tap sends no audio and the engine's input is closed (nothing is transcribed, nothing billed), so a lilac
mic there would say «I am listening» when nobody is. Measured on the RENDERED page, through the shipped cascade,
with the REAL LiveKit session module served at the `session.js` URL exactly as `server/livekit_api.py` does in
production — the Orb reads the park from the module that owns it, not from a copy.

Three states, each read as the colour actually painted and compared with the palette TOKENS (never a hex here):
  listening → mic and speaker carry `on` and paint `--hb-accent` (lilac);
  waiting   → mic and speaker carry `wait`, paint `--hb-muted-2` (grey) at full strength, and the mic wears NO
              slash (armed, not closed) and no level meter;
  closed    → the mic is `off` and crossed out (unchanged V2-648 behaviour).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys

import pytest

from tests.waiting import port_listening

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
@app.get("/static/app/services/session.js")
def _lk():   # the production swap (server/livekit_api.py): the LiveKit adapter AT the session.js URL
    return FileResponse(%r, media_type="application/javascript")
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

_READ = """() => {
  const tok = (n) => { const p = document.createElement('i'); p.style.color = `var(${n})`;
                       document.body.appendChild(p); const c = getComputedStyle(p).color; p.remove(); return c; };
  const face = (ctl) => {
    const b = document.querySelector(`[data-ctl="${ctl}"]`);
    const cs = getComputedStyle(b);
    return {cls: [...b.classList].sort().join(' '), color: cs.color, opacity: Number(cs.opacity),
            slash: !!b.querySelector('.mic-slash')};
  };
  return {lilac: tok('--hb-accent'), grey: tok('--hb-muted-2'), mic: face('mic'), spk: face('spk')};
}"""

_SET = """async ([muted, parked]) => {
  const store = await import('/static/app/core/store.js?v=2');
  const mic = await import('/static/app/services/mic.js?v=1');
  const session = await import('/static/app/services/session.js?v=3');
  store.setPowerOff(false); store.setRemoteHeld(false); store.setStarted(true); store.setBotMuted(false);
  mic.setMuted(muted, 'test');
  session.setTapParked(parked);
  await new Promise(r => setTimeout(r, 200));
  return session.tapParked();
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def measured():
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    lk = os.path.join(ENGINE, "frontend", "app", "services", "session-lk.js")
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, lk, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        port_listening(port, timeout_s=30)
        out = {}
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.wait_for_timeout(2200)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
            for name, muted, parked in (("listening", False, False), ("waiting", False, True),
                                        ("closed", True, False), ("reopened", False, False)):
                out[name + "_parked"] = pg.evaluate(_SET, [muted, parked])
                out[name] = pg.evaluate(_READ)
            out["errors"] = errors
            shots = os.environ.get("T18_SHOTS")
            if shots:   # audit captures for the Architect (writer rule 6), never shown to the operator
                os.makedirs(shots, exist_ok=True)
                for name, muted, parked in (("listening", False, False), ("waiting", False, True),
                                            ("closed", True, False)):
                    pg.evaluate(_SET, [muted, parked])
                    pg.locator("#orbwrap").screenshot(path=os.path.join(shots, f"orb-{name}.png"))
            b.close()
        return out
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


def test_the_tokens_are_two_different_colours(measured):
    m = measured["listening"]
    assert m["lilac"] and m["grey"] and m["lilac"] != m["grey"], m


def test_listening_paints_mic_and_speaker_lilac(measured):
    m = measured["listening"]
    assert measured["listening_parked"] is False
    for dev in ("mic", "spk"):
        assert " on" in " " + m[dev]["cls"], (dev, m[dev])
        assert m[dev]["color"] == m["lilac"], (dev, m[dev], m["lilac"])


def test_waiting_for_the_wake_word_paints_mic_and_speaker_grey(measured):
    m = measured["waiting"]
    assert measured["waiting_parked"] is True, "the tap must report itself parked"
    for dev in ("mic", "spk"):
        assert "wait" in m[dev]["cls"].split(), (dev, m[dev])
        assert m[dev]["color"] == m["grey"], f"{dev} must be GREY while the ear waits: {m[dev]} vs {m['grey']}"
        assert m[dev]["opacity"] == 1, f"waiting is not closed: full strength: {m[dev]}"
    assert not m["mic"]["slash"], "an armed ear is not a closed mic: no slash"
    assert "vu" not in m["mic"]["cls"].split(), "no level meter over audio nobody transcribes"


def test_closed_stays_crossed_out_and_reopening_is_lilac_again(measured):
    c, r = measured["closed"], measured["reopened"]
    assert "off" in c["mic"]["cls"].split() and c["mic"]["slash"], c["mic"]
    assert r["mic"]["color"] == r["lilac"] and r["spk"]["color"] == r["lilac"], r


def test_no_page_error(measured):
    assert measured["errors"] == [], measured["errors"]
