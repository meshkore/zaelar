"""V2-683 row 1 — a contact carries HOW to reach him, and the directory learns it on its own.

The operator's errand («contacta con Iván Musikin… deberíamos tener el contacto con el número de WhatsApp,
el contacto de Telegram y el mail vinculados, y uno de esos canales como favorito») needs an answer to two
questions the directory could not answer before: WHO is this name, and by WHICH channel is he written to.

The weight of this file is on the REFUSALS, because those are the ones that cost something real: an
ambiguous name resolved to the first row, a preference stored that no send can honour, or a channel learned
onto the wrong contact all end the same way — a private message delivered to somebody who was never meant
to read it. Choosing right when there is nothing to choose is the easy half.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


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


# ── what counts as a channel ─────────────────────────────────────────────────────────────────────────────

def test_a_stored_ADDRESS_is_an_email_channel(ct, dr):
    """The address IS the whole capability: nothing else is needed to write, so it is derived."""
    ct.apply_action("add_contact", {"name": "Iván Musikin", "email": "ivan@example.com"})
    ch = dr.channel_for(_one(ct, "Iván Musikin"))
    assert ch and ch["platform"] == "email" and ch["handle"] == "ivan@example.com"


def test_a_stored_PHONE_is_not_a_whatsapp_channel_on_its_own(ct, dr):
    """Having somebody's number is not proof they use WhatsApp. Deriving one would let «mándale un
    WhatsApp» reach a number that never agreed to be reachable there."""
    ct.apply_action("add_contact", {"name": "Ana Ruiz", "phone": "+34600111222"})
    ana = _one(ct, "Ana Ruiz")
    assert [c["platform"] for c in dr.channels(ana)] == []
    assert dr.channel_for(ana) is None


def test_a_phone_IS_offered_when_whatsapp_is_the_channel_he_NAMED(ct, dr):
    """The asymmetry, on purpose: he asked for that app, and a number with no WhatsApp fails loudly at the
    bridge — which is an honest answer. It is never the automatic choice (the test above)."""
    ct.apply_action("add_contact", {"name": "Ana Ruiz", "phone": "+34600111222"})
    ch = dr.channel_for(_one(ct, "Ana Ruiz"), "whatsapp")
    assert ch and ch["platform"] == "whatsapp" and ch["handle"] == "+34600111222"


def test_a_channel_with_no_way_to_reach_anybody_is_not_stored(ct, dr):
    """A row with a platform and nothing else would make the directory answer «sí, por Telegram» over
    nothing at all."""
    ct.apply_action("add_contact", {"name": "Ana Ruiz", "channels": [{"platform": "telegram"}]})
    assert _one(ct, "Ana Ruiz")["channels"] == []


# ── the operator fixing it by hand ───────────────────────────────────────────────────────────────────────

def test_set_channel_stores_the_handle_AND_makes_it_preferred(ct, dr):
    ct.apply_action("add_contact", {"name": "Iván Musikin", "email": "ivan@example.com"})
    cid = _one(ct, "Iván Musikin")["id"]
    r = ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ivanm"})
    assert r["ok"]
    ivan = _one(ct, "Iván Musikin")
    assert ivan["preferred"] == "telegram"
    assert dr.channel_for(ivan)["handle"] == "@ivanm"


def test_a_preference_nothing_can_HONOUR_is_refused(ct):
    """«Escríbele por Telegram» with no Telegram anywhere: storing the preference would read as done to him
    and every later send would have to refuse it. The refusal names what is missing instead."""
    ct.apply_action("add_contact", {"name": "Ana Ruiz", "email": "ana@example.com"})
    cid = _one(ct, "Ana Ruiz")["id"]
    r = ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram"})
    assert r["ok"] is False and "handle" in r["error"]
    assert not _one(ct, "Ana Ruiz").get("preferred")


def test_the_PREFERRED_channel_wins_over_the_most_used_one(ct, dr):
    """He fixed it once; traffic does not overrule him (V2-052's sticky decision)."""
    ct.apply_action("add_contact", {"name": "Iván Musikin", "email": "ivan@example.com"})
    cid = _one(ct, "Iván Musikin")["id"]
    ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ivanm"})
    for _ in range(20):
        dr.note_inbound("email", {"chatId": "ivan@example.com", "senderId": "ivan@example.com",
                                  "from": "Iván Musikin"})
    assert dr.channel_for(_one(ct, "Iván Musikin"))["platform"] == "telegram"


def test_two_channels_used_EQUALLY_and_no_preference_is_an_ambiguity(ct, dr):
    """A coin toss here puts a private message in the wrong app. None means ASK."""
    ct.apply_action("add_contact", {"name": "Iván Musikin", "channels": [
        {"platform": "telegram", "handle": "@ivanm", "volume": 5},
        {"platform": "whatsapp", "handle": "+34600111222", "volume": 5}]})
    assert dr.channel_for(_one(ct, "Iván Musikin")) is None


def test_the_one_he_actually_USES_wins_when_nothing_was_fixed(ct, dr):
    ct.apply_action("add_contact", {"name": "Iván Musikin", "channels": [
        {"platform": "telegram", "handle": "@ivanm", "volume": 9},
        {"platform": "whatsapp", "handle": "+34600111222", "volume": 2}]})
    assert dr.channel_for(_one(ct, "Iván Musikin"))["platform"] == "telegram"


# ── WHO he meant ─────────────────────────────────────────────────────────────────────────────────────────

def test_a_name_said_in_part_finds_the_contact(ct, dr):
    ct.apply_action("add_contact", {"name": "Iván Musikin"})
    assert [c["name"] for c in dr.resolve("musikin")] == ["Iván Musikin"]
    assert [c["name"] for c in dr.resolve("ivan")] == ["Iván Musikin"]


def test_two_people_of_the_same_name_come_back_as_TWO(ct, dr):
    """The ambiguity IS the answer — the caller asks which one, it never picks the first row."""
    ct.apply_action("add_contact", {"name": "Javi", "city": "Soria"})
    ct.apply_action("add_contact", {"name": "Javi", "city": "Madrid"})
    assert len(dr.resolve("javi")) == 2


def test_an_empty_name_resolves_to_NOBODY(ct, dr):
    """«Mándale un mensaje» with no name must ask; returning the directory would let a caller take row one."""
    ct.apply_action("add_contact", {"name": "Iván Musikin"})
    assert dr.resolve("") == []
    assert dr.resolve("   ") == []


# ── what the traffic teaches ─────────────────────────────────────────────────────────────────────────────

def test_a_message_from_a_number_we_hold_teaches_that_channel(ct, dr):
    ct.apply_action("add_contact", {"name": "Iván Musikin", "phone": "+34 600 111 222"})
    assert dr.note_inbound("telegram", {"chatId": "987", "senderId": "34600111222", "from": "Iván"}) is True
    ch = dr.channel_for(_one(ct, "Iván Musikin"))
    assert ch["platform"] == "telegram" and ch["chatId"] == "987" and ch["volume"] == 1


def test_a_GROUP_teaches_nothing(ct, dr):
    """The sender of a group message is not that conversation's identity."""
    ct.apply_action("add_contact", {"name": "Iván Musikin", "phone": "+34600111222"})
    assert dr.note_inbound("whatsapp", {"chatId": "g1", "senderId": "34600111222",
                                        "from": "Iván", "isGroup": True}) is False
    assert _one(ct, "Iván Musikin").get("channels") in (None, [])


def test_an_unknown_sender_CREATES_nobody(ct, dr):
    """His directory is his, not a log of everyone who ever wrote to him."""
    ct.apply_action("add_contact", {"name": "Iván Musikin"})
    assert dr.note_inbound("telegram", {"chatId": "555", "senderId": "@stranger", "from": "Nadie"}) is False
    assert len(ct.load_db()["contacts"]) == 1


def test_an_AMBIGUOUS_sender_writes_nothing_at_all(ct, dr):
    """Two «Javi»s: writing the handle onto either one would make the next «escríbele a Javi» send to a
    person who was never in that conversation — silently, and with a stored handle backing it up."""
    ct.apply_action("add_contact", {"name": "Javi", "city": "Soria"})
    ct.apply_action("add_contact", {"name": "Javi", "city": "Madrid"})
    assert dr.note_inbound("telegram", {"chatId": "42", "senderId": "@javi", "from": "Javi"}) is False
    assert all(not c.get("channels") for c in ct.load_db()["contacts"])


def test_a_handle_the_OPERATOR_fixed_survives_the_traffic(ct, dr):
    """He typed «@ivanm»; a message whose sender id renders differently must not overwrite it."""
    ct.apply_action("add_contact", {"name": "Iván Musikin"})
    cid = _one(ct, "Iván Musikin")["id"]
    ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ivanm"})
    dr.note_inbound("telegram", {"chatId": "987", "senderId": "77777", "from": "Iván Musikin"})
    ch = dr.channel_for(_one(ct, "Iván Musikin"))
    assert ch["handle"] == "@ivanm"
    assert ch["chatId"] == "987"      # the id it resolves to is still worth keeping


def test_a_conversation_can_be_traced_back_to_its_contact(ct, dr):
    ct.apply_action("add_contact", {"name": "Iván Musikin"})
    cid = _one(ct, "Iván Musikin")["id"]
    ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram",
                                    "handle": "@ivanm", "chatId": "987"})
    assert dr.find_by_channel("telegram", "987")["name"] == "Iván Musikin"
    assert dr.find_by_channel("telegram", "000") is None


