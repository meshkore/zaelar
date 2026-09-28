"""A message he orders by voice is SEEN being sent (the operator's demo note, 2026-09-28).

«que se vea cómo se lo mandamos y cómo se le da el botón»: a Telegram to Ethan went out in the background and,
without sound, nobody watching could tell anything had happened. Measured here: `send_to` opens that
conversation, holds the queued order for as long as typing the text takes, publishes what is being written for
the card to type, and the queue releases the order only then — once. An email is not typed into a chat."""
from __future__ import annotations

import json
import pathlib
import time

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    cd.apply_action("add_contact", {"name": "Ethan Demo", "email": "ethan@example.com"})
    cid = cd.load_db()["contacts"][0]["id"]
    cd.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ethan_demo",
                                    "chatId": "555001"})
    return md


def test_the_chat_opens_and_the_text_is_published_for_the_card_to_type(box):
    r = box.apply_action("send_to", {"contact": "Ethan", "channel": "telegram", "text": "Moved to 3:15, see you then"})
    assert r["ok"], r
    v = box.view_data()
    assert v["active_chat"] == {"platform": "telegram", "chatId": "555001"}, "his conversation is the one on screen"
    c = v["composing"]
    assert c and c["text"] == "Moved to 3:15, see you then" and c["left_s"] > 0, c


def test_the_order_waits_while_it_is_typed_and_then_leaves_once(box, monkeypatch):
    from connectors.messaging import store as msgstore
    box.apply_action("send_to", {"contact": "Ethan", "channel": "telegram", "text": "Moved to 3:15"})
    assert msgstore.take_pending_send() == [], "released before the card pressed send"
    later = time.time() + 30
    monkeypatch.setattr(msgstore.time, "time", lambda: later)
    got = msgstore.take_pending_send()
    assert [o["text"] for o in got] == ["Moved to 3:15"]
    assert msgstore.take_pending_send() == [], "sent twice"


def test_an_email_is_not_typed_into_a_chat(box):
    from connectors.messaging import store as msgstore
    r = box.apply_action("send_to", {"contact": "ethan@example.com", "channel": "email", "text": "hi"})
    assert r["ok"], r
    assert box.view_data()["composing"] is None
    assert [o["text"] for o in msgstore.take_pending_send()] == ["hi"], "an email leaves at once"


def test_the_voice_order_brings_the_card(box):
    man = json.loads((ENGINE / "widgets/mensajeria/manifest.json").read_text("utf-8"))
    assert "present.mount" in man["actions"]["send_to"].get("effects", [])


def test_the_card_types_it_and_presses_send_only_for_show():
    js = (ENGINE / "widgets/mensajeria/widget.js").read_text("utf-8")
    i = js.index("function _playCompose(")
    body = js[i:js.index("\n}\n", i)]
    assert "ctx.action" not in body, "the order is already queued — the card must not send it a second time"
    assert "_playCompose(c, box, send)" in js and "data.composing" in js
