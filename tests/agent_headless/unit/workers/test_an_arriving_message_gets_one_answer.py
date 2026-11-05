"""One arriving message, one answer (V2-857 P0-4, architecture audit 2026-11-05).

Two consumers read an arriving message: the messaging card (store, triage, the autoresponder) and the event pump
(a waiting task, an errand's thread, his standing rules). «Cuando me escriba Quinn, dile que estoy de viaje» AND the
«estoy fuera» autoresponder both answered Quinn. The autoresponder now yields to whoever else owns the message
(`flow_events.owned`, no model call): a waiting task, a claimant, or a rule whose declared fields it carries.
"""
from __future__ import annotations

import pytest

from nucleo import events
from nucleo.turn import flow_events


@pytest.fixture
def rule(monkeypatch):
    from rules import subscriptions as subs
    row = {"key": subs.KEY, "value": {"topic": events.CONNECTOR_MSG, "match": {"name": "Quinn"}, "may": ["message"]}}
    monkeypatch.setattr(subs, "rows", lambda topic: [row] if topic == events.CONNECTOR_MSG else [])
    monkeypatch.setattr(flow_events, "_waiting_row", lambda ev: None)
    monkeypatch.setattr(flow_events, "_CLAIMANTS", {})
    return row


@pytest.mark.parametrize("body", ["¿estás en casa?", "are you home?"])
def test_a_message_his_rule_names_is_the_rules(rule, body):
    ev = events.of_message({"platform": "whatsapp", "chatId": "c1", "senderName": "Quinn", "body": body})
    assert flow_events.owned(ev) == "rule"


def test_a_message_nobody_owns_is_the_autoresponders(rule):
    ev = events.of_message({"platform": "whatsapp", "chatId": "c2", "senderName": "Rowan", "body": "hola"})
    assert flow_events.owned(ev) == ""


def test_the_autoresponder_yields_to_the_owner(rule, monkeypatch):
    from widgets.mensajeria.owner import apply
    assert apply._owned_elsewhere("whatsapp", {"chatId": "c1", "senderName": "Quinn", "body": "x"}) == "rule"
    monkeypatch.setattr(flow_events, "owned", lambda ev: "")     # disarm: nobody else owns it → it answers
    assert apply._owned_elsewhere("whatsapp", {"chatId": "c1", "senderName": "Quinn", "body": "x"}) == ""
    import inspect
    assert "_owned_elsewhere(platform, it)" in inspect.getsource(apply)
