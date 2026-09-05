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
WIDGET_JS = ('export function render(el, data){ el.style.minHeight = "300px";'
             # V2-551: a widget that renders FAR bigger than the reserved 400x340 tile — the shape of the bug the
             # operator saw («medio widget está en el área visible y medio fuera»). `_place` fits the tile; only a
             # standing guarantee can catch what the card becomes afterwards.
             ' if(data && data.huge){ el.style.width = "1900px"; el.style.height = "1400px"; }'
             ' el.textContent = "W:" + ((data && data.title) || "?"); }')

DATA = {"alpha": {"title": "Alpha"}, "beta": {"title": "Beta"}, "gamma": {"title": "Gamma"},
        "huge": {"title": "Huge", "huge": True},
        # V2-583: a widget that declares NATIVE fullscreen (the youtube player's shape). A voice order has no
        # user gesture, so requestFullscreen() rejects asynchronously — the card must maximize in-app instead
        # of failing into silence, which is what happened live («Maximiza el video», session 0e3a42d6).
        "video": {"title": "Video"}}
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
        # `huge` declares NO preferred size ON PURPOSE: with one, `_applyPreferred` would clamp the card back to
        # 360x300 and the «renders bigger than its tile» check would pass without ever having a big card —
        # vacuously, on a widget that never grew. It has to be the widgets that declare nothing (most of them)
        # whose card is free to become whatever its content renders.
        return j({"widgets": [dict({"id": w, "live_title": True},
                                   **({} if w == "huge" else {"size": {"w": 360, "h": 300}}),
                                   **({"fullscreen": "native"} if w == "video" else {}))
                              for w in DATA]})
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

        # ── bulk: hide all / show all — TWO buttons since V2-552, not one toggle that flips meaning ─────────
        # The four controls are checked HERE, before anything clicks them: a missing button makes `.click()` on
        # null throw and the run dies with a traceback instead of a red check, which is a worse signal for the
        # same defect (measured while disarming this).
        present = pg.evaluate("""() => [...document.querySelectorAll('#wrail .wr-tools > button')]
            .map(b => b.className)""")
        check("the four controls he asked for are there, in order",
              present[:4] == ["wr-hide", "wr-show", "wr-compact", "wr-fitall"], json.dumps(present))
        if present[:4] != ["wr-hide", "wr-show", "wr-compact", "wr-fitall"]:
            check("rail controls usable for the bulk steps (skipping them)", False, json.dumps(present))
            b.close()
            print()
            print(f"{len(fails)} FAILED: {fails}")
            return 1
        pg.evaluate("() => document.querySelector('#wrail .wr-hide').click()")
        pg.wait_for_timeout(250)
        rr = rects(pg)
        check("hide-all hides every card", not any(v["visible"] for v in rr.values()), json.dumps(rr))
        # HIDE, never CLOSE: the chips must all still be there, which is the only way back to any single card.
        chips_after_hide = pg.evaluate("() => document.querySelectorAll('#wrail .wr-chip').length")
        check("hiding all KEEPS a chip per card (hidden is not closed)",
              chips_after_hide == 3, str(chips_after_hide))
        pg.evaluate("() => document.querySelector('#wrail .wr-show').click()")
        pg.wait_for_timeout(250)
        rr = rects(pg)
        check("show-all brings every card back", all(v["visible"] for v in rr.values()), json.dumps(rr))
        # Each control says whether it would do anything, instead of one glyph changing under the operator.
        st = pg.evaluate("""() => ({hide: !!document.querySelector('#wrail .wr-hide').disabled,
                                    show: !!document.querySelector('#wrail .wr-show').disabled})""")
        check("with everything visible, SHOW-ALL is the one disabled",
              st["show"] and not st["hide"], json.dumps(st))

        # ── arrange: a regular grid, right of the rail, clear of the chat, inside the canvas ────────────────
        pg.evaluate("() => window.__zaelarDesktop.minimize('beta')")   # arrange must REVEAL what is minimized
        pg.evaluate("() => document.querySelector('#wrail .wr-fitall').click()")
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

        # ── V2-551: rejilla, apilado vertical y la garantía de que una tarjeta se vea ENTERA ────────────────
        # El operador: «que este escritorio tenga algún tipo de rejilla… ponle 5 píxeles», «colocados
        # verticalmente pegados unos a otros», y el fallo: «se abre un widget de imagen y medio widget está en
        # el área visible y medio aparece como si estuviera fuera de la pantalla».
        # Measured on a canvas placed by `_place`, NOT on the one `arrange()` tiled sixty lines above: those
        # positions come from a different algorithm and would answer a different question.
        # The CHAT WALL is closed for this measurement, the same reason V2-538 had to close it to measure
        # maximize: open and docked it eats the left columns, and the orb strip then blocks what is left of the
        # first one — so «did the second card go UNDER the first» becomes a question the geometry cannot answer.
        # Closing it does not weaken the check; it removes an obstacle that makes the property unmeasurable.
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2'); s.setChatOpen(false);
          window.zaelar.close();
        }""")
        pg.wait_for_timeout(500)
        for _w in ("alpha", "beta", "gamma"):
            pg.evaluate(f"() => window.zaelar.show('{_w}')")
            pg.wait_for_timeout(500)
        rr = rects(pg)
        geo = pg.evaluate("""() => [...document.querySelectorAll('.hb-win')].map(c => ({
          id: c.dataset.wid, left: parseInt(c.style.left)||0, top: parseInt(c.style.top)||0 }))""")
        check("every card sits on the 5px grid",
              all(g["left"] % 5 == 0 and g["top"] % 5 == 0 for g in geo), json.dumps(geo))

        # Vertical stacking: cards opened one after another share a column and go DOWN it, instead of marching
        # across the top of the screen. Measured on the x of each card, not on a pixel-perfect layout.
        # The property, not a pixel layout: two cards opened one after another share a COLUMN and the second
        # sits BELOW the first. Row-major placement produces the mirror image of this (same y, different x), so
        # the check distinguishes the two orders instead of describing one screen.
        col = sorted(rr.values(), key=lambda v: (round(v["x"]), round(v["y"])))
        stacked = any(abs(a["x"] - b_["x"]) <= 1 and b_["y"] > a["y"] + 10
                      for i, a in enumerate(col) for b_ in col[i + 1:])
        check("cards stack VERTICALLY (a later card goes UNDER an earlier one, same column)",
              stacked, json.dumps({k: (round(v["x"]), round(v["y"])) for k, v in rr.items()}))

        # THE bug: a widget that renders far bigger than its reserved tile must still be WHOLLY on screen.
        pg.evaluate("() => window.zaelar.show('huge')")
        pg.wait_for_timeout(900)
        big = pg.evaluate("""() => { const c=[...document.querySelectorAll('.hb-win')]
            .find(x=>x.dataset.wid==='huge'); if(!c) return null;
            const r=c.getBoundingClientRect();
            return {left:Math.round(r.left), top:Math.round(r.top), right:Math.round(r.right),
                    bottom:Math.round(r.bottom), vw:innerWidth, vh:innerHeight,
                    z:parseInt(c.style.zIndex)||0}; }""")
        # It must have GROWN past the reserved tile first — a check that a small card fits on screen guards
        # nothing, and that is exactly how the first version of this passed while the fix was disarmed.
        check("the oversized widget really did grow past its reserved tile",
              bool(big) and (big["right"] - big["left"] > 400 or big["bottom"] - big["top"] > 340),
              json.dumps(big))
        check("a card that renders BIGGER than its tile is still WHOLLY on screen",
              bool(big) and big["left"] >= 0 and big["top"] >= 0
              and big["right"] <= big["vw"] and big["bottom"] <= big["vh"],
              json.dumps(big))
        # And when there is no room for it, it comes to the FRONT — a card you cannot see is a card you cannot move.
        others = [v["z"] for k, v in rects(pg).items() if k != "huge"]
        check("the card with no room for it opens ON TOP (visible, therefore movable)",
              bool(big) and (not others or big["z"] >= max(others)),
              json.dumps({"huge_z": big and big["z"], "others": others}))

        # ── V2-552: la barra — iconos arriba, los cuatro controles abajo ────────────────────────────────────
        # «En la barra izquierda vas a dejar toda la parte superior para mostrar los iconos de los widgets que
        # están abiertos, y debajo es donde van los botones de control del frontend.»
        bar = pg.evaluate("""() => {
          const el = document.querySelector('#wrail'); if (!el) return null;
          const chips = el.querySelector('.wr-chips'), tools = el.querySelector('.wr-tools');
          const r = n => { const b = n.getBoundingClientRect(); return {t: Math.round(b.top), b: Math.round(b.bottom)}; };
          return {
            chips: chips ? r(chips) : null, tools: tools ? r(tools) : null,
            buttons: tools ? [...tools.children].map(b => b.className) : [],
          };
        }""")
        check("the open-widget icons occupy the UPPER part and the controls sit BELOW them",
              bool(bar) and bar["chips"] and bar["tools"] and bar["chips"]["t"] <= bar["tools"]["t"],
              json.dumps(bar))

        # ▦ REPACK vs ⤢ FIT are different gestures: the first must NOT resize. It used to be one button that
        # tiled everything into equal cells, so «optimiza los huecos» flattened a sheet made large on purpose.
        pg.evaluate("""() => { const c = [...document.querySelectorAll('.hb-win')]
            .find(x => x.dataset.wid === 'gamma');
          c.style.maxWidth='none'; c.style.maxHeight='none'; c.style.width='620px'; c.style.height='480px'; }""")
        pg.wait_for_timeout(250)
        before = pg.evaluate("""() => { const c = [...document.querySelectorAll('.hb-win')]
            .find(x => x.dataset.wid === 'gamma'); const r = c.getBoundingClientRect();
          return {w: Math.round(r.width), h: Math.round(r.height)}; }""")
        pg.evaluate("() => document.querySelector('#wrail .wr-compact').click()")
        pg.wait_for_timeout(400)
        after = pg.evaluate("""() => { const c = [...document.querySelectorAll('.hb-win')]
            .find(x => x.dataset.wid === 'gamma'); const r = c.getBoundingClientRect();
          return {w: Math.round(r.width), h: Math.round(r.height)}; }""")
        check("▦ repack KEEPS the size the operator gave a card",
              abs(before["w"] - after["w"]) <= 2 and abs(before["h"] - after["h"]) <= 2,
              json.dumps({"before": before, "after": after}))
        rr = rects(pg)
        # What repack MUST guarantee is that every card stays WHOLE and on the canvas. NOT that nothing
        # overlaps: with a card occupying 1178x656 of a 1280x800 viewport there is no arrangement of four cards
        # without overlap, and the whole point of this button is that it does NOT resize to make room — that is
        # the other button's job. Asking for no-overlap here would be asking for the impossible, and the honest
        # outcome when things do not fit is «as little overlap as possible, all of it visible».
        check("…and still leaves every card WHOLE and on the canvas",
              all(v["x"] >= 0 and v["y"] >= 0 and v["x"] + v["w"] <= W and v["y"] + v["h"] <= H
                  for v in rr.values()),
              json.dumps(rr))
        # …whereas ⤢ fit-on-screen is the one allowed to shrink it.
        pg.evaluate("() => document.querySelector('#wrail .wr-fitall').click()")
        pg.wait_for_timeout(400)
        fitted = pg.evaluate("""() => { const c = [...document.querySelectorAll('.hb-win')]
            .find(x => x.dataset.wid === 'gamma'); const r = c.getBoundingClientRect();
          return {w: Math.round(r.width), h: Math.round(r.height)}; }""")
        check("⤢ fit-on-screen IS the one that resizes",
              fitted["w"] != after["w"] or fitted["h"] != after["h"],
              json.dumps({"repacked": after, "fitted": fitted}))

        # ── V2-583: a VOICE fullscreen order actually changes the screen ────────────────────────────────────
        # The youtube card declares `fullscreen:"native"`, and a voice order arrives over SSE with NO user
        # activation — the browser rejects requestFullscreen() ASYNCHRONOUSLY, so the old code returned true,
        # nothing moved, and no error surfaced anywhere (measured live: «Maximiza el video», twice, session
        # 0e3a42d6). page.evaluate carries no user activation either, which is exactly the context to test.
        # ⚠️ MEASUREMENT TRAP, found by this very test's first run: Playwright's evaluate goes over CDP with
        # userGesture:true, so the automation channel GRANTS the activation a real voice order never has —
        # requestFullscreen() succeeded here while failing in the operator's browser, which is also why no
        # Playwright test ever saw the live bug. The real no-gesture context is unreachable from this harness,
        # so BOTH refusal signals are simulated explicitly instead.
        pg.evaluate("() => window.zaelar.close()")
        pg.wait_for_timeout(400)
        pg.evaluate("() => window.zaelar.show('video')")
        pg.wait_for_timeout(500)
        vbefore = pg.evaluate("""() => { const c=[...document.querySelectorAll('.hb-win')]
            .find(x=>x.dataset.wid==='video'); const r=c.getBoundingClientRect();
          return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; }""")
        # (a) the modern signal: navigator.userActivation says there is no gesture → straight to maximize.
        pg.evaluate("""() => { Object.defineProperty(navigator, 'userActivation',
            {value: {isActive: false}, configurable: true});
          window.zaelar.fullscreen('video'); }""")
        pg.wait_for_timeout(400)
        vfull = pg.evaluate("""() => { const c=[...document.querySelectorAll('.hb-win')]
            .find(x=>x.dataset.wid==='video'); const r=c.getBoundingClientRect();
          return {w:Math.round(r.width), h:Math.round(r.height),
                  nativeEngaged: document.fullscreenElement === c}; }""")
        check("a gesture-less fullscreen order MAXIMIZES the native-fullscreen card on screen",
              vfull["w"] > W * 0.7 and vfull["h"] > H * 0.6 and not vfull["nativeEngaged"],
              json.dumps({"before": vbefore, "after": vfull}))
        # And it stays a TOGGLE: the same order again puts the card back where and how it was.
        pg.evaluate("() => window.zaelar.fullscreen('video')")
        pg.wait_for_timeout(400)
        vback = pg.evaluate("""() => { const c=[...document.querySelectorAll('.hb-win')]
            .find(x=>x.dataset.wid==='video'); const r=c.getBoundingClientRect();
          return {x:Math.round(r.x), y:Math.round(r.y), w:Math.round(r.width), h:Math.round(r.height)}; }""")
        check("the second order RESTORES the card's previous geometry (toggle, V2-551 restore intact)",
              abs(vback["w"] - vbefore["w"]) <= 2 and abs(vback["h"] - vbefore["h"]) <= 2
              and abs(vback["x"] - vbefore["x"]) <= 2 and abs(vback["y"] - vbefore["y"]) <= 2,
              json.dumps({"before": vbefore, "back": vback}))
        # (b) an older engine: no userActivation API at all, and the browser's gate shows up ONLY as an
        # asynchronously rejected promise — the exact shape the old code swallowed. The fallback must still
        # land on maximize, and the rejection must not surface as a page error.
        pg.evaluate("""() => { Object.defineProperty(navigator, 'userActivation',
            {value: undefined, configurable: true});
          const c=[...document.querySelectorAll('.hb-win')].find(x=>x.dataset.wid==='video');
          c.requestFullscreen = () => Promise.reject(new TypeError('API can only be initiated by a user gesture'));
          window.zaelar.fullscreen('video'); }""")
        pg.wait_for_timeout(500)
        vrej = pg.evaluate("""() => { const c=[...document.querySelectorAll('.hb-win')]
            .find(x=>x.dataset.wid==='video'); const r=c.getBoundingClientRect();
          return {w:Math.round(r.width), h:Math.round(r.height),
                  nativeEngaged: document.fullscreenElement === c}; }""")
        check("when the browser's gate only shows up as a REJECTED promise, the card still maximizes",
              vrej["w"] > W * 0.7 and vrej["h"] > H * 0.6 and not vrej["nativeEngaged"],
              json.dumps(vrej))

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
