"""A line owed to a turn is said in THAT turn or not at all; a pass that failed is never said (V2-831 audit A3).

The class: `follow_up_pass.deliver` is the one door for the turn's late lines — the detached confirm-or-correct pass
(R5b), the honest line after a memory write (R1b) and the reply-promise question (R11b). It spoke whenever the line
was ready: a line about «the meeting» landed inside his next turn about something else, and with the agent switched
off. And a detached pass whose stream broke halfway was said as a correction — half a sentence.

The mechanism: a late line belongs to the trace it was born in; once he begins another turn (`trace.his_turn_after`)
or switches the agent off, the door drops it. A failed pass is a SKIP. Variants: a typed turn (`ui`) and a voice turn
(`turno`) both count as moving on; a background trace (`cron`) does not.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.waiting import until

CORRECTION = "Actually, the meeting is at five, not four."


@pytest.fixture
def got(monkeypatch):
    from nucleo import runstate
    from nucleo.flash import dialog
    from voice import observer, proactive
    out = {"said": [], "wall": [], "dropped": []}

    monkeypatch.setattr(proactive, "_speaker", out["said"].append)    # a plain speaker: no task outlives the test
    monkeypatch.setattr(dialog, "note_spoken", lambda text, about="": None)
    monkeypatch.setattr(runstate, "stopped", lambda: False)

    def _emit(kind, label, **k):
        if (k.get("extra") or {}).get("wall"):
            out["wall"].append(k.get("text"))
        if "dropped" in str(label) or "failed" in str(label):
            out["dropped"].append(label)
    monkeypatch.setattr(observer, "emit", _emit)
    return out


def _deliver_in(origin_then: str, *, later: str | None, line: str = CORRECTION) -> bool:
    """Begin a turn, maybe begin another one (`later` origin), then deliver a line from inside the FIRST turn's context."""
    import contextvars

    from nucleo.flash import follow_up_pass as fup
    from voice import trace
    trace.begin("when is the meeting", origin=origin_then)
    ctx = contextvars.copy_context()                     # the late line's task carries its turn's context
    if later:
        trace.begin("open the weather", origin=later)
    return ctx.run(fup.deliver, line)


@pytest.mark.parametrize("later", ["turno", "ui"])
def test_a_line_whose_turn_he_left_is_dropped(got, later):
    assert _deliver_in("turno", later=later) is False
    assert got["said"] == [] and got["wall"] == [] and got["dropped"], "a late line was said into another turn"


def test_a_line_in_its_own_turn_is_said(got):
    assert _deliver_in("turno", later=None) is True
    assert got["wall"] == [CORRECTION]


def test_a_background_trace_is_not_him_moving_on(got):
    assert _deliver_in("turno", later="cron") is True


def test_with_the_agent_switched_off_nothing_is_said(got, monkeypatch):
    from nucleo import runstate
    monkeypatch.setattr(runstate, "stopped", lambda: True)
    assert _deliver_in("turno", later=None) is False and got["wall"] == []


def test_a_pass_that_failed_halfway_is_never_said(got, monkeypatch):
    import nucleo.llm.fast_client as fc
    from nucleo.flash import follow_up_pass as fup
    from voice import trace

    class _Broken:
        def stream(self, messages, **k):
            async def _gen():
                yield "Actually, the meeting is at"
                raise ConnectionError("stream cut")
            return _gen()
    monkeypatch.setattr(fc, "FastClient", _Broken)

    async def _go():
        trace.begin("when is the meeting", origin="turno")
        assert fup.detach("SYS", "user", "It's at four.", None, 220, "op answer compose", lambda *a, **k: None)
        await until(lambda: not fup._LIVE, "the detached pass to end", timeout_s=3.0)
    asyncio.run(_go())
    assert got["said"] == [] and got["wall"] == [], "half a correction was said"
