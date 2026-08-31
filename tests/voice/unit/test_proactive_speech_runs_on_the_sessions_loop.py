"""A proactive delivery has to speak on the LiveKit session's OWN loop, or it cuts the voice.

Operator report, 2026-08-31: «la voz también se corta cada vez que me está explicando algo… dice una palabra,
se corta, a veces se corta para siempre». Measured in session c480413b, and the correlation is total:

    proactive say 18:52:44 → RuntimeError 18:52:47      proactive say 19:00:30 → RuntimeError 19:00:32
    proactive say 18:53:39 → RuntimeError 18:53:41      proactive say 19:00:57 → RuntimeError 19:01:00
    proactive say 18:56:04 → RuntimeError 18:56:06

Five deliveries, five failures, ~2 s apart, no exceptions either way. The error:

    RuntimeError: Task <…_ParticipantAudioOutput._wait_for_playout…_wait_buffered_audio…>
                  got Future <…> attached to a different loop

`session.say()` builds its playout futures on the loop running the LiveKit job — a thread of its own. Every
proactive delivery is awaited from the CALLER's loop instead (uvicorn: `nucleo/workers/session.py` when a
worker finishes, the messaging connector, the orchestrator's scheduled tasks). Crossing that boundary makes
LiveKit await a future born on the other loop, and the playout wait dies mid-sentence.

Why nobody had seen it: the RuntimeError is raised inside a task nobody retrieves, so
`proactive.notify`'s own `except Exception` never fired and `nucleo/workers/session.py`'s
«entrega proactiva falló» never appeared. The only trace was asyncio's garbage collector complaining, in a
message that names neither the voice nor the delivery.
"""
import asyncio
import threading
from pathlib import Path

AGENT = Path(__file__).resolve().parents[3] / "voice" / "engine" / "pipeline" / "agent.py"


def _code() -> str:
    return "\n".join(l for l in AGENT.read_text(encoding="utf-8").splitlines()
                     if not l.strip().startswith("#"))


def test_the_session_loop_is_captured_where_the_session_lives():
    code = _code()
    assert "_session_loop = asyncio.get_running_loop()" in code, \
        "the entrypoint runs ON the session's loop — that is the only place its identity can be captured"


def test_every_proactive_say_hops_to_that_loop():
    """All three speaking paths that can be triggered from OFF this loop: the proactive speaker, its ephemeral
    twin, and the account-energy closer (which fires from energy_meter's fire-and-forget report)."""
    lines = _code().splitlines()
    says = [i for i, l in enumerate(lines) if "session.say(" in l]
    assert says, "no `session.say(` left: this guard would be watching nothing"
    for i in says:
        # the call may be wrapped, so the hop can legitimately sit on the line above
        window = "\n".join(lines[max(0, i - 1):i + 1])
        assert "_on_session_loop" in window, \
            f"a bare `session.say(` awaited from the caller's loop cuts the voice mid-sentence: {lines[i].strip()}"


# ── and the hop itself has to WORK, not just be written ───────────────────────────────────────────────────
def _make_hop(session_loop):
    """The same shape as `_on_session_loop` in agent.py, exercised against two real loops."""
    async def _on_session_loop(make_coro):
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if here is session_loop:
            await make_coro()
            return
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(make_coro(), session_loop))
    return _on_session_loop


def test_a_say_from_another_loop_reaches_the_sessions_loop():
    """The regression, reproduced: the coroutine must RUN on the session's loop even though it was awaited from
    a different one. Two real event loops in two real threads — the exact shape of the live failure."""
    session_loop = asyncio.new_event_loop()
    ran_on = {}
    t = threading.Thread(target=session_loop.run_forever, daemon=True)
    t.start()
    try:
        hop = _make_hop(session_loop)

        async def _say():
            ran_on["loop"] = asyncio.get_running_loop()
            await asyncio.sleep(0)          # a real suspension point, like a playout wait

        async def _caller():                # this is uvicorn's loop: a worker delivering its result
            await hop(_say)

        asyncio.run(_caller())
        assert ran_on["loop"] is session_loop, \
            "the say ran on the caller's loop — that is where `got Future attached to a different loop` comes from"
    finally:
        session_loop.call_soon_threadsafe(session_loop.stop)
        t.join(timeout=5)
        session_loop.close()


def test_the_hop_is_a_no_op_on_the_sessions_own_loop():
    """The voice turn itself already runs there and must pay nothing — no thread hop, no extra future."""
    ran_on = {}

    async def _main():
        loop = asyncio.get_running_loop()
        hop = _make_hop(loop)

        async def _say():
            ran_on["loop"] = asyncio.get_running_loop()

        await hop(_say)
        return loop

    loop = asyncio.run(_main())
    assert ran_on["loop"] is loop


def test_a_failure_inside_the_say_reaches_the_caller():
    """The reason this went unseen for so long: the error died in a task nobody retrieved. Whatever else the
    hop does, it must hand an exception BACK, so `proactive.notify`'s except can log it."""
    session_loop = asyncio.new_event_loop()
    t = threading.Thread(target=session_loop.run_forever, daemon=True)
    t.start()
    try:
        hop = _make_hop(session_loop)

        async def _boom():
            raise RuntimeError("playout exploded")

        async def _caller():
            try:
                await hop(_boom)
            except RuntimeError as e:
                return str(e)
            return ""

        assert asyncio.run(_caller()) == "playout exploded", \
            "a silent failure here is exactly what made the voice cut look like nothing at all"
    finally:
        session_loop.call_soon_threadsafe(session_loop.stop)
        t.join(timeout=5)
        session_loop.close()
