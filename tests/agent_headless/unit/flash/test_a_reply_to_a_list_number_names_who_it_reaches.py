"""V2-847 step 2 · a reply to a list NUMBER names who it reaches, and his words must name that person.

Measured on a live phone session (2026-11-04): «send Raquel a message saying I'm on my way» became
`mensajeria:reply {n: 1, text}` — no name, a number nobody had on screen. The send rule asked «does every recipient
this call carries appear in his words?», the call carried NONE, and «none» read as «no doubt». Chat 1 was the
WhatsApp STATUS feed; the text went there, as a reply to somebody else's status.

The mechanism, each a door that already existed:
  · `on_his_behalf.who_of` asks the CARD who an act reaches when the call names nobody (`recipients_of`, beside
    `held_row`): `reply {n}` answers with that conversation's name — so the rule compares a person with his words;
  · the conversation OPEN on a visible card is the one exception («contéstale que sí» answers the person on screen);
  · ONE reading of «he named this recipient» (`acts.message.is_his`): the whole name in his words, or a word of his
    that the directory gives to this person and nobody else — «mamá» does not name «Francisco Vecino Mama»;
  · a FEED (status, broadcast list, channel) is never a conversation: refused at the ingest door, dropped from a
    store written before it.
"""
from __future__ import annotations

import time

import pytest

from nucleo.acts import message as gate

RAQUEL = "Mándale un mensaje a Raquel y dile que estoy de camino."
CLAUDIA = "34611000111@s.whatsapp.net"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """ISOLATED stores — never the operator's real ones."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from nucleo import truth
    monkeypatch.setattr(truth, "canvas_state", lambda wid: "closed")
    from widgets.mensajeria import data as m
    from widgets.contactos import data as c
    db = m.load_db()
    now = time.time()
    db["items"] = [{"platform": "whatsapp", "chatId": CLAUDIA, "messageId": "m1", "from": "CLAUDIA RIVERO",
                    "senderId": CLAUDIA, "body": "Lugar disponible mañana", "ts": now - 60}]
    db["threads"] = {f"whatsapp|{CLAUDIA}": {"name": "CLAUDIA RIVERO", "msgs": []}}
    m.store.save(m.WIDGET_ID, db)
    return m, c


def _contacts(c, *names):
    for n in names:
        c.apply_action("add_contact", {"name": n})


# ── who a list number reaches ─────────────────────────────────────────────────────────────────────────────────

def test_a_reply_to_a_number_names_the_conversation_it_reaches(world):
    m, _c = world
    assert m.recipients_of("reply", {"n": 1, "text": "Hola Raquel, estoy de camino."}) == ["CLAUDIA RIVERO"]


def test_his_words_naming_somebody_else_make_it_a_doubt(world):
    assert gate.unnamed_recipients("mensajeria", "reply", {"n": 1, "text": "ok"}, RAQUEL) == ["CLAUDIA RIVERO"]
    assert gate.needs_asking(None, "mensajeria", "reply", payload={"n": 1, "text": "ok"}, said=RAQUEL) is True


def test_his_words_naming_that_person_send_it(world):
    assert gate.unnamed_recipients("mensajeria", "reply", {"n": 1, "text": "ok"},
                                   "Contesta a Claudia Rivero que sí") == []
    assert gate.unnamed_recipients("mensajeria", "reply", {"n": 1, "text": "ok"},
                                   "reply to claudia rivero saying yes") == [], "the same in English"


def test_the_conversation_open_on_screen_needs_no_name(world, monkeypatch):
    m, _c = world
    db = m.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": CLAUDIA}
    m.store.save(m.WIDGET_ID, db)
    from nucleo import truth
    monkeypatch.setattr(truth, "canvas_state", lambda wid: "visible")
    assert m.recipients_of("reply", {"text": "sí"}) == [], "«contéstale que sí» answers the person on screen"
    monkeypatch.setattr(truth, "canvas_state", lambda wid: "closed")
    assert m.recipients_of("reply", {"text": "sí"}) == ["CLAUDIA RIVERO"], "open in the store but not on screen"


def test_the_gate_turns_the_unnamed_send_into_a_question(world):
    from widgets import actions as wa
    assert gate.asked_if_leaving(wa.FAST, None, "mensajeria", "reply", payload={"n": 1, "text": "ok"},
                                 said=RAQUEL) == wa.CONFIRM


# ── one reading of «he named this recipient» ─────────────────────────────────────────────────────────────────

def test_a_word_the_directory_gives_to_many_names_nobody(world):
    _m, c = world
    _contacts(c, "Francisco Vecino Mama", "Amiga Mama", "Roser Amiga Mama Botiga")
    assert gate.is_his("Francisco Vecino Mama", ["manda un mensaje a mamá de que ya he hecho el bizum"]) is False


def test_a_first_name_names_a_person_only_when_the_directory_gives_it_to_one(world):
    _m, c = world
    _contacts(c, "Raquel Jofre", "Raquel Ares")
    assert gate.is_his("Raquel Jofre", [RAQUEL]) is False, "two Raquels: a doubt"
    _contacts(c, "Rowan Ferrer")
    assert gate.is_his("Rowan Ferrer", ["text Rowan that I'm on my way"]) is True, "one Rowan: named"


def test_somebody_the_directory_does_not_hold_is_named_by_a_shared_word(world):
    assert gate.is_his("Paco Pérez", ["invite paco to the meeting"]) is True


# ── a feed is not a conversation ─────────────────────────────────────────────────────────────────────────────

def test_the_ingest_door_refuses_a_feed(monkeypatch):
    from connectors.messaging import ingest
    sent = []
    monkeypatch.setattr(ingest.bus, "emit_sync", lambda topic, ev: sent.append(ev))
    ingest.publish_msg("whatsapp", {"chatId": "status@broadcast", "body": "my status"})
    ingest.publish_msg_out("whatsapp", {"chatId": "status@broadcast", "body": "Hola Raquel"})
    ingest.publish_msg("whatsapp", {"chatId": "120363000@newsletter", "body": "news"})
    assert sent == []
    ingest.publish_msg("whatsapp", {"chatId": CLAUDIA, "body": "hola"})
    assert len(sent) == 1


def test_a_store_written_before_the_door_loses_its_feeds(world):
    m, _c = world
    db = m.load_db()
    db["threads"]["whatsapp|status@broadcast"] = {"name": "Nieves de Cámara", "msgs": [{"dir": "out", "body": "x"}]}
    db["items"].insert(0, {"platform": "whatsapp", "chatId": "status@broadcast", "messageId": "s1", "from": "Nieves",
                           "body": "[video]", "ts": time.time()})
    m.store.save(m.WIDGET_ID, db)
    db = m.load_db()
    assert "whatsapp|status@broadcast" not in db["threads"]
    assert all(it["chatId"] != "status@broadcast" for it in db["items"])
    assert m.recipients_of("reply", {"n": 1, "text": "x"}) == ["CLAUDIA RIVERO"], "chat 1 is a person again"
