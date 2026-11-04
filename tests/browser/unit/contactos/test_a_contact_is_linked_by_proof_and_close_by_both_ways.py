"""V2-849 step 1 · a contact is linked to a conversation by PROOF, and how close it is counts BOTH directions.

Measured on a real directory (2,706 contacts imported from an address book): the few WhatsApp conversations linked to
a contact were linked by display name, never by number — WhatsApp now addresses people by linked identities (`@lid`)
whose digits are NOT a phone, and two readers took them as one: the address-book import made «+<lid>» a phone, and
the inbound learner suffix-matched those digits against stored numbers. A stranger could be linked to whoever shared
the suffix, and the person he saved never was. And closeness only counted what CAME IN: someone he writes to every
week who never answers looked like a stranger, and his default channel was the one people wrote to him on.

The rules, each one door:
  · only an id that IS a number is a phone (`directory._phone_of`), in the importer and in the learner alike;
  · a link made only by display name is kept and marked `linked_by: name` (the weakest proof);
  · every message he writes to a person (here or from his phone) counts as traffic on that channel;
  · the default channel is his own choice, else the one with more traffic both ways, else — a tie — nobody (ask).
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    return d


@pytest.fixture
def dr():
    from widgets import directory
    return directory


def _one(ct, name: str) -> dict:
    return next(c for c in ct.load_db()["contacts"] if c["name"] == name)


def _wa(c: dict) -> dict:
    return next(ch for ch in c.get("channels") or [] if ch["platform"] == "whatsapp")


# ── only a number is a phone ──────────────────────────────────────────────────────────────────────────────

def test_a_linked_identity_whose_digits_end_like_his_number_is_not_him(ct, dr):
    ct.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    assert dr.note_inbound("whatsapp", {"chatId": "98765680762886@lid", "senderId": "98765680762886@lid",
                                        "from": "Someone Else"}) is False
    assert not _one(ct, "Raquel Jofre").get("channels")


def test_a_phone_address_is_proof(ct, dr):
    ct.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    assert dr.note_inbound("whatsapp", {"chatId": "34680762886@s.whatsapp.net",
                                        "senderId": "34680762886@s.whatsapp.net", "from": "Raquel"}) is True
    ch = _wa(_one(ct, "Raquel Jofre"))
    assert ch["chatId"] == "34680762886@s.whatsapp.net" and "linked_by" not in ch


def test_a_telegram_account_number_is_not_a_phone_either(ct, dr):
    """The same class on another channel: a Telegram account id is an account number."""
    ct.apply_action("add_contact", {"name": "Ana Ruiz", "phone": "+34 611 222 333"})
    assert dr.note_inbound("telegram", {"chatId": "9934611222333", "senderId": "9934611222333",
                                        "from": "Nobody"}) is False


def test_a_link_made_only_by_the_display_name_is_kept_and_marked(ct, dr):
    ct.apply_action("add_contact", {"name": "Merce"})
    assert dr.note_inbound("whatsapp", {"chatId": "72061011628109@lid", "senderId": "72061011628109@lid",
                                        "from": "Merce"}) is True
    assert _wa(_one(ct, "Merce"))["linked_by"] == "name"


def test_the_address_book_import_never_makes_a_phone_of_a_linked_identity():
    from connectors.whatsapp.service import directory as wa
    lid = wa._wa_person({"id": "98765680762886@lid", "name": "Raquel"})
    assert lid["phone"] == "" and lid["channels"][0]["handle"] == "98765680762886@lid"
    pn = wa._wa_person({"id": "98765680762886@lid", "name": "Raquel", "phoneNumber": "34680762886@s.whatsapp.net"})
    assert pn["phone"] == "+34680762886"
    jid = wa._wa_person({"id": "34680762886@s.whatsapp.net", "name": "Raquel"})
    assert jid["phone"] == "+34680762886"


# ── closeness and the default channel count both directions ──────────────────────────────────────────────

def test_what_he_writes_counts_as_traffic_on_that_conversation(ct, dr):
    ct.apply_action("add_contact", {"name": "Pablo Sabin", "phone": "+34 600 000 001"})
    dr.note_inbound("whatsapp", {"chatId": "34600000001@s.whatsapp.net", "senderId": "34600000001@s.whatsapp.net",
                                 "from": "Pablo"})
    assert dr.note_reached("whatsapp", "34600000001@s.whatsapp.net", ts=1793800000.0) is True
    ch = _wa(_one(ct, "Pablo Sabin"))
    assert ch["volume"] == 2 and ch["last_seen"] == 1793800000.0


def test_a_conversation_nobody_holds_teaches_nothing(ct, dr):
    ct.apply_action("add_contact", {"name": "Pablo Sabin"})
    assert dr.note_reached("whatsapp", "34999@s.whatsapp.net") is False
    assert not _one(ct, "Pablo Sabin").get("channels")


def test_the_default_channel_is_where_the_conversation_happens(ct, dr):
    ct.apply_action("add_contact", {"name": "Lucía", "email": "lucia@example.com", "phone": "+34 600 000 002"})
    dr.note_inbound("telegram", {"chatId": "555", "senderId": "@lucia", "from": "Lucía"})
    for _ in range(3):
        dr.note_reached("telegram", "555")
    c = _one(ct, "Lucía")
    assert dr.channel_for(c)["platform"] == "telegram", "four messages on Telegram, none by mail"


def test_his_own_choice_of_channel_wins_over_the_traffic(ct, dr):
    ct.apply_action("add_contact", {"name": "Lucía", "email": "lucia@example.com", "preferred": "email"})
    dr.note_inbound("telegram", {"chatId": "555", "senderId": "@lucia", "from": "Lucía"})
    dr.note_reached("telegram", "555")
    assert dr.channel_for(_one(ct, "Lucía"))["platform"] == "email"


def test_a_tie_between_two_channels_he_uses_is_a_question_not_a_coin(ct, dr):
    ct.apply_action("add_contact", {"name": "Iván", "phone": "+34 600 000 003"})
    dr.note_inbound("telegram", {"chatId": "777", "senderId": "@ivan", "from": "Iván"})
    dr.note_inbound("whatsapp", {"chatId": "34600000003@s.whatsapp.net", "senderId": "34600000003@s.whatsapp.net",
                                 "from": "Iván"})
    assert dr.channel_for(_one(ct, "Iván")) is None


def _his_message_leaves(event: dict) -> None:
    """The real path: the connector's echo of what he wrote, applied by the messaging card's owner."""
    import queue
    from widgets.mensajeria import owner
    o = owner._Owner()
    o._out_sub = type("S", (), {"queue": queue.Queue()})()
    o._out_sub.queue.put(event)
    o._apply_outbound()


def test_a_message_he_writes_from_his_phone_reaches_the_directory_through_the_card(ct, dr):
    """The wiring, not the function: an echo with no `contactId` (he wrote it in his own app) still counts."""
    ct.apply_action("add_contact", {"name": "Pablo Sabin", "phone": "+34 600 000 001"})
    dr.note_inbound("whatsapp", {"chatId": "34600000001@s.whatsapp.net", "senderId": "34600000001@s.whatsapp.net",
                                 "from": "Pablo"})
    _his_message_leaves({"platform": "whatsapp", "chatId": "34600000001@s.whatsapp.net", "messageId": "O1",
                         "body": "¿Has probado Zaelar?", "isGroup": False, "timestamp": 1793800000})
    assert _wa(_one(ct, "Pablo Sabin"))["volume"] == 2
    _his_message_leaves({"platform": "whatsapp", "chatId": "120363000000@g.us", "messageId": "O2",
                         "body": "hola a todos", "isGroup": True, "timestamp": 1793800001})
    assert _wa(_one(ct, "Pablo Sabin"))["volume"] == 2, "a group is nobody's traffic"
