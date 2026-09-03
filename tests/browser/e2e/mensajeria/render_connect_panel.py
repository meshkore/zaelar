"""RENDER check — asking to connect a channel lands DIRECTLY on that connector's own screen (V2-520,
redesigned V2-570: two screens, list vs. a single connector's wizard).

The source-level tests in `tests/browser/unit/mensajeria/` prove the wiring was written; only this proves
it RUNS against the operator's real, live engine. Measured while building the fix: neutering the render
branch to `if(false && focus …)` left every source assertion green, because the string it greps for was
still in the file.

Drives the operator's real engine: calls the `open_connectors` data-op the brain would call, then looks at
the pixels — the breadcrumb naming the connector (not the connector LIST), and the email wizard's first
step showing the provider picker as an icon grid (Gmail / Outlook / …), never a `<select>`.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ZAELAR_URL", "http://127.0.0.1:43917")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    problems: list[str] = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(BASE + "/", wait_until="domcontentloaded")
        pg.wait_for_timeout(2500)
        pg.evaluate("window.__zaelarDesktop.show('mensajeria')")
        pg.wait_for_selector(".hb-msg", timeout=10000)
        pg.wait_for_timeout(800)

        # What the brain does for "connect my email": show the card + the declared data-op.
        pg.evaluate("""fetch('/widgets/mensajeria/action', {method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({action:'open_connectors', payload:{platform:'email'}})})""")
        pg.wait_for_timeout(2500)

        crumb = pg.query_selector(".hb-msg .crumb .cur")
        if not crumb or "email" not in (crumb.text_content() or "").lower():
            problems.append("connect_focus did not land on the Email connector's OWN screen")
        chanhead = pg.query_selector(".hb-msg .chanhead")
        if chanhead:
            problems.append("landed on the connector LIST instead of the Email wizard screen")

        grid = pg.query_selector(".hb-msg .igrid")
        if not grid:
            problems.append("the provider picker (step 1) did not render as an icon grid")
        else:
            box = grid.bounding_box()
            if not box or box["height"] < 40:
                problems.append(f"the icon grid is in the DOM but has no pixels: {box}")
            labels = [t.strip().lower() for t in pg.eval_on_selector_all(
                ".hb-msg .igrid .ilabel", "els => els.map(e => e.textContent)")]
            for want in ("gmail", "outlook"):
                if not any(want in lab for lab in labels):
                    problems.append(f"the provider picker does not offer {want}: {labels}")
        pg.screenshot(path=os.path.join(OUT, "connect_panel.png"))
        b.close()

    for p in problems:
        print("FAIL:", p)
    print("render_connect_panel:", "OK" if not problems else "FAILED")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
