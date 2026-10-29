"""A line the engine SAYS on behalf of a turn carries that turn's trace (V2-831 T-23b).

#128 bound a generated reply's speech to its turn; a `session.say()` we queue — the turn's spoken follow-up
(`follow_up_pass.deliver`), every `proactive.speaker()` caller — was not bound, so its transcript (added when the
PLAYOUT ends) read `trace.active()` and was stamped with whatever turn was live then (T1·6857 in the demo).

Class: the one door every say goes through (`agent_events._speak`) binds the speech it queues to the trace of the
context that asked, read before the hop to the session loop.

Disarm: drop the `bind_speech` line in `_speak` → red.
"""
from __future__ import annotations

import asyncio
import contextvars
from types import SimpleNamespace

from livekit.agents.voice.agent_activity import _SpeechHandleContextVar

from voice import trace


def test_a_follow_up_said_for_turn_a_keeps_a_s_trace_when_it_lands_in_turn_b(monkeypatch):
    from voice.engine.pipeline import agent as _ag, agent_events
    monkeypatch.setattr(_ag._reply_wall, "already_surfaced", lambda t: False)
    class _Handle:
        id = "SAY_A"

        def done(self):
            return True

        def __await__(self):
            return asyncio.sleep(0).__await__()
    h = _Handle()
    session = SimpleNamespace(say=lambda text, allow_interruptions=True: h)

    async def on_loop(fn):
        await fn()
    tid_a = trace.begin("and the nasdaq, over the whole year")          # the turn that asks for the follow-up
    asyncio.run(agent_events._speak("The NASDAQ is up 11.9% this year.", _busy={"bot": False, "user": False},
                                    _emit=lambda *a, **k: None, _on_session_loop=on_loop, session=session))
    tid_b = trace.begin("ok close that")                                 # the next turn is live when it lands
    assert trace.active() == tid_b and tid_a != tid_b
    emitted = []
    ctx = contextvars.copy_context()

    def land():                                                          # LiveKit adds the item in the say's task
        _SpeechHandleContextVar.set(h)
        agent_events._on_item(SimpleNamespace(item=SimpleNamespace(role="assistant",
                                                                   text_content="The NASDAQ is up 11.9% this year.")),
                              _emit=lambda kind, label, **kw: emitted.append((kind, (kw.get("extra") or {}).get("trace"))))
    ctx.run(land)
    assert ("transcript", tid_a) in emitted, f"stamped {emitted}; the asking turn is {tid_a}, the live one {tid_b}"
    trace.adopt("")
