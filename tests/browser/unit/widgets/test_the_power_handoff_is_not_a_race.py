"""V2-627 — ⏻ ON has to work on the FIRST press.

Operator report (2026-09-09) with his own console attached: «cuando le doy la primera vez cuando está parado,
parece que se sombrea un poco pero no arranca y le tengo que dar una segunda vez». It was not a feeling — his
observability log has it twice over:

    11:59:33  agent:state  starting (prev off)
    11:59:33  orb:power    on               ← first press
    11:59:33  agent:state  off (prev starting)   ← torn down in the same second
    11:59:38  agent:state  starting (prev off)
    11:59:38  orb:power    on               ← SECOND press, five seconds later
    11:59:38  agent:state  live (prev starting)

Two `orb:power on` in a row is the proof: after the first press, `powerOff` had gone back to TRUE.

The cause is two correct fixes from the SAME day (2026-08-31) racing each other. Orb.js was sequenced
server-first (`runStart().then(session.start)`), and main.js gained an effect that revives the voice when
`powerOff` drops from outside this tab. But `setPowerOff(false)` runs SYNCHRONOUSLY at the top of the ⏻
click, so that effect fires INSIDE the click — before `POST /api/run/start` has even been sent. Its
`session.start()` asks the server, is told STOPPED (true, for another few milliseconds), aborts, and sets
`powerOff` back to true. The click's own sequenced `start()` then finds `starting` still true and no-ops.

The fix is a HANDOFF: while a ⏻ ON is in flight, the click owns the startup and no other road may open a
session. The state machine below is tested by loading the REAL `core/store.js` in a browser — it is a module
with no dependencies beyond `reactive.js` and `localStorage`, so nothing here is a re-implementation of it.
The wiring at the three call sites is asserted structurally, as its neighbour
`test_power_on_brings_the_voice_up.py` does: this repo runs no bundler, so app modules that pull LiveKit
cannot be booted in a test.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
ORB = APP / "components" / "Orb.js"
MAIN = APP / "main.js"
SESSION = APP / "services" / "session-lk.js"


def _code(p: Path) -> str:
    """CODE only: a comment explaining the fix can neither pass this test nor break it."""
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


# ── the state machine, exercised for real in a browser ────────────────────────────────────────────────────
_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body></body></html>"""

_PROBE = """async () => {
  const store = await import('/core/store.js?v=2');
  const out = {};
  out.idle = store.powerOnPending();                 // nothing commanded yet
  store.markPowerOnPending();
  out.inFlight = store.powerOnPending();             // the command is travelling
  store.clearPowerOnPending();
  out.afterReply = store.powerOnPending();           // the server answered: the road opens again
  // An answer that NEVER comes must not wedge the voice shut for the rest of the session.
  store.markPowerOnPending();
  const realNow = Date.now;
  try {
    const t = realNow.call(Date);
    Date.now = () => t + 60000;
    out.expired = store.powerOnPending();
  } finally { Date.now = realNow; }
  return out;
}"""


def _run():
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            async def _serve(route):
                url = route.request.url.split("?", 1)[0]
                rel = url.replace("http://zaelar.test/", "")
                if not rel or rel.endswith("/"):
                    await route.fulfill(status=200, content_type="text/html", body=_HTML)
                    return
                f = APP / rel
                if not f.exists():
                    await route.fulfill(status=404, body="")
                    return
                await route.fulfill(status=200, content_type="text/javascript",
                                    body=f.read_text(encoding="utf-8"))
            await pg.route("http://zaelar.test/**", _serve)
            await pg.goto("http://zaelar.test/")
            out = await pg.evaluate(_PROBE)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


@pytest.fixture(scope="module")
def probe():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return _run()


def test_the_handoff_is_closed_while_the_command_travels_and_open_after(probe):
    assert probe["errors"] == [], probe["errors"]
    assert probe["idle"] is False, "nothing commanded: every road to the voice stays open"
    assert probe["inFlight"] is True, "with ⏻ ON in flight the click owns the startup"
    assert probe["afterReply"] is False, "the server answered: the other roads open again"


def test_a_reply_that_never_arrives_cannot_wedge_the_voice_shut(probe):
    """A boolean would have. This is why it is a timestamp."""
    assert probe["expired"] is False


