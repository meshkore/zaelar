"""A spoken turn the gate ruled DIRECTED is PAINTED on the chat wall (V2-738).

The operator, 2026-09-21 02:22, with a session behind him: *«no se transcribe el texto en el chat»*. The
engine's side of that session was blameless — every one of his eight turns emitted its `transcript` and its
`ambient` verdict, and every verdict said `directed: true`. So the words were lost on the CLIENT, between an
event that arrived and a `<div>` that never appeared.

WHY THIS TEST DID NOT EXIST, WHICH IS THE POINT. `attention_hold.js` is covered thoroughly — node 4.x drives
the real module and proves a directed turn is DELIVERED. But «delivered» there means «the deliver callback
ran», and the callback is a test double. Nothing measured the rest of the chain: the callback calls
`store.pushChat`, which writes a signal, which an effect in `ChatWall.js` reads to rebuild `listEl` by hand
with `replaceChildren`. Four seams, none of them exercised together, each able to fail in silence — which is
the shape of every defect this file has found since (a test that builds the handle by hand proves the
MAPPING, never the WIRING).

So this renders the REAL page, drives the two seams `sse.js` itself calls when those two events arrive, and
then reads the DOM. Nothing is stubbed but the network the page fetches its own state from.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

#: What he actually said, and what the gate actually answered, taken from session c1ba9d86 line by line.
HIS_TURNS = [
    "Te he dicho que abras el widget de vídeo.",
    "No me vayas.",
    "Es que no me oyes.",
    "¿Y por qué no se transcribe en el chat lo que hablamos?",
]

READ = """() => {
  const list = document.querySelector('.cw-list');
  return {
    exists: !!list,
    bubbles: [...document.querySelectorAll('.cw-list .cw-msg')].map(e => ({
      cls: e.className, text: (e.textContent || '').trim() })),
  };
}"""


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


@pytest.fixture(scope="module")
def run():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    port = _free_port()
    proc = subprocess.Popen([sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)],
                            cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


@pytest.fixture(scope="module")
def seen(run):
    """One browser. His four turns go in through the same two doors `sse.js` uses, in the same order and
    with the same verdicts the engine recorded; then the wall is read."""
    from playwright.sync_api import sync_playwright
    out = {"errors": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
        pg.on("pageerror", lambda e: out["errors"].append(str(e)))
        pg.goto(run, wait_until="domcontentloaded")
        pg.wait_for_timeout(2200)
        pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
        # The wall has to be OPEN and on Chat — a panel whose CSS hides it would let every assertion below
        # pass on nodes nobody can see (V2-690: a computed style does not prove something is painted).
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2');
          s.setChatMsgs([]); s.setChatTab('chat'); s.setChatOpen(true);
          s.setAttentionMode('smart');            // there IS a gate: every turn waits for its verdict
        }""")
        pg.wait_for_timeout(500)
        out["before"] = pg.evaluate(READ)

        # …and in they go, transcript first and verdict second, which is the order they arrive in.
        pg.evaluate("""async (turns) => {
          const sse = await import('/static/app/services/sse.js?v=2');
          for (const text of turns) {
            sse.holdSpokenTurn(window.__zaelarDesktop, text, true);
            sse.settleHeldTurns(window.__zaelarDesktop, "", true);   // the engine sends no text with it
          }
        }""", HIS_TURNS)
        pg.wait_for_timeout(600)
        out["directed"] = pg.evaluate(READ)

        # The other half of the same gate, and the one it exists for: the room's conversation.
        pg.evaluate("""async () => {
          const sse = await import('/static/app/services/sse.js?v=2');
          sse.holdSpokenTurn(window.__zaelarDesktop, "pues nada, y el tío se fue", true);
          sse.settleHeldTurns(window.__zaelarDesktop, "pues nada, y el tío se fue", false);
        }""")
        pg.wait_for_timeout(400)
        out["ambient"] = pg.evaluate(READ)

        # And what zaelar itself said comes back through its own door.
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2');
          s.pushAgentChat("Sí, ahora te oigo perfectamente, Ricardo.");
        }""")
        pg.wait_for_timeout(400)
        out["agent"] = pg.evaluate(READ)
        b.close()
    return out


def test_the_page_has_no_errors(seen):
    assert seen["errors"] == [], seen["errors"]


def test_the_wall_is_there_and_starts_empty(seen):
    assert seen["before"]["exists"], "there is no .cw-list to paint into"
    assert seen["before"]["bubbles"] == [], seen["before"]["bubbles"]


def test_every_directed_turn_is_PAINTED_in_the_order_he_said_it(seen):
    """The whole point. Not «pushChat was called» — the bubbles exist, in the DOM, with his words in them."""
    texts = [b["text"] for b in seen["directed"]["bubbles"]]
    assert texts == HIS_TURNS, (
        f"his session had four directed turns and the wall shows {len(texts)}: {texts}")
    for b in seen["directed"]["bubbles"]:
        assert "you" in b["cls"], f"a turn HE said must be styled as his: {b}"


def test_what_the_room_said_never_reaches_the_wall(seen):
    texts = [b["text"] for b in seen["ambient"]["bubbles"]]
    assert texts == HIS_TURNS, f"an ambient turn was painted anyway: {texts}"


def test_the_agents_reply_lands_as_the_agent(seen):
    bubbles = seen["agent"]["bubbles"]
    assert len(bubbles) == len(HIS_TURNS) + 1, [b["text"] for b in bubbles]
    assert "agent" in bubbles[-1]["cls"], bubbles[-1]
    assert "te oigo perfectamente" in bubbles[-1]["text"], bubbles[-1]
