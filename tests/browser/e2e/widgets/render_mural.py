"""Render the DESKTOP canvas in Chromium and MEASURE the mural rules (V2-537).

WHY A RENDER TEST: the incident this initiative fixes was invisible to every source-level check — a new
widget opened exactly under the floating chat (z 9001, above the cards' 8000 cap by design) and the operator
had no way to know it existed. Whether a rect lands under another rect, whether the rail actually paints its
chips, whether minimize really removes pixels: only a browser can answer (the V2-124 lesson, again).

SELF-CONTAINED AND NON-DESTRUCTIVE (same pattern as render_deck.py): its OWN preview server, fake widget
backend by route interception, never the operator's engine.

Run:  ./.venv/bin/python tests/browser/e2e/widgets/render_mural.py
"""
import json
import re
import socket
import subprocess
import sys
import time
import os

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
W, H = 1280, 800

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

LIFT_VEIL = """() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e => e.remove())"""
# The fake card is TALL on purpose: the incident's card was a browser widget. A short card placed on top of
# the chat would not visually overlap it and the D1 disarm went green over the restored defect.
WIDGET_JS = 'export function render(el, data){ el.style.minHeight = "300px"; el.textContent = "W:" + ((data && data.title) || "?"); }'

DATA = {"alpha": {"title": "Alpha"}, "beta": {"title": "Beta"}, "gamma": {"title": "Gamma"}}
ROUTE_RE = re.compile(  # anchored to the ORIGIN: /static/app/widgets/desktop.js also contains "/widgets/"
    r"^https?://[^/]+/(widgets(/.*)?|api/(canvas/.*|desktop/epoch|client-log|run|status|ui-event))(\?.*)?$")

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


def route(r):
    path = re.sub(r"^https?://[^/]+", "", r.request.url).split("?", 1)[0]
    def j(obj, status=200):
        r.fulfill(status=status, content_type="application/json", body=json.dumps(obj))
    if path == "/widgets":
        return j({"widgets": [{"id": w} for w in DATA]})
    if path == "/widgets/registry":
        return j({"registry": []})
    if path == "/api/desktop/epoch":
        return j({"epoch": ""})
    if path == "/api/canvas/layout":
        return j({"items": [], "live": []})
    if path in ("/api/canvas/state", "/api/client-log", "/api/ui-event"):
        return j({"ok": True})
    if path == "/api/run":
        return j({"state": "running", "running": True})
    m = re.match(r"^/widgets/([^/]+)/(data|manifest|widget\.js)$", path)
    if m:
        wid, kind = m.group(1), m.group(2)
        if kind == "widget.js":
            return r.fulfill(status=200, content_type="application/javascript", body=WIDGET_JS)
        if kind == "manifest":
            return j({"id": wid})
        return j(DATA.get(wid, {"title": wid}))
    return r.fallback()          # anything else (static modules, css) goes to the real preview server


def rects(pg):
    return pg.evaluate("""() => {
      const out = {};
      document.querySelectorAll('.hb-win').forEach(c => {
        const r = c.getBoundingClientRect();
        out[c.dataset.wid] = { x: r.x, y: r.y, w: r.width, h: r.height,
                               z: parseInt(c.style.zIndex) || 0,
                               visible: getComputedStyle(c).display !== 'none' && r.width > 0 };
      });
      return out;
    }""")


def overlap(a, b):
    return not (a["x"] + a["w"] <= b["x"] or b["x"] + b["w"] <= a["x"]
                or a["y"] + a["h"] <= b["y"] or b["y"] + b["h"] <= a["y"])


