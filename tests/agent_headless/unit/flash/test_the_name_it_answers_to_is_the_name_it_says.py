"""The assistant answers to the name it calls itself — and the name changes by a VERDICT, failing CLOSED (CRIT-V8).

Measured on the operator's engine, 2026-09-12: every kickoff introduced the agent as «Johnny» from a memory pill while
`state.assistant_name` was still «Zaelar», so «Hey, Johnny.» was ruled ambient thirty-five times. Then a regex read the
rename from his sentence (V2-682) — and a regex reading a name is the class CRIT-V8 forbids. Since refactor2710-07 the
brief's `identity_change` question decides WHETHER his turn renames the assistant (sure ≥ 0.85), and the NEW NAME is
the model's declared argument (`set_style_directive.name`): absent, unsure or nameless → nothing changes. A rename
then writes the structured fact the attention gate reads.

Disarm: lower `identity.SURE` to 0.0 and the unsure-verdict test goes red.
"""
import asyncio
import threading

import pytest

from nucleo.turn import identity


def _brief(choice, conf):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {identity.KEY: {"choice": choice, "confidence": conf}}}


@pytest.fixture
def world(monkeypatch):
    from voice import attention
    monkeypatch.setattr(attention, "_state", dict(attention._state), raising=False)
    wrote, events = {}, []
    import memory.api as mem
    monkeypatch.setattr(mem, "set_state", lambda fields: wrote.update(fields))
    from config import settings as cfg
    monkeypatch.setattr(cfg, "update", lambda fields: wrote.update(fields))
    yield wrote, (lambda *a, **k: events.append(a)), events
    attention.set_assistant_name("")


def test_a_sure_rename_verdict_with_the_models_name_renames(world):
    wrote, emit, events = world
    from voice import attention
    assert not attention.has_wakeword("Hey, Johnny.")          # the deaf state of 2026-09-12
    assert asyncio.run(identity.settle(_brief("rename", 0.95), "Johnny", emit)) == "rename"
    assert wrote == {"assistant_name": "Johnny"}, "written where the gate reads it, never as a pill or a rule"
    assert attention.has_wakeword("Hey, Johnny. Show me my agenda.")
    assert "zaelar" in [w.lower() for w in attention.wakewords()], "the shipped name keeps working"
    assert any(a[1] == "🏷️ zaelar se renombra" for a in events)


@pytest.mark.parametrize("brief,name", [
    (_brief("rename", 0.7), "Johnny"),     # unsure: fails closed
    (None, "Johnny"),                      # no verdict at all
    (_brief("none", 0.99), "Johnny"),      # the brief says this is no rename
    (_brief("rename", 0.95), ""),          # sure, but the model declared no name: nothing guessed from his words
])
def test_anything_short_of_a_sure_verdict_and_a_declared_name_renames_nothing(world, brief, name):
    wrote, emit, _events = world
    assert asyncio.run(identity.settle(brief, name, emit)) == ""
    assert "assistant_name" not in wrote


def test_the_attention_mode_is_a_verdict_too(world):
    wrote, emit, _events = world
    assert asyncio.run(identity.settle(_brief("attention_name_only", 0.9), "", emit)) == "smart"
    assert wrote == {"attention_mode": "smart"}
    assert asyncio.run(identity.settle(_brief("attention_always", 0.9), "", emit)) == "always"


def test_the_question_rides_every_brief():
    from nucleo.turn import brief
    assert identity.KEY in brief.keys()
    assert brief.build("llámate Johnny", open_ids=[])[identity.KEY]["criteria"] == identity.CHOICES
