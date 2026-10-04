"""A contact keeps the channel the model gave FLAT — `channel` + `handle`, or `telegram: @x` (2026-10-04).

Demo pass 101, INIT: «Save Ethan… Ethan's Telegram is @cryptonite_fund». The model called add_contact with
`{"name": "Ethan", "channel": "telegram", "handle": "@cryptonite_fund"}` — a sensible shape — and the card only
read the `channels: [...]` list, so Ethan was saved with no Telegram and the demo's message to him had nowhere
to go. The flat shapes now land as the same channel row.
"""
from __future__ import annotations

from widgets.contactos import model


def test_channel_and_handle_flat():
    rows = model.channels_in({"name": "Ethan", "channel": "telegram", "handle": "@cryptonite_fund"})
    assert [(r["platform"], r.get("handle")) for r in rows] == [("telegram", "@cryptonite_fund")], rows


def test_a_platform_named_as_its_own_key():
    rows = model.channels_in({"name": "Ethan", "telegram": "@cryptonite_fund"})
    assert [(r["platform"], r.get("handle")) for r in rows] == [("telegram", "@cryptonite_fund")], rows


def test_the_list_shape_still_wins():
    rows = model.channels_in({"channels": [{"platform": "whatsapp", "handle": "+34600000000"}],
                              "channel": "telegram", "handle": "@x"})
    assert [r["platform"] for r in rows] == ["whatsapp"], rows


def test_an_email_alone_is_not_a_channel_row_here():
    assert model.channels_in({"name": "Andrew", "email": "ago@proars.com"}) == []
