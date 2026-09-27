"""«Use his Telegram» must reach Ethan, and must not overwrite his real handle (demo pass INIT, 2026-09-28).

The list runner's step «From now on, when I ask you to contact Ethan, use his available Telegram contact»
came back as `set_channel {contactId: "Ethan", platform: "telegram", handle: "@Ethan", preferred: true}`:
  · the NAME sat in the id field and nothing resolved it (the text path only resolved `item`), so the widget
    answered «no encuentro ese contacto» with Ethan on file — the INIT reported 23 of 24;
  · and had it resolved, the invented `@Ethan` would have overwritten his real `@cryptonite_fund`.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    d.apply_action("add_contact", {"name": "Ethan", "city": "San Mateo", "preferred": "",
                                   "channels": [{"platform": "telegram", "handle": "@cryptonite_fund",
                                                 "chatId": "7477656357"}]})
    return d


def _ethan(ct):
    return next(c for c in ct.load_db()["contacts"] if c["name"] == "Ethan")


def test_an_invented_name_handle_does_not_overwrite_the_real_one(ct):
    cid = _ethan(ct)["id"]
    r = ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@Ethan",
                                        "preferred": True})
    assert r.get("ok") is True
    e = _ethan(ct)
    tg = next(ch for ch in e["channels"] if ch["platform"] == "telegram")
    assert tg["handle"] == "@cryptonite_fund" and tg["chatId"] == "7477656357"
    assert e["preferred"] == "telegram", "the preference — what was asked — still lands"


def test_a_real_new_handle_still_replaces(ct):
    cid = _ethan(ct)["id"]
    ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ethan_sf"})
    assert next(ch for ch in _ethan(ct)["channels"] if ch["platform"] == "telegram")["handle"] == "@ethan_sf"


def test_the_name_in_contactId_is_resolved_on_the_text_path(ct, monkeypatch):
    """Through `widget_data_turn.execute` — the path the list runner takes — with the real resolver."""
    from nucleo.flash import widget_data_turn as wdt
    from nucleo.flash import frontend as fe
    from widgets import actions as wa
    import widgets.server_api as sa
    seen = {}

    async def _brain_action(wid, act, pl):
        seen["pl"] = pl
        return ct.apply_action(act, pl)
    monkeypatch.setattr(sa, "brain_action", _brain_action)
    monkeypatch.setattr(fe, "action_mode", lambda w, a: wa.FAST)
    calls = [{"name": "widget_data", "args": {"widget_id": "contactos", "action": "set_channel",
                                               "payload": {"contactId": "Ethan", "platform": "telegram",
                                                           "handle": "@Ethan", "preferred": True}}}]
    asyncio.run(wdt.execute(calls, "use his Telegram"))
    assert seen["pl"]["contactId"] == _ethan(ct)["id"], seen
    assert _ethan(ct)["preferred"] == "telegram"
