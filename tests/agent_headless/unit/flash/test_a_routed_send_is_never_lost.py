"""A send the turn routed is never lost (V2-852 M2, CRIT-T2b).

An act that leaves is the turn's commission, and that commission is one slot many doors clear or claim: a close
backstop cancels a «spurious» escalation, a turn that answers a waiting task opens no errand of its own, a model
call claims the slot first with a narrower request («search hotels in Paris» while the same sentence also said «and
tell Raquel I land on Thursday»). The routed send is kept in its own slot and the launch folds it back
(`nucleo/turn/routed_sends.keep`), whatever happened to the commission on the way.
"""
from __future__ import annotations

import inspect

import pytest

from nucleo.turn import routed_sends

SEND_ES = "búscame hotel en París y dile a Raquel que llego el jueves"
SEND_EN = "find me a hotel in Paris and tell Raquel I land on Thursday"


def _req(said: str, *, v=None, more=()):
    req = {"v": v, "more": list(more), "surface": {}}
    routed_sends.note(req, "mensajeria", "send_to", said)
    return req


@pytest.mark.parametrize("said", [SEND_ES, SEND_EN])
def test_a_commission_a_guard_cleared_comes_back_as_the_send(said):
    req = _req(said)                    # the routed send set `v`, then a backstop cleared it
    assert routed_sends.keep(req, {"v": None}, False) == ["commission"] and req["v"] == said


@pytest.mark.parametrize("said", [SEND_ES, SEND_EN])
def test_a_commission_claimed_by_another_request_gets_the_send_beside_it(said):
    req = _req(said, v="search hotels in Paris")
    assert routed_sends.keep(req, {"v": None}, False) == ["more"] and req["more"] == [said]


def test_a_commission_that_already_carries_his_words_is_not_doubled():
    req = _req(SEND_EN, v=SEND_EN)
    assert routed_sends.keep(req, {"v": None}, False) == ["carried"] and req["more"] == []


def test_his_words_that_reached_a_live_worker_start_nothing_beside_it():
    req = _req(SEND_EN)
    assert routed_sends.keep(req, {"v": "answer"}, False) == ["reached"] and req["v"] is None


def test_a_turn_that_stopped_a_worker_starts_the_send_on_its_own_row(monkeypatch):
    from nucleo.request import ask_outside_door
    started = []
    monkeypatch.setattr(ask_outside_door, "to_message_task",
                        lambda wid, act, said, **k: started.append((wid, act, said, k.get("src"))) or 7)
    req = _req(SEND_EN)
    assert routed_sends.keep(req, {"v": "stop"}, False) == ["own-row"]
    assert started == [("mensajeria", "send_to", SEND_EN, "routed")]


def test_a_replace_beside_a_stop_launches_the_send_with_it():
    req = _req(SEND_EN)
    assert routed_sends.keep(req, {"v": "stop"}, True) == ["commission"] and req["v"] == SEND_EN


def test_the_launch_folds_the_sends_before_it_decides_what_starts():
    from nucleo.turn import pipeline_errands
    src = inspect.getsource(pipeline_errands.launch_the_errands)
    assert "_routed_sends.keep(" in src
    assert src.index("_routed_sends.keep(") < src.index('if escalate_req["v"] is not None and (not worker_acted["v"]')


def test_the_turns_leaving_call_notes_its_send():
    from nucleo.flash import tool_executor_widget_calls as calls
    req = {"v": None}
    assert calls._leaving_is_a_task("mensajeria", "send_to", SEND_ES, req, lambda *a, **k: None)
    assert [s["text"] for s in req["sends"]] == [SEND_ES]


def test_disarmed_a_cleared_commission_loses_the_send(monkeypatch):
    """Disarm: no fold (the state before this mechanism) → the cleared commission launches nothing."""
    monkeypatch.setattr(routed_sends, "_carried", lambda *_a: True)
    req = _req(SEND_EN, v="search hotels in Paris")
    routed_sends.keep(req, {"v": None}, False)
    assert req["more"] == [], "the disarm did not take"
