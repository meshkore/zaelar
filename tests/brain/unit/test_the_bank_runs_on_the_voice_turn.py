"""The decision bank runs on the VOICE turn, typed and dry (refactor2710-01 T-02).

`nucleo/cli/turn.py` drives `NucleoLLMStream` without a room. A recorded case through it must decide what the voice
turn decides and reach no door: every consequence it met is in the ledger, closed. Disarm: run the turn outside
`consequence.dry_turn` in `cli.turn.run_turn` (`policy = consequence.recorded()`) → the ledger shows open doors.
"""
from __future__ import annotations

import asyncio

from tests.brain import harness as H


def _case(cid):
    return next(c for c in H.load_cases() if c["id"] == cid)


def test_a_recorded_case_decides_on_the_voice_turn():
    out = H.run_case(_case("demo-v7-stop-it-and-close-the-video"))
    assert not out.error and out.decision == "close youtube", (out.decision, out.error)


def test_the_typed_dry_turn_reaches_no_door():
    case = _case("demo-v2-play-video-number-2")
    with H.Isolated(case["lang"]) as iso:
        iso.seed(case)
        from nucleo.cli import turn
        try:
            res = asyncio.run(turn.run_turn(case["phrase"], sid="bank:dry", ingest=False, execute=False))
        finally:
            turn.reset("bank:dry")
    doors = res.get("consequences") or []
    assert res.get("action") == "widget_data:youtube:play_item", res.get("action")
    assert doors and all(d["blocked"] for d in doors), f"a dry turn opened a door: {doors}"


def test_the_typed_turn_builds_no_livekit_stream(monkeypatch):
    """`cli.turn` borrows the stream's turn instead of building an `LLMStream` (its own task, its retries that would
    re-run the turn's doors). Disarm: drive it through `brain.chat(...)` again → this raises."""
    from voice.engine.llm.providers import nucleo

    def _no_stream(*_a, **_k):
        raise AssertionError("the typed channel built a LiveKit stream")
    monkeypatch.setattr(nucleo.NucleoLLMStream, "__init__", _no_stream)
    out = H.run_case(_case("demo-v7-stop-it-and-close-the-video"))
    assert not out.error and out.decision == "close youtube", (out.decision, out.error)
