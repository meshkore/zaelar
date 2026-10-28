"""«Use his Telegram» must reach Rowan, and must not overwrite his real handle (demo pass INIT, 2026-09-28).

The list runner's step «From now on, when I ask you to contact Rowan, use his available Telegram contact»
came back as `set_channel {contactId: "Rowan", platform: "telegram", handle: "@Rowan", preferred: true}`:
  · the NAME sat in the id field and nothing resolved it (the text path only resolved `item`), so the widget
    answered «no encuentro ese contacto» with Rowan on file — the INIT reported 23 of 24;
  · and had it resolved, the invented `@Rowan` would have overwritten his real `@northfund_demo`.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    d.apply_action("add_contact", {"name": "Rowan", "city": "San Mateo", "preferred": "",
                                   "channels": [{"platform": "telegram", "handle": "@northfund_demo",
                                                 "chatId": "1000000017"}]})
    return d


def _rowan(ct):
    return next(c for c in ct.load_db()["contacts"] if c["name"] == "Rowan")


def test_an_invented_name_handle_does_not_overwrite_the_real_one(ct):
    cid = _rowan(ct)["id"]
    r = ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@Rowan",
                                        "preferred": True})
    assert r.get("ok") is True
    e = _rowan(ct)
    tg = next(ch for ch in e["channels"] if ch["platform"] == "telegram")
    assert tg["handle"] == "@northfund_demo" and tg["chatId"] == "1000000017"
    assert e["preferred"] == "telegram", "the preference — what was asked — still lands"


def test_a_real_new_handle_still_replaces(ct):
    cid = _rowan(ct)["id"]
    ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@rowan_sf"})
    assert next(ch for ch in _rowan(ct)["channels"] if ch["platform"] == "telegram")["handle"] == "@rowan_sf"


def test_a_lone_initial_in_a_strangers_name_does_not_tie_with_him(ct):
    """Demo pass INIT, 2026-09-28, with the operator's 2,693 synced contacts: «Rowan» came back AMBIGUOUS
    against «Rebecca H», «Caroline N Farhat» and «uno-e» — each lone letter sat inside «rowan»."""
    for name in ("Rebecca H", "Caroline N Farhat", "uno-e"):
        ct.apply_action("add_contact", {"name": name})
    from widgets import refs
    r = refs.resolve("contactos", "set_channel", "", {"contactId": "Rowan", "platform": "telegram"})
    assert r.ok and r.payload["contactId"] == _rowan(ct)["id"], (r.needs, r.candidates)
