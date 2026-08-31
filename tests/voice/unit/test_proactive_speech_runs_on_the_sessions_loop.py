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
        # since the second cut, the say lives inside an `async def _do_say():` body and the hop call sits a
        # couple of lines below — the pair must stay within one small window, or the say has gone bare again
        window = "\n".join(lines[max(0, i - 3):i + 4])
        assert "_on_session_loop" in window, \
            f"a bare `session.say(` awaited from the caller's loop cuts the voice mid-sentence: {lines[i].strip()}"


# ── and the hop itself has to WORK, against the REAL shape of `say` ───────────────────────────────────────
# The SECOND cut (session f5e833f7, 2026-08-31) got past the first version of these tests because the fake
# speaker here was an `async def` — a coroutine function — while the real `AgentSession.say` is a SYNC method
# that schedules the speech on whatever loop is CURRENT and returns an awaitable SpeechHandle
# (`inspect.iscoroutinefunction(AgentSession.say)` is False, checked against livekit-agents 1.6.6). Fed a
# lambda, the hop ran `say` on the caller's loop (disease intact) and `run_coroutine_threadsafe` rejected the
# handle: «A coroutine object is required», playout dead at 3 s with 99 s synthesized. A test double that does
# not match the seam's real shape verifies the harness, not the product — so the fake below has say's exact
# shape, and the property asserted is WHERE THE SYNC CALL RAN.


class _FakeSession:
    """`say`'s real shape: sync, notes the loop it was CALLED on (that is where LiveKit builds the playout
    futures), returns an awaitable handle."""

    def __init__(self):
        self.called_on = []

    def say(self, text, **kw):
        self.called_on.append(asyncio.get_running_loop())

        async def _handle():
            await asyncio.sleep(0)          # a real suspension point, like a playout wait
        return _handle()


def _make_hop(session_loop):
    """The same shape as `_on_session_loop` in agent.py, exercised against two real loops."""
    async def _on_session_loop(coro_fn):
        try:
            here = asyncio.get_running_loop()
        except RuntimeError:
            here = None
        if here is session_loop:
            await coro_fn()
            return
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(coro_fn(), session_loop))
    return _on_session_loop


def _drive_from_another_loop(session_loop, hop, fake):
    async def _do_say():
        await fake.say("hola")

    async def _caller():                    # this is uvicorn's loop: a worker delivering its result
        await hop(_do_say)

    asyncio.run(_caller())


def test_the_sync_say_call_itself_runs_on_the_sessions_loop():
    """THE property (the second cut's lesson): not just the await — the CALL. `say` schedules its playout
    futures on whatever loop is current when the sync method executes."""
    session_loop = asyncio.new_event_loop()
    t = threading.Thread(target=session_loop.run_forever, daemon=True)
    t.start()
    try:
        fake = _FakeSession()
        _drive_from_another_loop(session_loop, _make_hop(session_loop), fake)
        assert fake.called_on == [session_loop], \
            "say() executed on the caller's loop — that schedules the playout cross-loop and it dies in seconds"
    finally:
        session_loop.call_soon_threadsafe(session_loop.stop)
        t.join(timeout=5)
        session_loop.close()


def test_the_hop_is_handed_coroutines_not_speech_handles():
    """`run_coroutine_threadsafe(SpeechHandle)` raises «A coroutine object is required» — the say has already
    been scheduled (wrongly) by then, so the error arrives AFTER the damage. The agent.py callers must wrap the
    call in an `async def` body, never a bare lambda around `session.say`."""
    src = "\n".join(l for l in AGENT.read_text(encoding="utf-8").splitlines()
                    if not l.strip().startswith("#"))
    assert "_on_session_loop(lambda" not in src, \
        "a lambda around session.say CALLS it on the caller's loop and hands the hop a SpeechHandle — the " \
        "exact «A coroutine object is required» failure of session f5e833f7"
    for l in src.splitlines():
        if "session.say(" in l:
            assert "await session.say(" in l, \
                f"every say must be awaited inside an async body that the hop runs on the session loop: {l.strip()}"


def test_the_hop_is_a_no_op_on_the_sessions_own_loop():
    """The voice turn itself already runs there and must pay nothing — no thread hop, no extra future."""
    fake = _FakeSession()

    async def _main():
        loop = asyncio.get_running_loop()
        hop = _make_hop(loop)

        async def _do_say():
            await fake.say("hola")

        await hop(_do_say)
        return loop

    loop = asyncio.run(_main())
    assert fake.called_on == [loop]


def test_a_failure_inside_the_say_reaches_the_caller():
    """The reason the FIRST cut went unseen: the error died in a task nobody retrieved. Whatever else the hop
    does, it must hand an exception BACK, so `proactive.notify`'s except can log AND emit it."""
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


def test_a_failed_voice_delivery_is_a_VISIBLE_error_event():
    """The operator's ask, verbatim: more observability in the voice management. A delivery that dies mid-say
    was a WARNING in server.log and nothing in the session timeline — today's «A coroutine object is required»
    sat invisible for an hour. The except in `proactive.notify` must emit an error event, not just log."""
    from voice import proactive as _p
    src = "\n".join(l for l in (Path(_p.__file__)).read_text(encoding="utf-8").splitlines()
                    if not l.strip().startswith("#"))
    i = src.find("proactive notify (voice) failed")
    assert i > 0, "the failure branch moved: this guard would be watching nothing"
    window = src[i:i + 500]
    assert '_emit_err("error"' in window or 'emit("error"' in window, \
        "a failed voice delivery has to land in the session timeline as an ERROR the operator can see"
