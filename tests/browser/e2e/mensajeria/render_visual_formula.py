"""RENDER check — the messaging widget's visual formula (V2-521).

The header shows EVERY channel (connected bright, unconnected dimmed); a dimmed icon opens the
connectors panel with its form ready — the same door the voice takes; a bright icon applies the
platform lens (underline = visible state, not memory) and a second click clears it. Tolerant of the
live engine's connection state: the dimmed/bright halves each run only when such an icon exists.
"""
import os, sys
from playwright.sync_api import sync_playwright

BASE = os.getenv("ZAELAR_URL", "http://127.0.0.1:43917")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out")
os.makedirs(OUT, exist_ok=True)
problems = []
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True)
    pg = b.new_page(viewport={"width": 1280, "height": 900})
    pg.goto(BASE + "/", wait_until="domcontentloaded")
    pg.wait_for_timeout(2500)
    pg.evaluate("window.__zaelarDesktop.show('mensajeria')")
    pg.wait_for_selector(".hb-msg", timeout=10000); pg.wait_for_timeout(800)

    # 1) the header shows ALL channels — connected bright, unconnected dimmed
    icons = pg.eval_on_selector_all(".hb-msg .dots .picon",
        "els => els.map(e => ({on: e.classList.contains('on'), title: e.title}))")
    print("header icons:", icons)
    if len(icons) != 3:
        problems.append(f"expected 3 channel icons, got {len(icons)}")
    dimmed = [i for i in icons if not i["on"]]
    pg.screenshot(path=f"{OUT}/vf_1_header.png")

    # 2) clicking a DIMMED icon opens the connectors panel with its form — the same door the voice takes
    if dimmed:
        pg.click(".hb-msg .dots .picon:not(.on)")
        pg.wait_for_timeout(500)
        if not pg.query_selector(".hb-msg .chanhead"):
            problems.append("clicking a dimmed icon did not open the connectors panel")
        if not pg.query_selector(".hb-msg .expand"):
            problems.append("the dimmed icon's form was not expanded")
        pg.screenshot(path=f"{OUT}/vf_2_connect_from_header.png")
        pg.click(".hb-msg .back")           # ← Messages
        pg.wait_for_timeout(400)

    # 3) clicking a BRIGHT icon applies the lens (underline marks it), clicking again removes it
    if any(i["on"] for i in icons):
        pg.click(".hb-msg .dots .picon.on")
        pg.wait_for_timeout(400)
        if not pg.query_selector(".hb-msg .picon.filt"):
            problems.append("the platform lens did not mark the active icon")
        pg.screenshot(path=f"{OUT}/vf_3_lens.png")
        pg.click(".hb-msg .dots .picon.filt")
        pg.wait_for_timeout(300)
        if pg.query_selector(".hb-msg .picon.filt"):
            problems.append("clicking the lensed icon again did not clear the lens")
    b.close()
for p in problems: print("FAIL:", p)
print("visual formula:", "OK" if not problems else "FAILED")
sys.exit(1 if problems else 0)
