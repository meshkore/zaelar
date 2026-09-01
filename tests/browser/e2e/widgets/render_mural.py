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
        # size + live_title matter: V2-538's fixes (preferred size on the instance path, live title) read them
        return j({"widgets": [{"id": w, "size": {"w": 360, "h": 300}, "live_title": True} for w in DATA]})
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

        pg.evaluate("() => window.zaelar.show('alpha::i1')")
        pg.wait_for_timeout(500)
        rr = rects(pg)
        A = "alpha::i1"
        check("a new card does NOT land under the open chat (the measured incident)",
              A in rr and not overlap(rr[A], chat), json.dumps({"chat": chat, "alpha": rr.get(A)}))
        # V2-538: the FIRST card of the session is an INSTANCE id — the path that used to skip _resolve, so
        # _meta was unloaded and BOTH the preferred size and the live title silently no-opped.
        check("an instance card gets its manifest size (grew with content before V2-538)",
              A in rr and 340 <= rr[A]["w"] <= 440 and 290 <= rr[A]["h"] <= 390, json.dumps(rr.get(A)))
        ltitle = pg.evaluate("""() => { const b = document.querySelector('.hb-win[data-wid="alpha::i1"] .hb-name');
          return b ? b.textContent : null; }""")
        check("live_title puts the TASK in the card header, not the piece's name", ltitle == "Alpha", str(ltitle))

        pg.evaluate("() => window.zaelar.show('beta')")
        pg.evaluate("() => window.zaelar.show('gamma')")
        pg.wait_for_timeout(600)
        rr = rects(pg)
        pairs = [(A, "beta"), (A, "gamma"), ("beta", "gamma")]
        check("three cards, none overlapping another while there is free room",
              len(rr) == 3 and not any(overlap(rr[a], rr[b]) for a, b in pairs), json.dumps(rr))
        check("none of the three sits under the chat",
              not any(overlap(rr[k], chat) for k in rr), json.dumps(rr))
        check("the NEWEST card carries the highest z (opens on top)",
              rr["gamma"]["z"] >= rr["beta"]["z"] >= rr[A]["z"], json.dumps({k: v["z"] for k, v in rr.items()}))

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
        rail_geom = pg.evaluate("""() => { const r = document.querySelector('#wrail').getBoundingClientRect();
          return { x: r.x, h: r.height, right: r.right }; }""")
        check("the rail is DOCKED: full height, at the left edge (V2-538)",
              rail_geom["x"] <= 1 and rail_geom["h"] >= H * 0.95, json.dumps(rail_geom))
        check("widgets do not overlap the docked rail (it owns the left edge)",
              all(v["x"] >= rail_geom["right"] - 1 for v in rr.values()), json.dumps({"rail": rail_geom, "cards": rr}))
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

        # ── V2-538: MAXIMIZE respects the reserved edge ─────────────────────────────────────────────────────
        # Measured with the chat OPEN this check cannot discriminate: a chat docked left pushes every layout
        # past the rail on its own. So the chat is closed first — then the only thing keeping a card off the
        # bar is Desktop.minX().
        pg.evaluate("() => window.zaelar.panel('chat')")   # toggle it shut
        pg.wait_for_timeout(300)
        pg.evaluate("() => window.__zaelarDesktop.maximize('beta')")
        pg.wait_for_timeout(300)
        rail_right = pg.evaluate("() => document.querySelector('#wrail').getBoundingClientRect().right")
        mx = rects(pg)["beta"]
        check("a MAXIMIZED card starts right of the docked rail (never under it)",
              mx["x"] >= rail_right - 1 and mx["w"] > W * 0.7,
              json.dumps({"rail_right": rail_right, "beta": mx}))
        pg.evaluate("() => window.__zaelarDesktop.maximize('beta')")   # restore
        pg.wait_for_timeout(200)

        # ── V2-538: folding gives the room back, unfolding takes it again ───────────────────────────────────
        pg.evaluate("() => document.querySelector('#wrail .wr-fold').click()")
        pg.wait_for_timeout(300)
        folded = pg.evaluate("""() => { const el = document.querySelector('#wrail');
          const r = el.getBoundingClientRect();
          return { w: r.width, right: r.right, on: el.classList.contains('on'),
                   folded: el.classList.contains('folded'),
                   visible: getComputedStyle(el).display !== 'none' }; }""")
        check("folded, the rail is a thin border that is STILL visible (never gone)",
              folded["folded"] and folded["visible"] and folded["on"] and folded["w"] <= 16, json.dumps(folded))
        # A card opened while the bar is folded may legitimately sit at the very left edge — that is the card
        # the reappearing bar has to shove. Without it, nothing is ever under the bar and the check is blind.
        pg.evaluate("() => window.__zaelarDesktop.wins.get('gamma').card.style.left = '2px'")
        pg.evaluate("() => document.querySelector('#wrail').click()")   # the whole strip unfolds it
        pg.wait_for_timeout(300)
        unfolded = pg.evaluate("""() => { const el = document.querySelector('#wrail');
          return { w: el.getBoundingClientRect().width, folded: el.classList.contains('folded') }; }""")
        check("clicking the folded strip brings the bar back",
              not unfolded["folded"] and unfolded["w"] > 20, json.dumps(unfolded))
        rr = rects(pg)
        rail_right = pg.evaluate("() => document.querySelector('#wrail').getBoundingClientRect().right")
        check("after unfolding, no card is left underneath the bar (hb:rail-resized)",
              all(v["x"] >= rail_right - 1 for v in rr.values()),
              json.dumps({"rail_right": rail_right, "cards": rr}))

        # ── V2-542: the bottom-left connection line is GONE, and nothing it carried was lost ────────────────
        # The operator, with the desktop in front of him: «ya tenemos una barra a la izquierda, las opciones
        # principales arriba a la derecha… no hace falta más mierda en pantalla. Si quieres poner un icono de
        # conexión, que sea el mismo que el del servidor». Whether a strip is still painting pixels at the
        # bottom of the desktop is a question only a browser can answer.
        chrome = pg.evaluate("""() => {
          const dot = document.querySelector('#statusBtn');
          const cs  = dot ? getComputedStyle(dot) : null;
          return {
            line_present: !!document.querySelector('.conn'),
            stray_ids: ['connv','latv','micv','micbar','micbarwrap'].filter(i => document.getElementById(i)),
            // `#desk` is the container (main.js), not a `.desk` class — and the selects were HIDDEN, so
            // a visibility-based count would have passed with the strip fully restored. Count the nodes.
            loose_selects: [...document.querySelectorAll('#desk select')].length,
            dot_present: !!dot,
            dot_visible: !!(cs && cs.display !== 'none' && cs.visibility !== 'hidden'),
            dot_classes: dot ? dot.className : '',
          };
        }""")
        check("the bottom connection line is GONE from the desktop",
              not chrome["line_present"] and not chrome["stray_ids"], json.dumps(chrome))
        check("no mic selector is left loose on the desktop (they live in Settings now)",
              chrome["loose_selects"] == 0, json.dumps(chrome))
        # And the half that makes the deletion safe: connection health did not disappear with the line. The ◉
        # already reads the SAME `store.conn()` through `overallStatus()` = worst(server, voice, offline) —
        # exactly the «mismo icono que el del servidor» he asked for — so it must be up there carrying a health
        # class, or the desktop would have LOST the signal instead of relocating it.
        check("connection health still has a home: the ◉ beacon, carrying its state class",
              chrome["dot_present"] and chrome["dot_visible"] and "st-" in chrome["dot_classes"],
              json.dumps(chrome))

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
