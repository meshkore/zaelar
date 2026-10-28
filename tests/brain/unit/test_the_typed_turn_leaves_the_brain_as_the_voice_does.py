"""The typed channel reports its act and never writes it into the brain (refactor2710-01, review H1).

`brain._last_action` belongs to the voice turn: it writes «search» after a search and reads it to resolve «open it»
on the next turn. `nucleo/cli/turn.py` used to overwrite it with its own report («canvas:show:x», «chat»), so a third
turn resolved differently typed than spoken. Three turns — a search, a show, a talk — must leave the brain exactly as
the voice turn leaves it. Disarm: write `brain._last_action = action` back in `cli.turn.run_turn` → red.
"""
from __future__ import annotations

import asyncio

from tests.brain import harness as H


def test_a_typed_turn_does_not_overwrite_the_voice_turns_last_action():
    case = {"id": "h1", "lang": "en", "phrase": "x", "source": "review H1", "screen": {"open": []}, "expect": "talk"}
    with H.Isolated("en") as iso:
        iso.seed(case)
        from nucleo.cli import turn
        try:
            brain = turn._brain("h1")
            brain._last_action = "search"                   # what the voice turn left after a search
            H.RecordedModel.load({"say": "Sure, here you go."})
            res = asyncio.run(turn.run_turn("Tell me something nice.", sid="h1", ingest=False))
            assert res.get("ok") and res.get("action") == "chat", res
            assert brain._last_action == "search", "the typed channel wrote its report into the voice turn's state"
        finally:
            turn.reset("h1")