def run(url):
    errors = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": H})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route(ROUTE_RE, route)
        pg.goto(url, wait_until="domcontentloaded")   # the shell holds /events open — networkidle never comes
        pg.wait_for_timeout(2000)
        pg.evaluate(LIFT_VEIL)

        # the incident's exact stage: the chat wall OPEN, floating on the left
        pg.evaluate("() => window.zaelar.panel('chat')")
        pg.wait_for_timeout(300)
        chat = pg.evaluate("""() => { const c = document.querySelector('#chatwall');
          const r = c.getBoundingClientRect();
          return { x: r.x, y: r.y, w: r.width, h: r.height, z: parseInt(getComputedStyle(c).zIndex) || 0 }; }""")
        check("the chat wall is open with real size", chat["w"] > 200 and chat["h"] > 200, json.dumps(chat))

        pg.evaluate("() => window.zaelar.show('alpha')")
        pg.wait_for_timeout(500)
        rr = rects(pg)
        check("a new card does NOT land under the open chat (the measured incident)",
              "alpha" in rr and not overlap(rr["alpha"], chat), json.dumps({"chat": chat, "alpha": rr.get("alpha")}))

        pg.evaluate("() => window.zaelar.show('beta')")
        pg.evaluate("() => window.zaelar.show('gamma')")
        pg.wait_for_timeout(600)
        rr = rects(pg)
        pairs = [("alpha", "beta"), ("alpha", "gamma"), ("beta", "gamma")]
        check("three cards, none overlapping another while there is free room",
              len(rr) == 3 and not any(overlap(rr[a], rr[b]) for a, b in pairs), json.dumps(rr))
        check("none of the three sits under the chat",
              not any(overlap(rr[k], chat) for k in rr), json.dumps(rr))
        check("the NEWEST card carries the highest z (opens on top)",
              rr["gamma"]["z"] >= rr["beta"]["z"] >= rr["alpha"]["z"], json.dumps({k: v["z"] for k, v in rr.items()}))

        # ── the rail: one chip per card, always on top of the chat ───────────────────────────────────────────
        rail = pg.evaluate("""() => { const el = document.querySelector('#wrail');
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return { on: el.classList.contains('on'), visible: getComputedStyle(el).display !== 'none',
                   w: r.width, z: parseInt(getComputedStyle(el).zIndex) || 0,
                   chips: [...el.querySelectorAll('.wr-chip')].map(c => ({ wid: c.dataset.wid, tag: c.tagName,
                        min: c.classList.contains('min') })) }; }""")
        check("the rail exists, is visible and thin", rail and rail["visible"] and rail["on"] and rail["w"] < 60,
              json.dumps(rail))
        check("one chip per open card, and they are buttons",
              rail and len(rail["chips"]) == 3 and all(c["tag"] == "BUTTON" for c in rail["chips"]),
              json.dumps(rail and rail["chips"]))
        check("the rail paints ABOVE the chat (a covered widget is never unknowable)",
              rail and rail["z"] > chat["z"], f"rail z={rail and rail['z']} chat z={chat['z']}")

        if not rail or not rail["on"] or len(rail["chips"]) < 3:
            check("rail usable for the interaction steps (skipping them)", False, json.dumps(rail))
            check("no page errors", not errors, " | ".join(errors[:4]))
            b.close()
            print(); print(f"{len(fails)} FAILED: {fails}"); return 1

        # ── taskbar semantics: chip of the TOP card minimizes; chip again reveals ────────────────────────────
        pg.evaluate("() => document.querySelector('#wrail .wr-chip[data-wid=gamma]').click()")
        pg.wait_for_timeout(200)
        rr = rects(pg)
        check("clicking the top card's chip MINIMIZES it (pixels gone, still open)",
              not rr["gamma"]["visible"], json.dumps(rr["gamma"]))
        still_open = pg.evaluate("() => [...window.__zaelarDesktop.wins.keys()]")
        check("a minimized card is still OPEN for the brain", "gamma" in still_open, json.dumps(still_open))
        pg.evaluate("() => document.querySelector('#wrail .wr-chip[data-wid=gamma]').click()")
        pg.wait_for_timeout(200)
        rr = rects(pg)
        check("clicking it again REVEALS it on top",
              rr["gamma"]["visible"] and rr["gamma"]["z"] >= max(v["z"] for v in rr.values()), json.dumps(rr["gamma"]))

        # ── bulk: minimize all / show all ────────────────────────────────────────────────────────────────────
        pg.evaluate("() => document.querySelector('#wrail .wr-toggle').click()")
        pg.wait_for_timeout(200)
        rr = rects(pg)
        check("minimize-all hides every card", not any(v["visible"] for v in rr.values()), json.dumps(rr))
        pg.evaluate("() => document.querySelector('#wrail .wr-toggle').click()")
        pg.wait_for_timeout(200)
        rr = rects(pg)
        check("show-all brings every card back", all(v["visible"] for v in rr.values()), json.dumps(rr))

        # ── arrange: a regular grid, right of the rail, clear of the chat, inside the canvas ────────────────
        pg.evaluate("() => window.__zaelarDesktop.minimize('beta')")   # arrange must REVEAL what is minimized
        pg.evaluate("() => document.querySelector('#wrail .wr-arrange').click()")
        pg.wait_for_timeout(300)
        rr = rects(pg)
        rail_r = pg.evaluate("() => document.querySelector('#wrail').getBoundingClientRect().right")
        ok_grid = (all(v["visible"] for v in rr.values())
                   and not any(overlap(rr[a], rr[b]) for a, b in pairs)
                   and all(v["x"] >= rail_r for v in rr.values())
                   and not any(overlap(rr[k], chat) for k in rr)
                   and all(v["x"] >= 0 and v["y"] >= 0 and v["x"] + v["w"] <= W and v["y"] + v["h"] <= H - 100
                           for v in rr.values()))
        check("arrange tiles every card in a visible, non-overlapping grid clear of chat and rail",
              ok_grid, json.dumps({"rail_right": rail_r, "chat": chat, "cards": rr}))

        check("no page errors", not errors, " | ".join(errors[:4]))
        b.close()

    print()
    if fails:
        print(f"{len(fails)} FAILED: {fails}")
        return 1
    print("all mural checks passed")
    return 0


def main():
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}/"
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


if __name__ == "__main__":
    sys.exit(main())
