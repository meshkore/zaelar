"""A standing rule's grant is read by the exit it names (V2-857 P0-3, architecture audit 2026-11-05).

The rule reader let the model write `may` from «agenda, note, reply, forward, message» while the worker's exit door
read only `message` (`mandate.covers`): «cuando me escriba Quinn, contéstale que estoy de viaje» became
`may: ["reply"]`, the stream session read Quinn's message (tainted) and every reply was asked — the rule was dead.
Now the grant has ONE vocabulary (`nucleo/errands/mandate.MAY`), the reader asks for it, old rows are read as their
act, and the exit door reads the same words.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from nucleo.errands import mandate
from nucleo.workers import exit_gate


@pytest.mark.parametrize("may", [["reply"], ["forward"], ["message"], ["send"]])
def test_every_word_for_a_message_grant_covers_a_message_exit(may):
    rec = SimpleNamespace(mandate={"may": may, "channels": ["whatsapp"]})
    assert exit_gate.under_mandate(rec, "message", "whatsapp")
    assert not exit_gate.under_mandate(rec, "message", "telegram")          # its channel still bounds it


def test_a_grant_nothing_reads_is_no_grant():
    assert mandate.acts(["dance", "agenda", "reply", "reply"]) == ["schedule", "message"]
    assert not exit_gate.under_mandate(SimpleNamespace(mandate={"may": ["dance"]}), "message", "")


def test_the_rule_reader_asks_for_the_one_vocabulary_and_stores_its_words():
    from rules import subscriptions
    assert all(f"- {a}:" in subscriptions._acts() for a, _w, _o in mandate.MAY)
    got = subscriptions.parse('{"topic": "connector.msg", "match": {"name": "Quinn"}, '
                              '"do": "dile que estoy de viaje", "may": ["reply", "agenda"]}')
    assert got["may"] == ["message", "schedule"]
