"""The commissioning turn's READING rides with its task (V2-852, after the audit of 2026-11-05).

Since an act that leaves is a task (CRIT-T2b), the worker does the send with no turn of its own: what the act needs
from his sentence — the channel he named, his sure order over the row he saw — was read on Flash's brief and lost on
the way, one wire at a time (the channel was the open one: `message_channel.his_channel` read a brief the worker never
had). Now the brief's verdicts are frozen once on the task (`nucleo/turn/brief.carried`), kept on the record
(`rec.reading`) and revived at the worker's exit door for the same readers Flash uses. ES and EN words alike: the
reading is the verdict, never his words.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.turn import brief as tb


def _brief(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


def test_a_reading_is_plain_data_and_revives_for_every_reader():
    from nucleo.turn import verdicts
    carried = tb.carried(_brief(message_channel=("whatsapp", 0.97), request_type=("order", 1.0)))
    import json
    assert json.loads(json.dumps(carried)) == carried                 # it travels on the bus as plain data
    turn = tb.revived(carried)
    assert verdicts.read(turn, "message_channel", None)[0] == "whatsapp"
    assert tb.carried({"event": threading.Event(), "result": {}}) == {}   # a brief still in flight carries nothing
    assert tb.revived({}) is None


@pytest.fixture
def door(monkeypatch):
    from nucleo.acts import card, message
    from nucleo.workers import exit_gate, taint
    from nucleo.workers.prompts import playbook
    from widgets import contract
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a: None)
    monkeypatch.setattr(card, "licence", lambda *a, **k: SimpleNamespace(verdict=card.RUN))
    monkeypatch.setattr(message, "his_recipient", lambda wid, act, inner, said, **k: inner)
    monkeypatch.setattr(taint, "tainted", lambda rec: False)
    from nucleo.acts import message_channel
    monkeypatch.setattr(message_channel, "_declares_channel", lambda *a: True)
    return exit_gate


@pytest.mark.parametrize("said", ["mándale a Quinn por whatsapp que llego tarde", "tell Quinn on whatsapp I'm late"])
def test_the_channel_he_named_reaches_the_worker_send(door, said):
    rec = SimpleNamespace(task_id="w1", uid="", reading=tb.carried(_brief(message_channel=("whatsapp", 0.97))),
                          mandate={}, goal=said)
    ex = door.gate(rec, {"widget_id": "mensajeria", "action": "send_to",
                         "payload": {"contact": "Quinn", "text": "late", "channel": "telegram"}})
    assert ex.payload["payload"]["channel"] == "whatsapp", ex


def test_disarmed_a_task_with_no_reading_keeps_the_models_channel(door):
    rec = SimpleNamespace(task_id="w2", uid="", reading={}, mandate={}, goal="tell Quinn I'm late")
    ex = door.gate(rec, {"widget_id": "mensajeria", "action": "send_to",
                         "payload": {"contact": "Quinn", "text": "late", "channel": "telegram"}})
    assert ex.payload["payload"]["channel"] == "telegram"


def test_the_escalation_carries_the_turns_reading():
    import inspect
    from nucleo.dispatch import session
    from nucleo.turn import pipeline_errands
    assert '"reading": _tb.carried(_brief)' in inspect.getsource(pipeline_errands.launch_the_errands)
    assert 'rec.reading = dict(task.context.get("reading")' in inspect.getsource(session)
