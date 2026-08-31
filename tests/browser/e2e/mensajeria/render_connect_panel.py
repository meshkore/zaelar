"""RENDER check — asking to connect a channel lands ON the form (V2-520).

The source-level test in `tests/browser/unit/mensajeria/` proves the wiring was written; only this proves
it RUNS. Measured while building the fix: neutering the render branch to `if(false && focus …)` left every
source assertion green, because the string it greps for was still in the file.

Drives the operator's real engine: calls the `open_connectors` data-op the brain would call, then looks at
the pixels — the channels panel present, and the EMAIL form (with its provider picker: Gmail / Outlook /
other) expanded inside it.
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

        panel = pg.query_selector(".hb-msg .chanhead")
        if not panel:
            problems.append("the channels panel did not open")
        form = pg.query_selector(".hb-msg .linkcard")
        if not form:
            problems.append("the email form was not expanded")
        else:
            box = form.bounding_box()
            if not box or box["height"] < 80:
                problems.append(f"the form is in the DOM but has no pixels: {box}")
            options = [o.strip().lower() for o in pg.eval_on_selector_all(
                ".hb-msg .linkcard select option", "els => els.map(e => e.textContent)")]
            for want in ("gmail", "outlook"):
                if not any(want in o for o in options):
                    problems.append(f"the provider picker does not offer {want}: {options}")
        pg.screenshot(path=os.path.join(OUT, "connect_panel.png"))
        b.close()

    for p in problems:
        print("FAIL:", p)
    print("render_connect_panel:", "OK" if not problems else "FAILED")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
