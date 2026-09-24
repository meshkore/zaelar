"""The wall paints what he is saying WHILE he says it (V2-743).

The operator, 2026-09-21: *«la actualización de esta columna de chat va bastante lenta, desde que hablo
hasta que se escriben las cosas ahí, además de perderse palabras por el camino»*.

Measured on that session (bcd4aba1), from his first VAD edge to the line appearing on the wall:

    median 3.45 s   ·   p90 10.1 s   ·   worst 19.0 s

The chain is correct and the sum of it is the delay: a spoken turn is HELD by `attention_hold` until the
gate's verdict arrives (V2-647), the verdict waits for the turn gate, the turn gate waits for the
endpointer, and the endpointer waits for him to stop talking — with a ceiling this repo had raised to 3.0 s
the day before (V2-742), which made the wait longer, not shorter, and is the half of that change nobody had
looked at from the chat's side.

So the wall now carries ONE provisional line fed by the live interim transcript. What this file pins is the
shape of it, because every part of the shape is load-bearing:

  · it appears WITHOUT a verdict — it is a caption of the open microphone, not something he said;
  · it is marked as provisional (`cw-live`), so it never reads as recorded history;
  · it is REPLACED by the real bubble when the verdict releases the turn — one line, not two;
  · it is REMOVED when the verdict discards the turn, which is what keeps V2-647 intact: the room's
    conversation must still leave no trace on his wall, and a caption left behind would be that defect
    coming back through a new door;
  · and it drives NOTHING — the canvas fast-path stays behind the verdict (V2-664).

Sibling of node 4.197, and built the same way and for the same reason: it renders the REAL page and drives
the seams `sse.js` itself calls, because a double of `deliver` proves the mapping and never the wiring.
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

#: The partials of one of his real sentences, as Deepgram delivered them.
PARTIALS = ["¿Por qué", "¿Por qué no", "¿Por qué no transcribes", "¿Por qué no transcribes el audio"]
FINAL = "¿Por qué no transcribes el audio que estoy dictando?"

# `painted` is not decoration: it is the difference between a node that exists and a node he can SEE.
# Its own disarm hid the caption with `display:none` and every `textContent` assertion stayed green
# (V2-690: a computed style does not prove something is painted).
READ = """() => {
  const painted = e => { const r = e.getBoundingClientRect();
                         return !!e.offsetParent && r.width > 0 && r.height > 0; };
  return {
    bubbles: [...document.querySelectorAll('.cw-list .cw-msg')].map(e => ({
      cls: e.className, text: (e.textContent || '').trim(), painted: painted(e) })),
    live: [...document.querySelectorAll('.cw-list .cw-msg.cw-live')]
            .filter(painted).map(e => (e.textContent || '').trim()),
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
    # A CLOCK, not an iteration count (`tests/waiting.py`'s lesson, enforced by
    # `test_a_wait_is_bounded_by_a_clock`): `range(60)` READS as thirty seconds and is not — the budget counts
    # iterations and an iteration costs whatever it costs, so the wall clock is unbounded exactly when
    # something is wrong. Copied from node 4.197 with the defect; the ratchet caught it at 61 over 58.
    deadline = time.time() + 30.0
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
        except OSError:
            time.sleep(0.5)
    else:  # pragma: no cover
        proc.terminate(); pytest.skip("preview server never came up in 30 s")
    time.sleep(1.0)
    yield f"http://127.0.0.1:{port}/"
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover
        proc.kill()


@pytest.fixture(scope="module")
def seen(run):
    """One browser, one sentence, read at every step of its life."""
    from playwright.sync_api import sync_playwright
    out = {"errors": []}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
        pg = b.new_context(viewport={"width": 1280, "height": 800}).new_page()
        pg.on("pageerror", lambda e: out["errors"].append(str(e)))
        pg.goto(run, wait_until="domcontentloaded")
        pg.wait_for_timeout(2200)
        pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e=>e.remove())")
        pg.evaluate("""async () => {
          const s = await import('/static/app/core/store.js?v=2');
          s.setChatMsgs([]); s.setChatTab('chat'); s.setChatOpen(true);
          s.setAttentionMode('smart');            // there IS a gate: nothing is released without a verdict
          // …and the orb is LISTENING (he said the name). V2-763: a caption is «you are being heard», and it
          // is only painted while the orb says so — the grey half is pinned on its own below.
          s.pulseAttentionHit(120);
          s.clearLiveChat();
        }""")
        pg.wait_for_timeout(400)

        # 1 · the partials arrive, one after another, with no verdict anywhere.
        steps = []
        for part in PARTIALS:
            pg.evaluate("""async (t) => {
              const sse = await import('/static/app/services/sse.js?v=2');
              sse.routeEvent(window.__zaelarDesktop, { kind: 'interim', label: '…', text: t, role: 'user' });
            }""", part)
            pg.wait_for_timeout(120)
            steps.append(pg.evaluate(READ))
        out["partials"] = steps

        # 2 · the FINAL arrives and is held — still no verdict.
        pg.evaluate("""async (t) => {
          const sse = await import('/static/app/services/sse.js?v=2');
          sse.routeEvent(window.__zaelarDesktop, { kind: 'transcript', label: 'transcript', text: t,
                                                   role: 'user' });
        }""", FINAL)
        pg.wait_for_timeout(300)
        out["held"] = pg.evaluate(READ)

        # 3 · the gate rules DIRECTED → the caption becomes a real bubble.
        pg.evaluate("""async () => {
          const sse = await import('/static/app/services/sse.js?v=2');
          sse.settleHeldTurns(window.__zaelarDesktop, "", true);
        }""")
        pg.wait_for_timeout(400)
        out["released"] = pg.evaluate(READ)

        # 4 · …and the other half of the same gate: the room's conversation leaves NOTHING behind.
        room = "pues nada, y el tío se fue sin pagar"
        pg.evaluate("""async (t) => {
          const sse = await import('/static/app/services/sse.js?v=2');
          const ev = (k, text) => sse.routeEvent(window.__zaelarDesktop,
                                                 { kind: k, label: k, text, role: 'user' });
          ev('interim', 'pues nada, y el tío');
          ev('transcript', t);
        }""", room)
        pg.wait_for_timeout(250)
        out["room_pending"] = pg.evaluate(READ)
        pg.evaluate("""async (t) => {
          const sse = await import('/static/app/services/sse.js?v=2');
          sse.settleHeldTurns(window.__zaelarDesktop, t, false);
        }""", room)
        pg.wait_for_timeout(400)
        out["room_settled"] = pg.evaluate(READ)

        # 4b · V2-763 — the orb GREY. His 2026-09-24 screenshot: a dashed «being heard» line over a grey orb,
        # for a monologue the gate had ruled ambient. With the ring off nothing is painted as heard, not even
        # as a caption; the verdict alone decides.
        grey = "esto se lo estoy contando a otra persona"
        pg.evaluate("""async (t) => {
          const s = await import('/static/app/core/store.js?v=2');
          s.clearAttentionHit();
          const sse = await import('/static/app/services/sse.js?v=2');
          const ev = (k, text) => sse.routeEvent(window.__zaelarDesktop,
                                                 { kind: k, label: k, text, role: 'user' });
          ev('interim', 'esto se lo estoy');
          ev('transcript', t);
        }""", grey)
        pg.wait_for_timeout(300)
        out["grey"] = pg.evaluate(READ)
        pg.evaluate("""async (t) => {
          const sse = await import('/static/app/services/sse.js?v=2');
          sse.settleHeldTurns(window.__zaelarDesktop, t, false);
          const s = await import('/static/app/core/store.js?v=2');
          s.pulseAttentionHit(120);
        }""", grey)
        pg.wait_for_timeout(300)

        # 5 · THE LAST METRE. Everything above enters through `routeEvent`; this proves the live subscription
        # actually calls it, by swapping `EventSource` for a double and re-opening the stream. Without it the
        # three-line delegation in `onmessage` is the one piece of this channel nothing measures — and its own
        # disarm showed that deleting it left every assertion above green.
        out["through_the_socket"] = pg.evaluate("""async () => {
          const sse = await import('/static/app/services/sse.js?v=2');
          const s = await import('/static/app/core/store.js?v=2');
          const RealES = window.EventSource;
          let last = null;
          window.EventSource = function () { last = this; this.close = () => {}; };
          sse.closeSSE(); sse.openSSE(window.__zaelarDesktop);
          s.clearLiveChat();
          last.onmessage({ data: JSON.stringify({ kind: 'interim', label: '…',
                                                  text: 'por el socket de verdad', role: 'user' }) });
          const painted = s.liveChat();
          sse.closeSSE(); window.EventSource = RealES;
          return painted;
        }""")
        b.close()
    return out


def test_the_page_has_no_errors(seen):
    assert seen["errors"] == [], seen["errors"]


def test_a_partial_reaches_the_wall_with_NO_verdict(seen):
    """The whole feature. Before today nothing at all appeared until the gate had ruled — a median 3.45 s
    after he started the sentence.

    It goes in through `routeEvent`, the same door a real SSE frame comes through, so deleting the `interim`
    branch fails this. The first version called `captionPartial` directly and survived exactly that."""
    assert seen["partials"][0]["live"] == [PARTIALS[0]], seen["partials"][0]
    assert seen["partials"][0]["bubbles"][0]["painted"], "the caption is in the DOM and not on the screen"


def test_the_caption_GROWS_as_he_talks_and_stays_a_single_line(seen):
    for part, step in zip(PARTIALS, seen["partials"]):
        assert step["live"] == [part], f"after «{part}» the wall showed {step['live']}"
        assert len(step["bubbles"]) == 1, f"the caption duplicated: {step['bubbles']}"


def test_the_caption_is_MARKED_as_provisional(seen):
    """A finished bubble and a half-heard one must not look alike — the dimmer lesson: two meanings on one
    channel and the new signal loses."""
    last = seen["partials"][-1]["bubbles"][0]
    assert "cw-live" in last["cls"], last
    assert "you" in last["cls"], f"it is still HIS line: {last}"


def test_the_FINAL_firms_up_the_caption_while_the_verdict_is_still_pending(seen):
    """The interim stream has stopped by now, so without this the line would freeze on the last partial —
    a word short of what he actually said — for as long as the hold lasts."""
    assert seen["held"]["live"] == [FINAL], seen["held"]
    assert len(seen["held"]["bubbles"]) == 1, seen["held"]["bubbles"]


def test_the_verdict_REPLACES_the_caption_with_the_real_line(seen):
    """One line, not two: the caption is not history and must not survive next to the thing it previewed."""
    assert seen["released"]["live"] == [], seen["released"]
    texts = [b["text"] for b in seen["released"]["bubbles"]]
    assert texts == [FINAL], texts
    assert "cw-live" not in seen["released"]["bubbles"][0]["cls"]


def test_the_ROOM_is_captioned_while_it_is_being_judged(seen):
    """It has to be — nothing knows whose voice it is until the verdict lands."""
    assert len(seen["room_pending"]["live"]) == 1, seen["room_pending"]


def test_the_ROOM_leaves_NOTHING_on_the_wall(seen):
    """V2-647, intact. An entire conversation he was having with somebody else once filled his chat, every
    line correctly ruled ambient server-side and every line shown as if he had said it. A caption that
    outlived its discarded turn would be that same defect through a new door."""
    assert seen["room_settled"]["live"] == [], seen["room_settled"]
    texts = [b["text"] for b in seen["room_settled"]["bubbles"]]
    assert texts == [FINAL], f"the room reached his wall: {texts}"


def test_with_the_orb_GREY_nothing_is_painted_as_heard(seen):
    """V2-763 — the orb and the wall may not contradict each other: grey means «not listening to you», so no
    caption and no bubble until a verdict says the turn was his."""
    assert seen["grey"]["live"] == [], seen["grey"]
    assert [b["text"] for b in seen["grey"]["bubbles"]] == [FINAL], seen["grey"]


def test_a_real_SSE_FRAME_reaches_the_caption(seen):
    """`onmessage` parses and hands off to `routeEvent`, and that hand-off is code like any other: deleting
    it silences this whole channel while every test that drives `routeEvent` directly stays green."""
    assert seen["through_the_socket"] == "por el socket de verdad", seen["through_the_socket"]
