"""Render the feedback panel in Chromium and MEASURE that a refused send is VISIBLE (V2-256, node 4.34).

WHY THIS IS A SEPARATE TEST FROM 4.33: the deterministic node proves the decision is right and that
both surfaces call it. It cannot tell you that the sentence reaches a human's eyes. On 2026-08-21 the
thing that shipped was precisely a node that was never appended — `justSent() ? h(…) : null` read as
a child, evaluated once while the tree was built — and no error appeared anywhere. A source-level
test counted the branch and would have been satisfied. Everything asserted below needs a browser:
that the element is CONNECTED, that its box has area, and that it carries translated text rather than
the raw i18n key (a key is truthy, so `t()` returning "feedback.sendError" passes any source check).

SELF-CONTAINED AND NON-DESTRUCTIVE. It starts its own preview server (server.pages + /static +
server.i18n_api) on a free port — never the operator's engine, which would post real feedback — and
the failing POST is faked at the network layer with Playwright routing, so nothing leaves the machine.
That fake is the exact body a live engine returned:

    {"ok": false, "error": "send_failed", "status": 401}

Run:  ./.venv/bin/python tests/browser/e2e/feedback/render_send_failure.py
"""
import json
import os
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

# engine/tests/browser/e2e/feedback/render_send_failure.py -> five levels up is engine/
ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
W, H = 1280, 900
MIN_AREA = 400          # px² — below this there is a node in the DOM and nothing on the screen

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

# What a person can actually read: connected to the document, laid out with area, non-empty text that
# is not just the i18n key coming back at us.
MEASURE = """(sel) => {
  const e = document.querySelector(sel);
  if (!e) return { found: false };
  const r = e.getBoundingClientRect();
  const cs = getComputedStyle(e);
  const text = (e.textContent || '').trim();
  return { found: true, connected: e.isConnected, area: Math.round(r.width * r.height),
           visible: cs.visibility !== 'hidden' && cs.display !== 'none' && Number(cs.opacity) > 0.05,
           text };
}"""

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
        return run(f"http://127.0.0.1:{port}/")
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
        ctx = b.new_context(viewport={"width": W, "height": H})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)))

        # The refusal, reproduced at the wire. GET fails the same way, which is what makes
        # the Sent tab claim "nothing sent yet" for a list it never managed to read.
        def refuse(route):
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps({"ok": False, "error": "send_failed", "status": 401, "items": []}))
        pg.route("**/api/feedback", refuse)

        pg.goto(url, wait_until="domcontentloaded")
        pg.wait_for_timeout(2500)     # let the i18n bundle land: a label read too early freezes on its key
        pg.evaluate(LIFT_VEIL)
        pg.wait_for_timeout(300)

        launcher = pg.query_selector(".fw-launcher")
        check("the feedback launcher is on the page", launcher is not None)
        if not launcher:
            b.close()
            return 1
        launcher.click()
        pg.wait_for_timeout(400)

        pg.fill(".fw-textarea", "probe: the send is refused upstream")
        pg.click(".fw-send")
        pg.wait_for_timeout(900)

        err = pg.evaluate(MEASURE, ".fw-error")
        check("a refused send paints an error line", bool(err.get("found")),
              "nothing was rendered — this is exactly the state the operator hit")
        if err.get("found"):
            check("the error line is connected to the document", bool(err.get("connected")))
            check("the error line has area", err.get("area", 0) >= MIN_AREA,
                  f"area={err.get('area')}px² — a node with no box is not a message")
            check("the error line is not transparent/hidden", bool(err.get("visible")))
            txt = err.get("text") or ""
            check("the error line carries translated text, not the i18n key",
                  bool(txt) and "feedback." not in txt, f"text={txt!r}")
            check("the error names the fact the transport already knew", "401" in txt,
                  f"text={txt!r} — the status was in hand and got dropped")

        # The message must survive the failure: a retry cannot cost the user their text.
        kept = pg.eval_on_selector(".fw-textarea", "e => e.value")
        check("the message stays in the box after a failure", "probe:" in kept, f"value={kept!r}")

        # And the Sent tab must not claim the user has sent nothing when it simply could not look.
        pg.click(".fw-tabs .fw-tab:nth-child(2)")
        pg.wait_for_timeout(700)
        empty = pg.evaluate(MEASURE, ".fw-sent .fw-empty")
        check("the Sent tab says something", bool(empty.get("found")))
        if empty.get("found"):
            txt = empty.get("text") or ""
            # Compared against the REAL string the reachable-but-empty case would show, read from the
            # bundle the page actually loaded — a hand-copied sentence here would drift and stop testing.
            empty_state = pg.evaluate("""() => {
              try {
                const lang = localStorage.getItem('hb_lang') || 'en';
                const b = JSON.parse(localStorage.getItem('hb_i18n_' + lang) || '{}');
                return b['feedback.emptyState'] || null;
              } catch (_) { return null; }
            }""")
            check("an unreachable list is NOT reported as 'nothing sent yet'",
                  "feedback." not in txt and txt.strip() != "" and (not empty_state or txt.strip() != empty_state),
                  f"text={txt!r} vs feedback.emptyState={empty_state!r}")
            cls = pg.eval_on_selector(".fw-sent .fw-empty", "e => e.className")
            check("…and it is marked as unreachable, not merely empty", "fw-empty-unreachable" in cls,
                  f"class={cls!r}")

        # --- and now the OTHER half of the same bug ------------------------------------------------
        # The thank-you was unreachable for two independent reasons: the bare ternary that appended
        # nothing, AND its home inside `.fw-new`, which a successful send hides by switching to the
        # Sent tab. Fixing only one of the two would still ship a form that confirms nothing, so the
        # success path is measured here rather than assumed from the failure path working.
        pg.unroute("**/api/feedback")
        pg.route("**/api/feedback", lambda r: r.fulfill(
            status=200, content_type="application/json",
            body=json.dumps({"ok": True, "id": "probe", "status": "received", "items": []})))
        pg.click(".fw-tabs .fw-tab:nth-child(1)")
        pg.wait_for_timeout(300)
        pg.fill(".fw-textarea", "probe: this one is accepted")
        pg.click(".fw-send")
        pg.wait_for_timeout(900)

        thanks = pg.evaluate(MEASURE, ".fw-thanks")
        check("an accepted send paints a thank-you", bool(thanks.get("found")),
              "the success state was as invisible as the failure one")
        if thanks.get("found"):
            check("the thank-you is connected", bool(thanks.get("connected")))
            check("the thank-you has area", thanks.get("area", 0) >= MIN_AREA,
                  f"area={thanks.get('area')}px² — it lives in the tab a successful send navigates AWAY from")
            check("the thank-you is not transparent/hidden", bool(thanks.get("visible")))
            ttxt = thanks.get("text") or ""
            check("the thank-you is translated, not the i18n key", bool(ttxt) and "feedback." not in ttxt,
                  f"text={ttxt!r}")
        gone = pg.evaluate(MEASURE, ".fw-error")
        check("the stale error line is cleared once a send succeeds", not gone.get("found"),
              f"still showing {gone.get('text')!r}")
        cleared = pg.eval_on_selector(".fw-textarea", "e => e.value")
        check("an accepted send empties the box", cleared.strip() == "", f"value={cleared!r}")

        check("no page errors", not errors, " | ".join(errors[:4]))
        b.close()

    print(("\nFAILED: " + ", ".join(fails)) if fails else "\nall checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
