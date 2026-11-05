"""An act that did not happen is never said done — the turn's one mouth, the door that holds it (V2-851 F1).

The honest line (`promise_kept`) used to add a second «I have not done it» after the reply. It is gone: the turn's ONE
line is the in-turn mouth (`nucleo/turn/reply.py`) speaking the verdict its acts ended in. What the honest line
protected — never claim done when nothing was done (V2-847: a yes is a START) — is held here: a completion (`met`)
comes only from an op whose result plainly landed; a refusal, a break, silence, a timeout or an op still running is
`unmet` or `started`, and `started` says nothing.

Disarm: make `reply.of_op` return `met` for any result, or let `reply.owed` say a `started` outcome, and these go red.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.circuit import verdict as V
from nucleo.turn import reply

NOT_LANDED = [None, {}, {"ok": False}, {"error": "boom"}, {"ok": False, "error": "no row"}, {"result": "?"}]


@pytest.mark.parametrize("res", NOT_LANDED)
def test_an_op_whose_result_did_not_land_is_never_met(res):
    out = reply.of_op("agenda", "add_meeting", res)
    assert out.verdict != V.MET.name, (res, out)


def test_an_op_still_running_when_the_turn_closes_is_started():
    async def run():
        never = asyncio.get_running_loop().create_future()
        try:
            return await reply.of_ops([("agenda::add_meeting", never)], timeout=0.01)
        finally:
            never.cancel()
    assert [o.verdict for o in asyncio.run(run())] == [V.STARTED.name]


def test_a_started_act_adds_no_line_to_the_reply():
    said: list[str] = []
    speech = SimpleNamespace(sanitize=lambda t, **k: t)
    started = [reply.Outcome(V.STARTED.name, "agenda", "add_meeting", object="«Dentist»"),
               reply.Outcome(V.STARTED.name, "errand", "e1", said="Done.")]
    assert reply.owed(started, "Me pongo con ello.") == []
    assert reply.speak(started, "Me pongo con ello.", said.append, speech) == "Me pongo con ello."
    assert said == []