# ── what the brain gets to read ──────────────────────────────────────────────────────────────────────────

def test_the_digest_says_by_which_channel_and_which_is_his(ct):
    ct.apply_action("add_contact", {"name": "Iván Musikin", "email": "ivan@example.com"})
    cid = _one(ct, "Iván Musikin")["id"]
    ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ivanm"})
    d = ct.prompt_digest()
    assert "canales:" in d and "telegram (preferido)" in d and "email" in d


def test_a_prompt_row_never_carries_the_HANDLE(ct):
    """The row is read inside a turn prompt; a phone number or a username in there is personal data
    travelling for no reason — the door that sends reads the handle from the store itself."""
    ct.apply_action("add_contact", {"name": "Iván Musikin", "email": "ivan@example.com"})
    cid = _one(ct, "Iván Musikin")["id"]
    r = ct.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ivanm"})
    row = json.dumps(r["result"]["contact"], ensure_ascii=False)
    assert "@ivanm" not in row and "ivan@example.com" not in row
    assert r["result"]["contact"]["channels"] == ["telegram", "email"]


def test_the_manifest_declares_the_new_capability(ct):
    m = json.loads((ENGINE / "widgets" / "contactos" / "manifest.json").read_text(encoding="utf-8"))
    assert "set_channel" in m["actions"]
    assert "platform" in m["actions"]["set_channel"]["payload"]
