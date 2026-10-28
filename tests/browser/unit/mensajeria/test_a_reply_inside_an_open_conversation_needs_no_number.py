"""«Contéstale que sí» inside an open conversation goes to THAT conversation — no number needed.

Measured with the messaging decision bank (2026-10-23): with Marta's chat open the model called `reply_message`
without `n` (it was already inside the chat) and the reply was lost — «Perdona, se me ha ido» 3/3. Now `n` is
optional: without it the card resolves the open conversation, the same way its compose box does. And the text
channel mirrors the voice tool (`reply_message` → mensajeria `reply`), or it could not see the decision at all.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data as md
    db = md.load_db()
    db["items"] = [{"platform": "whatsapp", "chatId": "34600000001@s.whatsapp.net", "messageId": "WA1",
                    "senderId": "34600000001@s.whatsapp.net", "from": "Marta", "body": "¿Quedamos a las 9?"}]
    db["active_chat"] = {"platform": "whatsapp", "chatId": "34600000001@s.whatsapp.net"}
    store.save("mensajeria", db)
    return md


def test_no_number_and_a_conversation_open_replies_there(box):
    box.apply_action("reply", {"text": "Sí, a las 9"})
    rep = box.load_db()["pending_reply"][-1]
    assert rep["chatId"] == "34600000001@s.whatsapp.net" and rep["text"] == "Sí, a las 9"


def test_no_number_and_nothing_open_still_refuses(box):
    db = box.load_db()
    db["active_chat"] = None
    box.store.save("mensajeria", db)
    r = box.apply_action("reply", {"text": "Sí"})
    assert r["ok"] is False and not box.load_db().get("pending_reply")


def test_the_voice_tool_no_longer_requires_a_number():
    from nucleo.flash.router_catalog import TOOLS
    spec = next(t for t in TOOLS if t["function"]["name"] == "reply_message")
    assert spec["function"]["parameters"]["required"] == ["text"]


def test_the_voice_tool_without_a_number_reaches_the_card():
    from nucleo.flash import tool_executor_calls as tx
    calls = []
    tx._t_reply_message(args={"text": "Sí"}, _apply_widget_data=lambda w, a, p: calls.append((w, a, p)),
                        _say=lambda: None, _tool_fired=set(), clarify={})
    assert calls == [("mensajeria", "reply", {"text": "Sí"})]
