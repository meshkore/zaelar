"""⏻ ON HAS TO START IT — without waiting for a second click, and without a page reload.

Real report (operator, 2026-08-31, with a screenshot of the amber ⏻):

  «apago el bot y hago el reset; al darle al botón de arranque se me queda en amarillo parpadeando y creo que al
   cabo de un minuto o dos sí que arranca. Pero por alguna razón si hago un refresh de la página, automáticamente
   ya se pone en marcha todo.»

Two faults stacked, and the reload is the tell — a state that only fixes itself by reloading is the state that
lies:

1. **ORDER.** The ⏻ ON handler called `session.start()` FIRST and `api.runStart()` after. But `session.start()`
   opens with a gate against the server's truth (`GET /api/run`, added 2026-08-15 to stop ghost sessions), so it
   read the switch from BEFORE this very click, found `running:false`, aborted the startup and set `powerOff`
   back to true. The server first, the session after.

2. **NOBODY BROUGHT IT BACK UP.** `powerOff` going FALSE from outside this tab (the SSE `run` event, another
   window's ⏻) had no effect watching it — only the OFF direction did. The voice waited for the next
   `pointerdown`, the other road to `ensureVoice()`. Hence "a minute or two": until he clicked something else.

And the defence, which is the rule main.js's seeding has followed since 2026-08-14 and this gate never did: a
`/api/run` reply is a snapshot of the moment it was REQUESTED, so a ⏻ command that lands meanwhile makes it
history. Ordering makes the race rare; `powerCmdAt` makes it harmless — the command can come from another tab,
which no ordering here can prevent.

Tested by TEXT because this repo runs no JS in tests (ES modules, no build), same as its neighbours.
"""
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]
APP = ENGINE / "frontend" / "app"
ORB = APP / "components" / "Orb.js"
MAIN = APP / "main.js"
SESSION = APP / "services" / "session-lk.js"


def _code(p: Path) -> str:
    """CODE only: a comment explaining the fix can neither pass this test nor break it."""
    return "\n".join(s for s in (l.strip() for l in p.read_text(encoding="utf-8").splitlines())
                     if s and not s.startswith("//"))


def _power_on_branch() -> str:
    """The `else` arm of the ⏻ click — the one that turns the agent ON."""
    code = _code(ORB)
    i = code.find('localStorage.setItem("hb_mic_muted", "0")')
    assert i > 0, "the ⏻ ON branch moved: this guard would be watching nothing"
    j = code.find('api.uiEvent("orb:power"', i)
    assert j > i, "the end of the ⏻ handler moved: this guard would be watching nothing"
    return code[i:j]


def test_powering_on_tells_the_SERVER_before_starting_the_session():
    """The whole bug in one assertion: with `session.start()` ahead of `runStart()`, the gate inside it reads a
    switch that this very click has not flipped yet."""
    branch = _power_on_branch()
    assert "api.runStart()" in branch, "⏻ ON has to command the server"
    assert "session.start()" in branch, "…and bring the voice session up"
    assert branch.index("api.runStart()") < branch.index("session.start()"), \
        "the SERVER goes first: starting the session before the switch flipped makes its own ⏻ gate abort it"


def test_the_session_start_hangs_off_the_runStart_reply():
    """Not just written first — SEQUENCED after the reply. Two calls fired side by side is the same race with the
    lines swapped."""
    branch = _power_on_branch()
    tail = branch[branch.index("api.runStart()"):]
    assert "then(" in tail[:tail.index("session.start()")], \
        "`session.start()` has to run in `runStart().then(...)`, not race it"


def test_the_power_gate_drops_a_snapshot_older_than_the_operators_command():
    """`GET /api/run` answers about the instant it was ASKED. Obeying a reply that a later ⏻ has already made
    history is how a startup gets torn down by its own click."""
    code = _code(SESSION)
    assert "store.powerCmdAt()" in code, \
        "the ⏻ gate has to consult the stamp of the operator's last command (store.js::markPowerCommand)"
    i = code.find("api.runState()")
    assert i > 0
    window = code[max(0, i - 400):i + 400]
    assert "askedAt" in window and "powerCmdAt" in window, \
        "the stamp has to be taken BEFORE asking and compared to the reply — not read somewhere else entirely"


def test_power_coming_back_ON_brings_the_voice_up_without_a_click():
    """The `powerOff` watcher covered only the OFF direction since V2-092. With the switch raised from outside
    this tab (SSE `run`, another window), nobody called `session.start()` again and the voice sat waiting for a
    pointer that may never come."""
    code = _code(MAIN)
    assert "if (store.powerOff()) return;\nensureVoice();" in code, \
        "an effect has to watch `powerOff` going FALSE and re-arm the voice (ensureVoice is idempotent)"


def test_the_OFF_direction_is_still_covered():
    """Counterweight: the effect this one mirrors must keep tearing the session down when the switch drops —
    otherwise a tab paints itself off with the mic open, which is the failure V2-092 was written for."""
    code = _code(MAIN)
    assert "if (!store.powerOff()) return;" in code and "session.stop()" in code, \
        "stopped still has to mean no voice session, wherever the order came from"
