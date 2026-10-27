"""A conversation is named by the contacts he already has — one resolver for every list and header (V2-819).

The operator: a WhatsApp chat titled with a bare phone number that is in his contacts as «mama». Every list and
header named a conversation its own way (the connector's index, the thread's stored name, the first sender, the
id's digits) and none asked his contacts. Now `widgets.directory.namer` is the ONE resolver — the contact holding
this conversation, then the contact whose phone or address the conversation's id carries, then the platform's own
display name, then the bare id — and `widgets/mensajeria/names.py` applies it to the whole view at once.
"""
from __future__ import annotations

import pytest

_MAMA = "34600111222@s.whatsapp.net"


def _namer(people):
    from widgets import directory
    return directory.namer(people)


def test_a_phone_jid_is_named_by_the_contact_holding_that_number():
    name = _namer([{"id": "1", "name": "mama", "phone": "+34 600 11 12 22"}])
    assert name("whatsapp", _MAMA, "Mamá ❤")["name"] == "mama"


def test_a_contact_wins_over_the_platform_name_and_the_platform_name_over_the_id():
    name = _namer([])
    assert name("whatsapp", _MAMA, "Mamá ❤")["name"] == "Mamá ❤"
    assert name("whatsapp", _MAMA, "")["name"] == "34600111222"


def test_an_id_that_is_not_a_phone_is_never_read_as_one():
    """A linked-identity id and a Telegram account id carry digits that are not a phone number."""
    name = _namer([{"id": "1", "name": "mama", "phone": "34600111222"}])
    assert name("whatsapp", "34600111222@lid", "Mamá")["name"] == "Mamá"
    assert name("telegram", "34600111222", "Tg name")["name"] == "Tg name"


def test_two_contacts_with_one_number_are_an_ambiguity_not_a_pick():
    name = _namer([{"id": "1", "name": "mama", "phone": "600111222"},
                   {"id": "2", "name": "casa", "phone": "+34600111222"}])
    assert name("whatsapp", _MAMA, "Mamá")["name"] == "Mamá"


def test_a_learned_channel_and_a_mail_address_name_the_conversation():
    name = _namer([{"id": "1", "name": "Ana", "channels": [{"platform": "whatsapp", "chatId": "999@lid"}]},
                   {"id": "2", "name": "Rowan Pike", "emails": [{"value": "rowan@example.com"}]}])
    assert name("whatsapp", "999@lid", "A.")["name"] == "Ana"
    assert name("email", "rowan@example.com", "R. Pike")["name"] == "Rowan Pike"


def test_a_photo_the_card_cannot_draw_without_a_fetch_is_left_out():
    name = _namer([{"id": "1", "name": "mama", "phone": "600111222", "avatar": "https://lh3.example/p.jpg"},
                   {"id": "2", "name": "Ana", "phone": "611000000", "avatar": "/widgets/contactos/asset/a.jpg"}])
    assert name("whatsapp", _MAMA, "")["photo"] == ""
    assert name("whatsapp", "34611000000@s.whatsapp.net", "")["photo"] == "/widgets/contactos/asset/a.jpg"


@pytest.fixture
def view(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cdb = cd.load_db()
    cdb["contacts"] = [{"id": "c1", "name": "mama", "phone": "+34 600 111 222", "kind": "person"}]
    store.save("contactos", cdb)
    from widgets.mensajeria import data as md
    db = md.load_db()
    db["platforms"]["whatsapp"] = {"status": "connected"}
    db["items"] = [{"platform": "whatsapp", "chatId": _MAMA, "messageId": "W1", "senderId": _MAMA,
                    "from": "+34 600 111 222", "body": "¿Vienes a comer?", "urgencia": "media", "ts": 1761550000}]
    db["threads"] = {f"whatsapp|{_MAMA}": {"name": "+34 600 111 222", "touched": 1761550000, "complete": False,
                                           "msgs": [{"id": "W1", "dir": "in", "who": "+34 600 111 222",
                                                     "body": "¿Vienes a comer?", "ts": 1761550000, "read": False}]}}
    db["active_chat"] = {"platform": "whatsapp", "chatId": _MAMA}
    store.save("mensajeria", db)
    return md


def test_every_list_and_the_header_say_the_contact_name(view):
    v = view.view_data()
    assert [c["name"] for c in v["chats"]] == ["mama"]
    assert v["thread_meta"]["name"] == "mama"
    assert [r["name"] for r in v["chat_list"]["whatsapp"]["rows"]] == ["mama"]
    assert v["items"][0]["from"] == "mama"


def test_his_own_name_on_a_message_he_sent_does_not_title_the_chat(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    import queue
    from connectors.messaging import store as ms
    from widgets.mensajeria import owner
    o = owner._Owner()
    o._out_sub = type("S", (), {"queue": queue.Queue()})()
    o._out_sub.queue.put({"platform": "whatsapp", "chatId": _MAMA, "messageId": "O1", "body": "Sí",
                          "senderName": "Ricart", "chatName": "Ricart", "isGroup": False, "timestamp": 1761550000})
    o._apply_outbound()
    assert ms.load()["threads"][f"whatsapp|{_MAMA}"].get("name", "") == ""
