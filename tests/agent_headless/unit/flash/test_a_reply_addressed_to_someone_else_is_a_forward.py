"""A reply addressed to someone else is a FORWARD (demo pass 110, E3, 2026-10-05).

«send the invoice to quinn, tell him we're already trying orion» — the verdict read `forward` at 0.49 (unsure), the
model called `reply` on Orion's receipt with «Hi Quinn — forwarding the receipt…», and the outward gate asked
«Shall I send it?»: a yes would have sent Quinn's note to ORION, the sender. His sentence names one person of the
directory who is not the sender, so the act is the card's `forward` to that person, with the same message.
"""
from __future__ import annotations

import pytest

from nucleo.flash import reply_or_forward as RF

_ORDER = "send the invoice to quinn, tell him we're already trying orion and he should book it"


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """ISOLATED stores — never the operator's real directory or inbox."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as ct
    ct.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    db = {"items": [{"platform": "email", "chatId": "billing@orion.example", "messageId": "m-1",
                     "from": "Orion Billing <billing@orion.example>", "subject": "Your receipt"},
                    {"platform": "email", "chatId": "quinn@example.com", "messageId": "m-2",
                     "from": "Quinn <quinn@example.com>", "subject": "Lunch"}],
          "active_chat": {"platform": "email", "chatId": "billing@orion.example"}}
    store.save("mensajeria", db)
    return store


def test_a_reply_to_the_sender_naming_another_person_is_a_forward(stores):
    got = RF.forward_of("mensajeria", "reply", {"n": 1, "text": "Hi Quinn — forwarding the receipt."}, _ORDER)
    assert got == {"contact": "Quinn", "messageId": "m-1", "text": "Hi Quinn — forwarding the receipt."}, got
    assert RF.instead("mensajeria", "reply", {"n": 1, "text": "x"}, _ORDER) == "forward"


def test_a_reply_to_the_person_he_named_stays_a_reply(stores):
    assert RF.forward_of("mensajeria", "reply", {"n": 2, "text": "Sounds good"}, "reply to quinn, sounds good") is None


def test_no_one_named_or_another_action_changes_nothing(stores):
    assert RF.forward_of("mensajeria", "reply", {"n": 1, "text": "Thanks"}, "reply thanks to that one") is None
    assert RF.forward_of("mensajeria", "send_to", {"contact": "Quinn", "text": "x"}, _ORDER) is None
    assert RF.forward_of("mensajeria", "reply", {"n": 9, "text": "x"}, _ORDER) is None, "an unresolved reply stays"


def test_both_channels_ask_the_rule():
    calls = open("nucleo/flash/tool_executor_widget_calls.py", encoding="utf-8").read()
    turn = open("nucleo/flash/widget_data_turn.py", encoding="utf-8").read()
    assert "_txw._rof.instead(" in calls and "_txw._rof.forward_of(" in calls, "the voice rail runs the forward"
    assert "_rof.forward_of(wid, act, pl, _order)" in turn, "the text channel runs the forward"
    assert turn.index("_rof.forward_of(") < turn.index("_leave_gate.asked_if_leaving("), "before the gate asks"
