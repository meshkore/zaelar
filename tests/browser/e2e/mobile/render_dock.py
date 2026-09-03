"""Render the MOBILE shell in a phone-sized Chromium and MEASURE it.

WHY THIS EXISTS AS ITS OWN TEST: the deterministic node (4.18) reads source and can prove the dock is
wired to the right seams — it cannot tell you that the orb is a black hole in the middle of the bar.
On 2026-08-18 that is exactly what shipped: 0 painted pixels of 9216, with the render loop running
741 frames into a DETACHED canvas, no error anywhere, and a green source-level test that counted the
canvases and was satisfied that they existed. Everything asserted below is something only a browser
can answer.

SELF-CONTAINED AND NON-DESTRUCTIVE. It starts its OWN preview server (server.pages + /static +
server.i18n_api) on a free port instead of driving the operator's engine, for one specific reason:
the interesting assertions require TAPPING the power switch, and against a live engine that would
stop the operator's agent. It also means this needs no `make run` and cannot be polluted by whatever
state a live instance happens to be in.

What the preview deliberately does NOT have is a backend, so the boot veil never lifts and the
`/api/*` calls 404. Both are expected: the veil is removed before measuring (what is under it is
exactly what a booted shell shows), and the 404s are the routes this preview does not mount.

Run:  ./.venv/bin/python tests/browser/e2e/mobile/render_dock.py
"""
import json
import os
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

# this file is engine/tests/browser/e2e/mobile/render_dock.py -> five levels up is engine/
ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
W, H = 390, 844          # iPhone 14/15 logical viewport
MIN_TAP = 44             # the platform minimum for a touch target
MIN_PAINT = 200          # painted pixels that mean "something is really drawn", not an anti-aliasing fringe

