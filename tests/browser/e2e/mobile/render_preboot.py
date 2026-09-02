"""Render the BOOT NARRATION in a phone-sized Chromium and MEASURE it (V2-558).

WHY A RENDERED TEST AND NOT A SOURCE ONE: everything that matters here is behaviour over TIME in a
real browser — that the step line actually advances, that the progress arc is really drawn, and above
all that it does NOT complete on its own. A source-level test would happily pass on a narration that
never moves, which is precisely the thing being fixed: the splash before this shipped a spinner and
one fixed sentence, and the operator sat in front of it for over a minute on his first ever run.

THE PROPERTY THIS FILE REALLY DEFENDS is the honest one. A boot screen is where progress UIs lie, and
the lie is always the same: the bar arrives, then nothing happens. So the arc is asymptotic and capped,
and only `__zaelarPrebootDone()` — called by main.js when the app is genuinely up — closes it. If a
future edit makes the ring fill on a timer, `the arc never completes on its own` goes red.

Self-contained: its own preview server on a free port, no live engine, nothing destructive.

Run:  ./.venv/bin/python tests/browser/e2e/mobile/render_preboot.py
"""
import os
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
W, H = 390, 844

PREVIEW = '''
import sys
sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages
app = FastAPI()
app.include_router(pages.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

#: How much of the arc is drawn, 0..1 — read from the SVG the way the browser has it, not from our own maths.
ARC = """() => {
  const c = document.querySelector('#preboot .pb-fill');
  if (!c) return { found: false };
  const total = parseFloat(c.getAttribute('stroke-dasharray') || '0');
  const off = parseFloat(c.getAttribute('stroke-dashoffset') || '0');
  const box = c.getBoundingClientRect();
  return { found: true, frac: total ? 1 - off / total : 0,
           visible: box.width > 40 && box.height > 40,
           stroke: getComputedStyle(c).stroke };
}"""

STEP = """() => (document.querySelector('#preboot .pb-step') || {}).textContent || ''"""
TITLE = """() => (document.querySelector('#preboot .pb-title') || {}).textContent || ''"""

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


def run(url):
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H}, locale="es-ES")
        # HOLD THE SPLASH by never letting the app module land. That is not a trick to make the test
        # convenient: "the modules have not finished loading" IS the situation this screen exists for, and
        # `main.js` removes the splash on its first lines, so with it loaded there is nothing to measure.
        pg.route("**/mobile/app/main.js*", lambda route: route.abort())
        pg.goto(url, wait_until="domcontentloaded")
        pg.wait_for_selector("#preboot .pb-fill", timeout=10000, state="attached")

        arc0 = pg.evaluate(ARC)
        check("el arco EXISTE y está pintado a tamaño real", arc0["found"] and arc0["visible"], str(arc0))
        check("el arco tiene trazo de color, no es invisible",
              "rgb" in arc0["stroke"] and arc0["stroke"] != "rgb(0, 0, 0)", arc0["stroke"])

        title = pg.evaluate(TITLE)
        check("el título dice de qué va el arranque", len(title.strip()) > 6, repr(title))

        # The narration has to MOVE. Two samples five seconds apart with the step line unchanged means the
        # user is looking at the same static sentence the fix exists to remove.
        first = pg.evaluate(STEP)
        pg.wait_for_timeout(5200)
        second = pg.evaluate(STEP)
        check("la línea de paso AVANZA sola", first != second, f"{first!r} -> {second!r}")
        check("los pasos dicen algo, no están vacíos", len(second.strip()) > 4, repr(second))

        # THE honesty assertion. Plenty of time has passed and nothing has told it the app is up, so it must
        # still be short of the end.
        arc1 = pg.evaluate(ARC)
        check("el arco NO se completa solo", arc1["frac"] < 0.95, f"frac={arc1['frac']:.3f}")
        check("pero sí ha avanzado", arc1["frac"] > arc0["frac"], f"{arc0['frac']:.3f} -> {arc1['frac']:.3f}")

        # Only the real event closes it.
        pg.evaluate("() => window.__zaelarPrebootDone && window.__zaelarPrebootDone()")
        pg.wait_for_timeout(500)
        arc2 = pg.evaluate(ARC)
        check("al avisar la app, el arco SÍ se cierra", arc2["frac"] > 0.99, f"frac={arc2['frac']:.3f}")

        # Spanish browser, Spanish narration — the boot screen cannot read /api/i18n/bundle (it needs the very
        # engine being waited for), which is why it carries its own strings. INI-024's raw-keys blemish.
        check("narra en el idioma del navegador", "Listo" in pg.evaluate(STEP) or "ready" not in pg.evaluate(STEP).lower(),
              repr(pg.evaluate(STEP)))
        check("nunca enseña una clave i18n cruda", "boot." not in (title + second), repr(title + " / " + second))

        b.close()
    return 1 if fails else 0


def main():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        return run(f"http://127.0.0.1:{port}/m")
    finally:
        proc.terminate()


if __name__ == "__main__":
    sys.exit(main())
