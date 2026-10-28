"""A turn that started an errand never says «not done» (refactor2710-99, node 2.902).

Use case `docs-report-lands-as-document__es` (2026-10-28, 1/5): turn 1 «Hecho, te aviso en cuanto lo tenga listo en
pantalla.» + «No lo he hecho: desde aquí no he podido ejecutarlo.»; turn 8 «le acabo de pedir que entregue ya…» + the
same line — and in both the errand WAS running. Whether a turn acted was read from the flags each lane keeps, and a
worker started by a lane none of them counts (a fallback, a relay) left the turn «not done» over a live errand. Now the
consequence door every effect asks (`consequence.passes`) notes what each turn went through, and the turn's end reads
it: a worker started, injected or answered this turn is `started`, never «not done».

Disarm: make `promise_kept.an_errand_was_reached` return False and the first test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import consequence
from nucleo.turn import brief, promise_kept


def _brief(**answers):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in answers.items()}}


@pytest.fixture
def turn(monkeypatch):
    from voice import trace
    monkeypatch.setattr(trace, "current", lambda: "trace-2902")
    monkeypatch.setattr(consequence, "_REACHED", {})
    monkeypatch.setattr(promise_kept, "_not_kept_line", lambda: "NOT-DONE")
    monkeypatch.setattr(promise_kept, "_state_holds", lambda open_ids=None: False)
    said = []

    def _end(reply="Hecho, te aviso en cuanto lo tenga."):
        return promise_kept.say_after(reply, {"v": None}, acted=False, send=said.append,
                                      speech=type("S", (), {"sanitize": staticmethod(lambda t, **k: t)}), window=[],
                                      emit=lambda *a, **k: None,
                                      turn=(_brief(**{brief.REQUEST_KEY: ("order", 0.95)}), [], "hazme el informe",
                                            lambda *a, **k: 0))
    return _end, said


@pytest.mark.parametrize("door", ["worker.spawn", "worker.inject", "worker.answer"])
def test_an_errand_reached_this_turn_is_no_not_done(turn, door):
    end, said = turn
    assert consequence.passes(door, request="hazme el informe")
    assert end() == "" and said == []


def test_without_an_errand_the_owed_act_is_still_not_done(turn):
    end, said = turn
    assert consequence.passes("memory.ingest")             # a door that is no errand
    assert "NOT-DONE" in (end() or " ".join(said))


def test_a_refused_spawn_is_not_a_start(turn, monkeypatch):
    end, said = turn
    monkeypatch.setattr(consequence, "_blocked", type(consequence._blocked)("x", default=frozenset({"worker.spawn"})))
    assert not consequence.passes("worker.spawn")
    assert not consequence.reached("worker.spawn")