PREVIEW = '''
import sys
sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI()
app.include_router(pages.router)
app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

# The boot veil covers the whole screen until the backend says ready, which is correct and, with no
# backend, permanent. Removing it lets the shell underneath be measured.
LIFT_VEIL = """() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e => e.remove())"""

PAINT = """() => {
  const c = document.querySelector('#orb');
  if (!c) return { found: false };
  const g = c.getContext('2d'); let painted = 0;
  const d = g.getImageData(0, 0, c.width, c.height).data;
  for (let i = 3; i < d.length; i += 4) if (d[i] > 8) painted++;
  return { found: true, painted, total: c.width * c.height, attached: c.isConnected,
           resized: c.width === Math.round(c.clientWidth * (devicePixelRatio || 1)) };
}"""

fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/m"
    try:
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            print("preview server never came up")
            return 1
        time.sleep(1.0)
        return run(url)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def run(url):
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H}, is_mobile=True, has_touch=True,
                            device_scale_factor=3)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(url, wait_until="networkidle")
        pg.wait_for_timeout(2500)      # let the i18n bundle land: a label read too early freezes on its key
        pg.evaluate(LIFT_VEIL)
        pg.wait_for_timeout(300)

        check("no page errors", not errors, " | ".join(errors[:4]))

        box = pg.evaluate("""() => {
          const dockEl = document.querySelector('.zm-dock');
          const r = dockEl && dockEl.getBoundingClientRect();
          const btns = [...document.querySelectorAll('.zm-dock button')]
            .filter(e => e.offsetParent !== null)     // the hidden centre face is mounted but is not a control
            .map(e => { const q = e.getBoundingClientRect();
              return { label: e.getAttribute('aria-label'), x: q.x, y: q.y, w: q.width, h: q.height }; });
          // Both centre faces are always mounted, the ⏻ first in DOM order — so querySelector would hand back
          // the HIDDEN one (a 0x0 box at 0,0). Ask for the VISIBLE face.
          const centre = [...document.querySelectorAll('.zm-orb-btn, .zm-pwr')]
            .find(e => e.offsetParent !== null);
          const c = centre && centre.getBoundingClientRect();
          const labels = [...document.querySelectorAll('[aria-label]')].map(e => e.getAttribute('aria-label'));
          const texts = [...document.querySelectorAll('body *')]
            .filter(e => e.offsetParent !== null)
            .flatMap(e => [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent.trim()))
            .filter(Boolean);
          return { dock: r && { y: r.y, h: r.height },
                   zones: [...document.querySelectorAll('.zm-dock > div')].map(e => e.className),
                   btns, labels, texts,
                   centre: c && { cx: c.x + c.width / 2, w: c.width },
                   canvases: document.querySelectorAll('.zm-dock canvas').length };
        }""")

        check("the dock sits at the bottom edge",
              box["dock"] and abs(box["dock"]["y"] + box["dock"]["h"] - H) < 2, json.dumps(box["dock"]))
        check("the dock is side / centre / side, in that order",
              box["zones"] == ["zm-side", "zm-centre", "zm-side"], str(box["zones"]))

        # The orb centred on the SCREEN, not merely between its neighbours: the side groups hold a
        # different number of buttons, and a bare `1fr` track let the wider one shove it 8px off.
        check("the orb is centred on the screen",
              box["centre"] and abs(box["centre"]["cx"] - W / 2) <= 1.5,
              f"centre x={box['centre'] and round(box['centre']['cx'], 1)}, screen centre={W / 2}")
        # TWO controls per side since V2-573 (2026-09-04). It was 3+2 — mic · speaker · captions | ORB | chat ·
        # menu — until the operator's restyle: chat · dashboards | ORB | mic · config, with the captions button
        # retired and the speaker moved into the config sheet. Measured on the RENDERED bar rather than trusted
        # from the source, because "the icon is declared" and "the icon is on screen at a reachable size" are
        # different claims, and this shell has already paid for the difference once (the unpainted orb).
        left = [x["label"] for x in box["btns"] if x["x"] + x["w"] / 2 < box["centre"]["cx"] - 5]
        right = [x["label"] for x in box["btns"] if x["x"] + x["w"] / 2 > box["centre"]["cx"] + 5]
        check("two controls left of the orb, two right",
              len(left) == 2 and len(right) == 2,
              f"left={left} right={right}")

        small = [(x["label"], x["w"], x["h"]) for x in box["btns"] if min(x["w"], x["h"]) < MIN_TAP]
        check(f"every tap target is at least {MIN_TAP}px", not small, str(small))
        out = [x["label"] for x in box["btns"]
               if x["y"] < box["dock"]["y"] - 1 or x["y"] + x["h"] > H + 1]
        check("no control escapes the dock", not out, str(out))

        # ── the orb is really DRAWN ──
        check("the orb has its two canvases", box["canvases"] == 2, f"{box['canvases']}")
        paint = pg.evaluate(PAINT)
        check("the orb is PAINTED, not just present",
              paint.get("found") and paint["painted"] > MIN_PAINT,
              json.dumps(paint) + "  <- empty canvas: the visualiser is drawing into a detached node")
        check("the visualiser owns the canvas that is ON SCREEN",
              paint.get("attached") and paint.get("resized"), json.dumps(paint))

        # ── no label rendered as its own i18n key (t() returns the KEY on a miss, and a key is truthy) ──
        NS = {"mobile", "orb", "camera", "config", "feedback", "energy", "desktop", "chat", "viz"}
        keyish = [s for s in box["texts"] + [x for x in box["labels"] if x]
                  if s and "." in s and " " not in s and s.split(".")[0] in NS]
        check("no label rendered as a raw i18n key", not keyish, str(keyish[:6]))

        # ── a sheet must never bury the dock: no mic and no power switch while chatting ──
        pg.evaluate("""() => { const b = [...document.querySelectorAll('.zm-dock button')]
            .find(e => /hat|onversa/i.test(e.getAttribute('aria-label') || '')); if (b) b.click(); }""")
        pg.wait_for_timeout(700)
        sheet = pg.evaluate("""() => {
          const d = document.querySelector('.zm-dock').getBoundingClientRect();
          const sh = document.querySelector('.zm-sheet.open');
          const s = sh && sh.getBoundingClientRect();
          const mic = [...document.querySelectorAll('.zm-dock button')]
            .filter(e => e.offsetParent !== null)[0].getBoundingClientRect();
          const hit = document.elementFromPoint(mic.x + mic.width / 2, mic.y + mic.height / 2);
          return { open: !!sh, dockTop: d.y, sheetBottom: s ? s.y + s.height : null,
                   micReachable: !!(hit && hit.closest('.zm-dock')) };
        }""")
        check("the chat button opens a sheet", sheet["open"])
        check("the sheet stops ON TOP of the dock, never over it",
              sheet["sheetBottom"] is None or sheet["sheetBottom"] <= sheet["dockTop"] + 1,
              json.dumps(sheet))
        check("the mic is still tappable with the chat open", sheet["micReachable"], json.dumps(sheet))

        # ── STOPPED: the centre slot becomes a ⏻, and the orb comes BACK painted when restarted ──
        pg2 = ctx.new_page()
        pg2.add_init_script("localStorage.setItem('hb_power_off','1')")
        pg2.goto(url, wait_until="networkidle")
        pg2.wait_for_timeout(2000)
        pg2.evaluate(LIFT_VEIL)
        st = pg2.evaluate("""() => {
          const p = document.querySelector('.zm-pwr'), o = document.querySelector('.zm-orb-btn');
          const r = p && p.getBoundingClientRect();
          // both faces are mounted for the life of the page, so ask which is VISIBLE
          return { pwr: !!(p && p.offsetParent), orb: !!(o && o.offsetParent),
                   cx: r && r.x + r.width / 2, w: r && r.width };
        }""")
        check("stopped: the centre slot is a ⏻", st["pwr"], json.dumps(st))
        check("stopped: the orb is not visible as well", not st["orb"],
              "both faces are showing — the centre slot must present one at a time")
        check("stopped: the ⏻ is centred and big",
              st["cx"] is not None and abs(st["cx"] - W / 2) <= 1.5 and st["w"] >= 52, json.dumps(st))

        # This is the path the frozen-orb latch broke: while hidden the orb's width is 0, and recording
        # "already frozen" on those frames left it permanently blank once it came back.
        pg2.evaluate("() => document.querySelector('.zm-dock .zm-pwr').click()")
        pg2.wait_for_timeout(1800)
        back = pg2.evaluate("""() => {
          const o = document.querySelector('.zm-orb-btn'), p = document.querySelector('.zm-pwr');
          return { orb: !!(o && o.offsetParent), pwr: !!(p && p.offsetParent) };
        }""")
        check("restarted: the orb replaces the switch", back["orb"] and not back["pwr"], json.dumps(back))
        rp = pg2.evaluate(PAINT)
        check("restarted: the orb PAINTS again", rp.get("painted", 0) > MIN_PAINT,
              json.dumps(rp) + "  <- the frozen-orb latch is holding it blank")

        b.close()

    print(f"\n{'ALL OK' if not fails else str(len(fails)) + ' FAILURE(S): ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
