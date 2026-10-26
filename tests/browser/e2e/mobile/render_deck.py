"""Render the mobile DECK with several widgets open and MEASURE its navigation (2026-08-29 UX pass).

WHY THIS EXISTS: the deterministic node (4.18) can prove the pips' CSS names --dock-h — it cannot tell you
they are visible, and that is exactly how they shipped the first time: at bottom:6px, 100% hidden UNDER the
fixed dock, with every source-level test green. Everything below is something only a browser can answer:
where the pips actually sit, whether a tap on one changes the card, whether the switcher opens/jumps/closes,
whether a one-finger swipe pages (anywhere, V2-815 — and NOT over a sideways scroller), whether the HOME shows
one tile per card and jumps, and whether the producing badge follows the declared runtime.active_when and not a
widget-name list.

SELF-CONTAINED: starts its own preview (server.pages + /static + i18n) and serves THREE FAKE WIDGETS through
Playwright route interception — catalog, data, manifest and the widget.js module itself — so no backend and
no real widget is touched. The fakes exist so the deck has cards to page through; their content is one line.

Run:  ./.venv/bin/python tests/browser/e2e/mobile/render_deck.py
"""
import json
import os
import re
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
W, H = 390, 844
MIN_TAP = 24            # a pip is a small control by design; 26px is its declared hit box

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

WIDGET_JS = 'export function render(el, data){ el.className = "fake-w"; el.textContent = "W:" + ((data && data.title) || "?"); }'

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


# ── the fake widget backend, served by route interception ─────────────────────────────────────────────────────
DATA = {
    "alpha": {"title": "Alpha card"},
    # beta DECLARES production (runtime.active_when) and its data says it is playing — the badge must follow
    # this, the same contract widgets/producers.py evaluates, never a youtube/musica name list.
    "beta": {"title": "Beta tunes", "playing": True},
    "gamma": {"title": "Gamma view"},
    "results": {"title": "Sheet"},
    "navegador": {"title": "Nav"},
}
MANIFESTS = {
    "beta": {"id": "beta", "runtime": {"output": "audio", "suspend": "pause",
                                       "produce": ["play"], "active_when": [{"playing": True}]}},
}
ROUTE_RE = re.compile(r"/(widgets(/.*)?|api/(canvas/.*|desktop/epoch|client-log))(\?.*)?$")


