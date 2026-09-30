"""A data-op with no item is resolved from the operator's own sentence in the TEXT channel too (demo pass 31, INIT).

«From now on, when I ask you to contact Rowan, use his available Telegram contact» reached contactos as
`set_channel {platform: telegram, preferred: true}` — no contact — and was refused with Rowan on file; the list
reported «25 of 26 done. I couldn't do: Contact Rowan on Telegram». The voice path has passed his sentence to
`refs.resolve(order=…)` since V2-708; the text channel's executor never did.
"""
import asyncio
import tempfile

import pytest

from nucleo.flash import widget_data_turn as WDT

_SAID = ("From now on, when I ask you to contact Rowan, use his available Telegram contact unless I specify "
         "another channel.")


@pytest.fixture
def rail(monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", tempfile.mkdtemp())
    from widgets.contactos import data as C
    C.apply_action("add_contact", {"name": "Rowan", "channels": [{"platform": "telegram", "handle": "@cryptonite_fund"}]})
    C.apply_action("add_contact", {"name": "Quinn", "email": "contact@example.com"})
    seen = []

    async def _brain_action(wid, act, payload):
        seen.append((wid, act, payload))
        return {"ok": True}
    import widgets.server_api as _sa
    monkeypatch.setattr(_sa, "brain_action", _brain_action)
    from widgets import actions as _wa
    monkeypatch.setattr("nucleo.flash.frontend.action_mode", lambda wid, act: _wa.FAST)
    return seen


def test_the_contact_comes_from_his_sentence(rail):
    op = {"name": "widget_data", "args": {"widget_id": "contactos", "action": "set_channel",
                                          "payload": {"platform": "telegram", "preferred": True}}}
    asyncio.run(WDT.execute([op], text=_SAID))
    assert rail and rail[0][2].get("contactId") == "c1", rail
