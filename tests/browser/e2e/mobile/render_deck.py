"""Render the mobile DECK with several widgets open and MEASURE its navigation (2026-08-29 UX pass).

WHY THIS EXISTS: the deterministic node (4.18) can prove the pips' CSS names --dock-h — it cannot tell you
they are visible, and that is exactly how they shipped the first time: at bottom:6px, 100% hidden UNDER the
fixed dock, with every source-level test green. Everything below is something only a browser can answer:
where the pips actually sit, whether a tap on one changes the card, whether the switcher opens/jumps/closes,
whether a one-finger swipe on the header pages, and whether the producing badge follows the declared
runtime.active_when and not a widget-name list.

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
        pg.goto(url, wait_until="networkidle")
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
                   count: count && { text: count.textContent, tag: count.tagName,
                                     visible: !!count.offsetParent, h: cr.height } };
        }""")
        check("three cards open, the last one in front",
              deck["open"] == ["alpha", "beta", "gamma"] and deck["liveId"] == "gamma", json.dumps(deck["open"]))
        check("the fake widget really mounted (its module was imported and rendered)",
              deck["liveText"] and "W:Gamma view" in deck["liveText"], str(deck["liveText"])[:80])
        check("three pips, and they are buttons", len(deck["pips"]) == 3
              and all(x["tag"] == "BUTTON" for x in deck["pips"]), json.dumps(deck["pips"]))
        check("the pips are VISIBLE above the dock (the original ones were 100% under it)",
              deck["pips"] and all(x["bottom"] <= deck["dockTop"] + 1 for x in deck["pips"]),
              f"dockTop={deck['dockTop']}, pips={[round(x['bottom'], 1) for x in deck['pips']]}")
        check(f"each pip's hit box is at least {MIN_TAP}px",
              all(min(x["w"], x["h"]) >= MIN_TAP for x in deck["pips"]), json.dumps(deck["pips"]))
        check("the producing card's pip carries the badge (from active_when, index 1 = beta)",
              "prod" in deck["pips"][1]["cls"] and "prod" not in deck["pips"][0]["cls"]
              and "prod" not in deck["pips"][2]["cls"],
              json.dumps([x["cls"] for x in deck["pips"]]))
        check("the k/n chip is visible on the front card and is a button",
              deck["count"] and deck["count"]["visible"] and deck["count"]["tag"] == "BUTTON"
              and deck["count"]["text"] == "3/3", json.dumps(deck["count"]))

        # a tap on a pip JUMPS to its card
        pg.evaluate("() => document.querySelectorAll('.zm-pip')[0].click()")
        pg.wait_for_timeout(400)
        check("tapping the first pip brings the first card to front",
              pg.evaluate("() => document.querySelector('.zm-card.live').dataset.wid") == "alpha")

        # ONE-finger swipe on the HEADER pages (host chrome; the body's one finger still belongs to the widget)
        pg.evaluate("""() => {
          const head = document.querySelector('.zm-card.live .zm-head');
          const t = (type, x, y) => {
            const touch = new Touch({ identifier: 1, target: head, clientX: x, clientY: y });
            head.dispatchEvent(new TouchEvent(type, { touches: type === 'touchend' ? [] : [touch],
                                                      bubbles: true, cancelable: true }));
          };
          t('touchstart', 300, 40); t('touchmove', 230, 42); t('touchend', 230, 42);
        }""")
        pg.wait_for_timeout(400)
        check("a one-finger swipe LEFT on the header pages to the next card",
              pg.evaluate("() => document.querySelector('.zm-card.live').dataset.wid") == "beta")

        # ── the switcher: open from the chip, rows mirror the deck, jump, close one, close all ───────────────
        pg.evaluate("() => document.querySelector('.zm-card.live .zm-count').click()")
        pg.wait_for_timeout(350)
        sw = pg.evaluate("""() => {
          const ov = document.querySelector('.zm-switch');
          const dock = document.querySelector('.zm-dock').getBoundingClientRect();
          const ovr = ov.getBoundingClientRect();
          const rows = [...ov.querySelectorAll('.zm-swrow')].map(e => ({
            cls: e.className, name: e.querySelector('.zm-swgo span').textContent,
            prod: !!e.querySelector('.zm-swprod'),
            xh: e.querySelector('.zm-swx').getBoundingClientRect().height }));
          return { open: ov.classList.contains('open'), rows, ovBottom: ovr.y + ovr.height, dockTop: dock.y };
        }""")
        check("the chip opens the switcher", sw["open"])
        check("the switcher stops ABOVE the dock (mic and ⏻ stay reachable)",
              sw["ovBottom"] <= sw["dockTop"] + 1, json.dumps({k: sw[k] for k in ("ovBottom", "dockTop")}))
        check("one row per card, named by the LIVE title",
              [r["name"] for r in sw["rows"]] == ["Alpha card", "Beta tunes", "Gamma view"],
              json.dumps([r["name"] for r in sw["rows"]]))
        check("the current card's row is marked", "cur" in sw["rows"][1]["cls"], json.dumps(sw["rows"]))
        check("only the producing row carries the ♪ badge",
              [r["prod"] for r in sw["rows"]] == [False, True, False], json.dumps(sw["rows"]))
        check("every row close button is a 44px tap target",
              all(r["xh"] >= 44 for r in sw["rows"]), json.dumps([r["xh"] for r in sw["rows"]]))

        pg.evaluate("() => document.querySelectorAll('.zm-swrow .zm-swgo')[0].click()")
        pg.wait_for_timeout(400)
        check("tapping a row jumps to that card and dismisses the switcher",
              pg.evaluate("""() => document.querySelector('.zm-card.live').dataset.wid === 'alpha'
                               && !document.querySelector('.zm-switch').classList.contains('open')"""))

        pg.evaluate("() => { document.querySelector('.zm-card.live .zm-count').click(); }")
        pg.wait_for_timeout(300)
        pg.evaluate("() => document.querySelectorAll('.zm-swrow .zm-swx')[2].click()")
        pg.wait_for_timeout(500)
        after_close = pg.evaluate("""() => ({ open: window.__zaelarDeck.list(),
          rows: [...document.querySelectorAll('.zm-swrow')].length,
          swOpen: document.querySelector('.zm-switch').classList.contains('open') })""")
        check("closing a card from the switcher removes it and the list repaints in place",
              after_close["open"] == ["alpha", "beta"] and after_close["rows"] == 2 and after_close["swOpen"],
              json.dumps(after_close))

        pg.evaluate("() => document.querySelector('.zm-swall').click()")
        pg.wait_for_timeout(600)
        emptied = pg.evaluate("""() => ({ open: window.__zaelarDeck.list(),
          swOpen: document.querySelector('.zm-switch').classList.contains('open'),
          empty: !!document.querySelector('.zm-empty.on') })""")
        check("close-all empties the deck, dismisses the switcher and shows the resting state",
              emptied["open"] == [] and not emptied["swOpen"] and emptied["empty"], json.dumps(emptied))

        # ── PAGE 2: restore parity with the desktop (V2-351) ─────────────────────────────────────────────────
        pg2 = ctx.new_page()
        pg2.route(ROUTE_RE, make_router({"items": [], "live": ["results::live1", "navegador::t9"]}))
        pg2.add_init_script(
            "localStorage.setItem('zaelar_mobile_deck', JSON.stringify(['results','results::abc','navegador::t4']))")
        pg2.goto(url, wait_until="networkidle")
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
        pg3.goto(url, wait_until="networkidle")
        pg3.wait_for_timeout(2500)
        fresh = pg3.evaluate("() => window.__zaelarDeck.list()")
        check("a fresh install restores the account's open set from the server (a phone IS a new browser)",
              fresh == ["alpha"], json.dumps(fresh))

        b.close()

    print(f"\n{'ALL OK' if not fails else str(len(fails)) + ' FAILURE(S): ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
