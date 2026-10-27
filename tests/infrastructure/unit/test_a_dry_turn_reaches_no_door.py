"""A dry turn reaches no consequence door (refactor2710-01 T-02).

The text channel and the decision bank run the SAME voice turn as the microphone; what makes them dry is not a second
turn but `nucleo.consequence`: every effect that leaves a turn passes one funnel, every funnel asks
`consequence.passes(<door>)`, and `dry_turn()` closes them all. Two things are held here:
- every door in the table names a funnel whose source asks for THAT door — a funnel that stops asking is a door left
  open in every dry run (disarm: delete the `passes("cron.create", …)` line in `nucleo/scheduler.py` → red);
- inside a dry turn the funnels do nothing and the ledger names what each would have done.
"""
from __future__ import annotations

import asyncio
import importlib
import inspect

import pytest

from nucleo import consequence


@pytest.mark.parametrize("door", sorted(consequence.DOORS))
def test_every_door_is_asked_by_its_funnel(door):
    module, func = consequence.DOORS[door].split(":")
    fn = getattr(importlib.import_module(module), func)
    src = inspect.getsource(inspect.unwrap(fn))
    assert f'passes("{door}"' in src, f"{module}.{func} no longer asks consequence.passes({door!r}) — the door is open"


def test_an_undeclared_door_is_refused():
    with pytest.raises(KeyError):
        consequence.passes("somewhere.new")


def test_a_dry_turn_closes_every_door_but_memory_when_ingesting():
    with consequence.dry_turn(ingest=True) as ledger:
        assert not consequence.passes("worker.spawn", request="book a table")
        assert consequence.passes("memory.ingest")
    with consequence.dry_turn(ingest=False):
        assert not consequence.passes("memory.ingest")
    assert consequence.passes("worker.spawn"), "outside a dry turn every door is open"
    assert [e["door"] for e in ledger] == ["worker.spawn", "memory.ingest"]
    assert ledger[0]["blocked"] and ledger[0]["request"] == "book a table"


def test_inside_a_dry_turn_the_funnels_do_nothing(monkeypatch):
    from nucleo import scheduler
    from nucleo.flash import escalate
    from widgets import server_api

    published, dispatched = [], []
    monkeypatch.setattr(escalate, "_emit_bus", lambda topic, payload: published.append(topic))
    monkeypatch.setattr(server_api, "_dispatch", lambda *a, **k: dispatched.append(a))
    monkeypatch.setattr(scheduler, "_journal", None)          # a real create would touch it and fail loudly

    async def turn():
        with consequence.dry_turn() as ledger:
            out = await server_api.brain_action("agenda", "add_meeting", {"title": "x"})
            made = scheduler.create("call mum", "in 10 minutes", name="mum")
            return out, made, ledger

    out, made, ledger = asyncio.run(turn())
    assert out.get("dry") and not dispatched, "a dry data-op reached the widget"
    assert made.get("dry"), "a dry turn scheduled a reminder"
    assert {e["door"] for e in ledger} >= {"widget.data", "cron.create"}
    assert not published
