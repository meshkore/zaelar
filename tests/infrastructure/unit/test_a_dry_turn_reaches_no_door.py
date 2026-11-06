"""A dry turn reaches no consequence door (refactor2710-01 T-02).

The text channel and the decision bank run the SAME voice turn as the microphone; what makes them dry is not a second
turn but `nucleo.consequence`: every effect that leaves a turn passes one funnel, every funnel asks
`consequence.passes(<door>)`, and `dry_turn()` closes them all. Two things are held here:
- every door in the table names a funnel whose source asks for THAT door — a funnel that stops asking is a door left
  open in every dry run (disarm: delete the `@consequence.door("cron.create", …)` line over `nucleo/pulse/scheduler.create` → red);
- inside a dry turn the funnels do nothing and the ledger names what each would have done.
"""
from __future__ import annotations

import importlib
import inspect

import pytest

from nucleo import consequence


@pytest.mark.parametrize("door", sorted(consequence.DOORS))
def test_every_door_is_asked_by_its_funnel(door):
    module, func = consequence.DOORS[door].funnel.split(":")
    fn = getattr(importlib.import_module(module), func)
    asks = getattr(fn, "__door__", None) == door or f'passes("{door}"' in inspect.getsource(inspect.unwrap(fn))
    assert asks, f"{module}.{func} no longer asks door {door!r} (decorator or `passes`) — the door is open"


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
