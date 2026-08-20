"""V2-211 — the worker dies at OUR OWN permission gate, in silence.

Three cases measured the same day, three different commands, one shape:

    find-theatre-tickets__es  15:24  cd in '…/zaelar/engine' was blocked. For security, Claude Code may only
                                     change directories to the allowed working directory
    cheapest-monitor          15:35  This Bash command contains multiple operations. The following part
                                     requires approval: curl -s "https://www.pccomponentes.com/monitores"
    remember-and-remind       15:38  …requires approval: cd /Users/…

Headless, NOBODY approves. So an approval request is a dead end: the worker reads it as a refusal and stops,
and the turn goes on saying it is making progress. It is the confirm-gate of V2-202 one layer down — a gate that
stops the work and has no way back to anyone who could authorise it.

Two halves, and the first is the one that matters:

  · PREVENTION (`dispatch_prompts`): the rules of the box it runs in. It cannot deduce them, so either we hand
    them over or it discovers them by crashing — and crashing here costs the task. Exactly what the interpreter
    header already fixed on 2026-08-02, when the worker burned minutes trying `python`, `python3`,
    `.venv/bin/python` because nothing told it which one was allowed.
  · RECOVERY (`workers/session.py`): if it crashes anyway, it is told AT THAT MOMENT what happened and how to
    rewrite it — one injected turn, once, the same shape as the context wrap-up.
"""
import asyncio

import pytest

from nucleo import dispatch_prompts as dp


def _header():
    return dp._with_interpreter("usa python -m nucleo.nav_cli snapshot")


def test_the_prompt_forbids_cd_and_says_why():
    h = _header()
    assert "NUNCA `cd`" in h and "BLOQUEADO" in h


def test_the_prompt_forbids_chaining_operations():
    h = _header()
    assert "UN comando por llamada" in h
    for op in ("&&", ";", "|", "$("):
        assert op in h


def test_the_prompt_names_the_alternative_to_curl():
    """“Don't use curl” without saying what to use instead is how a worker starts writing its own script — which
    the delivery recipe already had to forbid separately."""
    h = _header()
    assert "curl" in h and "nav_cli" in h and "worker_bridge" in h


def test_the_prompt_says_an_approval_request_is_a_DEAD_END():
    """The costly belief is that waiting or retrying might work. It never does here, and the way out is to say so
    rather than to end in silence."""
    h = _header()
    assert "no va a llegar nunca" in h
    assert "DILO" in h and "silencio" in h


def test_a_prompt_without_bridges_gets_no_header():
    """The UNTRUSTED profile (a peer's text) runs with no tools by construction: handing it this header would
    give it the engine's absolute path for nothing."""
    assert dp._with_interpreter("resume esta conversación") == "resume esta conversación"


# ── the recovery half ─────────────────────────────────────────────────────────────────────────────────────────
class _FakeBackend:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)


def _session():
    from nucleo.workers import session as S
    s = S.WorkerSession.__new__(S.WorkerSession)
    s._perm_warned = False
    s._b = _FakeBackend()
    s._rec = type("R", (), {"task_id": "7"})()
    s._emit_chip = lambda *a, **k: None
    return s


@pytest.mark.parametrize("text", [
    "cd in '/Users/x/zaelar/engine' was blocked. For security, Claude Code may only change directories to the "
    "allowed working directory",
    'This Bash command contains multiple operations. The following part requires approval: curl -s "https://x"',
])
def test_a_denial_gets_ONE_corrective_turn(text):
    async def go():
        s = _session()
        s._maybe_unstick_permission({"text": text})
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(s._b.sent) == 1
        msg = s._b.sent[0]
        assert "NADIE puede aprobarlo" in msg and "nav_cli" in msg
        # …and only once: a second crash must not turn into a loop of system notices.
        s._maybe_unstick_permission({"text": text})
        await asyncio.sleep(0)
        assert len(s._b.sent) == 1
    asyncio.run(go())


def test_an_ordinary_step_result_is_left_alone():
    """Sensitivity: this reads EVERY step result, so a wide match would inject system notices into healthy runs."""
    async def go():
        s = _session()
        s._maybe_unstick_permission({"text": "OK: navegado a https://www.entradas.com"})
        await asyncio.sleep(0)
        assert s._b.sent == []
    asyncio.run(go())


# ── the WIRING, and it is the half the tests above could not see ──────────────────────────────────────────────
# Everything above calls `_maybe_unstick_permission` directly, so all of it would keep passing with the call site
# at `session.py:176` DELETED. That is exactly the shape of hole this whole area keeps falling into: a fix that
# travels correctly and dies one line short of its reader. So this walks the real door — a `step_result` event
# through `_on_event`, the way a backend actually delivers one.
#
# The MEMORY bridge case is asserted by name because it is the one that cost the most: when the gate ate
# `cd … && … -m nucleo.mem_cli recall`, the worker was left unable to read the operator's memory at all, and the
# chip says «memoria» only because the step is coloured by the bridge it used (`_PLACE`), which sent the finding
# to the wrong owner for a while.
def test_a_step_result_event_REACHES_the_recovery():
    from nucleo.workers.base import WorkerEvent

    async def go():
        s = _session()
        s._touch = lambda *a, **k: None
        s._bus = lambda *a, **k: None
        s._on_event(WorkerEvent(task_id="7", type="step_result", data={
            "tool": "Bash", "is_error": True,
            "text": "cd in '/Users/x/zaelar/engine' was blocked. For security, Claude Code may only change "
                    "directories to the allowed working directory"}))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(s._b.sent) == 1, "the corrective turn never reached the worker"
        assert "NADIE puede aprobarlo" in s._b.sent[0]
    asyncio.run(go())


def test_a_healthy_step_result_event_injects_NOTHING():
    """Sensitivity on the same door: every step result goes through here, so a wide match would inject system
    notices into runs that are working."""
    from nucleo.workers.base import WorkerEvent

    async def go():
        s = _session()
        s._touch = lambda *a, **k: None
        s._bus = lambda *a, **k: None
        s._on_event(WorkerEvent(task_id="7", type="step_result",
                                data={"tool": "Bash", "text": "píldoras: el operador vive en Madrid"}))
        await asyncio.sleep(0)
        assert s._b.sent == []
    asyncio.run(go())
