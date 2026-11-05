"""The playbook is the worker's, and the harness holds checkpoint 1 (V2-852 T19b, operator 2026-11-05).

His Raquel run: the task entered with the engine's generic `errand`, no end state, and the send could have left with
neither. Now the worker receives the playbook CATALOGUE, names the one its task is (`report playbook`), and an act that
LEAVES the machine — a send, an agent call — is refused until checkpoint 1 is closed; a message also needs its end
state on the row (the harness judges the send by it). Reads are never held. Disarm: `checkpoint_one` returning ''.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.workers import exit_gate
from nucleo.workers.prompts import playbook as pb


def _rec(**kw):
    return SimpleNamespace(task_id="k1", uid="", mandate={}, done_when=None, **kw)


def test_the_brief_carries_the_catalogue_and_how_checkpoint_one_closes():
    text = pb.block(pb.MESSAGE, pb.done_when(pb.MESSAGE))
    for name in pb.NAMES:
        assert f"· {name} —" in text
    assert "report playbook" in text


def test_a_leaving_act_is_refused_until_the_worker_names_its_playbook(monkeypatch):
    monkeypatch.setattr(exit_gate, "leaves", lambda wid, act: True)
    rec = _rec()
    out = exit_gate.gate(rec, {"widget_id": "mensajeria", "action": "send_to",
                               "payload": {"contact": "Rakel Karó", "text": "¿cuándo vuelves?"}})
    assert out.refused and "checkpoint 1" in out.refused
    assert pb.chosen(rec, "errand") == "" and pb.checkpoint_one(rec) == ""


@pytest.mark.parametrize("dw, open_", [(None, True), ({"all": [{"widget": "mensajeria", "field": "last_sent",
                                                                 "expect": "changed"}]}, False)])
def test_a_message_also_needs_its_end_state_on_the_row(dw, open_):
    rec = _rec()
    rec.done_when = dw
    pb.chosen(rec, "message")
    assert bool(pb.checkpoint_one(rec)) is open_


def test_an_unknown_playbook_is_refused_with_the_names():
    rec = _rec()
    why = pb.chosen(rec, "trip-of-a-lifetime")
    assert why and all(n in why for n in pb.NAMES) and not getattr(rec, "playbook_chosen", "")


def test_an_agent_call_waits_for_checkpoint_one_too():
    out = exit_gate.mesh(_rec(), {"agent": "stayfinder", "prompt": "hotel in Rome"})
    assert out.refused and "checkpoint 1" in out.refused
