"""RENDER check — the messaging widget's visual formula (V2-521, redesigned V2-570).

The header shows EVERY channel (connected bright, unconnected dimmed); a dimmed icon opens THAT
connector's own screen directly (breadcrumb + its wizard/status), the same door the voice takes and the
same door `connect_focus` takes — never the connector LIST. A bright icon applies the platform lens
(underline = visible state, not memory) and a second click clears it. Tolerant of the live engine's
connection state: the dimmed/bright halves each run only when such an icon exists.
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

    # 2) clicking a DIMMED icon enters THAT connector's own screen directly — never the list
    if dimmed:
        pg.click(".hb-msg .dots .picon:not(.on)")
        pg.wait_for_timeout(500)
        if not pg.query_selector(".hb-msg .crumb"):
            problems.append("clicking a dimmed icon did not enter the connector's own screen")
        if pg.query_selector(".hb-msg .chanhead"):
            problems.append("clicking a dimmed icon landed on the connector LIST instead of its own screen")
        if not (pg.query_selector(".hb-msg .wstep") or pg.query_selector(".hb-msg .linkcard")):
            problems.append("the dimmed icon's screen has no wizard step or status card")
        pg.screenshot(path=f"{OUT}/vf_2_connect_from_header.png")
        pg.click(".hb-msg .crumb .back")    # ‹ Conectores -> the list
        pg.wait_for_timeout(300)
        back_to_msgs = pg.query_selector(".hb-msg .chanhead .back")
        if back_to_msgs:
            back_to_msgs.click()            # ← Mensajes, only shown once something is connected
            pg.wait_for_timeout(300)

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
