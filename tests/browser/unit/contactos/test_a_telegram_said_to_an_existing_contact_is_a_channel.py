"""A Telegram said for a contact already on file lands as his CHANNEL, by name (demo pass 102, 2026-10-04).

«Save Rowan and Quinn in my contacts: Rowan's Telegram is @rowan_example…» with both already on file: the
model called `add_phone {name: "Rowan", channel: "telegram", handle: "@rowan_example"}`. Two things lost it —
the text channel read an empty `item` as a loose pronoun on a closed card and dropped the call (the voice rail
already took a name in the payload as the reference), and `add_phone` would have saved the @handle as a PHONE.
C5 then had no Telegram for Rowan. The name is the reference, and a messaging handle is a channel.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    d.apply_action("add_contact", {"name": "Rowan"})
    return d


def _rowan(ct) -> dict:
    return next(c for c in ct.load_db()["contacts"] if c["name"] == "Rowan")


def test_add_phone_with_a_telegram_handle_saves_the_channel_not_a_phone(ct):
    cid = _rowan(ct)["id"]
    res = ct.apply_action("add_phone", {"contactId": cid, "channel": "telegram", "handle": "@rowan_example"})
    assert res.get("ok"), res
    e = _rowan(ct)
    assert [(c["platform"], c.get("handle")) for c in e.get("channels") or []] == [("telegram", "@rowan_example")]
    assert not e.get("phones") and not e.get("phone"), "the @handle was stored as a phone number"


def test_a_real_phone_still_goes_to_phones(ct):
    cid = _rowan(ct)["id"]
    assert ct.apply_action("add_phone", {"contactId": cid, "phone": "+34600111222"}).get("ok")
    assert "+34600111222" in str(_rowan(ct).get("phones"))


def test_a_name_in_the_payload_is_the_reference():
    from nucleo.flash import frontend
    assert frontend.payload_ref("contactos", "add_phone", {"name": "Rowan", "channel": "telegram"}) == "Rowan"
    assert frontend.payload_ref("contactos", "add_phone", {"contact": "Rowan"}) == "Rowan"
    assert frontend.payload_ref("contactos", "add_phone", {"contactId": "c1", "name": "Rowan"}) == "c1"
    assert frontend.payload_ref("contactos", "add_contact", {"name": "Rowan"}) == "", \
        "a creation has no row to point at — its name is the new row, not a reference"


def test_a_named_row_on_a_closed_card_is_not_a_loose_pronoun(monkeypatch):
    from nucleo.flash import frontend
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": []})
    assert not frontend.absent_widget_misroute("contactos", "add_phone", "",
                                               payload={"name": "Rowan", "channel": "telegram"})
