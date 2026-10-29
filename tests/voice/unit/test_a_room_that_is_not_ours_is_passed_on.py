"""A voice room this worker does not own is PASSED ON to the next worker, never terminated.

Several workers register with one LiveKit server (the operator's engine, a sandbox, a lab, a second install). With
automatic dispatch LiveKit offers a new room to ONE worker at a time. `JobRequest.reject()` defaults to
`terminate=True`, which ends the dispatch for every worker: whichever foreign worker LiveKit picked first left the
room without an agent for good, and the page waited forever for a first turn (measured: demo sandbox room joined
8 s after its worker registered, the job went to the operator's worker, which rejected it — the sandbox worker was
never asked). Reproduced against an isolated livekit-server 1.13.3 with an owner and a refusing worker: 5 of 12
rooms got no agent with the default reject, 0 of 24 with `terminate=False`.

The test drives our `request_fnc` with the library's REAL `JobRequest`, so it reads the flag the library would
send to LiveKit — not a stand-in that could agree with us on a default the library does not have.
"""
from __future__ import annotations

import asyncio
import dataclasses

from livekit.agents.job import JobRequest
from livekit.protocol import agent as lk_agent
from livekit.protocol import models as lk_models

from voice.engine.pipeline import agent as voice_agent


def _offer(room: str) -> tuple[JobRequest, dict]:
    seen: dict = {}

    async def on_reject(terminate: bool) -> None:
        seen["rejected"] = True
        seen["terminate"] = terminate

    async def on_accept(_args) -> None:
        seen["accepted"] = True

    job = lk_agent.Job(id="AJ_test", room=lk_models.Room(name=room))
    return JobRequest(job=job, on_reject=on_reject, on_accept=on_accept), seen


def _run(monkeypatch, prefix: str, room: str) -> dict:
    monkeypatch.setattr(voice_agent, "SETTINGS", dataclasses.replace(voice_agent.SETTINGS, room_name=prefix))
    req, seen = _offer(room)
    asyncio.run(voice_agent.request_fnc(req))
    return seen


def test_the_library_default_would_terminate_the_job():
    """The premise: a bare `reject()` asks LiveKit to give the job to nobody. A library upgrade that flips this
    default turns this red on purpose, so the reason is re-read; the explicit flag in `request_fnc` stays correct."""
    req, seen = _offer("anything")
    asyncio.run(req.reject())
    assert seen == {"rejected": True, "terminate": True}


def test_a_foreign_room_is_refused_without_terminating_it(monkeypatch):
    # another engine's room on the same server, another project's room, a prefix that only LOOKS like ours
    for prefix, room in (("zaelar", "demot19-ad3b7b88"),
                         ("demot19", "zaelar-38f4b4be"),
                         ("zaelar-0a1b", "zaelar-0a1b2c3d4e5f60-ab12cd34"),
                         ("zaelar", "voice-lab-2-9f00")):
        seen = _run(monkeypatch, prefix, room)
        assert seen.get("rejected") and seen.get("terminate") is False, (prefix, room, seen)
        assert not seen.get("accepted"), (prefix, room, seen)


def test_our_own_room_is_still_accepted(monkeypatch):
    for prefix, room in (("zaelar", "zaelar-ab12cd34"), ("demot19", "demot19-ad3b7b88"), ("zaelar", "zaelar")):
        seen = _run(monkeypatch, prefix, room)
        assert seen == {"accepted": True}, (prefix, room, seen)