# ── the wiring, at the three places that can open a session ───────────────────────────────────────────────
def test_every_road_to_the_voice_respects_the_handoff():
    """The guard lives INSIDE `ensureVoice`, not in one of its callers: it is reached from boot, from every
    `pointerdown`, and from the effect that watches `powerOff` drop — and it was that third one, firing
    synchronously inside the click, that opened the ghost session."""
    code = _code(MAIN)
    i = code.find("function ensureVoice()")
    assert i > 0, "ensureVoice moved: this guard would be watching nothing"
    body = code[i:code.index("}", code.index("session.start()", i))]
    assert "store.powerOnPending()" in body, \
        "ensureVoice has to stand down while the operator's ⏻ ON is still travelling to the server"
    assert body.index("store.powerOnPending()") < body.index("session.start()"), \
        "the guard has to come BEFORE the start, not after it"


def test_the_power_click_takes_the_handoff_and_gives_it_back():
    code = _code(ORB)
    i = code.find('mic.setMuted(false, "power-on")')   # V2-654: the mic write moved behind the door
    j = code.find('api.uiEvent("orb:power"', i)
    branch = code[i:j]
    assert "store.markPowerOnPending()" in branch, "the ⏻ ON click has to claim the startup"
    assert branch.index("store.markPowerOnPending()") < branch.index("api.runStart()"), \
        "claim it BEFORE commanding the server: the window opens the instant `powerOff` flips"
    tail = branch[branch.index("api.runStart()"):]
    assert "store.clearPowerOnPending()" in tail, "…and give it back when the server answers"
    assert tail.index("store.clearPowerOnPending()") < tail.index("session.start()"), \
        "give it back BEFORE starting the session itself, or the click blocks its own startup"


def test_the_gate_treats_an_in_flight_power_on_as_history():
    """`powerCmdAt` only catches a command that lands AFTER the request. The press that starts the agent
    stamps itself before, so the gate needs the in-flight window too — defence in depth for a start that
    got in anyway (another tab, a road added later)."""
    code = _code(SESSION)
    i = code.find("api.runState()")
    assert i > 0
    window = code[i:i + 400]
    assert "store.powerOnPending()" in window, \
        "the ⏻ gate has to drop a snapshot taken while the operator's ⏻ ON was still travelling"


def test_the_refusal_is_not_silent_any_more():
    """The whole reason this cost a log read: the abort said nothing, anywhere. It is a legitimate outcome,
    so it is not an error — but it is a decision, and a decision nobody can see is the expensive kind."""
    code = _code(SESSION)
    i = code.find('store.setPowerOff(true); mic.setMuted(true, "server-stopped")')   # V2-654: the door
    assert i > 0, "the gate's abort moved"
    window = code[max(0, i - 400):i]
    assert "console.warn" in window, "say it in the console the operator is already looking at"
    assert "voice:refused" in window, "and put it on the server's timeline, next to orb:power"


def test_the_press_itself_says_so_in_the_console():
    """The operator's own request: «escribe algo en la consola cada vez que se toca ese botón»."""
    code = _code(ORB)
    i = code.find("const off = !store.powerOff();")
    assert i > 0
    window = code[i:i + 400]
    assert "console.info" in window and "store.agentState()" in window, \
        "every ⏻ press has to name itself AND the state it was pressed in"

def test_a_newer_press_supersedes_the_handoff():
    """The counterweight, and a regression this fix could have introduced on its own: ON and then OFF inside
    the 15 s window. The ON's `runStart().then(...)` is still scheduled, so if the stamp survived, the gate —
    told to treat that window as history — would wave a voice session up over an agent the operator had just
    stopped. Every press drops the handoff; only the ON branch takes it again."""
    code = _code(ORB)
    i = code.find("store.markPowerCommand()")
    assert i > 0, "the ⏻ handler moved"
    j = code.find("store.setPowerOff(off)", i)
    assert j > i
    assert "store.clearPowerOnPending()" in code[i:j], \
        "the handoff has to drop on EVERY press, before the branch: a newer command supersedes an older one"
    on_branch = _code(ORB)[code.find('mic.setMuted(false, "power-on")'):]   # V2-654: same anchor as above
    assert "store.markPowerOnPending()" in on_branch[:on_branch.index('api.uiEvent("orb:power"')], \
        "…and only the ON branch takes it again"