def make_router(layout):
    def route(r):
        url = r.request.url
        path = re.sub(r"^https?://[^/]+", "", url).split("?", 1)[0]
        def j(obj, status=200):
            r.fulfill(status=status, content_type="application/json", body=json.dumps(obj))
        if path == "/widgets":
            return j({"widgets": [{"id": w} for w in DATA]})
        if path == "/widgets/registry":
            return j({"registry": []})
        if path == "/api/desktop/epoch":
            return j({"epoch": ""})           # falsy epoch: the wipe branch stays out of the way
        if path == "/api/canvas/layout":
            return j(layout)
        if path in ("/api/canvas/state", "/api/client-log"):
            return j({"ok": True})
        m = re.match(r"^/widgets/([^/]+)/(data|manifest|widget\.js)$", path)
        if m:
            wid, kind = m.group(1), m.group(2)
            if kind == "widget.js":
                return r.fulfill(status=200, content_type="application/javascript", body=WIDGET_JS)
            if kind == "manifest":
                return j(MANIFESTS.get(wid, {"id": wid}))
            return j(DATA.get(wid, {"title": wid}))
        return j({"error": "unrouted " + path}, 404)
    return route


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

        # ── PAGE 1: three cards open → pips, switcher, header swipe, producing badge ─────────────────────────
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route(ROUTE_RE, make_router({"items": [], "live": []}))
        pg.goto(url, wait_until="domcontentloaded")
        pg.wait_for_timeout(2200)
        pg.evaluate(LIFT_VEIL)
        pg.evaluate("""async () => {
          await window.zaelar.show('alpha');
          await window.zaelar.show('beta');
          await window.zaelar.show('gamma');
        }""")
        pg.wait_for_timeout(900)          # manifest fetch + repaint for the producing badge

        check("no page errors", not errors, " | ".join(errors[:4]))

        deck = pg.evaluate("""() => {
          const dock = document.querySelector('.zm-dock').getBoundingClientRect();
          const pips = [...document.querySelectorAll('.zm-pip')].map(e => {
            const r = e.getBoundingClientRect();
            return { cls: e.className, tag: e.tagName, y: r.y, h: r.height, w: r.width,
                     bottom: r.y + r.height, label: e.getAttribute('aria-label') };
          });
          const live = document.querySelector('.zm-card.live');
          const count = live && live.querySelector('.zm-count');
          const cr = count && count.getBoundingClientRect();
          return { open: window.__zaelarDeck.list(), dockTop: dock.y, pips,
                   liveId: live && live.dataset.wid, liveText: live && live.textContent,
                   count: count && { text: count.textContent, tag: count.tagName, inButton: !!count.closest('button'),
                                     visible: !!count.offsetParent, h: cr.height } };
        }""")
        check("three cards open, the last one in front",
              deck["open"] == ["alpha", "beta", "gamma"] and deck["liveId"] == "gamma", json.dumps(deck["open"]))
        check("the fake widget really mounted (its module was imported and rendered)",
              deck["liveText"] and "W:Gamma view" in deck["liveText"], str(deck["liveText"])[:80])
        # THE HOME IS PAGE ZERO (V2-815): one pip for the home, then one per card.
        check("four pips — the home and three cards — and they are buttons", len(deck["pips"]) == 4
              and all(x["tag"] == "BUTTON" for x in deck["pips"]) and "home" in deck["pips"][0]["cls"],
              json.dumps(deck["pips"]))
        check("the pips are VISIBLE above the dock (the original ones were 100% under it)",
              deck["pips"] and all(x["bottom"] <= deck["dockTop"] + 1 for x in deck["pips"]),
              f"dockTop={deck['dockTop']}, pips={[round(x['bottom'], 1) for x in deck['pips']]}")
        check(f"each pip's hit box is at least {MIN_TAP}px",
              all(min(x["w"], x["h"]) >= MIN_TAP for x in deck["pips"]), json.dumps(deck["pips"]))
        check("the current card's pip is lit, the home's is not",
              "on" in deck["pips"][3]["cls"].split() and "on" not in deck["pips"][0]["cls"].split(),
              json.dumps([x["cls"] for x in deck["pips"]]))
        check("the producing card's pip carries the badge (from active_when, index 1 = beta → pip 2)",
              "prod" in deck["pips"][2]["cls"] and "prod" not in deck["pips"][1]["cls"]
              and "prod" not in deck["pips"][3]["cls"],
              json.dumps([x["cls"] for x in deck["pips"]]))
        check("the top bar says k/n under the name, inside a tappable title",
              deck["count"] and deck["count"]["visible"] and deck["count"]["text"] == "3/3"
              and deck["count"]["inButton"], json.dumps(deck["count"]))

        # THE TOP BAR: ⌂ · ‹ · name · › · ×, every control a 44px target, the ⌂ first.
        bar = pg.evaluate("""() => {
          const head = document.querySelector('.zm-card.live .zm-head');
          const btns = [...head.querySelectorAll('button')].filter(e => e.offsetParent !== null).map(e => {
            const r = e.getBoundingClientRect();
            return { cls: e.className, label: e.getAttribute('aria-label'), w: r.width, h: r.height, x: r.x,
                     disabled: e.disabled }; });
          return btns; }""")
        check("the bar holds ⌂ · ‹ · title · › · × in that order",
              [b["cls"].split()[-1] for b in bar] == ["zm-home-b", "zm-prev", "zm-ttl", "zm-next", "zm-x"],
              json.dumps([b["cls"] for b in bar]))
        check("every control in the bar is a 44px-tall target", all(b["h"] >= 44 for b in bar),
              json.dumps([(b["cls"], b["h"]) for b in bar]))
        check("on the last card › is disabled and ‹ is not",
              bar[3]["disabled"] and not bar[1]["disabled"], json.dumps(bar))

        # a tap on a pip JUMPS to its card
        pg.evaluate("() => document.querySelectorAll('.zm-pip')[1].click()")
        pg.wait_for_timeout(400)
        check("tapping the first card's pip brings the first card to front",
              pg.evaluate("() => document.querySelector('.zm-card.live').dataset.wid") == "alpha")

        # ONE-finger swipe, anywhere (V2-815): on the header…
        def swipe1(sel, x_from, x_to, y=40):
            pg.evaluate("""([sel, xa, xb, y]) => {
              const el = document.querySelector(sel);
              const t = (type, x) => {
                const touch = new Touch({ identifier: 1, target: el, clientX: x, clientY: y });
                el.dispatchEvent(new TouchEvent(type, { touches: type === 'touchend' ? [] : [touch],
                                                      bubbles: true, cancelable: true }));
              };
              t('touchstart', xa); t('touchmove', xb); t('touchend', xb);
            }""", [sel, x_from, x_to, y])
            pg.wait_for_timeout(400)
        live = lambda: pg.evaluate("() => document.querySelector('.zm-card.live') && document.querySelector('.zm-card.live').dataset.wid")
        swipe1('.zm-card.live .zm-head', 300, 230)
        check("a one-finger swipe LEFT on the header pages to the next card", live() == "beta")
        # …and on the widget's BODY, which used to belong to the widget alone
        swipe1('.zm-card.live .fake-w', 300, 200, 400)
        check("a one-finger swipe LEFT on the card's body pages to the next card", live() == "gamma")
        swipe1('.zm-card.live .fake-w', 100, 220, 400)
        check("a one-finger swipe RIGHT on the body pages back", live() == "beta")
        # A finger that commits to going DOWN first is the widget's: a diagonal drift later does not page.
        pg.evaluate("""() => {
          const el = document.querySelector('.zm-card.live .fake-w');
          const t = (type, x, y) => el.dispatchEvent(new TouchEvent(type, { touches: type === 'touchend' ? []
            : [new Touch({ identifier: 1, target: el, clientX: x, clientY: y })], bubbles: true, cancelable: true }));
          t('touchstart', 300, 300); t('touchmove', 298, 340); t('touchmove', 200, 420); t('touchend', 200, 420);
        }""")
        pg.wait_for_timeout(300)
        check("a finger that went down first (a scroll) never pages, whatever it does later", live() == "beta")
        # A swipe that starts on something that scrolls SIDEWAYS on its own (a tab strip) is that element's…
        pg.evaluate("""() => {
          const el = document.querySelector('.zm-card.live .fake-w');
          const strip = document.createElement('div'); strip.id = 'strip';
          strip.style.cssText = 'overflow-x:auto;white-space:nowrap;width:200px;height:40px';
          strip.innerHTML = '<span style="display:inline-block;width:900px">tabs</span>';
          el.appendChild(strip);
        }""")
        swipe1('#strip', 300, 200, 420)
        check("a one-finger swipe on a sideways scroller inside the card does NOT page", live() == "beta")
        # …unless it starts at the screen's EDGE, which always pages.
        swipe1('#strip', 6, 160, 420)
        check("a swipe from the screen's edge pages even over a sideways scroller", live() == "alpha")

        # TWO- AND THREE-FINGER PAGING ON THE BODY (V2-573, operator: «we can switch screens moving mobile screen
        # with 2 or 3 fingers, right and left»). Dispatched on the STAGE, which is where the deck listens in the
        # capture phase, and with the real touch COUNT: three was refused outright before this, and a three-finger
        # horizontal swipe is both iOS muscle memory and what a two-finger swipe becomes when a thumb rests on the
        # edge. Both counts are exercised in opposite directions so a fix that pages the wrong way is not green.
        def swipe(fingers, x_from, x_to):
            pg.evaluate("""([n, xa, xb]) => {
              const st = document.querySelector('#zm-stage');
              const mk = (x) => Array.from({ length: n }, (_, i) =>
                new Touch({ identifier: i + 1, target: st, clientX: x + i * 24, clientY: 400 }));
              const fire = (type, x) => st.dispatchEvent(new TouchEvent(type, {
                touches: type === 'touchend' ? [] : mk(x), bubbles: true, cancelable: true }));
              fire('touchstart', xa); fire('touchmove', xb); fire('touchend', xb);
            }""", [fingers, x_from, x_to])
            pg.wait_for_timeout(400)

        swipe(2, 300, 180)      # right-to-left → next
        check("a TWO-finger swipe left pages to the next card", live() == "beta")
        swipe(3, 120, 300)      # left-to-right → previous
        check("a THREE-finger swipe right pages back", live() == "alpha")

        # CARD CONTENT STARTS AT THE TOP, AND EVERY CARD IS THE SAME BOX (V2-573). Measured, not read from the
        # stylesheet: `margin-block:auto` used to centre anything shorter than the screen, so the check that
        # matters is where the content actually IS relative to the scroller, and that a short widget's box still
        # fills the card. A source-level assertion on the CSS cannot see either.
        geom = pg.evaluate("""() => {
          const sc = document.querySelector('.zm-card.live .zm-scroll');
          const kid = sc && sc.firstElementChild;
          if (!kid) return null;
          const s = sc.getBoundingClientRect(), k = kid.getBoundingClientRect();
          const dock = document.querySelector('.zm-dock').getBoundingClientRect();
          const card = document.querySelector('.zm-card.live').getBoundingClientRect();
          return { gap: Math.round(k.y - s.y), kidH: Math.round(k.height), scH: Math.round(s.height),
                   cardBottom: Math.round(card.bottom), dockTop: Math.round(dock.y) };
        }""")
        check("the widget starts at the TOP of the card, not floating in the middle",
              geom and geom["gap"] <= 2, json.dumps(geom))
        check("a short widget still fills the card's box",
              geom and geom["kidH"] >= geom["scH"] - 2, json.dumps(geom))
        check("the card ends exactly at the dock's top edge — nothing under the bar, no band wasted",
              geom and abs(geom["cardBottom"] - geom["dockTop"]) <= 1, json.dumps(geom))

        # ── THE HOME: the launcher of what is open (V2-815) ──────────────────────────────────────────────────
        # Swiping RIGHT from the first card lands on the home; so does ⌂ in the bar and the first pip.
        swipe1('.zm-card.live .fake-w', 100, 260, 400)
        home = pg.evaluate("""() => {
          const h = document.querySelector('.zm-home');
          const dock = document.querySelector('.zm-dock').getBoundingClientRect();
          const hr = h.getBoundingClientRect();
          const tiles = [...h.querySelectorAll('.zm-tile')].map(e => {
            const r = e.getBoundingClientRect();
            return { cls: e.className, name: e.querySelector('.zm-tn').textContent, prod: !!e.querySelector('.zm-tprod'),
                     mono: e.querySelector('.zm-tic').firstChild.textContent, h: r.height, w: r.width,
                     bg: getComputedStyle(e.querySelector('.zm-tic')).backgroundColor }; });
          const xs = [...h.querySelectorAll('.zm-tx')].map(e => { const r = e.getBoundingClientRect(); return Math.min(r.width, r.height); });
          const pips = [...document.querySelectorAll('.zm-pip')].map(e => e.className);
          return { live: h.classList.contains('live'), cardLive: !!document.querySelector('.zm-card.live'),
                   bottom: hr.bottom, dockTop: dock.y, tiles, xs, pips,
                   count: h.querySelector('.zm-count').textContent, all: !!h.querySelector('.zm-hall:not(.hide)') }; }""")
        check("a one-finger swipe right from the first card lands on the HOME, and no card is live",
              home["live"] and not home["cardLive"], json.dumps({k: home[k] for k in ("live", "cardLive")}))
        check("the home ends at the dock's top edge like a card", abs(home["bottom"] - home["dockTop"]) <= 1,
              json.dumps({k: home[k] for k in ("bottom", "dockTop")}))
        check("one tile per card, named by the LIVE title",
              [t["name"] for t in home["tiles"]] == ["Alpha card", "Beta tunes", "Gamma view"],
              json.dumps([t["name"] for t in home["tiles"]]))
        check("each tile wears the app's monogram on its own colour",
              [t["mono"] for t in home["tiles"]] == ["A", "B", "G"] and len({t["bg"] for t in home["tiles"]}) == 3,
              json.dumps([(t["mono"], t["bg"]) for t in home["tiles"]]))
        check("only the producing tile carries the ♪ badge",
              [t["prod"] for t in home["tiles"]] == [False, True, False], json.dumps(home["tiles"]))
        check("the home's pip is lit and it says how many are open",
              "on" in home["pips"][0].split() and home["count"].startswith("3"), json.dumps([home["pips"][0], home["count"]]))
        check("every tile and every tile × is a 44px target",
              all(t["h"] >= 44 for t in home["tiles"]) and all(x >= 40 for x in home["xs"]),
              json.dumps([t["h"] for t in home["tiles"]] + home["xs"]))

        pg.evaluate("() => document.querySelectorAll('.zm-tile')[1].click()")
        pg.wait_for_timeout(400)
        check("tapping a tile opens that card", live() == "beta")
        pg.evaluate("() => document.querySelector('.zm-card.live .zm-home-b').click()")
        pg.wait_for_timeout(400)
        check("⌂ in the bar goes home", pg.evaluate("() => document.querySelector('.zm-home').classList.contains('live')"))
        check("the tile of the card we came from is marked current",
              pg.evaluate("() => [...document.querySelectorAll('.zm-tile')].map(e => e.classList.contains('cur'))") == [False, True, False])

        pg.evaluate("() => document.querySelectorAll('.zm-tx')[2].click()")
        pg.wait_for_timeout(500)
        after_close = pg.evaluate("""() => ({ open: window.__zaelarDeck.list(),
          tiles: document.querySelectorAll('.zm-tile').length,
          home: document.querySelector('.zm-home').classList.contains('live') })""")
        check("closing a card from its tile removes it, the grid repaints in place, and we stay home",
              after_close["open"] == ["alpha", "beta"] and after_close["tiles"] == 2 and after_close["home"],
              json.dumps(after_close))

        # «minimise» from the engine (the canvas order the brain emits for «go home») lands on the home too
        pg.evaluate("() => { window.__zaelarDeck.show('alpha'); }")
        pg.wait_for_timeout(300)
        pg.evaluate("() => window.__zaelarDeck.shrink('alpha')")
        pg.wait_for_timeout(300)
        check("the engine's minimize order takes the phone to the home, the card still open",
              pg.evaluate("() => document.querySelector('.zm-home').classList.contains('live') && window.__zaelarDeck.list().length === 2"))

        pg.evaluate("() => document.querySelector('.zm-hall').click()")
        pg.wait_for_timeout(600)
        emptied = pg.evaluate("""() => ({ open: window.__zaelarDeck.list(),
          pips: document.querySelectorAll('.zm-pip').length,
          empty: !!document.querySelector('.zm-empty.on'),
          grid: getComputedStyle(document.querySelector('.zm-hgrid')).display })""")
        check("close-all empties the deck: no pips, the grid gone, the resting state on the home",
              emptied["open"] == [] and emptied["pips"] == 0 and emptied["empty"] and emptied["grid"] == "none",
              json.dumps(emptied))

        # ── PAGE 2: restore parity with the desktop (V2-351) ─────────────────────────────────────────────────
        pg2 = ctx.new_page()
        pg2.route(ROUTE_RE, make_router({"items": [], "live": ["results::live1", "navegador::t9"]}))
        pg2.add_init_script(
            "localStorage.setItem('zaelar_mobile_deck', JSON.stringify(['results','results::abc','navegador::t4']))")
        pg2.goto(url, wait_until="domcontentloaded")
        pg2.wait_for_timeout(2500)
        restored = pg2.evaluate("() => window.__zaelarDeck.list()")
        check("restore sweeps the base-card fossil (bare 'results' next to its own instance)",
              "results" not in restored and "results::abc" in restored, json.dumps(restored))
        check("restore brings back the errands LIVE on the server, even unsaved here",
              "results::live1" in restored and "navegador::t9" in restored, json.dumps(restored))
        check("a navegador instance with no live task behind it does not come back",
              "navegador::t4" not in restored, json.dumps(restored))

        # ── PAGE 3: a fresh browser (empty localStorage) falls back to the SERVER's desktop ──────────────────
        # Its OWN context: pages 1-2 share this origin's localStorage, so "fresh install" must not inherit the
        # deck page 2 just persisted — that leak produced a false FAIL on this very check the first time.
        ctx3 = b.new_context(viewport={"width": W, "height": H}, is_mobile=True, has_touch=True,
                             device_scale_factor=3)
        pg3 = ctx3.new_page()
        pg3.route(ROUTE_RE, make_router({"items": [{"id": "alpha", "q": ""}], "live": []}))
        pg3.goto(url, wait_until="domcontentloaded")
        pg3.wait_for_timeout(2500)
        fresh = pg3.evaluate("() => window.__zaelarDeck.list()")
        check("a fresh install restores the account's open set from the server (a phone IS a new browser)",
              fresh == ["alpha"], json.dumps(fresh))

        b.close()

    print(f"\n{'ALL OK' if not fails else str(len(fails)) + ' FAILURE(S): ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
