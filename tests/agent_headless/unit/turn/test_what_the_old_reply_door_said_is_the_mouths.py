"""What the old text channel's reply door added after the model's words, waiting for the mouth that speaks the verdict.

`nucleo/flash/delivery.py` ran after a typed reply and appended what the turn's state said and the words did not:
the rows a waiting reply owed, the line for an errand that is stuck or died while the reply promised it, and the cut of an amount
no source carried. The voice turn never had that door (its words had already streamed), and refactor2710-01 deleted
it with the channel. These are the behaviours, driven through the one turn: strict expected failures where the one
turn lacks them (red the day refactor2710-03 makes the reply say the verdict), a guard where it already has one.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.brain import harness as H

XFAIL = pytest.mark.xfail(reason="refactor2710-03: the mouth speaks the verdict", strict=True)


def _typed(said: str, heard: str, lang: str = "es") -> str:
    with H.Isolated(lang):
        from nucleo.cli import turn
        H.RecordedModel.load({"say": said, "tools": []})
        try:
            res = asyncio.run(turn.run_turn(heard, sid="test-old-reply-door", ingest=False))
        finally:
            turn.reset("test-old-reply-door")
    return str(res.get("reply") or "")


@XFAIL
def test_a_waiting_reply_goes_out_with_the_rows_the_sheet_already_holds(monkeypatch):
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows",
                        lambda n=3: ("pisos de alquiler en Gràcia", ["Piso en Gràcia, calle Verdi — 1.150 €"]))
    reply = _typed("Dame un momento, sigo con ello.", "¿Cómo va lo del piso?")
    assert "calle Verdi" in reply, reply


@XFAIL
def test_an_amount_no_source_carries_does_not_survive_a_live_errand(monkeypatch):
    from nucleo import dispatch
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("un móvil libre", []))
    monkeypatch.setattr(dispatch, "pending_summaries", lambda *a, **k: [{"goal": "un móvil libre", "state": "running"}])
    reply = _typed("Con AT&T sale a 830 dólares.", "¿Y cuánto cuesta?")
    assert "830" not in reply, reply



@XFAIL
def test_a_waiting_reply_over_a_stalled_errand_says_it_is_stuck(monkeypatch):
    import time
    from nucleo import dispatch
    from nucleo.flash import live_blocks
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("una moto de segunda mano", []))
    monkeypatch.setattr(dispatch, "pending_summaries", lambda *a, **k: [
        {"goal": "buscar una moto de segunda mano", "state": "running", "started_at": time.time() - 900,
         "progress_at": time.time() - 600}])
    reply = _typed("Sigo con ello, te aviso en cuanto tenga algo.", "¿Cómo va lo de la moto?")
    assert any(w in reply.lower() for w in ("atasc", "sin avanzar", "parad", "min")), reply

def test_a_promise_over_an_errand_that_just_died_says_it_died(monkeypatch):
    """The one turn already has this one (the death note reaches the turn, and the promise backstop says it): kept as
    the guard on the one turn, not an expected failure."""
    from nucleo.workers import ended
    from nucleo.workers.session import SessionRecord
    monkeypatch.setattr(ended, "_live_goals", lambda: set())
    rec = SessionRecord(task_id="7", goal='Build a new widget called "workouts"', kind="code")
    rec.ok, rec.status, rec.error_class = False, "error", "rate"
    rec.result_summary = "The provider is saturated."
    ended._ENDED_SESSIONS.clear()
    ended._remember_ended(rec)
    said = "Building it in the background — I'll let you know the moment it's ready."
    try:
        reply = _typed(said, "No rush.", lang="en")
    finally:
        ended._ENDED_SESSIONS.clear()
    assert reply.strip() != said, "the reply still promises an errand that died"
    assert "workouts" in reply or "fail" in reply.lower() or "died" in reply.lower() or "couldn" in reply.lower(), reply
