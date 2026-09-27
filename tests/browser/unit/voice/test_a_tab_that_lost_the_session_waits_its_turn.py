"""A tab that lost the single voice session retries every 3 s — not as fast as the event loop allows.

Measured live (2026-09-27, the demo pass): the demo driver stole the session lock from the operator's open tab.
That tab went `live → stalled` and then flipped `stalled ↔ starting` ~140 times a second, flooding the timeline
with 4,000 `agent:state` events per 30 s. `start()` arms a 3 s retry when `sessionAcquire` is refused, but it
also drops `starting` — and main.js's `ensureVoice` effect watches exactly that signal, so it called `start()`
again at once and the retry timer never got to be the one that retried.

Tested by TEXT, like its neighbours (this repo runs no browser JS in unit tests).
"""
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
SESSION = ENGINE / "frontend" / "app" / "services" / "session-lk.js"
MAIN = ENGINE / "frontend" / "app" / "main.js"


def _code(p: Path) -> str:
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


def _start_head() -> str:
    code = _code(SESSION)
    i = code.find("export async function start()")
    assert i >= 0, "start() moved: this guard would be watching nothing"
    j = code.find("api.runState()", i)
    assert j > i
    return code[i:j]


def test_the_effect_that_restarts_the_voice_still_watches_starting():
    """The premise: if main.js stopped re-running on `starting`, the loop could not happen and this guard
    would be protecting nothing — so say so instead of passing silently."""
    code = _code(MAIN)
    assert "function ensureVoice()" in code and "!store.starting()" in code


def test_start_does_nothing_while_the_blocked_retry_is_armed():
    head = _start_head()
    assert "if (_blockedRetry) return;" in head, \
        "start() must leave the retry to the 3 s timer while another tab holds the session"


def test_the_timer_clears_itself_before_retrying():
    """Otherwise the guard above would also block the one retry that is supposed to run."""
    code = _code(SESSION)
    assert "_blockedRetry = setTimeout(() => { _blockedRetry = null; start(); }, 3000);" in code
